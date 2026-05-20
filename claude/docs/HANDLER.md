# 处置工具详解（handle_violations.py）

## 概述

`handle_violations.py` 是系统的处置入口，负责管理违规图片的生命周期。

**核心特性**：直接在 MinIO 层物理隔离，原 URL 立即失效，控制力明确。每次隔离自动关联批次ID，支持按批次追溯和还原。

## MinIO 控制能力说明

| 命令 | MinIO 层操作 | 数据库变化 | 说明 |
|------|-------------|-----------|------|
| `quarantine` | ✅ 物理移入隔离桶 | blocked=2, quarantine_batch_id 写入 | 原 URL 立即失效，真正隔离 |
| `restore` | ✅ 物理移回原桶 | blocked=0, is_violation=0 | 误判恢复，图片恢复可访问 |
| `delete` | ✅ 从隔离桶删除 | 记录删除 | 永久删除，不可恢复 |

> MinIO 不支持单对象 ACL，访问控制依赖**对象物理位置**（原桶 vs 隔离桶）而非权限标志。

## 工作流程

```
待处理违规 (blocked=0/1，在原桶)
    │
    ├─→ quarantine --suggestion Block         自动批次ID，输入 yes 确认
    ├─→ quarantine --suggestion Block \       手动批次ID，显示后输入 yes 确认
    │     --batch <batch_id>
    │   ↓
    │   [blocked=2，在隔离桶，quarantine_batch_id 已记录]
    │   ├─→ restore --ids ...           按 ID 还原（输入 yes）
    │   ├─→ restore --batch <batch_id>  按批次还原（重新输入批次ID确认）
    │   ├─→ restore --all               全量还原（输入 RESTORE-ALL 确认）
    │   └─→ delete  --ids ...           彻底删除（输入 DELETE 确认，不可恢复）
    │
    └─→ quarantine --ids ...    按 ID 直接隔离
```

## 基本用法

```bash
python handle_violations.py <command> [选项]
```

## 命令列表

| 命令 | 功能 | 状态变化 |
|------|------|---------|
| `list` | 查看待处理违规（原桶） | blocked=0/1 |
| `quarantine` | 物理隔离到隔离桶，记录批次ID | → blocked=2 |
| `list-quarantined` | 查看已隔离的（含批次ID） | blocked=2 |
| `restore` | 从隔离桶移回原桶（误判） | → blocked=0 |
| `delete` | 从隔离桶彻底删除 | 记录删除 |

## 输出格式

列表命令输出统一列格式。`list-quarantined` 额外显示批次ID列：

```
ID     violation_type    suggestion  label_cn    sub_label_cn    置信度   批次ID              路径
1      Gamble            Block       违法         赌博            0.95     gamble_wave1        images/photo_1.jpg
2      SexyBehavior      Block       色情         性行为          0.89     20260520_150010     images/photo_2.jpg
```

**列说明**：
- `ID`：数据库记录 ID，用于后续操作
- `violation_type`：违规类型（直接取 SubLabel 或 Label 的原始值）
- `suggestion`：IMS 建议（Block=建议拦截、Review=需人工审核）
- `label_cn`：一级 Label 中文名
- `sub_label_cn`：二级 SubLabel 中文名
- `置信度`：0–1 之间，越接近 1 越确定违规
- `批次ID`：隔离时关联的批次，仅 list-quarantined 显示
- `路径`：`桶名/对象键`

## IMS 标签过滤说明

> **提示**：SubLabel 值直接取自 IMS API 返回，请先用 `list` 命令查看实际的 `violation_type` / `sub_label` 列，再带入 `--sub-label` 过滤，避免拼写不一致（如 `Gamble` 和 `Gambling` 是不同值）。

所有列表和隔离命令支持四种过滤维度：

