"""minio_client 测试：图片扩展名识别、move_object 调用顺序、错误码处理。"""

from unittest.mock import MagicMock, patch

import pytest

from minio_client import _is_image_file
from minio.error import S3Error


class TestIsImageFile:
    def test_common_extensions(self):
        for name in ['a.jpg', 'b.JPEG', 'c.PNG', 'd.gif', 'e.webp']:
            assert _is_image_file(name), f"{name} 应识别为图片"

    def test_non_image_rejected(self):
        for name in ['readme.txt', 'data.csv', 'video.mp4', 'no_ext']:
            assert not _is_image_file(name), f"{name} 不应识别为图片"

    def test_uppercase_extension(self):
        assert _is_image_file("IMG_001.JPG")

    def test_path_with_dots(self):
        assert _is_image_file("path.with.dots/file.png")


@pytest.fixture
def client():
    """构造 MinIOClient 但拦截 Minio() 初始化。"""
    with patch('minio_client.Minio') as fake_minio_cls:
        fake_client = MagicMock()
        fake_minio_cls.return_value = fake_client
        from minio_client import MinIOClient
        c = MinIOClient('host:9000', 'ak', 'sk')
        yield c


class TestMoveObject:
    """move_object 必须 copy + remove，顺序固定。"""

    def test_copy_before_remove(self, client):
        client.move_object('src_b', 'src_k', 'dst_b', 'dst_k')
        # 调用顺序：先 copy_object，再 remove_object
        method_calls = [call[0] for call in client.client.method_calls]
        assert method_calls == ['copy_object', 'remove_object']

    def test_copy_failure_does_not_delete_source(self, client):
        """copy 失败时源对象必须保留。"""
        client.client.copy_object.side_effect = RuntimeError("network")
        with pytest.raises(RuntimeError):
            client.move_object('src_b', 'src_k', 'dst_b', 'dst_k')
        client.client.remove_object.assert_not_called()


class TestObjectExists:
    """object_exists 处理 NoSuchKey 错误码必须返回 False，其它错误向上传播。"""

    def test_existing_object_returns_true(self, client):
        client.client.stat_object.return_value = MagicMock()
        assert client.object_exists('b', 'k') is True

    def test_no_such_key_returns_false(self, client):
        err = S3Error("NoSuchKey", "msg", "resource", "request_id", "host_id", None)
        client.client.stat_object.side_effect = err
        assert client.object_exists('b', 'k') is False

    def test_other_error_raises(self, client):
        err = S3Error("AccessDenied", "msg", "resource", "request_id", "host_id", None)
        client.client.stat_object.side_effect = err
        with pytest.raises(S3Error):
            client.object_exists('b', 'k')


class TestEnsureBucket:
    def test_create_if_missing(self, client):
        client.client.bucket_exists.return_value = False
        client.ensure_bucket('new_bucket')
        client.client.make_bucket.assert_called_once_with('new_bucket')

    def test_skip_if_exists(self, client):
        client.client.bucket_exists.return_value = True
        client.ensure_bucket('existing')
        client.client.make_bucket.assert_not_called()


class TestSetViolationTag:
    """set_violation_tag 至少打上 status=violation；可选 violation_type。"""

    def test_basic_tag(self, client):
        client.set_violation_tag('b', 'k')
        args = client.client.set_object_tags.call_args
        bucket, obj, tags = args[0]
        assert tags['status'] == 'violation'
        assert 'violation_type' not in tags

    def test_with_violation_type(self, client):
        client.set_violation_tag('b', 'k', violation_type='gambling')
        args = client.client.set_object_tags.call_args
        _, _, tags = args[0]
        assert tags['status'] == 'violation'
        assert tags['violation_type'] == 'gambling'


class TestClearTags:
    def test_no_such_tag_set_swallowed(self, client):
        """对象没标签时 MinIO 返回 NoSuchTagSet，不应抛异常。"""
        err = S3Error("NoSuchTagSet", "msg", "resource", "request_id", "host_id", None)
        client.client.delete_object_tags.side_effect = err
        # 不应抛
        client.clear_tags('b', 'k')

    def test_other_error_raises(self, client):
        err = S3Error("AccessDenied", "msg", "resource", "request_id", "host_id", None)
        client.client.delete_object_tags.side_effect = err
        with pytest.raises(S3Error):
            client.clear_tags('b', 'k')
