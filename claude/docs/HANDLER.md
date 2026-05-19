# 处置工具详解（handle_violations.py）

## 概述

`handle_violations.py` 是系统的处置入口，负责管理违规图片的生命周期，实现三阶段工作流：标记私密 → 观察决策 → 确认隔离 → 彻底删除。

**核心特性**：渐进式处置，观察期内可恢复，降低误判风险。

## 工作流程

```
新增违规 (blocked=0)
    ↓
[mark-private] → blocked=1 (观察期 24-48 小时)
    ↓
    ├─→ [confirm-quarantine] → blocked=2 (隔离，不可恢复)
    │   ↓
    │   [delete] → 彻底删除
    │
    └─→ [restore-public] → blocked=0 (视为误判)
```

## 基本用法

### 命令结构

```bash
python handle_violations.py <command> [选项]
```

### 命令列表

| 命令 | 功能 | 状态 |
|------|------|------|
| `list` | 查看新增违规 | blocked=0 |
| `mark-private` | 标记为私密 | blocked → 1 |
| `list-private` | 查看观察中的 | blocked=1 |
| `confirm-quarantine` | 确认隔离 | blocked → 2 |
| `restore-public` | 恢复公开 | blocked → 0 |
| `list-quarantined` | 查看已隔离的 | blocked=2 |
| `delete` | 彻底删除 | 记录删除 |

## 第一阶段：发现 & 标记私密

### list - 查看新增违规

```bash
python handle_violations.py list [选项]
```

**选项**：
- `--type <type>`：按违规类型过滤（可选）
- `--limit <n>`：显示最多 n 条（默认 100）
- `--order-by <field>`：排序字段（默认 created_at DESC）

**示例**：

```bash
# 查看所有新增违规
$ python handle_violations.py list

未处理的违规图片（blocked=0）（共 3 条）

ID  | 对象名                  | 类型      | 置信度 | 首次发现
----|------------------------|----------|--------|----------
1   | uploads/photo_1.jpg     | gambling  | 0.95   | 2026-05-19
2   | uploads/photo_2.jpg     | porn      | 0.89   | 2026-05-19
3   | uploads/photo_3.jpg     | violence  | 0.92   | 2026-05-19

# 只查看赌博类违规
$ python handle_violations.py list --type gambling

未处理的赌博违规（共 1 条）

ID  | 对象名                  | 类型      | 置信度 | 首次发现
----|------------------------|----------|--------|----------
1   | uploads/photo_1.jpg     | gambling  | 0.95   | 2026-05-19
```

**输出含义**：
- `ID`：数据库记录 ID，用于后续操作
- `对象名`：MinIO 对象键（文件路径）
- `类型`：违规类型（gambling/porn/violence 等）
- `置信度`：0-1 之间，越接近 1 越确定违规
- `首次发现`：首次扫描时间

### mark-private - 标记为私密

```bash
python handle_violations.py mark-private [选项]
```

**选项**（至少指定一个）：
- `--type <type>`：按违规类型标记（见下表）
- `--ids <ids>`：指定 ID，逗号分隔（如 1,2,3）
- `--dry-run`：预演，不实际执行
- `--confidence-threshold <threshold>`：置信度阈值（默认 0.5）

**违规类型说明**：

| 类型 | 中文含义 | 说明 | 优先级 |
|------|---------|------|--------|
| `gambling` | 赌博 | 赌场、赌博网站、赌博相关内容 | 🔴 高 |
| `porn` | 色情 | 不雅、色情相关内容 | 🔴 高 |
| `violence` | 暴力 | 暴力、血腥、残暴内容 | 🟠 中 |
| `politics` | 政治 | 政治敏感内容 | 🟠 中 |
| `terrorism` | 恐怖 | 恐怖主义相关内容 | 🔴 高 |
| `ads` | 广告 | 虚假或骚扰广告 | 🟡 低 |
| `contraband` | 违禁品 | 毒品、枪支等违禁品 | 🔴 高 |
| `vulgar` | 低俗 | 低俗、不适当语言或手势 | 🟡 低 |
| `qrcode` | 二维码 | 未知/可疑二维码 | 🟡 低 |

**示例**：

```bash
# 方法 1：按类型标记
$ python handle_violations.py mark-private --type gambling
✓ 已标记 ID 1 为私密 (uploads/photo_1.jpg)

# 方法 2：指定 ID 标记
$ python handle_violations.py mark-private --ids 2,3
✓ 已标记 ID 2 为私密 (uploads/photo_2.jpg)
✓ 已标记 ID 3 为私密 (uploads/photo_3.jpg)

# 方法 3：预演（查看将要标记的）
$ python handle_violations.py mark-private --type gambling --dry-run
[预演] 将标记以下赌博违规为私密：
  - ID 1: uploads/photo_1.jpg (置信度 0.95)
```

**执行效果**：
1. 修改 MinIO 对象权限为私密（`set_object_private`）
2. 更新数据库 `blocked = 1`
3. 记录到 `violations.log`
4. **图片在原桶，但无法公开访问**

