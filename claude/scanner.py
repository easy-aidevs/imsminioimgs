"""图片内容安全扫描器：遍历 MinIO 桶，调用腾讯云 IMS 检测，结果写入 MySQL。

入口：直接运行本文件。配置通过 .env 读取。
"""

import hashlib
import os
import sys
from datetime import datetime
from typing import Dict, Optional

from dotenv import load_dotenv
from tqdm import tqdm

from logger_config import setup_logger
from minio_client import MinIOClient
from image_feature import ImageFeatureExtractor
from tencent_ims import TencentIMSScanner
from database import ImageDatabase

logger = setup_logger(log_dir="logs")

# 汉明距离 <= 此阈值视为"高度相似"，直接复用扫描结果，跳过 IMS。
# 4-5 之间属于"中度相似"，仍调用 IMS 复核。
SIMILAR_DISTANCE_REUSE = 3
SIMILAR_DISTANCE_MAX = 5


class ImageSecurityScanner:
    """扫描器主体。三层去重：路径 -> 内容 Key -> 特征相似度。"""

    def __init__(self, config: Dict):
        self.config = config

        self.minio = MinIOClient(
            endpoint=config['minio']['endpoint'],
            access_key=config['minio']['access_key'],
            secret_key=config['minio']['secret_key'],
            secure=config['minio'].get('secure', False),
            bucket_name=config['minio'].get('bucket_name'),
        )
        self.features = ImageFeatureExtractor(hash_size=config.get('hash_size', 8))
        self.ims = TencentIMSScanner(
            secret_id=config['tencent']['secret_id'],
            secret_key=config['tencent']['secret_key'],
            region=config['tencent'].get('region', 'ap-guangzhou'),
        )
        self.db = ImageDatabase(
            host=config['mysql']['host'],
            port=config['mysql'].get('port', 3306),
            user=config['mysql']['user'],
            password=config['mysql']['password'],
            database=config['mysql']['database'],
        )

        self.stats = {
            'total': 0,
            'scanned': 0,      # 调用了 IMS API 的数量
            'violations': 0,
            'skipped': 0,      # 路径/内容去重命中、未调用 API
            'api_saved': 0,    # 通过相似匹配复用结果，少调一次 API
            'errors': 0,
        }

        logger.info("扫描器初始化完成")

    # ------------------------------------------------------------------ 主循环

    def scan_all(self, bucket_name: str = None, prefix: str = "",
                 force_rescan: bool = False, limit: Optional[int] = None):
        bucket = bucket_name or self.config['minio'].get('bucket_name')
        if not bucket:
            raise ValueError("必须指定 bucket_name")

        logger.info(f"开始扫描 bucket={bucket} prefix={prefix or '(无)'} "
                    f"force={force_rescan} limit={limit or '(无)'}")

        objects = list(self.minio.list_objects(bucket, prefix=prefix, recursive=True))
        if limit:
            objects = objects[:limit]
        logger.info(f"待处理 {len(objects)} 个图片")

        start = datetime.now()
        total_objects = len(objects)
        for object_name, _ in tqdm(objects, desc="扫描", unit="img"):
            self.stats['total'] += 1
            try:
                self._process_one(bucket, object_name, force_rescan)
            except Exception as e:
                self.stats['errors'] += 1
                logger.error(f"处理失败 [{object_name}]: {e}")
                self._record_error(bucket, object_name, e)

            # 每 100 张打一次进度统计；最后一张留给循环外的最终统计打印。
            if self.stats['total'] % 100 == 0 and self.stats['total'] != total_objects:
                self._log_stats()

        duration = (datetime.now() - start).total_seconds()
        logger.info(f"扫描完成，耗时 {duration:.1f}s，平均 "
                    f"{self.stats['total'] / max(duration, 1):.2f} img/s")
        self._log_stats()

    # ------------------------------------------------------------------ 单张处理

    def _process_one(self, bucket: str, object_name: str, force_rescan: bool):
        """单张图片处理流程：三层去重 -> IMS 检测 -> 写库。"""

        # 第1层：路径去重——同一 MinIO 路径已扫描过，直接跳过。
        if not force_rescan:
            existing = self.db.find_by_bucket_object(bucket, object_name)
            if existing:
                self.stats['skipped'] += 1
                if existing.get('is_violation'):
                    self.stats['violations'] += 1
                    logger.warning(f"违规(路径重复): {object_name} | "
                                   f"类型={existing.get('violation_type')}")
                return

        # 下载图片，准备做内容级和特征级判断。
        image_data = self.minio.get_object_data(bucket, object_name)
        key = self.features.calculate_key(image_data)
        feats = self.features.extract_features(image_data)

        # 第2层：内容去重——相同内容不同路径，复用扫描结果但插一条新路径记录。
        if not force_rescan:
            same_content = self.db.find_by_key(key)
            if same_content:
                self._write_reused(bucket, object_name, image_data, key, feats,
                                   source=same_content, match='content')
                self.stats['skipped'] += 1
                if same_content.get('is_violation'):
                    self.stats['violations'] += 1
                    logger.warning(f"违规(内容重复): {object_name} | "
                                   f"类型={same_content.get('violation_type')}")
                return

        # 第3层：特征相似——若有高度相似的已扫描图片，复用其结果。
        similar = self.db.find_similar_scanned(feats['phash'],
                                               max_distance=SIMILAR_DISTANCE_MAX)
        if similar and similar[0]['hash_distance'] <= SIMILAR_DISTANCE_REUSE:
            most = similar[0]
            self._write_reused(bucket, object_name, image_data, key, feats,
                               source=most, match='similar',
                               distance=most['hash_distance'])
            self.stats['scanned'] += 1
            self.stats['api_saved'] += 1
            if most.get('is_violation'):
                self.stats['violations'] += 1
                logger.warning(f"违规(相似匹配): {object_name} | "
                               f"距离={most['hash_distance']} | "
                               f"类型={most.get('violation_type')}")
            return

        # 走到这里：必须调用 IMS API。
        ims_result = self.ims.scan_image(image_data)
        self._write_ims(bucket, object_name, image_data, key, feats, ims_result)

        self.stats['scanned'] += 1
        if ims_result['is_violation']:
            self.stats['violations'] += 1
            logger.warning(f"违规(IMS): {object_name} | "
                           f"类型={ims_result.get('violation_type')} | "
                           f"置信度={ims_result.get('confidence')}")

    # ------------------------------------------------------------------ 写库辅助

    def _build_record_base(self, bucket: str, object_name: str,
                           image_data: bytes, key: str, feats: Dict) -> Dict:
        return {
            'key': key,
            'feature_hash': feats['phash'],
            'feature_hash_dhash': feats['dhash'],
            'feature_hash_ahash': feats['ahash'],
            'feature_hash_phash': feats['phash'],
            'bucket_name': bucket,
            'object_key': object_name,
            'file_size': len(image_data),
            'blocked': 0,
            'scan_status': 'completed',
            'last_scanned_at': datetime.now(),
        }

    def _write_reused(self, bucket: str, object_name: str, image_data: bytes,
                      key: str, feats: Dict, source: Dict, match: str,
                      distance: int = 0):
        """根据已有的扫描记录写入新路径，不调用 IMS。"""
        record = self._build_record_base(bucket, object_name, image_data, key, feats)
        record.update({
            'is_violation': 1 if source.get('is_violation') else 0,
            'violation_type': source.get('violation_type'),
            'violation_label': source.get('violation_label'),
            'violation_description': source.get('violation_description'),
            'confidence': source.get('confidence'),
            'suggestion': source.get('suggestion'),
            'ims_result': {
                'matched_by': match,
                'source_bucket': source.get('bucket_name'),
                'source_object_key': source.get('object_key'),
                'hash_distance': distance,
            },
        })
        self.db.upsert_record(record)

    def _write_ims(self, bucket: str, object_name: str, image_data: bytes,
                   key: str, feats: Dict, ims_result: Dict):
        """根据 IMS 返回结果写入新记录。"""
        record = self._build_record_base(bucket, object_name, image_data, key, feats)
        record.update({
            'is_violation': 1 if ims_result['is_violation'] else 0,
            'violation_type': ims_result.get('violation_type'),
            'violation_label': ims_result.get('violation_label'),
            'violation_description': ims_result.get('violation_description'),
            'confidence': ims_result.get('confidence'),
            'suggestion': ims_result.get('suggestion'),
            'ims_result': ims_result.get('raw_result'),
            'ims_request_id': ims_result.get('request_id'),
        })
        self.db.upsert_record(record)

    def _record_error(self, bucket: str, object_name: str, err: Exception):
        # key 字段长 VARCHAR(128)，object_name 可能很长，用 md5 保证长度有界。
        path_hash = hashlib.md5(f"{bucket}/{object_name}".encode()).hexdigest()
        error_msg = str(err)[:60000]  # error_message 是 TEXT (64KB)，做个上限保险
        try:
            self.db.upsert_record({
                'key': f"error-{path_hash}",
                'feature_hash': '',
                'bucket_name': bucket,
                'object_key': object_name,
                'file_size': 0,
                'scan_status': 'failed',
                'error_message': error_msg,
                'last_scanned_at': datetime.now(),
            })
        except Exception as write_err:
            logger.error(f"无法写入错误记录 [{object_name}]: {write_err}")

    # ------------------------------------------------------------------ 统计

    def _log_stats(self):
        logger.info(
            f"统计 - 总:{self.stats['total']} "
            f"已扫描:{self.stats['scanned']} "
            f"违规:{self.stats['violations']} "
            f"跳过:{self.stats['skipped']} "
            f"节约API:{self.stats['api_saved']} "
            f"错误:{self.stats['errors']}"
        )

    # ------------------------------------------------------------------ 生命周期

    def close(self):
        self.db.close()
        logger.info("扫描器已关闭")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def load_config() -> Dict:
    load_dotenv()
    config = {
        'minio': {
            'endpoint': os.getenv('MINIO_ENDPOINT', 'localhost:9000'),
            'access_key': os.getenv('MINIO_ACCESS_KEY', ''),
            'secret_key': os.getenv('MINIO_SECRET_KEY', ''),
            'secure': os.getenv('MINIO_SECURE', 'false').lower() == 'true',
            'bucket_name': os.getenv('MINIO_BUCKET_NAME', ''),
        },
        'tencent': {
            'secret_id': os.getenv('TENCENT_SECRET_ID', ''),
            'secret_key': os.getenv('TENCENT_SECRET_KEY', ''),
            'region': os.getenv('TENCENT_REGION', 'ap-guangzhou'),
        },
        'mysql': {
            'host': os.getenv('MYSQL_HOST', 'localhost'),
            'port': int(os.getenv('MYSQL_PORT', '3306')),
            'user': os.getenv('MYSQL_USER', 'root'),
            'password': os.getenv('MYSQL_PASSWORD', ''),
            'database': os.getenv('MYSQL_DATABASE', 'image_security'),
        },
        'hash_size': int(os.getenv('HASH_SIZE', '8')),
    }

    required = [
        ('MINIO_ACCESS_KEY', config['minio']['access_key']),
        ('MINIO_SECRET_KEY', config['minio']['secret_key']),
        ('MINIO_BUCKET_NAME', config['minio']['bucket_name']),
        ('TENCENT_SECRET_ID', config['tencent']['secret_id']),
        ('TENCENT_SECRET_KEY', config['tencent']['secret_key']),
        ('MYSQL_PASSWORD', config['mysql']['password']),
    ]
    missing = [name for name, value in required if not value]
    if missing:
        raise ValueError(f"缺少必要配置: {', '.join(missing)}")
    return config


def main():
    try:
        config = load_config()
        with ImageSecurityScanner(config) as scanner:
            scanner.scan_all(
                bucket_name=os.getenv('SCAN_BUCKET_NAME') or config['minio']['bucket_name'],
                prefix=os.getenv('SCAN_PREFIX', ''),
                force_rescan=os.getenv('FORCE_RESCAN', 'false').lower() == 'true',
                limit=int(os.getenv('SCAN_LIMIT')) if os.getenv('SCAN_LIMIT') else None,
            )
    except Exception as e:
        logger.error(f"扫描器异常退出: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
