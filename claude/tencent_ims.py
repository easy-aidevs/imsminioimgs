"""
腾讯云IMS（图片内容安全）API调用模块
用于检测图片是否包含违规内容
"""

from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.ims.v20201229 import ims_client, models
import json
from typing import Dict, Optional
from loguru import logger


class TencentIMSScanner:
    """腾讯云图片内容安全扫描器"""
    
    # 违规类型映射
    VIOLATION_TYPE_MAP = {
        'Porn': 'porn',           # 色情
        'Gambling': 'gambling',    # 赌博/棋牌
        'Violence': 'violence',    # 暴力
        'Politics': 'politics',    # 政治敏感
        'Ads': 'ads',              # 广告
        'Terrorism': 'terrorism',  # 恐怖主义
        'Contraband': 'contraband', # 违禁品
        'Vulgar': 'vulgar',        # 低俗
        'Qrcode': 'qrcode',        # 二维码
        'Others': 'other'          # 其他
    }
    
    def __init__(self, secret_id: str, secret_key: str, region: str = "ap-guangzhou"):
        """
        初始化腾讯云IMS客户端
        
        Args:
            secret_id: 腾讯云SecretId
            secret_key: 腾讯云SecretKey
            region: 地域，默认广州
        """
        self.cred = credential.Credential(secret_id, secret_key)
        
        # HTTP配置
        httpProfile = HttpProfile()
        httpProfile.endpoint = "ims.tencentcloudapi.com"
        
        # 客户端配置
        clientProfile = ClientProfile()
        clientProfile.httpProfile = httpProfile
        
        # 创建IMS客户端
        self.client = ims_client.ImsClient(self.cred, region, clientProfile)
        
        logger.info(f"腾讯云IMS客户端初始化成功，区域: {region}")
    
    def scan_image(self, image_data: bytes, biz_type: str = None) -> Dict:
        """
        扫描图片内容
        
        Args:
            image_data: 图片二进制数据
            biz_type: 业务场景标识，可用于区分不同业务
            
        Returns:
            Dict: 扫描结果，包含以下字段：
                - is_violation: 是否违规 (bool)
                - violation_type: 违规类型 (str)
                - violation_label: 违规标签 (str)
                - violation_description: 违规描述 (str)
                - confidence: 置信度 (float, 0-1)
                - suggestion: 建议操作 (str: Block/Review/Pass)
                - raw_result: 原始返回结果 (dict)
                - request_id: 请求ID (str)
        """
        try:
            import base64
            
            # 创建请求对象
            req = models.ImageModerationRequest()
            
            # 设置参数 - 使用Base64编码图片数据
            image_base64 = base64.b64encode(image_data).decode('utf-8')
            
            # 重要：SDK中的属性名是 FileContent，不是 Content！
            # 直接赋值属性（避免from_json_string产生null值）
            req.FileContent = image_base64  # ✅ 正确的属性名
            req.BizType = biz_type or "default"
            
            logger.debug(f"准备调用IMS API - 图片大小: {len(image_data)} bytes, Base64长度: {len(image_base64)}")
            
            # 调用API
            resp = self.client.ImageModeration(req)
            
            # 解析结果
            result = self._parse_response(resp)
            
            logger.debug(
                f"图片扫描完成 - 违规: {result['is_violation']}, "
                f"类型: {result['violation_type']}, "
                f"置信度: {result['confidence']}"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 腾讯云IMS扫描失败")
            logger.error(f"  - 错误类型: {type(e).__name__}")
            logger.error(f"  - 错误信息: {str(e)}")
            logger.error(f"  - 图片数据大小: {len(image_data) if 'image_data' in locals() else 'N/A'} bytes")
            if hasattr(e, 'code'):
                logger.error(f"  - API错误码: {e.code}")
            if hasattr(e, 'message'):
                logger.error(f"  - API错误消息: {e.message}")
            if hasattr(e, 'requestId'):
                logger.error(f"  - RequestID: {e.requestId}")
            logger.exception("详细堆栈信息:")
            raise
    
    def _parse_response(self, resp) -> Dict:
        """
        解析腾讯云IMS响应
        
        Args:
            resp: IMS API响应对象
            
        Returns:
            Dict: 解析后的结果
        """
        result = {
            'is_violation': False,
            'violation_type': None,
            'violation_label': None,
            'violation_description': None,
            'confidence': 0.0,
            'suggestion': 'Pass',
            'raw_result': {},
            'request_id': resp.RequestId if hasattr(resp, 'RequestId') else None
        }
        
        try:
            # 获取建议操作
            if hasattr(resp, 'Suggestion'):
                result['suggestion'] = resp.Suggestion

            # 判断是否违规
            if result['suggestion'] in ['Block', 'Review']:
                result['is_violation'] = True

            # resp.Label 是字符串（如 "Porn"），"Normal" 表示正常，不写入违规字段
            if hasattr(resp, 'Label') and resp.Label and resp.Label != 'Normal':
                result['violation_label'] = resp.Label
                result['violation_type'] = self.VIOLATION_TYPE_MAP.get(resp.Label, 'other')

            # 子标签作为描述（仅违规时有意义）
            if hasattr(resp, 'SubLabel') and resp.SubLabel:
                result['violation_description'] = resp.SubLabel

            # Score 是 0-100 整数，归一化到 0-1；仅违规时存置信度
            if result['is_violation'] and hasattr(resp, 'Score') and resp.Score is not None:
                result['confidence'] = resp.Score / 100.0

            # 保存原始结果
            result['raw_result'] = json.loads(resp.to_json_string())
            
        except Exception as e:
            logger.error(f"解析IMS响应失败: {e}")
            result['violation_description'] = f"解析错误: {str(e)}"
        
        return result
    
    def scan_image_batch(self, images: list, biz_type: str = None) -> list:
        """
        批量扫描图片（逐个调用API）
        
        Args:
            images: 图片数据列表 [(image_data, extra_info), ...]
            biz_type: 业务场景标识
            
        Returns:
            list: 扫描结果列表
        """
        results = []
        total = len(images)
        
        for idx, (image_data, extra_info) in enumerate(images, 1):
            try:
                logger.info(f"扫描进度: {idx}/{total}")
                result = self.scan_image(image_data, biz_type)
                result['extra_info'] = extra_info
                results.append(result)
            except Exception as e:
                logger.error(f"扫描第{idx}张图片失败: {e}")
                results.append({
                    'is_violation': False,
                    'error': str(e),
                    'extra_info': extra_info
                })
        
        return results