**权限机制**：
- MinIO 支持对象级权限控制
- `set_object_private()`：仅所有者可访问
- `set_object_public()`：任何人可访问
- 修改权限不移动对象位置

### list-private - 查看观察中的

```bash
python handle_violations.py list-private [选项]
```

**示例**：

```bash
$ python handle_violations.py list-private

观察中的违规（共 3 条）

ID  | 对象名                  | 类型      | 标记时间
----|------------------------|----------|----------
1   | uploads/photo_1.jpg     | gambling  | 2026-05-19 10:00
2   | uploads/photo_2.jpg     | porn      | 2026-05-19 10:05
3   | uploads/photo_3.jpg     | violence  | 2026-05-19 10:10
```

**观察期建议**：
- 监控业务日志（用户反馈、访问异常）
- 验证应用是否报错（404 等）
- 检查数据一致性（缓存是否清理）
- 建议观察 24-48 小时

## 第二阶段：观察决策

### confirm-quarantine - 确认隔离

```bash
python handle_violations.py confirm-quarantine --ids <ids> [选项]
```

**选项**：
- `--ids <ids>`：要隔离的 ID，**必需**（如 1,2,3）
- `--dry-run`：预演

**示例**：

```bash
# 预演
$ python handle_violations.py confirm-quarantine --ids 1,2 --dry-run
[预演] 将隔离以下图片：
  - ID 1: uploads/photo_1.jpg (gambling)
  - ID 2: uploads/photo_2.jpg (porn)

# 实际隔离
$ python handle_violations.py confirm-quarantine --ids 1,2
✓ 已隔离 ID 1 (uploads/photo_1.jpg)
  - 从 'images' 移到 'quarantine' 桶
  - 数据库更新 blocked=2
✓ 已隔离 ID 2 (uploads/photo_2.jpg)
  - 从 'images' 移到 'quarantine' 桶
  - 数据库更新 blocked=2
```

**执行效果**：
1. 将对象从原桶移到隔离桶
2. 更新数据库 `blocked = 2`
3. **此后仅能删除，不可恢复**
4. 记录到 `violations.log`

**注意事项**：
- ⚠️ **不可逆**：隔离后无法恢复
- 隔离前应充分确认（24-48 小时观察）
- 建议使用 `--dry-run` 先预演

### restore-public - 恢复公开

```bash
python handle_violations.py restore-public --ids <ids> [选项]
```

**选项**：
- `--ids <ids>`：要恢复的 ID，**必需**
- `--dry-run`：预演

**示例**：

```bash
# 预演
$ python handle_violations.py restore-public --ids 3 --dry-run
[预演] 将恢复以下图片为公开：
  - ID 3: uploads/photo_3.jpg (violence)

# 实际恢复
$ python handle_violations.py restore-public --ids 3
✓ 已恢复 ID 3 为公开 (uploads/photo_3.jpg)
  - 权限改回公开
  - 数据库更新 blocked=0
  - 视为误判
```

**执行效果**：
1. 修改 MinIO 对象权限为公开
2. 更新数据库 `blocked = 0`
3. **图片可再次访问**
4. 视为误判，可重新扫描或保留

### list-quarantined - 查看已隔离的

```bash
python handle_violations.py list-quarantined [选项]
```

**示例**：

```bash
$ python handle_violations.py list-quarantined

已隔离的违规（共 2 条）

ID  | 对象名                  | 类型      | 隔离时间
----|------------------------|----------|----------
1   | uploads/photo_1.jpg     | gambling  | 2026-05-20 14:00
2   | uploads/photo_2.jpg     | porn      | 2026-05-20 14:05
```

## 第三阶段：彻底删除

### delete - 删除隔离的图片

```bash
python handle_violations.py delete --ids <ids> [选项]
```

**选项**：
- `--ids <ids>`：要删除的 ID，**必需**
- `--dry-run`：预演
- `--force`：跳过确认提示

**示例**：

```bash
# 预演
$ python handle_violations.py delete --ids 1 --dry-run
[预演] 将删除以下图片：
  - ID 1: uploads/photo_1.jpg (gambling, 隔离于 2026-05-20 14:00)

# 实际删除（需确认）
$ python handle_violations.py delete --ids 1
准备删除以下图片：
  - ID 1: uploads/photo_1.jpg
确定吗？(y/n) y
✓ 已删除 ID 1 (uploads/photo_1.jpg)
  - 从隔离桶 'quarantine' 永久删除
  - 数据库记录删除
  - 不可恢复

# 跳过确认（危险）
$ python handle_violations.py delete --ids 1,2,3 --force
```

**执行效果**：
1. 从隔离桶永久删除对象
2. 删除数据库记录
3. **不可恢复**
4. 记录到 `violations.log`

**警告**：
- ⚠️ **永久删除**，不可恢复
- 务必确认删除后再执行
- 建议先用 `--dry-run` 预演

## 实际操作示例

### 完整 3 天流程

**第一天：发现阶段**

