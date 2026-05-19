# 扫描器详解（scanner.py）

## 概述

`scanner.py` 是系统的扫描入口，负责遍历 MinIO 桶中的所有图片，提取特征，调用腾讯云 IMS 进行内容检测，并将结果存入数据库。

**类名**：`ImageSecurityScanner`

**核心特性**：三层去重机制，最小化 API 调用，节省费用。

## 工作流程

```
遍历 MinIO 桶
    ↓
┌─────────────────────────────────────────────┐
│ 第 1 层：路径去重                            │
│ 同一路径已扫描？→ 跳过                      │
└─────────────────────────────────────────────┘
    ↓ (否)
┌─────────────────────────────────────────────┐
│ 下载图片 & 提取特征                          │
│ - 计算内容 Key (md5-size)                   │
│ - 计算 pHash / dHash / aHash               │
└─────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────┐
│ 第 2 层：内容去重                            │
│ 相同内容已扫描？→ 复用结果                   │
└─────────────────────────────────────────────┘
    ↓ (否)
┌─────────────────────────────────────────────┐
│ 第 3 层：特征相似                            │
│ 有高度相似的已扫描图片？→ 复用结果           │
│ (pHash 距离 ≤ 3)                            │
└─────────────────────────────────────────────┘
    ↓ (否)
┌─────────────────────────────────────────────┐
│ 调用腾讯云 IMS API                          │
│ 获取：violation_label, sub_label, confidence │
└─────────────────────────────────────────────┘
    ↓
写入数据库
```

## 基本用法

scanner.py **没有命令行参数**，所有配置通过环境变量控制：

```bash
# 普通扫描
python scanner.py

# 强制重扫
FORCE_RESCAN=true python scanner.py

# 限量扫描
SCAN_LIMIT=100 python scanner.py

# 指定前缀
SCAN_PREFIX=uploads/ python scanner.py
```

## 环境变量配置

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `SCAN_BUCKET_NAME` | 覆盖要扫描的桶名 | `.env` 中的 `MINIO_BUCKET_NAME` |
| `SCAN_PREFIX` | 路径前缀过滤 | 空（扫描全桶） |
| `FORCE_RESCAN` | `true` 则强制重扫所有图片 | `false` |
| `SCAN_LIMIT` | 限制本次最多扫描的图片数 | 无限制 |
| `MINIO_ENDPOINT` | MinIO 地址 | - |
| `MINIO_ACCESS_KEY` | MinIO 访问密钥 | - |
| `MINIO_SECRET_KEY` | MinIO 密钥 | - |
| `MINIO_BUCKET_NAME` | 业务图片桶 | - |
| `TENCENT_SECRET_ID` | 腾讯云 SecretId | - |
| `TENCENT_SECRET_KEY` | 腾讯云 SecretKey | - |
| `TENCENT_REGION` | 腾讯云区域 | - |
| `MYSQL_HOST` | MySQL 地址 | - |
| `MYSQL_PORT` | MySQL 端口 | `3306` |
| `MYSQL_USER` | MySQL 用户名 | - |
| `MYSQL_PASSWORD` | MySQL 密码 | - |
| `MYSQL_DATABASE` | 数据库名 | - |
| `CACHE_ENABLED` | 是否启用内存缓存 | - |
| `CACHE_STRATEGY` | 缓存策略 | - |
| `CACHE_MAX_SIZE` | 缓存最大条目数 | - |

## 使用场景

### 场景 1：首次全量扫描

```bash
python scanner.py
```

扫描所有配置桶中的所有图片，第一次遇到每张图片时调用 IMS API。

**输出**：
```
统计 - 总:1000 | IMS扫描:1000 | 路径复用:0 | 内容复用:0 | 特征复用:0 | 复用合计:0 | 违规:12 | 错误:0
```

### 场景 2：增量扫描（新增图片）

```bash
python scanner.py
```

自动跳过已扫描的图片（第 1 层去重），只扫描新增图片。

**输出**：
```
统计 - 总:1050 | IMS扫描:50 | 路径复用:1000 | 内容复用:0 | 特征复用:0 | 复用合计:1000 | 违规:2 | 错误:0
```

