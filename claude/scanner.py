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

# 汉明距离说明（基于8x8 pHash的64位哈希）：
#   距离=0     完全相同（像素级重复）
#   距离=1-3   高度相似（<5%像素变化，视觉上几乎相同）→ 直接复用
#   距离=4-5   中度相似（5-8%像素变化，轮廓/颜色接近）→ 调用IMS复核
#   距离6+     不相似（>8%像素变化）→ 新增扫描
#
# 性能考量：
#   缓存只包含最近10000条（LRU），覆盖率仅1%，大部分查询仍需查数据库。
#   若只查缓存可能遗漏最相似的记录（距离4 vs 距离1），故必须双层查询。
#   双层查询成本：缓存O(n) + 数据库O(m)，但可避免不必要的IMS API调用。
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
            'scanned': 0,      # 实际调用了 IMS API 的数量
            'violations': 0,   # 检测出违规的总数（不管来源）
            'skipped': 0,      # 路径/内容去重命中、未调用 API
            'api_saved': 0,    # 通过特征相似复用结果，省去 IMS API 调用
            'reused': 0,       # 通过路径/内容/特征复用的总数
            'errors': 0,
        }

        # 特征缓存：key -> list of record dicts，用于快速查找相似图片
        self.feature_cache = {}
        cache_config = config.get('cache', {})
        self.cache_enabled = cache_config.get('enabled', True)
        self.cache_max_size = cache_config.get('max_size', 10000)
        self.cache_strategy = cache_config.get('strategy', 'lru')

        logger.info("扫描器初始化完成")

        # 初始化时从数据库加载已有的扫描记录到缓存
        if self.cache_enabled and self.cache_strategy != 'none':
            self._load_scanned_to_cache()
        else:
            logger.info("特征缓存已禁用")

    # ------------------------------------------------------------------ 缓存管理

    def _is_complete_record(self, record: Dict) -> bool:
        """检查记录是否包含必需的字段（用于缓存完整性验证）。"""
        required = ['key', 'bucket_name', 'object_key', 'feature_hash',
                    'is_violation', 'violation_type', 'violation_label']
        return all(k in record for k in required)

    def _load_scanned_to_cache(self):
        """从数据库加载已扫描图片到特征缓存。"""
        try:
            logger.info("加载已扫描图片到特征缓存...")
            scanned_images = self.db.get_all_scanned_images(
                limit=self.cache_max_size * 10 if self.cache_strategy == 'lru' else None
            )
            if not scanned_images:
                logger.info("没有历史扫描记录")
                return

            loaded_count = 0
            for record in scanned_images:
                feature_hash = record.get('feature_hash')
                # 只加载包含必需字段的完整记录
                if feature_hash and self._is_complete_record(record):
                    if feature_hash not in self.feature_cache:
                        if self.cache_strategy == 'lru' and len(self.feature_cache) >= self.cache_max_size:
                            break
                        self.feature_cache[feature_hash] = []
                    self.feature_cache[feature_hash].append(record)
                    loaded_count += 1

            logger.info(f"特征缓存加载完成: {loaded_count}条记录, {len(self.feature_cache)}个特征")
        except Exception as e:
            logger.warning(f"加载特征缓存失败: {e}")

    def _add_to_feature_cache(self, record: Dict):
        """将新记录添加到特征缓存。使用 LRU 防止内存溢出。"""
        feature_hash = record.get('feature_hash')
        if not feature_hash:
            return
        if feature_hash not in self.feature_cache:
            # LRU 淘汰：缓存满时删除最早的特征
            if self.cache_strategy == 'lru' and len(self.feature_cache) >= self.cache_max_size:
                oldest_key = next(iter(self.feature_cache))
                del self.feature_cache[oldest_key]
            self.feature_cache[feature_hash] = []
        self.feature_cache[feature_hash].append(record)

    def _find_similar_in_cache(self, feature_hash: str, max_distance: int = 5) -> list:
        """在缓存中查找相似的特征。"""
        if not self.cache_enabled:
            return []
        similar = []
        for cached_hash, records in self.feature_cache.items():
            distance = self.features.calculate_hash_distance(feature_hash, cached_hash)
            if 0 <= distance <= max_distance:
                for record in records:
                    record_copy = record.copy()
                    record_copy['hash_distance'] = distance
                    similar.append(record_copy)
        similar.sort(key=lambda x: x['hash_distance'])
        return similar[:10]

    def _merge_similar_results(self, cache_results: list, db_results: list) -> list:
        """合并缓存和数据库的相似结果，去重后按距离排序。

        由于缓存只包含部分记录，必须查数据库以保证找到最相似的图片。
        本方法按key去重，保留距离最小的版本，最后返回top10。
        """
        # 用dict按key去重，距离小的覆盖距离大的
        merged = {}
        for result in db_results + cache_results:
            key = result.get('key')
            if key:
                if key not in merged or result['hash_distance'] < merged[key]['hash_distance']:
                    merged[key] = result

        # 按距离排序，取top10
        similar_list = sorted(merged.values(), key=lambda x: x['hash_distance'])
        return similar_list[:10]

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
                self.stats['reused'] += 1
                if existing.get('is_violation'):
                    self.stats['violations'] += 1
                    logger.warning(f"复用(路径重复): {object_name} | "
                                   f"状态=违规 | 类型={existing.get('violation_type')}")
                else:
                    logger.debug(f"复用(路径重复): {object_name} | 状态=正规")
                return

        # 下载图片和元数据，准备做内容级和特征级判断。
        image_data, metadata = self.minio.get_object_data(bucket, object_name)
        key = self.features.calculate_key(image_data)
        feats = self.features.extract_features(image_data)
        content_type = metadata.get('content_type')

        # 第2层：内容去重——相同内容不同路径，复用扫描结果但插一条新路径记录。
        if not force_rescan:
            same_content = self.db.find_by_key(key)
            if same_content:
                self._write_reused(bucket, object_name, image_data, key, feats,
                                   source=same_content, match='content',
                                   content_type=content_type)
                self.stats['skipped'] += 1
                self.stats['reused'] += 1
                if same_content.get('is_violation'):
                    self.stats['violations'] += 1
                    logger.warning(f"复用(内容重复): {object_name} | "
                                   f"状态=违规 | 类型={same_content.get('violation_type')}")
                else:
                    logger.debug(f"复用(内容重复): {object_name} | 状态=正规")
                return

        # 第3层：特征相似——若有高度相似的已扫描图片，复用其结果。
        # 策略：缓存优先（快速），但一定查数据库以确保找到最相似的。
        # 取缓存和数据库结果中距离最小的。
        cache_similar = self._find_similar_in_cache(feats['phash'], max_distance=SIMILAR_DISTANCE_MAX)
        db_similar = self.db.find_similar_scanned(feats['phash'],
                                                  max_distance=SIMILAR_DISTANCE_MAX)
        # 合并并去重：优先使用距离最小的
        all_similar = self._merge_similar_results(cache_similar, db_similar)

        if all_similar and all_similar[0]['hash_distance'] <= SIMILAR_DISTANCE_REUSE:
            most = all_similar[0]
            self._write_reused(bucket, object_name, image_data, key, feats,
                               source=most, match='similar',
                               distance=most['hash_distance'], content_type=content_type)
            self.stats['skipped'] += 1
            self.stats['api_saved'] += 1
            self.stats['reused'] += 1
            if most.get('is_violation'):
                self.stats['violations'] += 1
                logger.warning(f"复用(特征相似): {object_name} | "
                               f"状态=违规 | 距离={most['hash_distance']} | "
                               f"类型={most.get('violation_type')}")
            else:
                logger.debug(f"复用(特征相似): {object_name} | 状态=正规 | 距离={most['hash_distance']}")
            return

        # 走到这里：必须调用 IMS API。
        ims_result = self.ims.scan_image(image_data)
        self._write_ims(bucket, object_name, image_data, key, feats, ims_result,
                       content_type=content_type)

        self.stats['scanned'] += 1
        if ims_result['is_violation']:
            self.stats['violations'] += 1
            logger.warning(f"违规(IMS): {object_name} | "
                           f"类型={ims_result.get('violation_type')} | "
                           f"置信度={ims_result.get('confidence')}")

    # ------------------------------------------------------------------ 写库辅助

    def _build_record_base(self, bucket: str, object_name: str,
                           image_data: bytes, key: str, feats: Dict,
                           content_type: str = None) -> Dict:
        return {
            'key': key,
            'feature_hash': feats['phash'],
            'feature_hash_dhash': feats['dhash'],
            'feature_hash_ahash': feats['ahash'],
            'feature_hash_phash': feats['phash'],
            'bucket_name': bucket,
            'object_key': object_name,
            'file_size': len(image_data),
            'content_type': content_type,
            'blocked': 0,
            'scan_status': 'completed',
            'last_scanned_at': datetime.now(),
        }

    def _write_reused(self, bucket: str, object_name: str, image_data: bytes,
                      key: str, feats: Dict, source: Dict, match: str,
                      distance: int = 0, content_type: str = None):
        """根据已有的扫描记录写入新路径，不调用 IMS。"""
        record = self._build_record_base(bucket, object_name, image_data, key, feats,
                                         content_type=content_type)
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
        self._add_to_feature_cache(record)

    def _write_ims(self, bucket: str, object_name: str, image_data: bytes,
                   key: str, feats: Dict, ims_result: Dict, content_type: str = None):
        """根据 IMS 返回结果写入新记录。"""
        record = self._build_record_base(bucket, object_name, image_data, key, feats,
                                         content_type=content_type)
        record.update({
            'is_violation': 1 if ims_result['is_violation'] else 0,
            'violation_type': ims_result.get('violation_type'),
            'violation_label': ims_result.get('violation_label'),
            'violation_description': ims_result.get('violation_description'),
            'confidence': ims_result.get('confidence'),
            'suggestion': ims_result.get('suggestion'),
            'ims_result': {
                'matched_by': 'ims_api',
                'raw_result': ims_result.get('raw_result'),
                'request_id': ims_result.get('request_id'),
            },
            'ims_request_id': ims_result.get('request_id'),
        })
        self.db.upsert_record(record)
        self._add_to_feature_cache(record)

    def _record_error(self, bucket: str, object_name: str, err: Exception):
        # key 字段长 VARCHAR(128)，object_name 可能很长，用 md5 保证长度有界。
        path_hash = hashlib.md5(f"{bucket}/{object_name}".encode()).hexdigest()
        error_msg = str(err)[:60000]  # error_message 是 TEXT (64KB)，做个上限保险
        try:
            self.db.upsert_record({
                'key': f"error-{path_hash}",
                'feature_hash': '',
                'feature_hash_dhash': '',
                'feature_hash_ahash': '',
                'feature_hash_phash': '',
                'bucket_name': bucket,
                'object_key': object_name,
                'file_size': 0,
                'content_type': None,
                'is_violation': 0,
                'blocked': 0,
                'scan_status': 'failed',
                'error_message': error_msg,
                'last_scanned_at': datetime.now(),
            })
        except Exception as write_err:
            logger.error(f"无法写入错误记录 [{object_name}]: {write_err}")

    # ------------------------------------------------------------------ 统计

    def _log_stats(self):
        logger.info(
            f"统计 - 总:{self.stats['total']} | "
            f"IMS扫描:{self.stats['scanned']} | "
            f"复用:{self.stats['reused']} | "
            f"违规:{self.stats['violations']} | "
            f"节约API:{self.stats['api_saved']} | "
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
        'cache': {
            'enabled': os.getenv('CACHE_ENABLED', 'true').lower() == 'true',
            'strategy': os.getenv('CACHE_STRATEGY', 'lru'),
            'max_size': int(os.getenv('CACHE_MAX_SIZE', '10000')),
        },
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
