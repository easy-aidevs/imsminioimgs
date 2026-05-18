"""
MinIO客户端模块
用于连接MinIO服务器并遍历图片文件
"""

from minio import Minio
from minio.error import S3Error
from typing import Generator, Tuple
from loguru import logger


class MinIOClient:
    """MinIO客户端封装类"""
    
    def __init__(self, endpoint: str, access_key: str, secret_key: str, 
                 secure: bool = False, bucket_name: str = None):
        """
        初始化MinIO客户端
        
        Args:
            endpoint: MinIO服务器地址 (例如: localhost:9000)
            access_key: 访问密钥
            secret_key: 秘密密钥
            secure: 是否使用HTTPS
            bucket_name: 默认存储桶名称
        """
        self.client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure
        )
        self.bucket_name = bucket_name
        logger.info(f"MinIO客户端初始化成功: {endpoint}")
    
    def list_buckets(self) -> list:
        """列出所有存储桶"""
        try:
            buckets = self.client.list_buckets()
            bucket_names = [bucket.name for bucket in buckets]
            logger.info(f"找到 {len(bucket_names)} 个存储桶: {bucket_names}")
            return bucket_names
        except S3Error as e:
            logger.error(f"列出存储桶失败: {e}")
            raise
    
    def list_objects(self, bucket_name: str = None, prefix: str = "", 
                     recursive: bool = True) -> Generator[Tuple[str, object], None, None]:
        """
        遍历存储桶中的对象
        
        Args:
            bucket_name: 存储桶名称，如果为None则使用默认存储桶
            prefix: 对象前缀过滤
            recursive: 是否递归遍历子目录
            
        Yields:
            Tuple[str, object]: (object_name, object_info)
        """
        bucket = bucket_name or self.bucket_name
        if not bucket:
            raise ValueError("必须指定bucket_name或在初始化时设置默认bucket_name")
        
        try:
            logger.info(f"开始遍历存储桶: {bucket}, 前缀: {prefix}")
            objects = self.client.list_objects(
                bucket,
                prefix=prefix,
                recursive=recursive
            )
            
            count = 0
            for obj in objects:
                # 只处理图片文件
                if self._is_image_file(obj.object_name):
                    yield obj.object_name, obj
                    count += 1
                    
                    if count % 100 == 0:
                        logger.info(f"已遍历 {count} 个图片文件...")
            
            logger.info(f"遍历完成，共找到 {count} 个图片文件")
            
        except S3Error as e:
            logger.error(f"遍历对象失败: {e}")
            raise
    
    def get_object_data(self, bucket_name: str, object_name: str) -> bytes:
        """
        获取对象数据
        
        Args:
            bucket_name: 存储桶名称
            object_name: 对象名称
            
        Returns:
            bytes: 对象数据
        """
        try:
            response = self.client.get_object(bucket_name, object_name)
            data = response.read()
            response.close()
            response.release_conn()
            return data
        except S3Error as e:
            logger.error(f"获取对象数据失败 [{bucket_name}/{object_name}]: {e}")
            raise
    
    def get_object_stat(self, bucket_name: str, object_name: str) -> object:
        """
        获取对象统计信息
        
        Args:
            bucket_name: 存储桶名称
            object_name: 对象名称
            
        Returns:
            object: 对象统计信息
        """
        try:
            return self.client.stat_object(bucket_name, object_name)
        except S3Error as e:
            logger.error(f"获取对象统计信息失败 [{bucket_name}/{object_name}]: {e}")
            raise
    
    @staticmethod
    def _is_image_file(object_name: str) -> bool:
        """
        判断是否为图片文件
        
        Args:
            object_name: 对象名称
            
        Returns:
            bool: 是否为图片文件
        """
        image_extensions = {
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', 
            '.tiff', '.tif', '.svg', '.ico'
        }
        
        # 获取文件扩展名（转小写）
        ext = '.' + object_name.rsplit('.', 1)[-1].lower() if '.' in object_name else ''
        return ext in image_extensions
    
    def check_bucket_exists(self, bucket_name: str = None) -> bool:
        """
        检查存储桶是否存在
        
        Args:
            bucket_name: 存储桶名称
            
        Returns:
            bool: 存储桶是否存在
        """
        bucket = bucket_name or self.bucket_name
        if not bucket:
            raise ValueError("必须指定bucket_name")
        
        try:
            return self.client.bucket_exists(bucket)
        except S3Error as e:
            logger.error(f"检查存储桶存在性失败: {e}")
            return False
    
    def set_object_blocked(self, bucket_name: str, object_name: str, is_blocked: bool = True):
        """
        设置对象为blocked状态（通过标签标记 + Bucket Policy）
        
        注意: MinIO不支持直接设置单个对象的ACL
        实现方式:
        1. 给对象添加标签 blocked=true
        2. 需要配合 Bucket Policy 才能真正阻止访问
        
        Args:
            bucket_name: 存储桶名称
            object_name: 对象名称
            is_blocked: 是否标记为blocked（True=违规，False=正常）
        """
        try:
            from minio.datatypes import ObjectTags
            
            if is_blocked:
                # 设置为违规状态，添加标签
                tags = ObjectTags()
                tags["status"] = "violation"
                tags["blocked"] = "true"
                self.client.set_object_tags(bucket_name, object_name, tags)
                logger.info(f"✅ 已标记对象为blocked: {bucket_name}/{object_name}")
                logger.warning("⚠️ 注意: 仅设置标签不会阻止访问，需要配置Bucket Policy")
            else:
                # 恢复为正常状态，清除标签
                self.client.delete_object_tags(bucket_name, object_name)
                logger.info(f"✅ 已清除对象blocked标记: {bucket_name}/{object_name}")
                
        except Exception as e:
            logger.error(f"设置对象blocked状态失败 [{bucket_name}/{object_name}]: {e}")
            raise
    
    def set_bucket_policy_block_tagged_objects(self, bucket_name: str):
        """
        设置 Bucket Policy，拒绝访问带有 blocked=true 标签的对象
        
        这样当对象被标记为 blocked 后，将无法通过公开 URL 访问
        
        Args:
            bucket_name: 存储桶名称
        """
        try:
            import json
            
            # 创建 Bucket Policy，拒绝访问带 blocked=true 标签的对象
            policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Deny",
                        "Principal": {"AWS": ["*"]},
                        "Action": ["s3:GetObject"],
                        "Resource": [f"arn:aws:s3:::{bucket_name}/*"],
                        "Condition": {
                            "StringEquals": {
                                "s3:ExistingObjectTag/blocked": "true"
                            }
                        }
                    }
                ]
            }
            
            policy_json = json.dumps(policy)
            self.client.set_bucket_policy(bucket_name, policy_json)
            logger.info(f"✅ 已设置 Bucket Policy，拒绝访问带 blocked 标签的对象: {bucket_name}")
            
        except Exception as e:
            logger.error(f"设置 Bucket Policy 失败 [{bucket_name}]: {e}")
            raise
    
    def remove_bucket_policy(self, bucket_name: str):
        """
        移除 Bucket Policy
        
        Args:
            bucket_name: 存储桶名称
        """
        try:
            self.client.delete_bucket_policy(bucket_name)
            logger.info(f"✅ 已移除 Bucket Policy: {bucket_name}")
        except Exception as e:
            logger.error(f"移除 Bucket Policy 失败 [{bucket_name}]: {e}")
            raise
    
    def get_object_acl(self, bucket_name: str, object_name: str) -> dict:
        """
        获取对象访问权限状态
        
        Args:
            bucket_name: 存储桶名称
            object_name: 对象名称
            
        Returns:
            dict: 包含权限状态的字典
        """
        try:
            tags = self.client.get_object_tags(bucket_name, object_name)
            is_blocked = tags.get("blocked", "false") == "true"
            status = tags.get("status", "normal")
            
            return {
                "is_blocked": is_blocked,
                "status": status,
                "tags": dict(tags)
            }
        except S3Error as e:
            # 如果没有标签，说明是正常对象
            if "NoSuchTagSet" in str(e):
                return {
                    "is_blocked": False,
                    "status": "normal",
                    "tags": {}
                }
            logger.error(f"获取对象权限失败 [{bucket_name}/{object_name}]: {e}")
            raise
    
    def remove_object(self, bucket_name: str, object_name: str):
        """
        删除对象
        
        Args:
            bucket_name: 存储桶名称
            object_name: 对象名称
        """
        try:
            self.client.remove_object(bucket_name, object_name)
            logger.debug(f"已删除对象: {bucket_name}/{object_name}")
        except S3Error as e:
            logger.error(f"删除对象失败 [{bucket_name}/{object_name}]: {e}")
            raise
    
    def upload_object(self, bucket_name: str, object_name: str, data: bytes, content_type: str = None):
        """
        上传对象
        
        Args:
            bucket_name: 存储桶名称
            object_name: 对象名称
            data: 对象数据
            content_type: MIME类型
        """
        from io import BytesIO
        try:
            self.client.put_object(
                bucket_name,
                object_name,
                BytesIO(data),
                length=len(data),
                content_type=content_type or 'application/octet-stream'
            )
            logger.debug(f"已上传对象: {bucket_name}/{object_name}")
        except S3Error as e:
            logger.error(f"上传对象失败 [{bucket_name}/{object_name}]: {e}")
            raise