### 场景 3：强制重新扫描

```bash
FORCE_RESCAN=true python scanner.py
```

忽略所有已有扫描记录，重新对所有图片调用 IMS API。用于：
- IMS 模型升级，需要重跑老数据
- 调整置信度阈值
- 验证扫描结果

### 场景 4：有限数量扫描（测试）

```bash
SCAN_LIMIT=100 python scanner.py
```

控制单次扫描数量，用于测试或控制 API 费用。

## 三层去重详解

### 第 1 层：路径去重

**原理**：同一 MinIO 路径（bucket + object_key）已扫描过，直接跳过。

**特点**：
- 最快速，无需下载和计算
- 路径命中时完全跳过，不下载图片

### 第 2 层：内容去重

**原理**：相同内容（md5 + 文件大小）已扫描过，复用结果。

**特点**：
- 处理同一内容不同路径的情况
- 避免重复 API 调用

**示例**：
```
图片 A (100KB): /upload/photo.jpg     → 第一次，调用 IMS，结果: 违规
图片 B (100KB): /archive/photo.jpg    → 内容相同，复用 A 的结果（不调用 IMS）
```

### 第 3 层：特征相似

**原理**：pHash 特征相似度高（汉明距离 ≤ 3）的已扫描图片，复用其结果。

**汉明距离**：
- 距离 ≤ 3 → 复用结果（高度相似）
- 距离 4–5 → 继续调用 IMS（中度相似，需复核）
- 距离 > 5 → 视为不相似，调用 IMS

**示例**：
```
原图: photo_original.jpg  → phash = "8f4a5e2c1b9d7f3a" → 扫描 → 违规
编辑: photo_cropped.jpg   → phash = "8f4a5e2c1b9d7f3c" → 汉明距离 = 1 → 复用结果
```

## 缓存说明

扫描器在内存中维护相似图片特征缓存，加速查库查询。缓存大小由 `CACHE_MAX_SIZE` 控制。通过 `CACHE_ENABLED` 和 `CACHE_STRATEGY` 配置缓存行为。

相似检测查库时，从数据库拉取最近 `SIMILAR_CANDIDATE_LIMIT`（默认 2000）条已扫描记录，在内存中逐条计算汉明距离。

## 启动时修复

扫描器启动时执行 `_fix_historical_records`，修复旧格式数据，确保数据完整性。修复完成后才加载缓存。

## 统计信息

扫描完成后输出统计日志：

```
统计 - 总:{total} | IMS扫描:{scanned} | 路径复用:{path_reused} | 内容复用:{content_reused} | 特征复用:{api_saved} | 复用合计:{reused} | 违规:{violations} | 错误:{errors}
```

| 字段 | 含义 |
|------|------|
| total | 本次遍历到的图片总数 |
| scanned | 实际调用 IMS API 的次数 |
| path_reused | 路径去重命中次数 |
| content_reused | 内容去重命中次数 |
| api_saved | 特征相似复用次数（节省的 IMS 调用） |
| reused | 三层复用合计 |
| violations | 检出的违规图片数 |
| errors | 处理失败的图片数 |

## 错误处理

任何单张图片处理失败，主循环捕获后：
1. 写一条 `scan_status='failed'` 的记录到数据库，附带 `error_message`
2. 错误记录的 `key` 字段为 `error-{md5(bucket/object_key)}`，防止 key 为空或过长
3. 继续处理下一张图片，整批不中断

## 日志查看

### 扫描日志

```bash
tail -f logs/scan.log
```

### 违规日志

```bash
tail -f logs/violations.log
```

### 错误日志

```bash
tail -f logs/error.log
```

## 特征提取

### pHash（知觉哈希）

将图片缩小到 8×8，转换为灰度，计算 64 位哈希值。对裁剪、缩放、压缩变化鲁棒，固定长度（64 位）。

### 内容 Key（唯一标识）

构成：`md5(内容) + '-' + 文件大小`

用于确保相同内容可被识别，检测完全重复的图片。

---

← [INDEX](./INDEX.md) | [USAGE](./USAGE.md) | [HANDLER](./HANDLER.md) →
