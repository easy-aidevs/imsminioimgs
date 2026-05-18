"""
测试脚本 - 验证各个模块功能
"""

import sys
from loguru import logger

# 配置日志
logger.remove()
logger.add(sys.stderr, level="INFO")


def test_imports():
    """测试所有模块是否可以正常导入"""
    logger.info("测试模块导入...")
    
    try:
        from minio_client import MinIOClient
        logger.success("✓ MinIO客户端模块导入成功")
    except Exception as e:
        logger.error(f"✗ MinIO客户端模块导入失败: {e}")
        return False
    
    try:
        from image_feature import ImageFeatureExtractor
        logger.success("✓ 图片特征提取模块导入成功")
    except Exception as e:
        logger.error(f"✗ 图片特征提取模块导入失败: {e}")
        return False
    
    try:
        from tencent_ims import TencentIMSScanner
        logger.success("✓ 腾讯云IMS模块导入成功")
    except Exception as e:
        logger.error(f"✗ 腾讯云IMS模块导入失败: {e}")
        return False
    
    try:
        from database import ImageDatabase
        logger.success("✓ 数据库模块导入成功")
    except Exception as e:
        logger.error(f"✗ 数据库模块导入失败: {e}")
        return False
    
    try:
        from scanner import ImageSecurityScanner, load_config
        logger.success("✓ 主扫描器模块导入成功")
    except Exception as e:
        logger.error(f"✗ 主扫描器模块导入失败: {e}")
        return False
    
    return True


def test_image_feature():
    """测试图片特征提取功能"""
    logger.info("\n测试图片特征提取...")
    
    try:
        from image_feature import ImageFeatureExtractor
        from PIL import Image
        import io
        
        # 创建一个测试图片
        img = Image.new('RGB', (100, 100), color='red')
        buffer = io.BytesIO()
        img.save(buffer, format='JPEG')
        image_data = buffer.getvalue()
        
        # 测试特征提取
        extractor = ImageFeatureExtractor()
        features = extractor.extract_features(image_data)
        
        logger.success(f"✓ 特征提取成功")
        logger.info(f"  - pHash: {features['phash']}")
        logger.info(f"  - dHash: {features['dhash']}")
        logger.info(f"  - aHash: {features['ahash']}")
        
        # 测试Key计算
        key = extractor.calculate_key(image_data)
        logger.success(f"✓ Key计算成功: {key[:50]}...")
        
        # 测试相似度计算
        distance = extractor.calculate_hash_distance(features['phash'], features['phash'])
        logger.success(f"✓ 哈希距离计算成功: {distance} (相同图片应为0)")
        
        similarity = extractor.get_similarity_score(features['phash'], features['phash'])
        logger.success(f"✓ 相似度计算成功: {similarity} (相同图片应为1.0)")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ 图片特征提取测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_config_loading():
    """测试配置文件加载"""
    logger.info("\n测试配置加载...")
    
    try:
        from scanner import load_config
        import os
        
        # 检查是否有.env文件
        if not os.path.exists('.env'):
            logger.warning("⚠ .env文件不存在，使用默认配置")
            logger.warning("  请复制.env.example为.env并填写配置")
            return True
        
        config = load_config()
        logger.success("✓ 配置加载成功")
        
        # 检查必要字段
        required = [
            ('minio.endpoint', config['minio']['endpoint']),
            ('minio.bucket_name', config['minio']['bucket_name']),
            ('tencent.secret_id', config['tencent']['secret_id']),
            ('mysql.host', config['mysql']['host']),
        ]
        
        missing = [name for name, value in required if not value or 'your_' in value]
        if missing:
            logger.warning(f"⚠ 以下配置项未设置: {', '.join(missing)}")
            logger.warning("  请在.env文件中填写实际值")
        else:
            logger.success("✓ 所有必要配置项已设置")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ 配置加载测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_database_schema():
    """测试数据库表结构文件"""
    logger.info("\n测试数据库Schema...")
    
    try:
        import os
        
        if not os.path.exists('schema.sql'):
            logger.error("✗ schema.sql文件不存在")
            return False
        
        with open('schema.sql', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 检查是否包含必要的表
        tables = ['image_scan_records', 'similar_images', 'scan_statistics']
        for table in tables:
            if table in content:
                logger.success(f"✓ 表 {table} 定义存在")
            else:
                logger.error(f"✗ 表 {table} 定义缺失")
                return False
        
        logger.success("✓ 数据库Schema文件完整")
        return True
        
    except Exception as e:
        logger.error(f"✗ 数据库Schema测试失败: {e}")
        return False


def main():
    """运行所有测试"""
    logger.info("=" * 60)
    logger.info("开始系统测试")
    logger.info("=" * 60)
    
    results = []
    
    # 测试1: 模块导入
    results.append(("模块导入", test_imports()))
    
    # 测试2: 图片特征提取
    results.append(("图片特征提取", test_image_feature()))
    
    # 测试3: 配置加载
    results.append(("配置加载", test_config_loading()))
    
    # 测试4: 数据库Schema
    results.append(("数据库Schema", test_database_schema()))
    
    # 输出测试结果
    logger.info("\n" + "=" * 60)
    logger.info("测试结果汇总")
    logger.info("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        logger.info(f"{name:20s} {status}")
    
    logger.info("=" * 60)
    logger.info(f"总计: {passed}/{total} 测试通过")
    
    if passed == total:
        logger.success("\n🎉 所有测试通过！系统可以正常使用。")
        logger.info("\n下一步:")
        logger.info("1. 编辑.env文件填写实际配置")
        logger.info("2. 执行: mysql -u root -p < schema.sql")
        logger.info("3. 运行: python scanner.py 或 ./run.sh")
        return 0
    else:
        logger.error(f"\n⚠ {total - passed} 个测试失败，请检查错误信息")
        return 1


if __name__ == "__main__":
    sys.exit(main())
