"""database 层测试：用 mock connection 验证查询字符串和参数。"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def db():
    """构造一个 ImageDatabase 实例，但拦截 _connect 让它不真连 MySQL。"""
    with patch('database.mysql.connector.connect') as fake_connect:
        fake_conn = MagicMock()
        fake_conn.is_connected.return_value = True
        fake_connect.return_value = fake_conn
        from database import ImageDatabase
        d = ImageDatabase('h', 3306, 'u', 'p', 'db')
        # 让 fetchall 默认返回空，单测里再 override
        d.connection.cursor.return_value.__enter__ = lambda s: s
        d.connection.cursor.return_value.fetchall.return_value = []
        d.connection.cursor.return_value.lastrowid = 1
        yield d


class TestFindSimilarScannedDefensiveFilter:
    """审计 bug #2 回归：feature_hash 为空字符串的记录必须被 SQL 过滤掉。"""

    def test_query_filters_empty_feature_hash(self, db):
        db.find_similar_scanned("abcd1234", max_distance=5)
        # 检查最近一次 execute 的 SQL
        cursor = db.connection.cursor.return_value
        sql = cursor.execute.call_args[0][0]
        assert "feature_hash IS NOT NULL" in sql
        assert "feature_hash != ''" in sql, "空字符串过滤缺失——bug #2 回归"

    def test_query_limits_candidates(self, db):
        db.find_similar_scanned("abcd1234", max_distance=5, limit=500)
        cursor = db.connection.cursor.return_value
        params = cursor.execute.call_args[0][1]
        assert params == (500,)

    def test_only_completed_records(self, db):
        db.find_similar_scanned("abcd1234")
        cursor = db.connection.cursor.return_value
        sql = cursor.execute.call_args[0][0]
        assert "scan_status = 'completed'" in sql


class TestUpsertRecord:
    """upsert_record 字段映射：22 列对 22 占位符，所有 NOT NULL 字段都被提供。"""

    def test_insert_has_22_placeholders(self, db):
        db.upsert_record({
            'key': 'abc-123',
            'feature_hash': 'phash1',
            'bucket_name': 'b1',
            'object_key': 'k1',
            'file_size': 100,
        })
        cursor = db.connection.cursor.return_value
        sql = cursor.execute.call_args[0][0]
        params = cursor.execute.call_args[0][1]
        # INSERT 段的占位符数量
        insert_section = sql.split("ON DUPLICATE")[0]
        assert insert_section.count("%s") == 22
        assert len(params) == 22

    def test_blocked_default_zero(self, db):
        """没传 blocked 字段时，默认值是 0，避免插入 NULL。"""
        db.upsert_record({
            'key': 'k', 'feature_hash': 'fh',
            'bucket_name': 'b', 'object_key': 'o', 'file_size': 1,
        })
        cursor = db.connection.cursor.return_value
        params = cursor.execute.call_args[0][1]
        # blocked 是第 16 个参数（按 INSERT 字段顺序）
        # key, feature_hash, dhash, ahash, phash, bucket_name, object_key, file_size,
        # content_type, is_violation, violation_type, violation_label,
        # violation_description, confidence, suggestion, blocked, ...
        assert params[15] == 0

    def test_ims_result_json_serialized(self, db):
        """dict 类型的 ims_result 应该被 json.dumps 成字符串。"""
        db.upsert_record({
            'key': 'k', 'feature_hash': 'fh',
            'bucket_name': 'b', 'object_key': 'o', 'file_size': 1,
            'ims_result': {'matched_by': 'similar', 'distance': 2},
        })
        cursor = db.connection.cursor.return_value
        params = cursor.execute.call_args[0][1]
        # ims_result 是第 17 个参数
        ims_param = params[16]
        assert isinstance(ims_param, str)
        assert 'matched_by' in ims_param

    def test_unique_key_clause(self, db):
        """ON DUPLICATE KEY UPDATE 子句存在，依赖 (bucket_name, object_key) 唯一约束。"""
        db.upsert_record({
            'key': 'k', 'feature_hash': 'fh',
            'bucket_name': 'b', 'object_key': 'o', 'file_size': 1,
        })
        cursor = db.connection.cursor.return_value
        sql = cursor.execute.call_args[0][0]
        assert "ON DUPLICATE KEY UPDATE" in sql
        # first_seen_at 必须用 COALESCE 保留原值
        assert "COALESCE(first_seen_at" in sql