| 选项 | 过滤字段 | 示例 | 说明 |
|------|----------|------|------|
| `--suggestion <s>` | suggestion | `--suggestion Block` | 按 IMS 建议过滤（Block/Review/Pass） |
| `--label <Label>` | violation_label | `--label Illegal` | 按一级 Label 过滤，包含该 Label 下所有子类 |
| `--sub-label <SubLabel>` | sub_label | `--sub-label Gamble` | 按精细子类过滤 |
| `--type <type>` | violation_type | `--type Gamble` | 按 violation_type 过滤 |
| `--confidence <float>` | confidence | `--confidence 0.9` | 按最低置信度过滤 |

## 命令详解

### list - 查看待处理违规

```bash
python handle_violations.py list [选项]
```

**选项**：
- `--suggestion <s>`：IMS 建议过滤（Block/Review/Pass）
- `--type <violation_type>`：按 violation_type 过滤
- `--sub-label <sub_label>`：按 IMS SubLabel 过滤
- `--label <violation_label>`：按 IMS 一级 Label 过滤
- `--confidence <float>`：按最低置信度过滤
- `--ids <ids>`：按 ID 查看指定记录

**示例**：
```bash
python handle_violations.py list
python handle_violations.py list --suggestion Block
python handle_violations.py list --sub-label Gamble
python handle_violations.py list --label Illegal
python handle_violations.py list --confidence 0.9
```

### quarantine - 物理隔离

```bash
python handle_violations.py quarantine [选项]
```

**选项**（至少指定一个过滤条件或 --ids）：
- `--suggestion <s>`：按 IMS 建议过滤（推荐使用 `Block`）
- `--sub-label <sub_label>`：按 IMS SubLabel 隔离
- `--label <violation_label>`：按 IMS 一级 Label 隔离
- `--type <violation_type>`：按 violation_type 隔离
- `--confidence <float>`：按最低置信度过滤
- `--ids <ids>`：指定 ID，逗号分隔
- `--batch <batch_id>`：手动指定批次ID（留空则自动生成时间戳 `YYYYMMDD_HHMMSS`）
- `--dry-run`：预演，不实际执行（展示批次ID预览值）

**批次ID 策略**：

| 场景 | 推荐做法 |
|------|---------|
| 日常处理 | 不指定 `--batch`，使用自动时间戳 |
| 按类型分批 | `--batch gamble_20260520`、`--batch sexy_wave2` |
| 按来源分批 | `--batch user_report_0520`、`--batch scanner_daily` |

**示例**：

```bash
# 预演（查看批次ID预览）
python handle_violations.py quarantine --suggestion Block --dry-run

# 自动批次ID
python handle_violations.py quarantine --suggestion Block

# 手动批次ID（执行前显示并二次确认）
python handle_violations.py quarantine --label Illegal --batch illegal_0520
python handle_violations.py quarantine --sub-label Gamble --batch gamble_wave1

# 组合过滤
python handle_violations.py quarantine --sub-label Gamble --confidence 0.9

# 按 ID 直接隔离
python handle_violations.py quarantine --ids 1,2,3
```

**执行效果**：
1. 对象从原桶**物理移动**到隔离桶（MinIO 层真正隔离，原 URL 失效）
2. 更新数据库 `blocked = 2`，写入 `quarantine_batch_id`
3. 记录到 `violations.log`

### list-quarantined - 查看已隔离的

```bash
python handle_violations.py list-quarantined [--batch <batch_id>]
```

**选项**：
- `--batch <batch_id>`：按批次ID过滤

```bash
# 查看全部已隔离
python handle_violations.py list-quarantined

# 查看某批次
python handle_violations.py list-quarantined --batch gamble_wave1
```

### restore - 误判恢复

```bash
python handle_violations.py restore (--ids <ids> | --batch <batch_id> | --all) [--dry-run]
```

**三种模式与确认机制**：

