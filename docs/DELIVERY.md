# 图片内容安全扫描系统 - 项目交付说明

## 📦 项目概述

这是一个完整的Python图片内容安全检测系统，专门用于扫描MinIO存储中的图片，使用腾讯云IMS API识别违规内容（特别是棋牌类图片），并将结果存储到MySQL数据库。

## ✅ 已完成功能

### 核心功能
1. ✅ MinIO图片遍历 - 自动扫描存储桶中的所有图片文件
2. ✅ 智能去重机制 - 基于MD5和感知哈希的双重去重
3. ✅ 图片特征提取 - pHash/dHash/aHash/wHash多种特征算法
4. ✅ 腾讯云IMS集成 - 调用官方API进行内容安全检测
5. ✅ MySQL数据存储 - 完整的数据库表结构和CRUD操作
6. ✅ 增量扫描支持 - 避免重复扫描已处理的图片
7. ✅ 违规报告生成 - 自动生成详细的违规图片清单
8. ✅ 实时进度追踪 - 显示扫描进度和统计信息

### 特别优化
- ⭐ 重点监控棋牌类(gambling)违规图片
- ⭐ 相似图片检测和警告
- ⭐ 完善的错误处理和日志记录
- ⭐ 灵活的配置选项

## 📁 项目文件清单

### 核心代码文件 (5个)
1. **scanner.py** (15.3KB) - 主程序入口，整合所有模块
2. **minio_client.py** (5.1KB) - MinIO客户端封装
3. **image_feature.py** (5.2KB) - 图片特征提取器
4. **tencent_ims.py** (7.5KB) - 腾讯云IMS API调用
5. **database.py** (10.4KB) - MySQL数据库操作

### 配置文件 (3个)
6. **schema.sql** (4.7KB) - 数据库表结构定义
7. **requirements.txt** - Python依赖包列表
8. **.env.example** - 环境变量配置模板

### 脚本文件 (2个)
9. **run.sh** - 快速启动脚本（交互式）
10. **verify.sh** - 系统验证脚本

### 文档文件 (4个)
11. **README.md** (4.8KB) - 项目说明文档（英文）
12. **USAGE.md** (8.1KB) - 详细使用指南（中文）
13. **PROJECT_STRUCTURE.md** (7.5KB) - 项目结构说明
14. **DELIVERY.md** - 本交付说明文档

### 其他文件
15. **.gitignore** - Git忽略配置
16. **test_system.py** - 系统测试脚本

**总计**: 16个文件，代码约43KB

## 🚀 快速开始

### 步骤1: 安装依赖
```bash
cd /Users/macbook/imsminioimgs
pip install -r requirements.txt
```

### 步骤2: 配置环境
```bash
cp .env.example .env
# 编辑.env文件，填写您的实际配置
```

需要配置的信息：
- MinIO服务器地址和凭证
- 腾讯云SecretId和SecretKey
- MySQL连接信息

### 步骤3: 初始化数据库
```bash
mysql -u root -p
CREATE DATABASE image_security CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE image_security;
source schema.sql;
```

### 步骤4: 运行扫描
```bash
# 方法1: 使用交互式脚本（推荐新手）
./run.sh

# 方法2: 直接运行
python scanner.py

# 方法3: 先验证系统
./verify.sh
```

## 📊 系统架构

```
用户配置(.env)
    ↓
主程序(scanner.py)
    ↓
┌─────────────────────────────────────┐
│  MinIO客户端 → 遍历图片              │
│       ↓                             │
│  特征提取器 → 计算哈希               │
│       ↓                             │
│  数据库模块 → 检查缓存               │
│       ↓                             │
│  腾讯云IMS → 内容检测                │
│       ↓                             │
│  数据库模块 → 保存结果               │
└─────────────────────────────────────┘
    ↓
生成报告(violations.txt)
```

## 🎯 核心设计亮点

### 1. 双重去重机制

