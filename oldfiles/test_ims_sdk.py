#!/usr/bin/env python3
"""
测试腾讯云IMS SDK调用逻辑
验证参数设置和序列化是否正确
"""

import sys
import os
import json
import base64

print("="*80)
print("腾讯云IMS SDK 调用逻辑测试")
print("="*80)

# 1. 检查SDK是否安装
print("\n1. 检查SDK安装...")
try:
    from tencentcloud.ims.v20201229 import ims_client, models
    print("   ✓ IMS模块导入成功")
except ImportError as e:
    print(f"   ❌ SDK未安装: {e}")
    print("\n请先安装依赖:")
    print("   pip install -r requirements.txt")
    sys.exit(1)

# 2. 创建请求对象
print("\n2. 创建ImageModerationRequest对象...")
try:
    req = models.ImageModerationRequest()
    print("   ✓ 请求对象创建成功")
except Exception as e:
    print(f"   ❌ 创建失败: {e}")
    sys.exit(1)

# 3. 准备测试数据
print("\n3. 准备测试图片数据...")
test_image_data = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100  # 模拟PNG文件头
image_base64 = base64.b64encode(test_image_data).decode('utf-8')
print(f"   ✓ 测试图片大小: {len(test_image_data)} bytes")
print(f"   ✓ Base64长度: {len(image_base64)} chars")

# 4. 测试方案1: 直接赋值属性
print("\n4. 测试方案1: 直接赋值属性 (req.Content = ...)")
try:
    req1 = models.ImageModerationRequest()
    req1.Content = image_base64
    req1.BizType = "default"
    
    json_str = req1.to_json_string()
    json_obj = json.loads(json_str)
    
    print(f"   ✓ 序列化成功")
    print(f"   JSON字段: {list(json_obj.keys())}")
    
    if 'Content' in json_obj:
        print("   ✓ Content字段存在")
    else:
        print("   ❌ Content字段缺失")
        
    if 'Ontent' in json_obj:
        print("   ❌ 发现Bug: Ontent字段（应该是Content）")
    else:
        print("   ✓ 没有Ontent错误字段")
        
    # 检查是否有null值
    null_fields = [k for k, v in json_obj.items() if v is None]
    if null_fields:
        print(f"   ⚠️  发现null字段: {null_fields}")
    else:
        print("   ✓ 没有null字段")
        
except Exception as e:
    print(f"   ❌ 测试失败: {e}")
    import traceback
    traceback.print_exc()

# 5. 测试方案2: from_json_string
print("\n5. 测试方案2: from_json_string")
try:
    req2 = models.ImageModerationRequest()
    params_dict = {
        "Content": image_base64,
        "BizType": "default"
    }
    req2.from_json_string(json.dumps(params_dict))
    
    json_str = req2.to_json_string()
    json_obj = json.loads(json_str)
    
    print(f"   ✓ 序列化成功")
    print(f"   JSON字段: {list(json_obj.keys())}")
    
    if 'Content' in json_obj:
        print("   ✓ Content字段存在")
    else:
        print("   ❌ Content字段缺失")
        
    if 'Ontent' in json_obj:
        print("   ❌ 发现Bug: Ontent字段（应该是Content）")
    else:
        print("   ✓ 没有Ontent错误字段")
        
    # 检查是否有null值
    null_fields = [k for k, v in json_obj.items() if v is None]
    if null_fields:
        print(f"   ⚠️  发现null字段 ({len(null_fields)}个): {null_fields[:5]}...")
    else:
        print("   ✓ 没有null字段")
        
except Exception as e:
    print(f"   ❌ 测试失败: {e}")
    import traceback
    traceback.print_exc()

# 6. 总结
print("\n" + "="*80)
print("测试结果总结")
print("="*80)
print("\n请查看上面的测试结果，重点关注:")
print("  1. Content字段是否存在")
print("  2. 是否有Ontent错误字段")
print("  3. 是否有大量null字段")
print("\n根据结果选择正确的调用方式。")
