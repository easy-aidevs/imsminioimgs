"""
MySQL数据库操作模块
用于存储和查询图片扫描结果
"""

import mysql.connector
from mysql.connector import Error
from typing import Dict, List, Optional
from datetime import datetime
import json
from loguru import logger
from image_feature import ImageFeatureExtractor


class ImageDatabase:
    """图片扫描结果数据库管理类"""
    
    def __init__(self, host: str, port: int, user: str, password: str, 
                 database: str, charset: str = 'utf8mb4'):
        """
        初始化数据库连接
        
        Args:
            host: MySQL主机地址
            port: MySQL端口
            user: 用户名
            password: 密码
            database: 数据库名
            charset: 字符集
        """
        self.config = {
            'host': host,
            'port': port,
            'user': user,
            'password': password,
            'database': database,
            'charset': charset,
            'use_pure': True,
            'autocommit': False
        }
        self.connection = None
        self._connect()
        logger.info(f"数据库连接成功: {host}:{port}/{database}")
    
    def _connect(self):
        """建立数据库连接"""
        try:
            self.connection = mysql.connector.connect(**self.config)
            if self.connection.is_connected():
                logger.debug("数据库连接已建立")
        except Error as e:
            logger.error(f"数据库连接失败: {e}")
            raise
    
    def _ensure_connection(self):
        """确保数据库连接有效"""
        try:
            if not self.connection or not self.connection.is_connected():
                self._connect()
        except Error:
            self._connect()
    
    def execute_query(self, query: str, params: tuple = None, fetch: bool = False):
        """
        执行SQL查询
        
        Args:
            query: SQL语句
            params: 参数元组
            fetch: 是否返回结果
            
        Returns:
            查询结果（如果fetch=True）
        """
        self._ensure_connection()
        cursor = None
        try:
            cursor = self.connection.cursor(dictionary=True)
            cursor.execute(query, params or ())
            
            if fetch:
                result = cursor.fetchall()
                return result
            else:
                self.connection.commit()
                return cursor.lastrowid
                
        except Error as e:
            logger.error(f"SQL执行失败: {e}\nQuery: {query}\nParams: {params}")
            self.connection.rollback()
            raise
        finally:
            if cursor:
                cursor.close()
    
    def find_by_key(self, key: str) -> Optional[Dict]:
        """
        根据key查找记录（返回第一条，用于获取特征信息）
        
        Args:
            key: 图片唯一标识
            
        Returns:
            Dict or None: 记录字典，不存在则返回None
        """
        query = "SELECT * FROM image_scan_records WHERE `key` = %s LIMIT 1"
        results = self.execute_query(query, (key,), fetch=True)
        return results[0] if results else None
    
    def find_all_by_key(self, key: str) -> List[Dict]:
        """
        根据key查找所有记录（同一张图片的所有路径）
        
        Args:
            key: 图片唯一标识
            
        Returns:
            List[Dict]: 所有匹配的记录列表
        """
        query = "SELECT * FROM image_scan_records WHERE `key` = %s ORDER BY created_at DESC"
        return self.execute_query(query, (key,), fetch=True)
    
    def find_by_feature_hash(self, feature_hash: str, similarity_threshold: int = 5) -> List[Dict]:
        """
        根据特征哈希查找相似图片（包括违规记录）
        
        Args:
            feature_hash: 特征哈希值
            similarity_threshold: 相似度阈值（汉明距离）
            
        Returns:
            List[Dict]: 相似图片记录列表
        """
        # 精确匹配pHash、dHash、aHash
        query = """
            SELECT * FROM image_scan_records 
            WHERE feature_hash = %s 
               OR feature_hash_dhash = %s 
               OR feature_hash_ahash = %s
            ORDER BY is_violation DESC, confidence DESC, created_at DESC
        """
        results = self.execute_query(query, (feature_hash, feature_hash, feature_hash), fetch=True)
        return results
    
    def find_similar_violations(self, feature_hash: str, max_distance: int = 5) -> List[Dict]:
        """
        查找相似的违规图片（用于快速判断）
        通过计算汉明距离来找到高度相似的已标记违规图片
        
        Args:
            feature_hash: 当前图片的特征哈希
            max_distance: 最大汉明距离阈值（默认5）
            
        Returns:
            List[Dict]: 相似违规图片列表，包含距离信息
        """
        # 先获取所有违规记录的哈希值
        query = """
            SELECT `key`, object_key, bucket_name, feature_hash, feature_hash_dhash, 
                   feature_hash_ahash, violation_type, violation_label, confidence
            FROM image_scan_records 
            WHERE is_violation = 1 
              AND scan_status = 'completed'
              AND feature_hash IS NOT NULL
            ORDER BY confidence DESC
            LIMIT 1000
        """
        violations = self.execute_query(query, fetch=True)
        
        # 在Python中计算汉明距离并过滤
        similar_violations = []
        for violation in violations:
            # 计算与pHash的距离
            if violation.get('feature_hash'):
                distance = ImageFeatureExtractor.calculate_hash_distance(
                    feature_hash, 
                    violation['feature_hash']
                )
                if 0 <= distance <= max_distance:
                    violation['hash_distance'] = distance
                    violation['match_type'] = 'phash'
                    similar_violations.append(violation)
                    continue
            
            # 计算与dHash的距离
            if violation.get('feature_hash_dhash'):
                distance = ImageFeatureExtractor.calculate_hash_distance(
                    feature_hash,
                    violation['feature_hash_dhash']
                )
                if 0 <= distance <= max_distance:
                    violation['hash_distance'] = distance
                    violation['match_type'] = 'dhash'
                    similar_violations.append(violation)
                    continue
            
            # 计算与aHash的距离
            if violation.get('feature_hash_ahash'):
                distance = ImageFeatureExtractor.calculate_hash_distance(
                    feature_hash,
                    violation['feature_hash_ahash']
                )
                if 0 <= distance <= max_distance:
                    violation['hash_distance'] = distance
                    violation['match_type'] = 'ahash'
                    similar_violations.append(violation)
        
        # 按距离排序（距离越小越相似）
        similar_violations.sort(key=lambda x: x['hash_distance'])
        
        return similar_violations[:10]  # 返回最相似的10个
    
    def insert_record(self, record: Dict) -> int:
        """
        插入扫描记录
        
        Args:
            record: 记录字典，包含所有字段
            
        Returns:
            int: 新记录的ID
        """
        query = """
            INSERT INTO image_scan_records (
                `key`, feature_hash, feature_hash_dhash, feature_hash_ahash, 
                feature_hash_phash, bucket_name, object_key, file_size, 
                content_type, is_violation, violation_type, violation_label,
                violation_description, confidence, suggestion, ims_result,
                ims_request_id, scan_status, error_message, last_scanned_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s
            )
        """
        
        params = (
            record.get('key'),
            record.get('feature_hash'),
            record.get('feature_hash_dhash'),
            record.get('feature_hash_ahash'),
            record.get('feature_hash_phash'),
            record.get('bucket_name'),
            record.get('object_key'),
            record.get('file_size'),
            record.get('content_type'),
            record.get('is_violation', 0),
            record.get('violation_type'),
            record.get('violation_label'),
            record.get('violation_description'),
            record.get('confidence'),
            record.get('suggestion'),
            json.dumps(record.get('ims_result')) if record.get('ims_result') else None,
            record.get('ims_request_id'),
            record.get('scan_status', 'completed'),
            record.get('error_message'),
            record.get('last_scanned_at', datetime.now())
        )
        
        record_id = self.execute_query(query, params)
        logger.debug(f"插入记录成功，ID: {record_id}")
        return record_id
    
    def update_record(self, key: str, updates: Dict) -> bool:
        """
        更新扫描记录
        
        Args:
            key: 图片唯一标识
            updates: 要更新的字段字典
            
        Returns:
            bool: 是否更新成功
        """
        if not updates:
            return False
        
        # 构建SET子句
        set_clauses = []
        params = []
        
        for field, value in updates.items():
            if field == 'ims_result' and isinstance(value, (dict, list)):
                set_clauses.append(f"{field} = %s")
                params.append(json.dumps(value))
            else:
                set_clauses.append(f"{field} = %s")
                params.append(value)
        
        params.append(key)
        
        query = f"UPDATE image_scan_records SET {', '.join(set_clauses)} WHERE `key` = %s"
        
        try:
            self.execute_query(query, tuple(params))
            logger.debug(f"更新记录成功: {key}")
            return True
        except Exception as e:
            logger.error(f"更新记录失败: {e}")
            return False
    
    def upsert_record(self, record: Dict) -> int:
        """
        插入或更新记录（如果key已存在则更新）
        
        Args:
            record: 记录字典
            
        Returns:
            int: 记录ID
        """
        existing = self.find_by_key(record['key'])
        
        if existing:
            # 更新现有记录
            updates = {
                'feature_hash': record.get('feature_hash'),
                'feature_hash_dhash': record.get('feature_hash_dhash'),
                'feature_hash_ahash': record.get('feature_hash_ahash'),
                'feature_hash_phash': record.get('feature_hash_phash'),
                'is_violation': record.get('is_violation', 0),
                'violation_type': record.get('violation_type'),
                'violation_label': record.get('violation_label'),
                'violation_description': record.get('violation_description'),
                'confidence': record.get('confidence'),
                'suggestion': record.get('suggestion'),
                'ims_result': record.get('ims_result'),
                'ims_request_id': record.get('ims_request_id'),
                'scan_status': record.get('scan_status', 'completed'),
                'error_message': record.get('error_message'),
                'last_scanned_at': datetime.now()
            }
            self.update_record(record['key'], updates)
            return existing['id']
        else:
            # 插入新记录
            return self.insert_record(record)
    
    def get_violation_images(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        """
        获取违规图片列表
        
        Args:
            limit: 限制数量
            offset: 偏移量
            
        Returns:
            List[Dict]: 违规图片记录列表
        """
        query = """
            SELECT * FROM image_scan_records 
            WHERE is_violation = 1 
            ORDER BY confidence DESC, created_at DESC
            LIMIT %s OFFSET %s
        """
        return self.execute_query(query, (limit, offset), fetch=True)
    
    def get_statistics(self) -> Dict:
        """
        获取扫描统计信息
        
        Returns:
            Dict: 统计信息
        """
        queries = {
            'total': "SELECT COUNT(*) as count FROM image_scan_records",
            'violations': "SELECT COUNT(*) as count FROM image_scan_records WHERE is_violation = 1",
            'pending': "SELECT COUNT(*) as count FROM image_scan_records WHERE scan_status = 'pending'",
            'by_type': """
                SELECT violation_type, COUNT(*) as count 
                FROM image_scan_records 
                WHERE is_violation = 1 AND violation_type IS NOT NULL
                GROUP BY violation_type
            """
        }
        
        stats = {}
        for key, query in queries.items():
            if key == 'by_type':
                results = self.execute_query(query, fetch=True)
                stats[key] = {row['violation_type']: row['count'] for row in results}
            else:
                result = self.execute_query(query, fetch=True)
                stats[key] = result[0]['count'] if result else 0
        
        return stats
    
    def close(self):
        """关闭数据库连接"""
        if self.connection and self.connection.is_connected():
            self.connection.close()
            logger.info("数据库连接已关闭")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