**第一层：精确去重**
- Key = MD5(文件内容) + "-" + 文件大小
- 完全相同的图片只扫描一次
- 即使文件名不同也能识别

**第二层：相似检测**
- 使用感知哈希算法(pHash/dHash/aHash)
- 汉明距离 ≤ 5 认为高度相似
- 发现相似违规图片时给出警告

### 2. 增量扫描

首次扫描后，系统会：
- 记录每张图片的特征和结果
- 后续扫描自动跳过已处理的图片
- 只处理新上传的图片
- 支持强制重扫模式

### 3. 多维度特征

每个图片计算4种哈希特征：
- **pHash**: 对缩放、亮度变化鲁棒（主要特征）
- **dHash**: 对梯度变化敏感
- **aHash**: 简单快速
- **wHash**: 结合频率和空间信息

### 4. 完善的错误处理

- 单张图片失败不影响整体扫描
- 错误信息记录到数据库和日志
- 支持断点续扫
- 详细的日志记录（scanner.log）

## 📈 性能预期

基于典型配置（单线程）：

| 图片数量 | 预计耗时 | 说明 |
|---------|---------|------|
| 100张 | 2-5分钟 | 测试规模 |
| 1,000张 | 30-50分钟 | 小规模 |
| 10,000张 | 5-8小时 | 中等规模 |
| 100,000张 | 2-3天 | 大规模 |

**影响因素**：
- 网络带宽（MinIO和腾讯云API）
- 图片大小
- 腾讯云IMS API响应时间
- 服务器性能

**优化建议**：
- 使用SCAN_LIMIT分批处理大量图片
- 确保网络连接稳定
- 考虑多进程并行（需改造代码）

## 🔍 检测结果示例

### 控制台输出
```
2024-01-15 10:30:00 | INFO | 开始扫描存储桶: my-images
2024-01-15 10:30:05 | INFO | 共找到 1234 个图片文件
2024-01-15 10:35:20 | WARNING | 🎲 发现棋牌类违规图片: uploads/poker_001.jpg | 标签: Gambling_Card | 置信度: 0.98
2024-01-15 10:40:15 | INFO | 统计信息 - 总数: 100, 已扫描: 95, 违规: 3, 跳过: 5, 错误: 0
```

### 违规报告 (violations.txt)
```
================================================================================
违规图片检测报告
生成时间: 2024-01-15 10:45:00
================================================================================

总计违规图片: 3

--------------------------------------------------------------------------------
违规类型: gambling (共2张)
--------------------------------------------------------------------------------

1. 路径: my-images/uploads/poker_001.jpg
   置信度: 0.98
   标签: Gambling_Card
   描述: 检测到扑克牌内容
   建议: Block
   扫描时间: 2024-01-15 10:35:20

2. 路径: my-images/uploads/mahjong_002.jpg
   置信度: 0.95
   标签: Gambling_Mahjong
   描述: 检测到麻将内容
   建议: Block
   扫描时间: 2024-01-15 10:38:10
```

## 🛠️ 技术栈

| 组件 | 技术 | 版本 |
|------|------|------|
| 语言 | Python | 3.7+ |
| MinIO SDK | minio | 7.2.0 |
| 图片处理 | Pillow | 10.2.0 |
| 哈希算法 | imagehash | 4.3.1 |
| 云服务SDK | tencentcloud-sdk-python-ims | 3.0.1076 |
| 数据库驱动 | mysql-connector-python | 8.3.0 |
| 日志 | loguru | 0.7.2 |
| 进度条 | tqdm | 4.66.2 |

## 📝 数据库表结构

### image_scan_records (主表)
- 存储所有扫描记录
- 包含图片特征、检测结果、路径信息等
- 建立多个索引优化查询

### similar_images (相似图片表)
- 记录相似图片关系
- 用于快速查找相似违规图片

### scan_statistics (统计表)
- 汇总扫描统计数据
- 按日期和存储桶分组

