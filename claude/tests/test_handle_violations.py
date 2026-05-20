"""handle_violations 操作流程测试：block/restore/delete 各分支的 MinIO+DB 调用顺序。"""

from unittest.mock import MagicMock, patch

import pytest

# 这些纯函数可以直接测，不需要 fixture。
from handle_violations import _quarantine_key, _parse_ids


class TestQuarantineKey:
    def test_basic_format(self):
        assert _quarantine_key("images", "a/b.jpg") == "images/a/b.jpg"

    def test_unicode_path(self):
        assert _quarantine_key("桶名", "图片.png") == "桶名/图片.png"

    def test_round_trip(self):
        """从隔离桶 key 应能还原出原桶+原 key。"""
        original_bucket = "biz_bucket"
        original_key = "deep/nested/img.jpg"
        q = _quarantine_key(original_bucket, original_key)
        parsed_bucket, parsed_key = q.split('/', 1)
        assert parsed_bucket == original_bucket
        assert parsed_key == original_key


class TestParseIds:
    def test_comma_separated(self):
        assert _parse_ids("1,2,3") == [1, 2, 3]

    def test_with_spaces(self):
        assert _parse_ids("1, 2 , 3") == [1, 2, 3]

    def test_empty_string(self):
        assert _parse_ids("") == []

    def test_trailing_comma(self):
        assert _parse_ids("1,2,") == [1, 2]

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            _parse_ids("abc")


@pytest.fixture
def handler():
    """构造 ViolationHandler，拦截数据库和 MinIO 初始化。"""
    with patch('handle_violations.ImageDatabase'), \
         patch('handle_violations.MinIOClient'):
        from handle_violations import ViolationHandler
        h = ViolationHandler()
        # ensure_bucket 在 init 被调一次
        h.minio.ensure_bucket.reset_mock()
        yield h


class TestConfirmQuarantine:
    """confirm_quarantine：原桶 → 隔离桶 + 打 tag + 数据库 blocked=2。"""

    def test_confirm_quarantine_happy_path(self, handler):
        handler.minio.object_exists.return_value = True
        records = [{
            'id': 1, 'bucket_name': 'images', 'object_key': 'bad.jpg',
            'violation_type': 'Gambling',
        }]
        stats = handler.confirm_quarantine(records, dry_run=False)

        assert stats == {'success': 1, 'failed': 0, 'skipped': 0}
        # 调用顺序：检查存在 → move_object → set_violation_tag → DB 更新
        handler.minio.move_object.assert_called_once_with(
            'images', 'bad.jpg', handler.quarantine, 'images/bad.jpg'
        )
        handler.minio.set_violation_tag.assert_called_once()
        # 数据库 blocked = 2
        update_call = handler.db.execute_query.call_args_list[-1]
        assert "blocked = 2" in update_call[0][0]
        assert update_call[0][1] == (1,)

    def test_confirm_quarantine_source_missing_marks_only(self, handler):
        """源文件已不存在时，只标记数据库不做迁移。"""
        handler.minio.object_exists.return_value = False
        records = [{'id': 1, 'bucket_name': 'images', 'object_key': 'gone.jpg',
                    'violation_type': 'Porn'}]
        stats = handler.confirm_quarantine(records, dry_run=False)
        assert stats == {'success': 0, 'failed': 0, 'skipped': 1}
        handler.minio.move_object.assert_not_called()
        handler.minio.set_violation_tag.assert_not_called()

    def test_confirm_quarantine_dry_run_does_not_call_minio(self, handler):
        records = [{'id': 1, 'bucket_name': 'images', 'object_key': 'bad.jpg',
                    'violation_type': 'Gambling'}]
        handler.confirm_quarantine(records, dry_run=True)
        handler.minio.move_object.assert_not_called()
        handler.minio.set_violation_tag.assert_not_called()
        handler.db.execute_query.assert_not_called()

    def test_confirm_quarantine_tag_failure_does_not_fail(self, handler):
        """打标签失败仅警告，不应让整个隔离失败（迁移已完成）。"""
        handler.minio.object_exists.return_value = True
        handler.minio.set_violation_tag.side_effect = RuntimeError("tag service down")
        records = [{'id': 1, 'bucket_name': 'b', 'object_key': 'k.jpg',
                    'violation_type': 'Porn'}]
        stats = handler.confirm_quarantine(records, dry_run=False)
        assert stats['success'] == 1

    def test_confirm_quarantine_move_failure_no_db_update(self, handler):
        """移动失败时数据库不应被标记为 quarantined。"""
        handler.minio.object_exists.return_value = True
        handler.minio.move_object.side_effect = RuntimeError("network error")
        records = [{'id': 1, 'bucket_name': 'b', 'object_key': 'k.jpg',
                    'violation_type': 'Porn'}]
        stats = handler.confirm_quarantine(records, dry_run=False)
        assert stats == {'success': 0, 'failed': 1, 'skipped': 0}
        # 数据库没有 UPDATE 调用
        handler.db.execute_query.assert_not_called()


class TestRestore:
    """restore：隔离桶 → 原桶 + 清标签 + blocked=0 is_violation=0。"""

    def test_restore_happy_path(self, handler):
        handler.minio.object_exists.return_value = True
        records = [{'id': 5, 'bucket_name': 'images', 'object_key': 'falsepos.jpg',
                    'violation_type': 'gambling'}]
        stats = handler.restore(records, dry_run=False)

        assert stats == {'success': 1, 'failed': 0, 'skipped': 0}
        handler.minio.move_object.assert_called_once_with(
            handler.quarantine, 'images/falsepos.jpg', 'images', 'falsepos.jpg'
        )
        handler.minio.clear_tags.assert_called_once()
        update_call = handler.db.execute_query.call_args_list[-1]
        sql = update_call[0][0]
        assert "blocked = 0" in sql
        assert "is_violation = 0" in sql

    def test_restore_missing_in_quarantine_skips(self, handler):
        handler.minio.object_exists.return_value = False
        records = [{'id': 1, 'bucket_name': 'b', 'object_key': 'k.jpg',
                    'violation_type': 'porn'}]
        stats = handler.restore(records, dry_run=False)
        assert stats == {'success': 0, 'failed': 0, 'skipped': 1}
        handler.minio.move_object.assert_not_called()


class TestDelete:
    """delete：从隔离桶物理删除 + 删数据库记录。"""

    def test_delete_happy_path(self, handler):
        handler.minio.object_exists.return_value = True
        records = [{'id': 7, 'bucket_name': 'images', 'object_key': 'bad.jpg',
                    'violation_type': 'porn'}]
        stats = handler.delete(records, dry_run=False)

        assert stats == {'success': 1, 'failed': 0}
        handler.minio.remove_object.assert_called_once_with(
            handler.quarantine, 'images/bad.jpg'
        )
        # DB DELETE
        delete_call = handler.db.execute_query.call_args_list[-1]
        assert "DELETE FROM image_scan_records" in delete_call[0][0]
        assert delete_call[0][1] == (7,)

    def test_delete_missing_still_deletes_db_record(self, handler):
        """隔离桶里已经没了，仍应清理数据库记录。"""
        handler.minio.object_exists.return_value = False
        records = [{'id': 1, 'bucket_name': 'b', 'object_key': 'k.jpg',
                    'violation_type': 'porn'}]
        stats = handler.delete(records, dry_run=False)
        assert stats == {'success': 1, 'failed': 0}
        handler.minio.remove_object.assert_not_called()
        delete_call = handler.db.execute_query.call_args_list[-1]
        assert "DELETE FROM image_scan_records" in delete_call[0][0]
