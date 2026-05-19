# 扫描逻辑详解

本文档说明 `scanner.py` 的内部处理流程。顶层 README 已涵盖配置和使用，这里只讲"为什么这么做"。

## 核心概念

### Key（内容标识）

```
key = md5(图片字节) + "-" + 字节长度
```

- 标识图片的**内容**，而不是路径
- 同一张图存在两个 MinIO 路径时，两条记录共享同一个 `key`
- 用于判断"这张内容是否已扫描过"

### Feature Hash（特征哈希）

`scanner.py` 计算三种感知哈希：`pHash` / `dHash` / `aHash`（默认 8×8 = 64 位）。`pHash` 作为主特征写入 `feature_hash` 字段，用于相似检测。

汉明距离参考：

| 距离 | 相似程度 |
|------|----------|
| 0    | 完全相同 |
| 1–3  | 高度相似（直接复用结果） |
| 4–5  | 中度相似（仍调 IMS 复核） |
| > 5  | 不相似 |

阈值定义在 [scanner.py](../scanner.py) 顶部：

```python
SIMILAR_DISTANCE_REUSE = 3   # ≤ 3 复用
SIMILAR_DISTANCE_MAX = 5     # > 5 不视为相似候选
```

## 单张图片处理流程

```
开始
  │
  ├─ ① 路径去重：find_by_bucket_object(bucket, key)
  │      命中 → 完全跳过（不下载、不扫描）
  │
  ├─ 下载图片，算 key 和 features
  │
  ├─ ② 内容去重：find_by_key(key)
  │      命中 → 复用源记录的扫描结论，插一条新路径记录
  │
  ├─ ③ 特征相似：find_similar_scanned(phash, max_distance=5)
  │      距离 ≤ 3 → 复用源记录的扫描结论
  │      距离 4–5 → 继续走 IMS（不复用）
  │
  ├─ ④ 调用腾讯云 IMS API
  │
  └─ ⑤ 写库（upsert_record）
```

三层去重逐层放宽：路径精确 → 内容精确 → 特征近似。前两层完全免 API 费用；第三层在高度相似时也免费。

## 数据库唯一约束

```sql
UNIQUE KEY uk_bucket_object (bucket_name, object_key(255))
```

- 同一 `(bucket, object_key)` 只能有一条记录
- `upsert_record` 用 `INSERT ... ON DUPLICATE KEY UPDATE`，避免并发或重扫导致重复插入

## 相似检测的查库实现

[database.py](../database.py) 的 `find_similar_scanned`：

```sql
SELECT key, bucket_name, object_key, feature_hash, ...
FROM image_scan_records
WHERE scan_status = 'completed' AND feature_hash IS NOT NULL
ORDER BY created_at DESC
LIMIT 2000
```

拉最近 2000 条已扫描记录到内存，在 Python 中逐条算汉明距离过滤。`SIMILAR_CANDIDATE_LIMIT = 2000` 定义在文件顶部。

**规模上限**：每次扫描读 2000 行 + 计算 2000 次汉明距离，单图开销约 10–50ms。已扫描 >50 万条时建议改为向量检索（Faiss / Milvus / pgvector）。

## 强制重扫

```bash
FORCE_RESCAN=true python scanner.py
```

设置后跳过路径去重和内容去重，每张图重新调 IMS。用于：
- 检测算法升级，需要重跑老数据
- 修复历史误判后重新评估

## 统计字段含义

扫描完成后输出的日志行格式：

```
统计 - 总:{total} | IMS扫描:{scanned} | 路径复用:{path_reused} | 内容复用:{content_reused} | 特征复用:{api_saved} | 复用合计:{reused} | 违规:{violations} | 错误:{errors}
```

示例：

```
统计 - 总:1000 | IMS扫描:780 | 路径复用:150 | 内容复用:50 | 特征复用:20 | 复用合计:220 | 违规:42 | 错误:0
```

| 字段 | 含义 |
|------|------|
| 总 | 本次遍历到的图片数 |
| IMS扫描 | 实际调用过 IMS API 的次数 |
| 路径复用 | 第一层去重命中次数（同一路径已扫描，完全跳过） |
| 内容复用 | 第二层去重命中次数（相同内容 md5，复用结果） |
| 特征复用 | 第三层去重命中次数（pHash 距离 ≤ 3，复用结果） |
| 复用合计 | 路径复用 + 内容复用 + 特征复用 |
| 违规 | `is_violation=1` 的命中数（含三种去重路径） |
| 错误 | 处理失败的图片数 |

复用合计约等于本次扫描省下的 IMS 调用费用（路径复用不下载，内容/特征复用不调 API）。

## 错误处理

任何单张图片处理失败，主循环捕获后写一条 `scan_status='failed'` 的记录到数据库，附带 `error_message`，然后继续下一张。整批不会因为一张图失败而中断。

错误记录的 `key` 字段是 `error-{md5(bucket/object_key)}`，避免因 key 为空而违反 NOT NULL 约束，同时防止 key 过长。
