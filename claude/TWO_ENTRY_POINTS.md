# 两个入口点完整使用指南

**目录：**
1. [系统架构](#系统架构)
2. [入口一：scanner.py（扫描器）](#入口一scannnerpy扫描器)
3. [入口二：handle_violations.py（处置工具）](#入口二handle_violationspy处置工具)
4. [两个工具的配合使用](#两个工具的配合使用)
5. [完整工作流示例](#完整工作流示例)

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│ 图片内容安全扫描系统                                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  MinIO 业务桶                                                     │
│  (images/)                                                       │
│        │                                                          │
│        │ 遍历图片                                                  │
│        ↓                                                          │
│  ┌─────────────────────────────────────────────────┐             │
│  │ 📊 入口一：scanner.py（扫描器）                    │             │
│  ├─────────────────────────────────────────────────┤             │
│  │ 功能：                                           │             │
│  │  1. 遍历 MinIO 桶中的图片                       │             │
│  │  2. 提取图片特征（哈希、感知哈希）              │             │
│  │  3. 三层去重（路径→内容→特征相似）             │             │
│  │  4. 调用腾讯云 IMS 检测违规内容                │             │
│  │  5. 结果写入 MySQL 数据库                       │             │
│  │                                                 │             │
│  │ 输出：                                          │             │
│  │  - image_scan_records 表（所有扫描结果）       │             │
│  │  - logs/scan.log（扫描日志）                    │             │
│  │  - logs/violations.log（违规记录）              │             │
│  └─────────────────────────────────────────────────┘             │
│        │                                                          │
│        │ is_violation=1                                          │
│        ↓                                                          │
│  MySQL image_security                                            │
│  (image_scan_records 表)                                         │
│        │                                                          │
│        │ 查看违规清单                                              │
│        ↓                                                          │
│  ┌─────────────────────────────────────────────────┐             │
│  │ 🛡️ 入口二：handle_violations.py（处置工具）      │             │
│  ├─────────────────────────────────────────────────┤             │
│  │ 功能（三阶段工作流）：                           │             │
│  │                                                 │             │
│  │ 第一阶段：mark-private                         │             │
│  │  - 标记为私密（MinIO 权限控制）                │             │
│  │  - 图片仍在原桶，无法公开访问                  │             │
│  │  - blocked = 1                                 │             │
│  │                                                 │             │
│  │ 观察期：监控业务日志（24-48 小时）             │             │
│  │                                                 │             │
│  │ 第二阶段（A）：confirm-quarantine             │             │
│  │  - 观察正常→移到隔离桶                         │             │
│  │  - blocked = 2                                 │             │
│  │                                                 │             │
│  │ 或第二阶段（B）：restore-public               │             │
│  │  - 观察异常→改回公开                           │             │
│  │  - blocked = 0（视为误判）                    │             │
│  │                                                 │             │
│  │ 第三阶段：delete                               │             │
│  │  - 从隔离桶彻底删除                            │             │
│  │                                                 │             │
│  │ 输出：                                          │             │
│  │  - MinIO：权限变更、对象移动、对象删除         │             │
│  │  - MySQL：blocked 字段状态更新                │             │
│  │  - logs/violations.log：处置记录              │             │
│  └─────────────────────────────────────────────────┘             │
│        │                                                          │
│        └─→ 隔离桶 (quarantine/)                                  │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 入口一：scanner.py（扫描器）

### 📋 职责

扫描 MinIO 中的图片，检测违规内容，结果写入数据库。

### 🎯 关键特性

1. **三层去重** - 节省 API 费用
   - 路径去重：同一路径只扫描一次
   - 内容去重：同一文件内容复用结果（md5-size）
   - 特征去重：相似图片复用结果（感知哈希）

2. **特征缓存** - 加速相似检测
   - LRU 缓存最近 10,000 个记录
   - 快速查找相似图片

3. **增量扫描** - 只扫描新增图片
   - 跳过已扫描的文件
   - 支持 `FORCE_RESCAN` 强制重新扫描

4. **批量处理** - 支持扫描限制
   - `SCAN_LIMIT` 参数用于测试

### 📖 使用说明

#### 基本命令

```bash
# 1. 进入项目目录
cd claude
source .venv/bin/activate

# 2. 运行扫描器（全量扫描）
python scanner.py

# 3. 扫描特定前缀（如 photos/ 目录）
python scanner.py --scan-prefix photos/

# 4. 强制重新扫描所有图片
FORCE_RESCAN=true python scanner.py

# 5. 仅扫描前 100 张（测试）
SCAN_LIMIT=100 python scanner.py
```

#### 必需的 .env 配置

```ini
# MinIO
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=...
MINIO_SECRET_KEY=...
MINIO_BUCKET_NAME=images           # 要扫描的桶

# MySQL
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASSWORD=...
MYSQL_DATABASE=image_security

# 腾讯云 IMS（内容检测）
TENCENT_SECRET_ID=...
TENCENT_SECRET_KEY=...
TENCENT_REGION=ap-guangzhou       # 区域

# 扫描参数（可选）
HASH_SIZE=8                        # 特征哈希大小
SCAN_PREFIX=                       # 扫描路径前缀
FORCE_RESCAN=false                 # 强制重新扫描
SCAN_LIMIT=                        # 扫描数量限制（用于测试）
```

#### 输出结果

**数据库表：** `image_scan_records`

新增的字段值：
- `is_violation = 1`（如果检出违规）
- `violation_type`：gambling, porn, violence, politics, ads, terrorism, contraband, vulgar 等
- `violation_label`：细分类型
- `confidence`：置信度 0.0000-1.0000
- `blocked = 0`（初始状态）
- `scan_status = "completed"`（扫描完成）
- `ims_result`：腾讯云 IMS 原始返回 JSON

**日志文件：**

```
logs/
├── scan.log         # 所有扫描日志（DEBUG 级别）
├── error.log        # 错误日志（ERROR 级别）
└── violations.log   # 违规记录（包含 is_violation=1 的）
```

#### 工作流示例

```bash
# 1. 首次全量扫描
$ python scanner.py
[2026-05-19 10:00:00] | INFO | 开始扫描 images 桶
[2026-05-19 10:00:05] | INFO | 遍历完成，共 1000 张图片
[2026-05-19 10:05:30] | INFO | 扫描完成
  - 总数：1000
  - 已扫描：800（调用 IMS API）
  - 复用结果：200（去重命中）
  - 检出违规：45 张
  
# 2. 观察扫描结果
$ mysql image_security -e "SELECT COUNT(*) FROM image_scan_records WHERE is_violation=1"
| COUNT(*) |
|----------|
|   45     |

# 3. 增量扫描（只扫描新增图片）
$ python scanner.py
[2026-05-19 11:00:00] | INFO | 开始扫描 images 桶
[2026-05-19 11:00:02] | INFO | 遍历完成，共 50 张新增图片
[2026-05-19 11:00:20] | INFO | 扫描完成
  - 总数：50（新增）
  - 已扫描：45
  - 复用结果：5
  - 检出违规：3 张
```

#### 常见问题

**Q1: 扫描很慢怎么办？**
- 检查腾讯云 API 配额和频率限制
- 调整 `HASH_SIZE` 大小（更小 = 更快但精度下降）
- 使用 `SCAN_LIMIT` 分批扫描

**Q2: 如何跳过某些路径？**
- 使用 `SCAN_PREFIX` 只扫描特定前缀
- 在 MinIO 中手动移除不需要的文件

**Q3: 相似图片判断标准是什么？**
见代码中的说明：
```
汉明距离 0     完全相同（像素级重复）
汉明距离 1-3   高度相似（<5%像素变化）→ 直接复用
汉明距离 4-5   中度相似（5-8%像素变化）→ 调用 IMS 复核
汉明距离 6+    不相似（>8%像素变化）→ 新增扫描
```

---

## 入口二：handle_violations.py（处置工具）

### 📋 职责

根据扫描结果，对违规图片进行三阶段处置（标记→观察→决策→删除）。

### 🎯 三阶段工作流

| 阶段 | 命令 | 操作 | 状态 | 可逆 |
|------|------|------|------|------|
| 一 | `mark-private` | 标记为私密 | blocked=1 | ✅ 可以 |
| 二-A | `confirm-quarantine` | 移到隔离桶 | blocked=2 | ❌ 不可 |
| 二-B | `restore-public` | 改回公开 | blocked=0 | ✅ 可以 |
| 三 | `delete` | 彻底删除 | 删除 | ❌ 不可 |

### 📖 使用说明

#### 第一阶段：发现和标记

```bash
# 1. 查看新增违规（未处理的）
python handle_violations.py list
python handle_violations.py list --type gambling --confidence 0.9

# 2. 标记为私密（开始观察期）
python handle_violations.py mark-private --type gambling
python handle_violations.py mark-private --ids 1,2,3,4,5

# 3. 查看观察中的
python handle_violations.py list-private
python handle_violations.py list-private --type gambling
```

**此时的状态：**
- 数据库：`blocked = 1`
- MinIO：对象权限设置为私密（无法公开访问）
- 应用层：可选择性地过滤不显示（通过查询 WHERE blocked=0）

**观察期建议：** 24-48 小时
- 监控应用日志是否有异常
- 检查用户是否反馈找不到某些图片
- 确认无业务影响再进行下一步

#### 第二阶段：观察后决策

**选项 A：观察正常 → 隔离**

```bash
# 确认隔离
python handle_violations.py confirm-quarantine --ids 1,2,3,4,5

# 查看已隔离的
python handle_violations.py list-quarantined
```

**此时的状态：**
- 数据库：`blocked = 2`
- MinIO：对象已移至隔离桶
- 不可恢复，仅能删除

**选项 B：观察异常 → 改回公开**

```bash
# 改回公开（视为误判）
python handle_violations.py restore-public --ids 6,7,8

# 查询改回公开的记录
mysql image_security -e "SELECT id, bucket_name, object_key FROM image_scan_records WHERE id IN (6,7,8)"
```

**此时的状态：**
- 数据库：`blocked = 0, is_violation = 0`
- MinIO：对象权限恢复为公开
- 对象回到原位置，可正常访问
- 标记为误判，不再参与违规处理

#### 第三阶段：彻底删除

```bash
# 列出已隔离的
python handle_violations.py list-quarantined

# 彻底删除（需确认）
python handle_violations.py delete --ids 1,2,3

# 注意：会要求输入 DELETE 确认
# 确认彻底删除 3 张？ (输入 DELETE 确认): DELETE
```

**此时的状态：**
- MinIO：隔离桶中的对象已删除
- 数据库：记录已删除
- **不可恢复**

### ⚠️ 重要提示：使用 --dry-run

所有修改命令都支持 `--dry-run`，预检查不实际执行：

```bash
# 预检查：不实际执行，只显示预期效果
python handle_violations.py mark-private --type gambling --dry-run
python handle_violations.py confirm-quarantine --ids 1,2,3 --dry-run
python handle_violations.py delete --ids 10,11,12 --dry-run

# 务必先 dry-run，再实际执行！
```

### 📊 数据库状态转移

```
未处理 (blocked=0)
    ↓
    └─→ mark-private
        ↓
    观察期 (blocked=1)
        ↓
        ├─→ confirm-quarantine → 已隔离 (blocked=2) → delete → 删除
        │
        └─→ restore-public → 改回公开 (blocked=0, is_violation=0)
```

### 📖 命令完整参考

见 `SETUP_AND_USAGE.md#命令参考` 部分。

---

## 两个工具的配合使用

### 数据流向

```
scanner.py
  ↓
  增加 image_scan_records 行（is_violation=1）
  ↓
handle_violations.py list
  ↓
  用户决策
  ↓
handle_violations.py mark-private
  ↓
  图片标记私密，blocked=1
  ↓
  [观察期]
  ↓
  观察正常或异常？
  ↓
  ├─→ handle_violations.py confirm-quarantine → blocked=2
  │     ↓
  │   handle_violations.py delete → 删除
  │
  └─→ handle_violations.py restore-public → blocked=0, is_violation=0
```

### 何时使用哪个工具

| 场景 | 使用工具 | 命令 |
|------|---------|------|
| 扫描新增图片 | scanner.py | `python scanner.py` |
| 查看检出的违规 | handle_violations.py | `python handle_violations.py list` |
| 开始处置违规 | handle_violations.py | `python handle_violations.py mark-private` |
| 监控观察期 | handle_violations.py | `python handle_violations.py list-private` |
| 确认隔离 | handle_violations.py | `python handle_violations.py confirm-quarantine` |
| 彻底删除 | handle_violations.py | `python handle_violations.py delete` |

### 日志查看

```bash
# 查看扫描日志
tail -f logs/scan.log

# 查看错误
tail -f logs/error.log

# 查看违规处置日志
tail -f logs/violations.log

# 搜索特定操作
grep "mark-private" logs/violations.log
grep "confirm-quarantine" logs/violations.log
grep "delete" logs/violations.log
```

---

## 完整工作流示例

### 场景：发现赌博图片，从扫描到删除的完整流程

```bash
# ================================================================
# 第一天：扫描阶段
# ================================================================

# 1. 运行扫描器（遍历 MinIO，调用 IMS，写库）
$ python scanner.py
[10:00:00] 开始扫描 images 桶...
[10:05:00] 扫描完成：检出 15 张违规（赌博类）

# 2. 查看扫描结果
$ python handle_violations.py list --type gambling
未处理的违规图片（blocked=0）（共 15 条）
ID     类型       置信度   路径
--
1      gambling   0.98     images/pic_001.jpg
2      gambling   0.95     images/pic_002.jpg
...

# ================================================================
# 第一天下午：第一阶段 - 标记为私密
# ================================================================

# 3. 干运行：预检查
$ python handle_violations.py mark-private --type gambling --dry-run
DRY-RUN: 将标记 15 张赌博类图片为私密
[DRY-RUN] 预计成功: 15

# 4. 实际执行：标记为私密
$ python handle_violations.py mark-private --type gambling
...
完成 - 成功: 15 失败: 0 跳过: 0

# 5. 查看观察中的
$ python handle_violations.py list-private --type gambling
私密观察中的图片（blocked=1）（共 15 条）
ID     类型       置信度   路径
--
1      gambling   0.98     images/pic_001.jpg
...

# 此时：
# - 数据库：blocked=1
# - MinIO：对象权限为 private，无法公开访问
# - 应用层：应该过滤不显示

# ================================================================
# 第二天：第二阶段 - 观察和决策
# ================================================================

# 6. 监控日志，确认无业务异常（开发人员操作）

# 7a. 观察正常 → 隔离
$ python handle_violations.py confirm-quarantine --ids 1,2,3,4,5,6,7,8,9,10,11,12,13,14,15 --dry-run
DRY-RUN: 将隔离 15 张图片
[DRY-RUN] 预计成功: 15

# 实际执行
$ python handle_violations.py confirm-quarantine --ids 1-15
...
完成 - 成功: 15 失败: 0 跳过: 0

# 或者（如果发现某些是误判）
# 7b. 观察异常 → 改回公开
$ python handle_violations.py restore-public --ids 5,10
...
完成 - 成功: 2 失败: 0 跳过: 0

# 此时：
# - 已隔离 13 张：blocked=2（不可恢复）
# - 改回公开 2 张：blocked=0, is_violation=0（可正常访问）

# ================================================================
# 第三天：第三阶段 - 彻底删除（可选，建议观察 30 天）
# ================================================================

# 8. 查看已隔离的
$ python handle_violations.py list-quarantined
隔离中的图片（blocked=2）（共 13 条）
...

# 9. 彻底删除
$ python handle_violations.py delete --ids 1,2,3,4,6,7,8,9,11,12,13,14,15 --dry-run
DRY-RUN: 将删除 13 张图片
[DRY-RUN] 预计成功: 13

# 实际执行（需要确认）
$ python handle_violations.py delete --ids 1,2,3,4,6,7,8,9,11,12,13,14,15
隔离中的图片（blocked=2）（共 13 条）
...
确认彻底删除 13 张？ (输入 DELETE 确认): DELETE
...
完成 - 成功: 13 失败: 0

# ================================================================
# 完成！所有违规图片已被处置
# ================================================================
```

### 日志记录示例

```
# logs/scan.log
[2026-05-19 10:00:00] | INFO | 开始扫描 images 桶
[2026-05-19 10:00:05] | INFO | 遍历完成，共 1000 张图片
[2026-05-19 10:00:30] | INFO | [1/800] 扫描 images/pic_001.jpg
[2026-05-19 10:00:35] | INFO | [1/800] 检出违规: gambling (0.98)
...

# logs/violations.log
[2026-05-19 14:00:00] | INFO | mark-private 成功: images/pic_001.jpg
[2026-05-19 14:00:05] | INFO | mark-private 成功: images/pic_002.jpg
...
[2026-05-20 10:00:00] | INFO | confirm-quarantine 成功: images/pic_001.jpg
...
[2026-05-21 10:00:00] | INFO | delete 成功: pic_001
```

---

## 快速参考

### scanner.py（扫描）

```bash
# 全量扫描
python scanner.py

# 扫描特定前缀
python scanner.py --scan-prefix photos/

# 强制重新扫描
FORCE_RESCAN=true python scanner.py

# 仅扫描前 100 张（测试）
SCAN_LIMIT=100 python scanner.py
```

### handle_violations.py（处置）

```bash
# 第一阶段
python handle_violations.py list                    # 查看违规
python handle_violations.py mark-private --type xxx # 标记私密

# 第二阶段
python handle_violations.py list-private            # 查看观察中的
python handle_violations.py confirm-quarantine --ids x,y # 隔离
python handle_violations.py restore-public --ids a,b    # 改回公开

# 第三阶段
python handle_violations.py list-quarantined        # 查看隔离的
python handle_violations.py delete --ids x,y        # 删除
```

### 所有命令都支持 --dry-run！

```bash
python handle_violations.py mark-private --type gambling --dry-run
python handle_violations.py confirm-quarantine --ids 1,2,3 --dry-run
python handle_violations.py delete --ids 4,5,6 --dry-run
```

---

**关键点总结：**
1. scanner.py 负责检测（输入 MinIO 图片 → 输出违规列表）
2. handle_violations.py 负责处置（三阶段：标记→观察→决策）
3. 两个工具通过 MySQL 数据库通信（image_scan_records 表）
4. 所有修改操作都支持 --dry-run 预检查
5. 有完整的日志记录，便于审计和故障排查
