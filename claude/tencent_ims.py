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
    
    LABEL_CN_MAP = {
        'Polity': '政治',
        'Porn': '色情',
        'Sexy': '性感',
        'Terror': '暴恐',
        'Illegal': '违法',
        'Religion': '宗教识别',
        'Ad': '广告',
        'Teenager': '未成年识别',
        'Abuse': '谩骂',
        'Normal': '正常',
    }

    SUB_LABEL_CN_MAP = {
        # Polity 政治
        'NationalOfficial': '国部级领导人', 'NationalOfficialA': '正国级领导人',
        'ProvincialOfficial': '省级领导人', 'CountryOfficial': '市/县级领导人',
        'TWOfficial': '台湾地区领导人', 'HKOfficial': '香港特区领导人',
        'MacaoOfficial': '澳门特区领导人', 'MainlandIllegalOfficial': '落马官员',
        'MainlandOfficialRelative': '大陆地区领导人亲属', 'ForeignOfficial': '外国/地区政治人物',
        'BadStar': '劣迹明星', 'Inferior': '劣迹网红',
        'AntiParty': '反党人士', 'Splitter': '反动分裂分子',
        'NaziCriminal': '纳粹战犯', 'Martyrs': '革命烈士',
        'WarCriminal': '侵华战犯', 'HistoricalPerson': '历史人物',
        'Terrorist': '恐怖分子头目', 'Cult': '邪教组织头目',
        'AVStar': 'AV人物', 'PolityLogo': '政治实体-中性',
        'SensitivePolityLogo': '政治实体-负面', 'PolityEvent': '政治事件',
        'NanHaiZhuDao': '南海诸岛缺失', 'ZangNan': '藏南缺失',
        'AKeSaiQin': '阿克赛钦缺失', 'TaiWan': '台湾岛错误',
        'TianAnMen': '天安门', 'RMYXJiNianBei': '人民英雄纪念碑',
        'RenMinDaHuiTang': '人民大会堂', 'RenMinDaHuiTangInner': '人民大会堂内部',
        'HuaBiao': '华表', 'MinZhuNvShengXiang64': '64民主女神像',
        'LadyLibertyHK': '香港民主女神像', 'JingGuoShengShe': '靖国神社',
        'WeiLingTa': '慰灵塔', 'FengTianZhongLingTa': '奉天忠灵塔',
        'GuoShangZhiZhu': '国殇之柱', 'MinZhuLieShiBei': '民主烈士纪念碑',
        '64JiNianBei': '64纪念碑', 'GuoQiTouXiang': '头像国旗',
        'GuoQiYingXiao': '国旗营销', 'WuRuGuoQi': '侮辱国旗',
        'ZhengChangRMB': '正常人民币', 'DaLiangRMB': '大量人民币',
        'RMBXuanFu': '人民币炫富', 'RMBYingXiao': '人民币营销',
        'EGaoRMB': '恶搞人民币', 'FenShaoRMB': '焚烧人民币',
        'TuYaRMB': '涂鸦人民币', 'RMBStack': '人民币堆叠',
        'GuoHuiZhengShu': '含国徽证书', 'GuoHuiICKa': '含国徽卡证',
        'GuoHuiWenJian': '含国徽文件', 'EGaoGuoHui': '恶搞国徽',
        'CCPVirus': '中共病毒', 'JingGangShanA': '井冈山A', 'JingGangShanB': '井冈山B',
        'Polity': '一号领导人', 'WorldMap': '世界地图', 'LocalMap': '区域地图',
        'CountryHuman': '国家拟人', 'ChineseLeaderXiFeature': '一号领导特征影射',
        'ChineseLeaderMaoFeature': '国家领导特征影射', 'YingSheGuoQi': '影射国旗',
        '64Candle': '六四蜡烛影射', 'ChineseLeaderVariant': '一号变形',
        'ChineseLeaderHairStyle': '一号领导发型',
        'FeiGuanFangShiYongGuoHui': '非官方使用国徽',
        'FeiGuanFangShiYongGuoQi': '非官方使用国旗',
        'FeiGuanFangShiYongDiTu': '非官方使用地图',
        'FeiGuanFangShiYongDangQiDangHui': '非官方使用党旗党徽',
        'ZhengChangGuoQi': '正常国旗', 'ZhengChangGuoHui': '正常国徽',
        'COVID-19': '新冠相关政治',
        # Porn 色情
        'SexyBehavior': '性行为画面', 'SM': 'SM',
        'WomenPrivatePart': '女性下体裸露', 'WomenChest': '女性胸部裸露',
        'MenPrivatePart': '男性下体裸露', 'ButtocksExposed': '臀部裸露',
        'NakedChild': '儿童裸露', 'SexAids': '性用品',
        'NakedAnimal': '动物裸露', 'TouchChest': '摸胸',
        'TouchHip': '摸臀', 'TouchTriangle': '摸下体',
        'Tongue': '吐舌挑逗', 'Lick': '舔舐动作',
        'AnimalSex': '动物性行为', 'SexSecretion': '性分泌物',
        'Suckle': '哺乳', 'ObjectShape': '物体形似',
        'TongueKiss': '舌吻', 'WomenChestSideNaked': '侧乳露出',
        'Naked': '裸体', 'Anus': '肛门',
        'WomenChestBump': '女上激凸', 'WomenPrivatePartProtruding': '女下激凸',
        'Endoscope': '女性下体内窥镜', 'MedicalPorn': '医学性器官',
        'GridPorn': '图中图色情', 'ACGPregnancy': 'ACG色情孕妇',
        'IPPorn': 'IP色情', 'ACGPornNew': 'ACG色情2.0',
        # Sexy 性感
        'NakedArt': '裸露艺术品', 'WomenSexy': '女性性感着装',
        'MenSexy': '男性性感着装', 'WomenSexyBack': '女性性感-背部',
        'WomenSexyChest': '女性性感-胸部', 'WomenSexyLeg': '女性性感-腿部',
        'MiddleFinger': '竖中指', 'Kiss': '亲吻',
        'HipCloseUp': '臀部性感', 'ChestCloseUp': '胸部特写',
        'FootCloseUp': '足部性联想', 'VulgarLeg': '低俗腿部',
        'VulgarChest': '低俗胸部', 'IntimateBehavior': '亲密行为',
        'ShoulderBare': '性感肩', 'CrotchCloseUp': '男下激凸',
        'MenNudity': '男上裸露', 'SeductivePose': '诱惑姿势',
        'Stockings': '丝袜', 'LegCloseUp': '腿部特写',
        'VulgarGesture': '低俗手势',
        # Terror 暴恐
        'Burka': '特殊服饰', 'Uniform': '军警制服',
        'Gun': '枪等热武器', 'BigWeapon': '军事武器',
        'Knife': '刀等冷兵器', 'Crowd': '人群聚集',
        'Blood': '血腥画面', 'Bloody': '血腥画面',
        'Fire': '火灾爆炸', 'SpecialCharacter': '特殊文字',
        'ActsTerrorism': '暴恐行为', 'Horror': '惊悚',
        'TerroristOrganization': '恐怖组织', 'PoliceCar': '警车',
        'Bullet': '子弹',
        # Illegal 违法
        'Smoking': '吸烟', 'Drug': '吸毒',
        'Gambling': '赌博', 'Gamble': '赌博',
        'Drink': '喝酒', 'Fight': '打斗',
        'CarLive': '车内直播', 'BedLive': '床上直播',
        'Tattoo': '纹身', 'Contraband': '违禁品',
        'PersonalPrivacy': '个人隐私', 'Nausea': '恶心画面',
        'WithoutFace': '人脸空播', 'NoBody': '人体空播',
        'Weapon': '武器违禁品',
        # Religion 宗教
        'ReligiousClothing': '宗教服饰', 'ReligiousObjects': '宗教物品',
        'ReligiousElement': '宗教元素', 'ReligiousBehavior': '宗教行为',
        # Ad 广告
        'QrCode': '广告二维码', 'Qrcode': '广告二维码',
        'AppLogo': '互联网应用台标', 'MovieLogo': '电影台标',
        'CCTVLogo': '央视台标', 'LocalTVLogo': '地方卫视台标',
        'ForeignVideoAppLogo': '海外视频应用台标', 'OlympicsLogo': '奥运台标',
        'Phone': '手机', 'ForeignTVLogo': '海外电视台标',
        'SexProductLogo': '性用品Logo', 'AntiChinaLogo': '辱华品牌Logo',
        'AdvertisingLaw': '广告法', 'StateOwnedEnterpriseLogo': '国央企LOGO',
        'DeceptiveImage': '干扰图',
        # Teenager 未成年
        'Minors': '未成年人出镜', 'MinorsPorn': '未成年人色情',
        'MinorsSexy': '未成年人性感', 'MinorsIllegal': '未成年人违禁行为',
        'Elsagate': '儿童邪典', 'ACGMinors': 'ACG未成年人',
        'MinorsNew': '未成年形象',
        # Abuse 谩骂
        'PornographicAbuse': '色情谩骂', 'Abuse': '谩骂',
        # Others / generic
        'Others': '其他', 'Other': '其他',
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
                - violation_label: IMS一级标签英文code (str)
                - violation_label_cn: IMS一级标签中文名 (str)
                - sub_label: IMS二级标签英文code (str)
                - sub_label_cn: IMS二级标签中文名 (str)
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
            'violation_label_cn': None,
            'sub_label': None,
            'sub_label_cn': None,
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
            label = resp.Label if hasattr(resp, 'Label') else ''
            sub_label = resp.SubLabel if hasattr(resp, 'SubLabel') else ''
            if label and label != 'Normal':
                result['violation_label'] = label
                result['violation_label_cn'] = self.LABEL_CN_MAP.get(label)
                # violation_type 直接用 SubLabel；无 SubLabel 时退回用 Label
                result['violation_type'] = sub_label if sub_label else label
                if sub_label:
                    result['sub_label'] = sub_label
                    result['sub_label_cn'] = self.SUB_LABEL_CN_MAP.get(sub_label)

            # Score 是 0-100 整数，归一化到 0-1；仅违规时存置信度
            if result['is_violation'] and hasattr(resp, 'Score') and resp.Score is not None:
                result['confidence'] = resp.Score / 100.0

            # 保存原始结果
            result['raw_result'] = json.loads(resp.to_json_string())
            
        except Exception as e:
            logger.error(f"解析IMS响应失败: {e}")
        
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
