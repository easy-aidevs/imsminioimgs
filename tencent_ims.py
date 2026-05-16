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
            # 创建请求对象
            req = models.ImageModerationRequest()
            
            # 设置参数
            params = {
                "Content": image_data.hex(),  # 图片Base64编码的十六进制字符串
                "DataEndpoint": "",
                "BizType": biz_type or "default"
            }
            req.from_json_string(json.dumps(params))
            
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
            logger.error(f"腾讯云IMS扫描失败: {e}")
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
            
            # 解析标签信息
            if hasattr(resp, 'Label') and resp.Label:
                label_info = resp.Label
                
                # 主要标签
                if hasattr(label_info, 'Label'):
                    main_label = label_info.Label
                    result['violation_label'] = main_label
                    
                    # 映射违规类型
                    if main_label in self.VIOLATION_TYPE_MAP:
                        result['violation_type'] = self.VIOLATION_TYPE_MAP[main_label]
                    else:
                        result['violation_type'] = 'other'
                
                # 子标签详情
                if hasattr(label_info, 'SubLabels') and label_info.SubLabels:
                    sub_labels = []
                    descriptions = []
                    max_confidence = 0.0
                    
                    for sub_label in label_info.SubLabels:
                        if hasattr(sub_label, 'Label'):
                            sub_labels.append(sub_label.Label)
                        
                        if hasattr(sub_label, 'Description'):
                            descriptions.append(sub_label.Description)
                        
                        # 获取最高置信度
                        if hasattr(sub_label, 'Confidence'):
                            max_confidence = max(max_confidence, sub_label.Confidence)
                    
                    if sub_labels:
                        result['violation_label'] = ','.join(sub_labels)
                    
                    if descriptions:
                        result['violation_description'] = '; '.join(descriptions)
                    
                    result['confidence'] = max_confidence
            
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
