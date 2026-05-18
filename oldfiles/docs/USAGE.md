# 图片内容安全扫描系统 - 使用指南

## 一、系统概述

本系统是一个基于Python的图片内容安全检测工具，主要功能包括：

1. **遍历MinIO存储**：自动扫描MinIO对象存储中的所有图片文件
2. **智能去重**：使用感知哈希算法识别相似图片，避免重复扫描
3. **内容检测**：调用腾讯云IMS API检测图片是否违规（特别是棋牌类）
4. **结果存储**：将扫描结果保存到MySQL数据库
5. **生成报告**：输出违规图片清单和统计信息

## 二、安装步骤

### 1. 环境准备

确保已安装：
- Python 3.7或更高版本
- MySQL 5.7或更高版本
- MinIO服务器（已有图片数据）

### 2. 安装Python依赖

```bash
cd /Users/macbook/imsminioimgs
pip install -r requirements.txt
```

### 3. 初始化数据库

登录MySQL并执行：

```bash
mysql -u root -p
```

在MySQL中执行：

```sql
CREATE DATABASE IF NOT EXISTS image_security CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE image_security;
source /Users/macbook/imsminioimgs/schema.sql;
```

或者直接：

```bash
mysql -u root -p image_security < schema.sql
```

### 4. 配置环境变量

复制配置文件模板：

```bash
cp .env.example .env
```

编辑`.env`文件，填写以下信息：

```ini
# MinIO配置
MINIO_ENDPOINT=localhost:9000                    # MinIO服务器地址
MINIO_ACCESS_KEY=your_access_key                 # MinIO访问密钥
MINIO_SECRET_KEY=your_secret_key                 # MinIO秘密密钥
MINIO_SECURE=false                               # 是否使用HTTPS
MINIO_BUCKET_NAME=your_bucket_name               # 要扫描的存储桶名称

# 腾讯云IMS配置
TENCENT_SECRET_ID=your_secret_id                 # 腾讯云SecretId
TENCENT_SECRET_KEY=your_secret_key               # 腾讯云SecretKey
TENCENT_REGION=ap-guangzhou                      # 地域（默认广州）

# MySQL配置
MYSQL_HOST=localhost                             # MySQL主机
MYSQL_PORT=3306                                  # MySQL端口
MYSQL_USER=root                                  # MySQL用户名
MYSQL_PASSWORD=your_password                     # MySQL密码
MYSQL_DATABASE=image_security                    # 数据库名

# 扫描配置
HASH_SIZE=8                                      # 哈希大小（8表示64位哈希）
SCAN_PREFIX=                                     # 对象前缀过滤（可选）
FORCE_RESCAN=false                               # 是否强制重扫
SCAN_LIMIT=                                      # 限制扫描数量（可选）
```

## 三、使用方法

### 方法1：使用快速启动脚本（推荐）

```bash
./run.sh
```

脚本会引导你完成：
- 检查Python版本和依赖
- 检查配置文件
- 确认数据库初始化
- 设置扫描选项
- 开始扫描

### 方法2：直接运行

```bash
python scanner.py
```

### 方法3：使用环境变量控制

```bash
# 扫描指定存储桶
export SCAN_BUCKET_NAME=my-images
python scanner.py

# 只扫描特定前缀的图片
export SCAN_PREFIX=uploads/2024/
python scanner.py

# 限制扫描数量（测试用）
export SCAN_LIMIT=100
python scanner.py

# 强制重新扫描所有图片
export FORCE_RESCAN=true
python scanner.py
```

## 四、工作流程

```
1. 连接MinIO → 2. 遍历图片 → 3. 计算特征 → 4. 检查缓存
                                              ↓
5. 保存结果 ← 6. 调用IMS API ← 5. 是否已存在？
```

详细说明：

1. **遍历MinIO**：列出存储桶中所有图片文件（jpg/png/gif等）
2. **计算Key**：对每个图片计算 `MD5(文件内容)-文件大小` 作为唯一标识
3. **提取特征**：计算多种感知哈希特征（pHash/dHash/aHash）
4. **检查缓存**：查询MySQL是否已扫描过该图片
   - 如果存在且未强制重扫：跳过
   - 如果不存在：继续下一步
5. **调用IMS**：发送图片到腾讯云IMS进行内容检测
6. **保存结果**：将检测结果存入MySQL

## 五、数据库表结构

### 1. image_scan_records（主表）

存储所有扫描记录，关键字段：

