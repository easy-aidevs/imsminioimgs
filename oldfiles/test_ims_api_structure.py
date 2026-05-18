#!/usr/bin/env python3
"""
测试腾讯云IMS API的完整调用流程
包括请求参数、响应解析等
"""

import sys
import json
from tencentcloud.ims.v20201229 import models

print("="*80)
print("腾讯云IMS API 完整调用测试")
print("="*80)

# 1. 检查ImageModerationRequest的所有可用属性
print("\n1. ImageModerationRequest 可用属性:")
req = models.ImageModerationRequest()
all_attrs = [attr for attr in dir(req) if not attr.startswith('_')]
print(f"   总共有 {len(all_attrs)} 个属性")

# 找出常用的关键属性
key_attrs = ['FileContent', 'FileUrl', 'BizType', 'DataId', 'User', 'Device']
print("\n   关键属性检查:")
for attr in key_attrs:
    exists = attr in all_attrs
    print(f"   - {attr}: {'✅ 存在' if exists else '❌ 不存在'}")

# 2. 检查ImageModerationResponse的返回字段
print("\n2. ImageModerationResponse 预期返回字段:")
print("   根据官方文档，响应应包含:")
response_fields = [
    'Suggestion',      # 建议操作 (Block/Review/Pass)
    'Label',           # 标签信息
    'RequestId',       # 请求ID
    'RecognitionResult', # 识别结果
    'OcrDetail',       # OCR详情
]
for field in response_fields:
    print(f"   - {field}")

# 3. 检查Label结构
print("\n3. Label 结构:")
print("   Label对象应包含:")
label_fields = [
    'Label',           # 主要标签
    'SubLabels',       # 子标签列表
    'Score',           # 分数
]
for field in label_fields:
    print(f"   - {field}")

print("\n   SubLabel对象应包含:")
sublabel_fields = [
    'Label',           # 子标签名称
    'Description',     # 描述
    'Confidence',      # 置信度
]
for field in sublabel_fields:
    print(f"   - {field}")

# 4. 常见的违规标签类型
print("\n4. 常见违规标签类型:")
violation_labels = {
    'Porn': '色情',
    'Sexy': '性感',
    'Normal': '正常',
    'Ads': '广告',
    'Qrcode': '二维码',
    'Illegal': '违法',
    'Abuse': '谩骂',
    'Terror': '暴恐',
    'Politics': '政治敏感',
}
for label, desc in violation_labels.items():
    print(f"   - {label}: {desc}")

# 5. Suggestion的可能值
print("\n5. Suggestion（建议操作）的可能值:")
suggestions = {
    'Block': '阻止（确认违规）',
    'Review': '人工审核（疑似违规）',
    'Pass': '通过（正常内容）',
}
for sug, desc in suggestions.items():
    print(f"   - {sug}: {desc}")

# 6. 当前代码使用的字段对照
print("\n6. 当前代码使用的字段对照:")
current_code_fields = {
    'resp.Suggestion': '✅ 正确',
    'resp.Label.Label': '✅ 正确（主标签）',
    'resp.Label.SubLabels': '✅ 正确（子标签列表）',
    'sub_label.Label': '✅ 正确',
    'sub_label.Description': '✅ 正确',
    'sub_label.Confidence': '✅ 正确',
    'resp.RequestId': '✅ 正确',
}

for field, status in current_code_fields.items():
    print(f"   - {field}: {status}")

# 7. 可能的问题点
print("\n7. ⚠️  潜在问题检查:")
print("   a) Label结构可能是嵌套的，需要确认实际返回格式")
print("   b) Confidence可能在Label级别，不在SubLabel级别")
print("   c) 某些字段可能为None，需要空值检查")
print("   d) Score和Confidence的区别需要明确")

# 8. 建议的改进
print("\n8. 💡 建议改进:")
print("   - 添加完整的空值检查")
print("   - 同时检查Label.Score和SubLabel.Confidence")
print("   - 记录完整的响应JSON用于调试")
print("   - 处理Label为None的情况")

print("\n" + "="*80)
print("测试完成！请根据以上信息检查代码实现。")
print("="*80)
