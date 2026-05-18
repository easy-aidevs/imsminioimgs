"""MinIO 客户端：图片列举、下载、隔离桶迁移、违规标签。"""

from typing import Generator, Tuple

from minio import Minio
from minio.commonconfig import CopySource, Tags
from minio.error import S3Error
from loguru import logger

IMAGE_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp',
    '.tiff', '.tif', '.svg', '.ico'
}


class MinIOClient:
    """MinIO 客户端封装。

    职责：
    - 遍历桶 / 下载对象（扫描器使用）
    - 在桶之间移动对象（隔离/恢复违规图片）
    - 给对象打/清违规标签（仅用于标记，不承担访问控制）
    """

    def __init__(self, endpoint: str, access_key: str, secret_key: str,
                 secure: bool = False, bucket_name: str = None):
        self.client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        self.bucket_name = bucket_name
        logger.info(f"MinIO 客户端就绪: {endpoint}")

    # ------------------------------------------------------------------ 遍历

    def list_objects(self, bucket_name: str = None, prefix: str = "",
                     recursive: bool = True) -> Generator[Tuple[str, object], None, None]:
        """遍历桶内的图片对象，yield (object_name, object_info)。"""
        bucket = bucket_name or self.bucket_name
        if not bucket:
            raise ValueError("必须指定 bucket_name")

        logger.info(f"遍历存储桶: {bucket}, 前缀: {prefix or '(无)'}")
        count = 0
        for obj in self.client.list_objects(bucket, prefix=prefix, recursive=recursive):
            if _is_image_file(obj.object_name):
                yield obj.object_name, obj
                count += 1
        logger.info(f"遍历完成，共 {count} 个图片对象")

    def get_object_data(self, bucket_name: str, object_name: str) -> bytes:
        """下载对象内容到内存。"""
        response = self.client.get_object(bucket_name, object_name)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def object_exists(self, bucket_name: str, object_name: str) -> bool:
        """判断对象是否存在。"""
        try:
            self.client.stat_object(bucket_name, object_name)
            return True
        except S3Error as e:
            if e.code in ("NoSuchKey", "NoSuchObject"):
                return False
            raise

    # ------------------------------------------------------------------ 桶管理

    def ensure_bucket(self, bucket_name: str):
        """如果桶不存在则创建（用于初始化隔离桶）。"""
        if not self.client.bucket_exists(bucket_name):
            self.client.make_bucket(bucket_name)
            logger.info(f"已创建存储桶: {bucket_name}")

    # ------------------------------------------------------------------ 迁移

    def move_object(self, src_bucket: str, src_key: str,
                    dst_bucket: str, dst_key: str):
        """跨桶移动对象：copy + remove。失败时不删除源对象。"""
        self.client.copy_object(
            dst_bucket, dst_key,
            CopySource(src_bucket, src_key),
        )
        self.client.remove_object(src_bucket, src_key)
        logger.debug(f"移动对象: {src_bucket}/{src_key} -> {dst_bucket}/{dst_key}")

    def remove_object(self, bucket_name: str, object_name: str):
        """删除对象。"""
        self.client.remove_object(bucket_name, object_name)
        logger.debug(f"删除对象: {bucket_name}/{object_name}")

    # ------------------------------------------------------------------ 标签（仅用于标记）

    def set_violation_tag(self, bucket_name: str, object_name: str,
                          violation_type: str = None):
        """打违规标签，仅用作资源标记，不承担访问控制。"""
        tags = Tags.new_object_tags()
        tags["status"] = "violation"
        if violation_type:
            tags["violation_type"] = violation_type
        self.client.set_object_tags(bucket_name, object_name, tags)

    def clear_tags(self, bucket_name: str, object_name: str):
        """清除对象上的所有标签。"""
        try:
            self.client.delete_object_tags(bucket_name, object_name)
        except S3Error as e:
            if e.code == "NoSuchTagSet":
                return
            raise


def _is_image_file(object_name: str) -> bool:
    """根据扩展名判断是否为图片。"""
    if '.' not in object_name:
        return False
    ext = '.' + object_name.rsplit('.', 1)[-1].lower()
    return ext in IMAGE_EXTENSIONS
