"""
图片内容安全扫描主程序
遍历MinIO中的图片，使用腾讯云IMS进行检测，结果存储到MySQL
"""

import os
import sys
from datetime import datetime
from typing import Dict, Optional
from loguru import logger
from tqdm import tqdm
from dotenv import load_dotenv

# 导入自定义模块
from minio_client import MinIOClient
from image_feature import ImageFeatureExtractor
from tencent_ims import TencentIMSScanner
from database import ImageDatabase


class ImageSecurityScanner:
    """图片内容安全扫描器"""
    
    def __init__(self, config: Dict):
        """
        初始化扫描器
        
        Args:
            config: 配置字典
        """
        self.config = config
        
        # 初始化MinIO客户端
        self.minio_client = MinIOClient(
            endpoint=config['minio']['endpoint'],
            access_key=config['minio']['access_key'],
            secret_key=config['minio']['secret_key'],
            secure=config['minio'].get('secure', False),
            bucket_name=config['minio'].get('bucket_name')
        )
        
        # 初始化特征提取器
        self.feature_extractor = ImageFeatureExtractor(
            hash_size=config.get('hash_size', 8)
        )
        
        # 初始化腾讯云IMS扫描器
        self.ims_scanner = TencentIMSScanner(
            secret_id=config['tencent']['secret_id'],
            secret_key=config['tencent']['secret_key'],
            region=config['tencent'].get('region', 'ap-guangzhou')
        )
        
        # 初始化数据库
        self.db = ImageDatabase(
            host=config['mysql']['host'],
            port=config['mysql'].get('port', 3306),
            user=config['mysql']['user'],
            password=config['mysql']['password'],
            database=config['mysql']['database']
        )
        
        # 统计信息
        self.stats = {
            'total': 0,
            'scanned': 0,
            'violations': 0,
            'skipped': 0,
            'errors': 0,
            'api_saved': 0  # 节约的API调用次数
        }
        
        logger.info("图片内容安全扫描器初始化完成")
    
    def scan_all(self, bucket_name: str = None, prefix: str = "", 
                 force_rescan: bool = False, limit: int = None):
        """
        扫描所有图片
        
        Args:
            bucket_name: 存储桶名称，None则使用默认
            prefix: 对象前缀过滤
            force_rescan: 是否强制重新扫描已存在的图片
            limit: 限制扫描数量，None表示不限制
        """
        bucket = bucket_name or self.config['minio'].get('bucket_name')
        if not bucket:
            raise ValueError("必须指定bucket_name")
        
        logger.info(f"开始扫描存储桶: {bucket}, 前缀: {prefix}")
        logger.info(f"强制重扫: {force_rescan}, 数量限制: {limit}")
        
        start_time = datetime.now()
        
        try:
            # 获取所有图片对象
            objects = list(self.minio_client.list_objects(
                bucket_name=bucket,
                prefix=prefix,
                recursive=True
            ))
            
            total_count = len(objects)
            logger.info(f"共找到 {total_count} 个图片文件")
            
            if limit:
                objects = objects[:limit]
                logger.info(f"限制扫描数量为: {limit}")
            
            # 使用进度条遍历
            for object_name, obj_info in tqdm(objects, desc="扫描进度", unit="图片"):
                try:
                    self.stats['total'] += 1
                    
                    # 处理单个图片
                    self._process_single_image(
                        bucket_name=bucket,
                        object_name=object_name,
                        force_rescan=force_rescan
                    )
                    
                    # 每处理100张图片输出一次统计
                    if self.stats['total'] % 100 == 0:
                        self._print_stats()
                        
                except Exception as e:
                    self.stats['errors'] += 1
                    logger.error(f"处理图片失败 [{object_name}]: {e}")
                    continue
            
            # 扫描完成
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            logger.info("=" * 60)
            logger.info("扫描完成！")
            self._print_stats()
            logger.info(f"总耗时: {duration:.2f} 秒")
            logger.info(f"平均速度: {self.stats['total'] / max(duration, 1):.2f} 图片/秒")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"扫描过程出错: {e}")
            raise
    
    def _process_single_image(self, bucket_name: str, object_name: str, 
                              force_rescan: bool = False):
        """
        处理单个图片
        
        Args:
            bucket_name: 存储桶名称
            object_name: 对象名称
            force_rescan: 是否强制重扫
        """
        try:
            # 1. 计算图片key
            image_data = self.minio_client.get_object_data(bucket_name, object_name)
            key = self.feature_extractor.calculate_key(image_data)
            
            # 2. 检查数据库中是否已存在（但还是要记录当前路径）
            existing_record = self.db.find_by_key(key)
            
            if existing_record and not force_rescan:
                # 已扫描过，但仍然需要记录当前路径到数据库
                logger.debug(f"图片已扫描过（Key: {key[:30]}...），但仍记录当前路径")
                
                # 提取当前图片的特征（即使跳过IMS，也要计算特征码）
                features = self.feature_extractor.extract_features(image_data)
                
                # 插入当前路径的记录（保留所有路径）
                record = {
                    'key': key,
                    'feature_hash': features['phash'],  # ⚠️ 重新计算特征码
                    'feature_hash_dhash': features['dhash'],
                    'feature_hash_ahash': features['ahash'],
                    'feature_hash_phash': features['phash'],
                    'bucket_name': bucket_name,
                    'object_key': object_name,  # ⚠️ 记录当前路径
                    'file_size': len(image_data),
                    'content_type': None,
                    'is_violation': existing_record.get('is_violation', 0),
                    'violation_type': existing_record.get('violation_type'),
                    'violation_label': existing_record.get('violation_label'),
                    'violation_description': existing_record.get('violation_description'),
                    'confidence': existing_record.get('confidence'),
                    'suggestion': existing_record.get('suggestion'),
                    # ⚠️ 关键：不复制ims_result，标记为通过特征匹配识别
                    'ims_result': {
                        'matched_by': 'key_duplicate',  # 通过Key去重识别
                        'original_key': key,
                        'note': 'Skipped IMS detection, copied from existing record'
                    },
                    'ims_request_id': None,  # ⚠️ 没有实际的IMS请求ID
                    'scan_status': 'completed',
                    'error_message': None,
                    'last_scanned_at': datetime.now()
                }
                
                # 保存到数据库（插入新记录，保留所有路径）
                self.db.insert_record(record)
                
                self.stats['skipped'] += 1
                
                # 如果已经是违规图片，记录日志
                if existing_record.get('is_violation'):
                    logger.warning(
                        f"发现违规图片（已扫描过）: {object_name} | "
                        f"类型: {existing_record.get('violation_type')} | "
                        f"置信度: {existing_record.get('confidence')}"
                    )
                
                return  # 跳过IMS检测，但已记录路径
            
            # 3. 提取图片特征
            features = self.feature_extractor.extract_features(image_data)
            
            # 4. 快速检查：基于特征哈希查找相似违规图片（节约API调用）
            similar_violations = self.db.find_similar_violations(features['phash'], max_distance=5)
            
            if similar_violations:
                # 发现高度相似的违规图片，可以直接标记为违规，跳过IMS检测
                most_similar = similar_violations[0]
                distance = most_similar.get('hash_distance', 99)
                
                logger.warning(
                    f"🔍 发现相似违规图片: {object_name} | "
                    f"相似于: {most_similar.get('object_key')} | "
                    f"违规类型: {most_similar.get('violation_type')} | "
                    f"汉明距离: {distance} | "
                    f"匹配类型: {most_similar.get('match_type')}"
                )
                
                # 智能判断：根据相似度决定是否跳过IMS检测
                # 距离0-1: 几乎相同，直接标记（节省100% API费用）
                # 距离2-3: 高度相似，直接标记（节省100% API费用）
                # 距离4-5: 中度相似，仍调用IMS确认（保证准确性）
                if distance <= 3:
                    logger.info(f"⚡ 高度相似（距离={distance}），直接标记为违规，跳过IMS检测（节约API费用）")
                    
                    # 构建记录
                    record = {
                        'key': key,
                        'feature_hash': features['phash'],
                        'feature_hash_dhash': features['dhash'],
                        'feature_hash_ahash': features['ahash'],
                        'feature_hash_phash': features['phash'],
                        'bucket_name': bucket_name,
                        'object_key': object_name,
                        'file_size': len(image_data),
                        'content_type': None,
                        'is_violation': 1,
                        'violation_type': most_similar.get('violation_type'),
                        'violation_label': most_similar.get('violation_label') + ' (相似匹配)',
                        'violation_description': f'与违规图片 {most_similar["object_key"]} 高度相似（汉明距离={distance}）',
                        'confidence': most_similar.get('confidence', 0.9),
                        'suggestion': 'Block',
                        'ims_result': {'matched_by': 'similarity', 'similar_to': most_similar['object_key'], 'hash_distance': distance},
                        'ims_request_id': None,
                        'scan_status': 'completed',
                        'error_message': None,
                        'last_scanned_at': datetime.now()
                    }
                    
                    # 保存到数据库
                    self.db.upsert_record(record)
                    
                    # 更新统计
                    self.stats['scanned'] += 1
                    self.stats['violations'] += 1
                    self.stats['api_saved'] = self.stats.get('api_saved', 0) + 1
                    
                    # 特别关注棋牌类违规
                    if most_similar.get('violation_type') == 'gambling':
                        logger.warning(
                            f"🎲 发现棋牌类违规图片（相似匹配）: {object_name} | "
                            f"相似于: {most_similar.get('object_key')} | "
                            f"已节约API调用: {self.stats['api_saved']}次"
                        )
                    
                    return  # 跳过后续的IMS检测
                else:
                    logger.info(f"⚠️ 中度相似（距离={distance}），仍调用IMS确认以保证准确性")
            
            # 5. 调用腾讯云IMS进行扫描（没有找到高度相似违规图片或距离>3）
            logger.debug(f"正在扫描: {object_name}")
            ims_result = self.ims_scanner.scan_image(image_data)
            
            # 6. 构建记录
            record = {
                'key': key,
                'feature_hash': features['phash'],
                'feature_hash_dhash': features['dhash'],
                'feature_hash_ahash': features['ahash'],
                'feature_hash_phash': features['phash'],
                'bucket_name': bucket_name,
                'object_key': object_name,
                'file_size': len(image_data),
                'content_type': None,  # 可以从obj_info获取
                'is_violation': 1 if ims_result['is_violation'] else 0,
                'violation_type': ims_result.get('violation_type'),
                'violation_label': ims_result.get('violation_label'),
                'violation_description': ims_result.get('violation_description'),
                'confidence': ims_result.get('confidence'),
                'suggestion': ims_result.get('suggestion'),
                'ims_result': ims_result.get('raw_result'),
                'ims_request_id': ims_result.get('request_id'),
                'scan_status': 'completed',
                'error_message': None,
                'last_scanned_at': datetime.now()
            }
            
            # 7. 保存到数据库
            self.db.upsert_record(record)
            
            # 8. 更新统计
            self.stats['scanned'] += 1
            if ims_result['is_violation']:
                self.stats['violations'] += 1
                
                # 特别关注棋牌类违规
                if ims_result.get('violation_type') == 'gambling':
                    logger.warning(
                        f"🎲 发现棋牌类违规图片: {object_name} | "
                        f"标签: {ims_result.get('violation_label')} | "
                        f"置信度: {ims_result.get('confidence')}"
                    )
                else:
                    logger.warning(
                        f"⚠️ 发现违规图片: {object_name} | "
                        f"类型: {ims_result.get('violation_type')} | "
                        f"置信度: {ims_result.get('confidence')}"
                    )
            
        except Exception as e:
            self.stats['errors'] += 1
            logger.error(f"处理图片失败 [{bucket_name}/{object_name}]: {e}")
            
            # 保存错误记录
            try:
                error_record = {
                    'key': key if 'key' in locals() else f"error-{object_name}",
                    'feature_hash': '',
                    'bucket_name': bucket_name,
                    'object_key': object_name,
                    'file_size': len(image_data) if 'image_data' in locals() else 0,
                    'scan_status': 'failed',
                    'error_message': str(e),
                    'last_scanned_at': datetime.now()
                }
                self.db.upsert_record(error_record)
            except:
                pass
    
    def _print_stats(self):
        """打印统计信息"""
        api_saved = self.stats.get('api_saved', 0)
        logger.info(
            f"统计信息 - 总数: {self.stats['total']}, "
            f"已扫描: {self.stats['scanned']}, "
            f"违规: {self.stats['violations']}, "
            f"跳过: {self.stats['skipped']}, "
            f"错误: {self.stats['errors']}, "
            f"节约API: {api_saved}次"
        )
    
    def get_violation_report(self, output_file: str = "violations.txt"):
        """
        生成违规图片报告
        
        Args:
            output_file: 输出文件路径
        """
        violations = self.db.get_violation_images(limit=10000)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write("违规图片检测报告\n")
            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")
            
            f.write(f"总计违规图片: {len(violations)}\n\n")
            
            # 按类型分组
            type_groups = {}
            for v in violations:
                vtype = v.get('violation_type', 'unknown')
                if vtype not in type_groups:
                    type_groups[vtype] = []
                type_groups[vtype].append(v)
            
            for vtype, items in sorted(type_groups.items()):
                f.write(f"\n{'-' * 80}\n")
                f.write(f"违规类型: {vtype} (共{len(items)}张)\n")
                f.write(f"{'-' * 80}\n\n")
                
                for idx, item in enumerate(items, 1):
                    f.write(f"{idx}. 路径: {item['bucket_name']}/{item['object_key']}\n")
                    f.write(f"   置信度: {item.get('confidence', 0)}\n")
                    f.write(f"   标签: {item.get('violation_label', 'N/A')}\n")
                    f.write(f"   描述: {item.get('violation_description', 'N/A')}\n")
                    f.write(f"   建议: {item.get('suggestion', 'N/A')}\n")
                    f.write(f"   扫描时间: {item.get('last_scanned_at', 'N/A')}\n")
                    f.write("\n")
        
        logger.info(f"违规报告已保存到: {output_file}")
    
    def close(self):
        """关闭资源"""
        self.db.close()
        logger.info("扫描器已关闭")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def load_config() -> Dict:
    """
    加载配置文件
    
    Returns:
        Dict: 配置字典
    """
    # 加载.env文件
    load_dotenv()
    
    config = {
        'minio': {
            'endpoint': os.getenv('MINIO_ENDPOINT', 'localhost:9000'),
            'access_key': os.getenv('MINIO_ACCESS_KEY', ''),
            'secret_key': os.getenv('MINIO_SECRET_KEY', ''),
            'secure': os.getenv('MINIO_SECURE', 'false').lower() == 'true',
            'bucket_name': os.getenv('MINIO_BUCKET_NAME', '')
        },
        'tencent': {
            'secret_id': os.getenv('TENCENT_SECRET_ID', ''),
            'secret_key': os.getenv('TENCENT_SECRET_KEY', ''),
            'region': os.getenv('TENCENT_REGION', 'ap-guangzhou')
        },
        'mysql': {
            'host': os.getenv('MYSQL_HOST', 'localhost'),
            'port': int(os.getenv('MYSQL_PORT', '3306')),
            'user': os.getenv('MYSQL_USER', 'root'),
            'password': os.getenv('MYSQL_PASSWORD', ''),
            'database': os.getenv('MYSQL_DATABASE', 'image_security')
        },
        'hash_size': int(os.getenv('HASH_SIZE', '8'))
    }
    
    # 验证必要配置
    required_fields = [
        ('minio.access_key', config['minio']['access_key']),
        ('minio.secret_key', config['minio']['secret_key']),
        ('minio.bucket_name', config['minio']['bucket_name']),
        ('tencent.secret_id', config['tencent']['secret_id']),
        ('tencent.secret_key', config['tencent']['secret_key']),
        ('mysql.password', config['mysql']['password']),
    ]
    
    missing = [name for name, value in required_fields if not value]
    if missing:
        raise ValueError(f"缺少必要的配置项: {', '.join(missing)}")
    
    return config


def main():
    """主函数"""
    # 配置日志
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO"
    )
    logger.add(
        "scanner.log",
        rotation="10 MB",
        retention="7 days",
        level="DEBUG"
    )
    
    try:
        # 加载配置
        config = load_config()
        
        # 创建扫描器
        with ImageSecurityScanner(config) as scanner:
            # 从命令行参数或环境变量获取扫描选项
            bucket_name = os.getenv('SCAN_BUCKET_NAME') or config['minio']['bucket_name']
            prefix = os.getenv('SCAN_PREFIX', '')
            force_rescan = os.getenv('FORCE_RESCAN', 'false').lower() == 'true'
            limit_str = os.getenv('SCAN_LIMIT')
            limit = int(limit_str) if limit_str else None
            
            # 开始扫描
            scanner.scan_all(
                bucket_name=bucket_name,
                prefix=prefix,
                force_rescan=force_rescan,
                limit=limit
            )
            
            # 生成违规报告
            scanner.get_violation_report("violations.txt")
            
    except Exception as e:
        logger.error(f"程序执行出错: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
