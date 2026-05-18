#!/usr/bin/env python3
"""
测试腾讯云IMS API调用
用于验证SDK配置和API调用是否正确
"""

import os
import sys
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

from tencent_ims import TencentIMSScanner

def test_ims_api():
    """测试IMS API调用"""
    
    print("="*80)
    print("腾讯云IMS API测试")
    print("="*80)
    
    # 检查环境变量
    secret_id = os.getenv('TENCENT_SECRET_ID')
    secret_key = os.getenv('TENCENT_SECRET_KEY')
    
    if not secret_id or not secret_key:
        print("❌ 错误: 未找到腾讯云密钥")
        print("请设置环境变量:")
        print("  export TENCENT_SECRET_ID=your_secret_id")
        print("  export TENCENT_SECRET_KEY=your_secret_key")
        return False
    
    print(f"✓ SecretId: {secret_id[:10]}...")
    print(f"✓ SecretKey: {secret_key[:10]}...")
    
    # 创建扫描器
    try:
        scanner = TencentIMSScanner(
            secret_id=secret_id,
            secret_key=secret_key,
            region=os.getenv('TENCENT_REGION', 'ap-guangzhou')
        )
        print("✓ IMS客户端创建成功")
    except Exception as e:
        print(f"❌ IMS客户端创建失败: {e}")
        return False
    
    # 测试图片（一个小的PNG图片 - 1x1像素）
    test_image = bytes([
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG header
        0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk
        0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,  # 1x1 pixel
        0x08, 0x02, 0x00, 0x00, 0x00, 0x90, 0x77, 0x53,
        0xDE, 0x00, 0x00, 0x00, 0x0C, 0x49, 0x44, 0x41,
        0x54, 0x08, 0xD7, 0x63, 0xF8, 0xCF, 0xC0, 0x00,
        0x00, 0x03, 0x01, 0x01, 0x00, 0x18, 0xDD, 0x8D,
        0xB4, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4E,
        0x44, 0xAE, 0x42, 0x60, 0x82  # IEND chunk
    ])
    
    print(f"\n测试图片大小: {len(test_image)} bytes")
    print("开始调用腾讯云IMS API...\n")
    
    try:
        result = scanner.scan_image(test_image)
        
        print("="*80)
        print("✓ API调用成功！")
        print("="*80)
        print(f"是否违规: {result['is_violation']}")
        print(f"违规类型: {result.get('violation_type', 'N/A')}")
        print(f"置信度: {result.get('confidence', 'N/A')}")
        print(f"建议操作: {result.get('suggestion', 'N/A')}")
        print(f"RequestID: {result.get('request_id', 'N/A')}")
        print("="*80)
        
        return True
        
    except Exception as e:
        print("="*80)
        print(f"❌ API调用失败")
        print("="*80)
        print(f"错误类型: {type(e).__name__}")
        print(f"错误信息: {str(e)}")
        print("="*80)
        return False

if __name__ == "__main__":
    success = test_ims_api()
    sys.exit(0 if success else 1)