详见 `schema.sql` 文件

## ⚙️ 配置项说明

### MinIO配置
- `MINIO_ENDPOINT`: MinIO服务器地址
- `MINIO_ACCESS_KEY`: 访问密钥
- `MINIO_SECRET_KEY`: 秘密密钥
- `MINIO_BUCKET_NAME`: 要扫描的存储桶

### 腾讯云配置
- `TENCENT_SECRET_ID`: SecretId
- `TENCENT_SECRET_KEY`: SecretKey
- `TENCENT_REGION`: 地域（默认广州）

### MySQL配置
- `MYSQL_HOST`: 主机地址
- `MYSQL_PORT`: 端口（默认3306）
- `MYSQL_USER`: 用户名
- `MYSQL_PASSWORD`: 密码
- `MYSQL_DATABASE`: 数据库名

### 扫描配置
- `HASH_SIZE`: 哈希大小（默认8）
- `SCAN_PREFIX`: 对象前缀过滤
- `FORCE_RESCAN`: 强制重扫（true/false）
- `SCAN_LIMIT`: 限制扫描数量

## 🔧 常用命令

### 查看违规图片
```sql
SELECT object_key, violation_type, confidence 
FROM image_scan_records 
WHERE is_violation = 1 
ORDER BY confidence DESC;
```

### 查看棋牌类违规
```sql
SELECT * FROM image_scan_records 
WHERE violation_type = 'gambling';
```

### 查看统计信息
```sql
SELECT 
    COUNT(*) as total,
    SUM(is_violation) as violations,
    violation_type,
    COUNT(*) as count
FROM image_scan_records
GROUP BY violation_type;
```

### 重新扫描特定图片
```bash
export FORCE_RESCAN=true
export SCAN_PREFIX=uploads/suspicious/
python scanner.py
```

## ❓ 常见问题

### Q1: 如何停止扫描？
按 `Ctrl+C` 即可安全停止，已扫描的结果会保留。

### Q2: 扫描中断后如何继续？
直接再次运行即可，系统会自动跳过已扫描的图片。

### Q3: 如何只扫描特定目录？
设置 `SCAN_PREFIX` 环境变量：
```bash
export SCAN_PREFIX=uploads/2024/
python scanner.py
```

### Q4: 误判如何处理？
- 查看置信度，低置信度的可能是误判
- 在数据库中标记为人工审核
- 联系腾讯云技术支持

### Q5: 如何提高扫描速度？
- 使用SCAN_LIMIT分批处理
- 优化网络连接
- 考虑改造为多进程并行

## 📞 技术支持

遇到问题时：

1. **查看日志**: `scanner.log` 包含详细错误信息
2. **检查配置**: 确认.env文件中的配置正确
3. **验证连接**: 测试MinIO和MySQL连接
4. **参考文档**: 查看USAGE.md详细说明

**相关文档链接**:
- [腾讯云IMS文档](https://cloud.tencent.com/document/product/1125)
- [MinIO文档](https://docs.min.io/)
- [ImageHash文档](https://github.com/JohannesBuchner/imagehash)

## 📄 许可证

MIT License

## 🎉 交付清单

✅ 完整的源代码（5个核心模块）
✅ 数据库表结构定义
✅ 配置文件模板
✅ 依赖包列表
✅ 快速启动脚本
✅ 系统验证脚本
✅ 详细文档（3份）
✅ 测试脚本

**项目位置**: `/Users/macbook/imsminioimgs`

---

## 下一步操作

1. **安装依赖**: `pip install -r requirements.txt`
2. **配置环境**: 复制并编辑 `.env` 文件
3. **初始化数据库**: 执行 `schema.sql`
4. **运行测试**: `./verify.sh`
5. **开始扫描**: `./run.sh` 或 `python scanner.py`

**祝您使用愉快！** 🚀

如有任何问题，请查看详细文档或检查日志文件。