| 选项 | 适用场景 | 确认方式 | 安全级别 |
|------|---------|---------|---------|
| `--ids <ids>` | 单条/少量误判 | 输入 `yes` | ★★☆ |
| `--batch <batch_id>` | 整批还原 | **重新输入批次ID** | ★★★ |
| `--all` | 紧急大规模还原 | 输入 `RESTORE-ALL` | ★★★ |

> 三种模式互斥，必须指定一种。`--dry-run` 预演时跳过确认环节。

**示例**：

```bash
# 按 ID 恢复
python handle_violations.py restore --ids 3 --dry-run
python handle_violations.py restore --ids 3

# 按批次恢复（需重新输入批次ID确认）
python handle_violations.py restore --batch gamble_wave1 --dry-run
python handle_violations.py restore --batch gamble_wave1
# 提示：请输入批次ID确认 (输入 gamble_wave1 确认): gamble_wave1

# 恢复全部（需输入 RESTORE-ALL）
python handle_violations.py restore --all --dry-run
python handle_violations.py restore --all
# 提示：确认恢复全部已隔离记录 (输入 RESTORE-ALL 确认): RESTORE-ALL
```

**执行效果**：
1. 对象从隔离桶**物理移回**原桶
2. 更新数据库 `blocked = 0, is_violation = 0`（清除违规标记，视为误判）
3. 清除 MinIO 标签

### delete - 彻底删除

```bash
python handle_violations.py delete --ids <ids> [--dry-run]
```

**选项**：
- `--ids <ids>`：要删除的 ID，**必填**
- `--dry-run`：预演

**注意：delete 需要在终端输入 `DELETE` 进行确认。此操作永久不可恢复。**

```bash
python handle_violations.py delete --ids 1,2 --dry-run
python handle_violations.py delete --ids 1,2
# 提示：请输入 DELETE 确认删除：DELETE
```

**执行效果**：
1. 从隔离桶永久删除对象
2. 删除数据库记录
3. **不可恢复**

## 实际操作示例

### 批量处理 IMS 建议拦截的违规（自动批次）

```bash
$ python handle_violations.py list --suggestion Block
$ python handle_violations.py quarantine --suggestion Block --dry-run
$ python handle_violations.py quarantine --suggestion Block
完成 - 成功: 5 失败: 0 跳过: 0  批次ID: 20260520_103022

$ python handle_violations.py list-quarantined
$ python handle_violations.py delete --ids 1,2,3,4,5
```

### 按类型分批隔离（手动批次）

```bash
# 赌博内容单独一批
$ python handle_violations.py quarantine --sub-label Gamble --batch gamble_0520

# 色情内容另一批
$ python handle_violations.py quarantine --label Porn --batch porn_0520

# 事后按批次查看
$ python handle_violations.py list-quarantined --batch gamble_0520
```

### 整批误判恢复

```bash
# 查看批次内容
$ python handle_violations.py list-quarantined --batch gamble_0520

# 预演确认无误
$ python handle_violations.py restore --batch gamble_0520 --dry-run

# 按批次还原（需重新输入批次ID）
$ python handle_violations.py restore --batch gamble_0520
⚠  即将恢复批次 [gamble_0520] 的 3 张图片到原桶（不可撤销）
请输入批次ID确认 (输入 gamble_0520 确认): gamble_0520
完成 - 成功: 3 失败: 0 跳过: 0
```

## 日志和记录

```bash
tail -f logs/violations.log
```

## 安全检查清单

- [ ] 先用 `list --suggestion Block` 查看待处理违规
- [ ] 用 `--dry-run` 预演操作，确认批次ID
- [ ] 执行 `quarantine` 隔离（手动批次ID语义更清晰）
- [ ] 用 `list-quarantined` 确认结果，记录批次ID
- [ ] 最后执行 `delete`（需输入 DELETE 确认）
- [ ] 如有误判：`restore --batch <批次ID>`（需重新输入批次ID确认）

---

← [INDEX](./INDEX.md) | [USAGE](./USAGE.md) | [WORKFLOW](./WORKFLOW.md) →