```bash
# 09:00 查看新增违规
$ python handle_violations.py list
未处理的违规图片（共 3 条）
ID | 对象名 | 类型 | 置信度
1  | photo_1.jpg | gambling | 0.95
2  | photo_2.jpg | porn | 0.89
3  | photo_3.jpg | violence | 0.92

# 10:00 标记赌博图片为私密（测试）
$ python handle_violations.py mark-private --type gambling --dry-run
[预演] 将标记以下赌博违规为私密：
  - ID 1: photo_1.jpg (置信度 0.95)

# 10:30 确认后标记
$ python handle_violations.py mark-private --type gambling
✓ 已标记 ID 1 为私密

# 11:00 标记其他违规为私密
$ python handle_violations.py mark-private --ids 2,3
✓ 已标记 ID 2 为私密
✓ 已标记 ID 3 为私密

# 17:00 查看观察中的
$ python handle_violations.py list-private
观察中的违规（共 3 条）
```

**第二天：观察决策**

```bash
# 09:00 查看观察中的图片
$ python handle_violations.py list-private

# 12:00 检查应用日志：
#   - ID 1（赌博）：正常 ✓
#   - ID 2（色情）：正常 ✓
#   - ID 3（暴力）：有用户投诉 ✗

# 14:00 确认隔离 ID 1 和 2
$ python handle_violations.py confirm-quarantine --ids 1,2 --dry-run
[预演] 将隔离以下图片：
  - ID 1: photo_1.jpg (gambling)
  - ID 2: photo_2.jpg (porn)

$ python handle_violations.py confirm-quarantine --ids 1,2
✓ 已隔离 ID 1
✓ 已隔离 ID 2

# 15:00 恢复 ID 3（误判）
$ python handle_violations.py restore-public --ids 3
✓ 已恢复 ID 3 为公开
```

**第三天：删除**

```bash
# 09:00 查看已隔离的
$ python handle_violations.py list-quarantined
已隔离的违规（共 2 条）
ID | 对象名 | 类型 | 隔离时间
1  | photo_1.jpg | gambling | 2026-05-20 14:00
2  | photo_2.jpg | porn | 2026-05-20 14:05

# 10:00 删除前预演
$ python handle_violations.py delete --ids 1,2 --dry-run
[预演] 将删除以下图片：
  - ID 1: photo_1.jpg (gambling)
  - ID 2: photo_2.jpg (porn)

# 11:00 实际删除
$ python handle_violations.py delete --ids 1,2
准备删除以下图片：
  - ID 1: photo_1.jpg
  - ID 2: photo_2.jpg
确定吗？(y/n) y
✓ 已删除 ID 1
✓ 已删除 ID 2
```

## 批量操作

### 批量标记私密

```bash
# 标记所有赌博图片
python handle_violations.py mark-private --type gambling

# 标记多个 ID
python handle_violations.py mark-private --ids 1,5,10,15,20
```

### 批量隔离

```bash
# 隔离 10 张图片
python handle_violations.py confirm-quarantine --ids $(seq 1 10 | paste -sd ',' -)
```

### 批量删除

```bash
# 删除所有已隔离的（需逐一确认）
IDS=$(python handle_violations.py list-quarantined --format ids)
python handle_violations.py delete --ids $IDS --force
```

## 日志和记录

### 违规处置日志

```bash
tail -f logs/violations.log

# 输出示例
[2026-05-19 10:30:00] | INFO | [mark-private] ID 1 已标记为私密
[2026-05-20 14:00:00] | INFO | [confirm-quarantine] ID 1 已隔离
[2026-05-21 11:00:00] | INFO | [delete] ID 1 已删除
```

### 数据库查询

```sql
-- 查看所有处置历史
SELECT id, object_key, violation_type, blocked, updated_at 
FROM image_scan_records 
ORDER BY updated_at DESC 
LIMIT 100;

-- 查看特定图片的处置历史
SELECT * FROM image_scan_records 
WHERE id = 1;
```

## 错误处理

### 常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| `ID not found` | ID 不存在 | 检查 ID 是否正确 |
| `Invalid state` | 状态转移不合法（如隔离已隔离的） | 检查当前状态 |
| `MinIO error` | 对象在 MinIO 中不存在 | 检查对象是否被删除 |
| `Permission denied` | MinIO 权限不足 | 检查凭据和桶权限 |

### 错误恢复

```bash
# 如果操作失败，可重试
python handle_violations.py confirm-quarantine --ids 1

# 检查当前状态
python handle_violations.py list-private  # 或 list-quarantined
```

## 安全检查清单

操作前检查：

- [ ] 查看新增违规（`list`）
- [ ] 确认违规类型和置信度
- [ ] 使用 `--dry-run` 预演操作
- [ ] 监控业务日志（标记后 24-48 小时）
- [ ] 确认应用无异常报错
- [ ] 用户反馈无申诉
- [ ] 然后执行确认隔离（`confirm-quarantine`）
- [ ] 最后删除（`delete`）

---

← [INDEX](./INDEX.md) | [USAGE](./USAGE.md) | [WORKFLOW](./WORKFLOW.md) →
