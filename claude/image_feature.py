"""
图片特征计算模块
使用感知哈希算法计算图片特征码，用于识别相似图片
"""

import hashlib
import io
from typing import Dict

from PIL import Image
import imagehash
from loguru import logger


class ImageFeatureExtractor:
    """图片特征提取器"""
    
    def __init__(self, hash_size: int = 8):
        """
        初始化特征提取器
        
        Args:
            hash_size: 哈希大小，默认8（生成8x8=64位哈希）
        """
        self.hash_size = hash_size
        logger.info(f"图片特征提取器初始化成功，hash_size={hash_size}")
    
    def calculate_key(self, image_data: bytes) -> str:
        """
        计算图片的唯一标识key
        key = md5(图片文件内容) + "-" + 图片字节长度
        
        Args:
            image_data: 图片二进制数据
            
        Returns:
            str: 图片唯一标识
        """
        md5_hash = hashlib.md5(image_data).hexdigest()
        file_size = len(image_data)
        key = f"{md5_hash}-{file_size}"
        return key
    
    def extract_features(self, image_data: bytes) -> Dict[str, str]:
        """
        提取图片的多种哈希特征

        Args:
            image_data: 图片二进制数据

        Returns:
            Dict[str, str]: 包含多种哈希特征的字典
                - phash: 感知哈希 (Perceptual Hash) - 主特征
                - dhash: 差异哈希 (Difference Hash)
                - ahash: 平均哈希 (Average Hash)
        """
        try:
            # 将二进制数据转换为PIL Image对象
            image = Image.open(io.BytesIO(image_data))
            
            # 转换为RGB模式（处理RGBA、灰度图等）
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            features = {}
            
            # 1. 感知哈希 (pHash) - 对缩放、亮度变化鲁棒
            phash = imagehash.phash(image, hash_size=self.hash_size)
            features['phash'] = str(phash)
            
            # 2. 差异哈希 (dHash) - 对梯度变化敏感
            dhash = imagehash.dhash(image, hash_size=self.hash_size)
            features['dhash'] = str(dhash)
            
            # 3. 平均哈希 (aHash) - 简单快速
            ahash = imagehash.average_hash(image, hash_size=self.hash_size)
            features['ahash'] = str(ahash)

            # 综合特征：使用phash作为主要特征（phash对缩放和亮度变化最鲁棒）
            features['feature_hash'] = features['phash']
            
            logger.debug(f"图片特征提取成功: phash={features['phash']}")
            return features
            
        except Exception as e:
            logger.error(f"图片特征提取失败: {e}")
            raise
    
    @staticmethod
    def calculate_hash_distance(hash1: str, hash2: str) -> int:
        """
        计算两个哈希值之间的距离（汉明距离）
        
        Args:
            hash1: 哈希字符串1
            hash2: 哈希字符串2
            
        Returns:
            int: 汉明距离，越小表示越相似
        """
        try:
            # 将十六进制字符串转换为整数
            int_hash1 = int(hash1, 16)
            int_hash2 = int(hash2, 16)
            
            # 计算异或后统计1的个数
            xor = int_hash1 ^ int_hash2
            distance = bin(xor).count('1')
            
            return distance
        except Exception as e:
            logger.error(f"计算哈希距离失败: {e}")
            return -1
    
    @staticmethod
    def is_similar(hash1: str, hash2: str, threshold: int = 5) -> bool:
        """
        判断两张图片是否相似
        
        Args:
            hash1: 哈希字符串1
            hash2: 哈希字符串2
            threshold: 相似度阈值，汉明距离小于此值认为相似
                      通常: 0-5非常相似, 5-10相似, >10不相似
            
        Returns:
            bool: 是否相似
        """
        distance = ImageFeatureExtractor.calculate_hash_distance(hash1, hash2)
        return distance >= 0 and distance <= threshold
    
    def get_similarity_score(self, hash1: str, hash2: str) -> float:
        """
        计算两张图片的相似度分数
        
        Args:
            hash1: 哈希字符串1
            hash2: 哈希字符串2
            
        Returns:
            float: 相似度分数 0.0-1.0，1.0表示完全相同
        """
        distance = self.calculate_hash_distance(hash1, hash2)
        if distance < 0:
            return 0.0
        
        # 哈希总位数
        total_bits = self.hash_size * self.hash_size
        
        # 相似度 = 1 - (汉明距离 / 总位数)
        similarity = 1.0 - (distance / total_bits)
        
        return max(0.0, min(1.0, similarity))
