"""scanner._process_one 的三层去重分支测试 + _record_error 长度有界。"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def scanner():
    """构造一个 ImageSecurityScanner，但拦截所有外部依赖。"""
    with patch('scanner.MinIOClient'), \
         patch('scanner.ImageFeatureExtractor'), \
         patch('scanner.TencentIMSScanner'), \
         patch('scanner.ImageDatabase'):
        from scanner import ImageSecurityScanner
        config = {
            'minio': {'endpoint': 'x', 'access_key': 'x', 'secret_key': 'x',
                      'bucket_name': 'b'},
            'tencent': {'secret_id': 'x', 'secret_key': 'x'},
            'mysql': {'host': 'x', 'user': 'x', 'password': 'x', 'database': 'x'},
        }
        s = ImageSecurityScanner(config)
        # 给特征提取器一个稳定的返回
        s.features.calculate_key.return_value = "md5hash-100"
        s.features.extract_features.return_value = {
            'phash': 'p1', 'dhash': 'd1', 'ahash': 'a1',
        }
        s.minio.get_object_data.return_value = (b"fake image bytes", {'content_type': 'image/jpeg'})
        yield s


class TestProcessOneLayer1PathDedup:
    """第 1 层：路径去重命中，完全跳过下载和 IMS。"""

    def test_path_dedup_skips_everything(self, scanner):
        scanner.db.find_by_bucket_object.return_value = {
            'id': 1, 'is_violation': 0, 'violation_type': None,
        }
        scanner._process_one('b', 'k.jpg', force_rescan=False)
        # 不应该下载
        scanner.minio.get_object_data.assert_not_called()
        # 不应该调 IMS
        scanner.ims.scan_image.assert_not_called()
        assert scanner.stats['path_reused'] == 1
        assert scanner.stats['scanned'] == 0

    def test_path_dedup_counts_violation(self, scanner):
        """命中的是违规记录，违规计数 +1。"""
        scanner.db.find_by_bucket_object.return_value = {
            'id': 1, 'is_violation': 1, 'violation_type': 'gambling',
        }
        scanner._process_one('b', 'k.jpg', force_rescan=False)
        assert scanner.stats['violations'] == 1

    def test_force_rescan_bypasses_path_dedup(self, scanner):
        """force_rescan=True 时即使命中路径也会继续走完整流程。"""
        scanner.db.find_by_bucket_object.return_value = {'id': 1, 'is_violation': 0}
        scanner.db.find_by_key.return_value = None
        scanner.db.find_similar_scanned.return_value = []
        scanner.ims.scan_image.return_value = {
            'is_violation': False, 'confidence': 0.1, 'raw_result': {},
        }
        scanner._process_one('b', 'k.jpg', force_rescan=True)
        scanner.ims.scan_image.assert_called_once()
        assert scanner.stats['scanned'] == 1


class TestProcessOneLayer2ContentDedup:
    """第 2 层：内容去重，复用扫描结果不调 IMS，但插一条新路径记录。"""

    def test_content_dedup_reuses_result(self, scanner):
        scanner.db.find_by_bucket_object.return_value = None
        scanner.db.find_by_key.return_value = {
            'id': 99, 'bucket_name': 'b', 'object_key': 'old_path.jpg',
            'is_violation': 1, 'violation_type': 'gambling',
            'confidence': 0.95, 'suggestion': 'Block',
        }
        scanner._process_one('b', 'new_path.jpg', force_rescan=False)

        scanner.ims.scan_image.assert_not_called()
        scanner.db.upsert_record.assert_called_once()
        record = scanner.db.upsert_record.call_args[0][0]
        assert record['object_key'] == 'new_path.jpg'  # 新路径
        assert record['is_violation'] == 1             # 复用结果
        assert record['ims_result']['matched_by'] == 'content'
        assert scanner.stats['content_reused'] == 1


class TestProcessOneLayer3Similarity:
    """第 3 层：相似检测，距离 <= 3 复用结果，距离 > 3 仍调 IMS。"""

    def test_distance_0_reuses_result(self, scanner):
        scanner.db.find_by_bucket_object.return_value = None
        scanner.db.find_by_key.return_value = None
        scanner.db.find_similar_scanned.return_value = [{
            'key': 'similar-key-abc',
            'bucket_name': 'b', 'object_key': 'similar.jpg',
            'is_violation': 1, 'violation_type': 'Porn',
            'confidence': 0.9, 'suggestion': 'Block',
            'hash_distance': 0,
        }]
        scanner._process_one('b', 'new.jpg', force_rescan=False)

        scanner.ims.scan_image.assert_not_called()
        assert scanner.stats['api_saved'] == 1
        assert scanner.stats['scanned'] == 0

    def test_distance_3_reuses_result(self, scanner):
        """边界值：距离 == 3 仍属于"高度相似"。"""
        scanner.db.find_by_bucket_object.return_value = None
        scanner.db.find_by_key.return_value = None
        scanner.db.find_similar_scanned.return_value = [{
            'key': 'similar-key-abc',
            'bucket_name': 'b', 'object_key': 'similar.jpg',
            'is_violation': 0, 'hash_distance': 3,
        }]
        scanner._process_one('b', 'new.jpg', force_rescan=False)
        scanner.ims.scan_image.assert_not_called()
        assert scanner.stats['api_saved'] == 1

    def test_distance_4_falls_through_to_ims(self, scanner):
        """距离 4 属于"中度相似"，应继续调 IMS 复核。"""
        scanner.db.find_by_bucket_object.return_value = None
        scanner.db.find_by_key.return_value = None
        scanner.db.find_similar_scanned.return_value = [{
            'key': 'similar-key-abc',
            'bucket_name': 'b', 'object_key': 'similar.jpg',
            'is_violation': 0, 'hash_distance': 4,
        }]
        scanner.ims.scan_image.return_value = {
            'is_violation': False, 'confidence': 0.1, 'raw_result': {},
        }
        scanner._process_one('b', 'new.jpg', force_rescan=False)
        scanner.ims.scan_image.assert_called_once()
        assert scanner.stats['api_saved'] == 0


class TestProcessOneIMSPath:
    """走到 IMS 的常规路径：scanned +1、违规计数正确。"""

    def test_ims_violation(self, scanner):
        scanner.db.find_by_bucket_object.return_value = None
        scanner.db.find_by_key.return_value = None
        scanner.db.find_similar_scanned.return_value = []
        scanner.ims.scan_image.return_value = {
            'is_violation': True, 'violation_type': 'gambling',
            'violation_label': 'Casino', 'confidence': 0.99,
            'suggestion': 'Block', 'raw_result': {'x': 1}, 'request_id': 'r1',
        }
        scanner._process_one('b', 'k.jpg', force_rescan=False)

        record = scanner.db.upsert_record.call_args[0][0]
        assert record['is_violation'] == 1
        assert record['violation_type'] == 'gambling'
        assert record['confidence'] == 0.99
        assert record['ims_request_id'] == 'r1'
        assert scanner.stats['scanned'] == 1
        assert scanner.stats['violations'] == 1


class TestRecordErrorKeyLength:
    """审计 bug #3 回归：错误记录的 key 必须长度有界。"""

    def test_long_object_name_key_stays_short(self, scanner):
        long_name = "a/" + ("x" * 1000) + "/very_long.jpg"
        scanner._record_error('some_bucket', long_name, ValueError("oops"))

        record = scanner.db.upsert_record.call_args[0][0]
        # error-{md5}: "error-" (6) + 32 hex = 38 字符，远小于 VARCHAR(128)
        assert len(record['key']) <= 128
        assert record['key'].startswith('error-')
        assert len(record['key']) == 38, f"key 长度异常: {len(record['key'])}"

    def test_error_message_truncated(self, scanner):
        """error_message 超长时应截断到 60000 字节，预防 TEXT 上限。"""
        huge_err = Exception("E" * 100000)
        scanner._record_error('b', 'k.jpg', huge_err)
        record = scanner.db.upsert_record.call_args[0][0]
        assert len(record['error_message']) <= 60000

    def test_normal_error_passes_through(self, scanner):
        scanner._record_error('b', 'k.jpg', ConnectionError("network down"))
        record = scanner.db.upsert_record.call_args[0][0]
        assert record['error_message'] == "network down"
        assert record['scan_status'] == 'failed'
        assert record['bucket_name'] == 'b'
        assert record['object_key'] == 'k.jpg'