- `key`: 图片唯一标识（MD5-文件大小）
- `feature_hash`: 图片感知哈希特征码
- `bucket_name`: MinIO存储桶名称
- `object_key`: 图片在MinIO中的路径
- `is_violation`: 是否违规（0/1）
- `violation_type`: 违规类型（gambling/porn/violence等）
- `violation_label`: 具体违规标签
- `confidence`: 置信度（0-1）
- `suggestion`: 建议操作（Block/Review/Pass）

### 2. similar_images（相似图片表）

记录相似图片关系，用于快速查找相似违规图片。

### 3. scan_statistics（统计表）

汇总扫描统计数据。

## 六、查看结果

### 1. 控制台输出

扫描过程中会实时显示：
- 当前进度
- 发现的违规图片
- 统计信息

### 2. 日志文件

- `scanner.log`: 详细日志（包含DEBUG信息）
- 控制台输出INFO级别日志

### 3. 违规报告

扫描完成后自动生成 `violations.txt`，包含：
- 所有违规图片列表
- 按违规类型分组
- 每张图片的详细信息（路径、置信度、标签等）

### 4. 数据库查询

```sql
-- 查看所有违规图片
SELECT * FROM image_scan_records WHERE is_violation = 1;

-- 查看棋牌类违规图片
SELECT * FROM image_scan_records 
WHERE violation_type = 'gambling' 
ORDER BY confidence DESC;

-- 查看统计信息
SELECT 
    COUNT(*) as total,
    SUM(is_violation) as violations,
    violation_type,
    COUNT(*) as count
FROM image_scan_records
GROUP BY violation_type;
```

## 七、违规类型说明

系统可识别以下违规类型：

| 类型 | 说明 | 重点关注 |
|------|------|----------|
| gambling | 赌博/棋牌类 | ⭐⭐⭐ 重点监控 |
| porn | 色情内容 | ⭐⭐⭐ |
| violence | 暴力内容 | ⭐⭐ |
| politics | 政治敏感 | ⭐⭐ |
| ads | 广告 spam | ⭐ |
| terrorism | 恐怖主义 | ⭐⭐⭐ |
| contraband | 违禁品 | ⭐⭐ |
| vulgar | 低俗内容 | ⭐ |
| qrcode | 可疑二维码 | ⭐ |

## 八、性能优化建议

### 1. 增量扫描

系统会自动跳过已扫描的图片，首次扫描后：
- 新增图片会被自动检测
- 已有图片不会重复扫描（除非设置FORCE_RESCAN）

### 2. 分批处理

对于大量图片（超过10万张）：

```bash
# 每次处理1000张
export SCAN_LIMIT=1000
python scanner.py

# 配合SCAN_PREFIX分目录扫描
export SCAN_PREFIX=folder1/
python scanner.py
```

### 3. 并发考虑

当前版本为单线程顺序处理，如需提高速度可以：
- 多进程并行扫描不同存储桶
- 增加腾讯云IMS API配额
- 优化网络带宽

## 九、常见问题

### Q1: 扫描速度慢？

**原因**：
- 网络延迟（MinIO或腾讯云API）
- 图片数量巨大
- IMS API限流

**解决**：
- 检查网络连接
- 使用SCAN_LIMIT分批处理
- 联系腾讯云提升API配额

### Q2: 内存占用高？

**原因**：
- 一次性加载大图片到内存

**解决**：
- 使用SCAN_LIMIT限制批量大小
- 监控系统资源
- 考虑增加服务器内存

### Q3: 如何识别相似图片？

系统使用感知哈希算法：
- pHash（感知哈希）：对缩放、亮度变化鲁棒
- dHash（差异哈希）：对梯度变化敏感
- aHash（平均哈希）：简单快速

汉明距离 <= 5 认为高度相似

### Q4: 误判如何处理？

腾讯云IMS可能存在误判：
- 查看置信度（confidence），低置信度的可能是误判
- 人工复核suggestion为"Review"的图片
- 可以在数据库中标记误判图片

## 十、维护建议

### 1. 定期清理日志

```bash
# 保留最近7天的日志
find . -name "*.log" -mtime +7 -delete
```

### 2. 数据库备份

```bash
mysqldump -u root -p image_security > backup_$(date +%Y%m%d).sql
```

### 3. 监控扫描状态

```sql
-- 查看扫描进度
SELECT 
    scan_status,
    COUNT(*) as count
FROM image_scan_records
GROUP BY scan_status;

-- 查看最近扫描的图片
SELECT * FROM image_scan_records 
ORDER BY last_scanned_at DESC 
LIMIT 10;
```

## 十一、技术支持

遇到问题时：

1. 查看日志文件：`scanner.log`
2. 检查数据库连接
3. 验证MinIO和腾讯云凭证
4. 参考README.md中的Troubleshooting部分

---

**祝使用愉快！** 🎉
