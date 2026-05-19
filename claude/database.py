"""MySQL 数据库层：图片扫描记录的增改查。"""

import json
from datetime import datetime
from typing import Dict, List, Optional

import mysql.connector
from mysql.connector import Error
from loguru import logger

from image_feature import ImageFeatureExtractor

# 相似检测时从数据库拉取的候选记录上限。设过大会拖慢扫描；建议根据已扫描总量调整。
SIMILAR_CANDIDATE_LIMIT = 2000


class ImageDatabase:
    """图片扫描记录数据库管理。"""

    def __init__(self, host: str, port: int, user: str, password: str,
                 database: str, charset: str = 'utf8mb4'):
        self.config = {
            'host': host,
            'port': port,
            'user': user,
            'password': password,
            'database': database,
            'charset': charset,
            'use_pure': True,
            'autocommit': False,
        }
        self.connection = None
        self._connect()
        logger.info(f"数据库已连接: {host}:{port}/{database}")

    def _connect(self):
        self.connection = mysql.connector.connect(**self.config)

    def _ensure_connection(self):
        if not self.connection or not self.connection.is_connected():
            self._connect()

    def execute_query(self, query: str, params: tuple = None, fetch: bool = False):
        """执行 SQL。fetch=True 返回行列表，否则返回 lastrowid 并提交。"""
        self._ensure_connection()
        cursor = self.connection.cursor(dictionary=True)
        try:
            cursor.execute(query, params or ())
            if fetch:
                return cursor.fetchall()
            self.connection.commit()
            return cursor.lastrowid
        except Error as e:
            logger.error(f"SQL 执行失败: {e} | Query: {query}")
            self.connection.rollback()
            raise
        finally:
            cursor.close()

    # ------------------------------------------------------------------ 查询

    def find_by_bucket_object(self, bucket_name: str, object_key: str) -> Optional[Dict]:
        """按 MinIO 路径查记录（路径级去重）。"""
        rows = self.execute_query(
            "SELECT * FROM image_scan_records WHERE bucket_name = %s AND object_key = %s LIMIT 1",
            (bucket_name, object_key),
            fetch=True,
        )
        return rows[0] if rows else None

    def find_by_key(self, key: str) -> Optional[Dict]:
        """按内容 Key 查记录（内容级去重；返回已完成扫描的同内容记录）。

        必须过滤 scan_status='completed'：若返回 failed 记录，
        _write_reused 会把 violation_type=NULL 等脏数据复制给新路径。
        """
        rows = self.execute_query(
            "SELECT * FROM image_scan_records "
            "WHERE `key` = %s AND scan_status = 'completed' LIMIT 1",
            (key,),
            fetch=True,
        )
        return rows[0] if rows else None

    def find_similar_scanned(self, feature_hash: str, max_distance: int = 5,
                             limit: int = SIMILAR_CANDIDATE_LIMIT) -> List[Dict]:
        """查找已扫描记录中与 feature_hash 汉明距离 <= max_distance 的图片。

        实现：拉最近 `limit` 条已完成扫描的记录到内存，逐个算汉明距离过滤。
        大规模场景建议加 feature_hash 索引或换向量检索方案。
        """
        rows = self.execute_query(
            """
            SELECT `key`, bucket_name, object_key, feature_hash,
                   violation_type, violation_label, violation_label_cn,
                   sub_label, sub_label_cn,
                   confidence, suggestion, is_violation
            FROM image_scan_records
            WHERE scan_status = 'completed'
              AND feature_hash IS NOT NULL
              AND feature_hash != ''
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (limit,),
            fetch=True,
        )

        similar = []
        for row in rows:
            distance = ImageFeatureExtractor.calculate_hash_distance(
                feature_hash, row['feature_hash']
            )
            if 0 <= distance <= max_distance:
                row['hash_distance'] = distance
                similar.append(row)
        similar.sort(key=lambda x: x['hash_distance'])
        return similar[:10]

    def get_all_scanned_images(self, limit: int = None) -> List[Dict]:
        """获取所有已扫描的图片（用于加载到缓存）。"""
        query = """
            SELECT * FROM image_scan_records
            WHERE scan_status = 'completed'
            ORDER BY created_at DESC
        """
        if limit:
            query += f" LIMIT {limit}"
        return self.execute_query(query, fetch=True)

    def get_violation_images(self, limit: int = 100, offset: int = 0) -> List[Dict]:
        """分页获取违规图片列表。"""
        return self.execute_query(
            """
            SELECT * FROM image_scan_records
            WHERE is_violation = 1
            ORDER BY confidence DESC, created_at DESC
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
            fetch=True,
        )

    def get_statistics(self) -> Dict:
        """汇总统计：总数、违规数、按类型分布。"""
        total = self.execute_query(
            "SELECT COUNT(*) AS c FROM image_scan_records", fetch=True)
        violations = self.execute_query(
            "SELECT COUNT(*) AS c FROM image_scan_records WHERE is_violation = 1", fetch=True)
        by_type = self.execute_query(
            """
            SELECT violation_type, COUNT(*) AS c FROM image_scan_records
            WHERE is_violation = 1 AND violation_type IS NOT NULL
            GROUP BY violation_type
            """,
            fetch=True,
        )
        return {
            'total': total[0]['c'] if total else 0,
            'violations': violations[0]['c'] if violations else 0,
            'by_type': {r['violation_type']: r['c'] for r in by_type},
        }

    # ------------------------------------------------------------------ 写入

    def upsert_record(self, record: Dict) -> int:
        """按 (bucket_name, object_key) 唯一约束插入或更新。"""
        query = """
            INSERT INTO image_scan_records (
                `key`, feature_hash, feature_hash_dhash, feature_hash_ahash,
                feature_hash_phash, bucket_name, object_key, file_size,
                content_type, is_violation, violation_type, violation_label,
                violation_label_cn, sub_label, sub_label_cn,
                confidence, suggestion, blocked, ims_result,
                ims_request_id, scan_status, error_message, first_seen_at, last_scanned_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON DUPLICATE KEY UPDATE
                `key` = VALUES(`key`),
                feature_hash = VALUES(feature_hash),
                feature_hash_dhash = VALUES(feature_hash_dhash),
                feature_hash_ahash = VALUES(feature_hash_ahash),
                feature_hash_phash = VALUES(feature_hash_phash),
                is_violation = VALUES(is_violation),
                violation_type = VALUES(violation_type),
                violation_label = VALUES(violation_label),
                violation_label_cn = VALUES(violation_label_cn),
                sub_label = VALUES(sub_label),
                sub_label_cn = VALUES(sub_label_cn),
                confidence = VALUES(confidence),
                suggestion = VALUES(suggestion),
                ims_result = VALUES(ims_result),
                ims_request_id = VALUES(ims_request_id),
                scan_status = VALUES(scan_status),
                error_message = VALUES(error_message),
                first_seen_at = COALESCE(first_seen_at, VALUES(first_seen_at)),
                last_scanned_at = NOW(),
                updated_at = NOW()
        """
        now = datetime.now()
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
            record.get('violation_label_cn'),
            record.get('sub_label'),
            record.get('sub_label_cn'),
            record.get('confidence'),
            record.get('suggestion'),
            record.get('blocked', 0),
            json.dumps(record['ims_result']) if record.get('ims_result') else None,
            record.get('ims_request_id'),
            record.get('scan_status', 'completed'),
            record.get('error_message'),
            record.get('first_seen_at', now),
            record.get('last_scanned_at', now),
        )
        return self.execute_query(query, params)

    # ------------------------------------------------------------------ 生命周期

    def close(self):
        if self.connection and self.connection.is_connected():
            self.connection.close()
            logger.info("数据库连接已关闭")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
