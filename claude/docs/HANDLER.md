# 处置工具详解（handle_violations.py）

## 概述

`handle_violations.py` 是系统的处置入口，负责管理违规图片的生命周期。

**核心特性**：直接在 MinIO 层物理隔离，原 URL 立即失效，控制力明确。

## MinIO 控制能力说明

| 命令 | MinIO 层操作 | 数据库变化 | 说明 |
|------|-------------|-----------|------|
| `quarantine` | ✅ 物理移入隔离桶 | blocked=2 | 原 URL 立即失效，真正隔离 |
| `restore` | ✅ 物理移回原桶 | blocked=0, is_violation=0 | 误判恢复，图片恢复可访问 |
| `delete` | ✅ 从隔离桶删除 | 记录删除 | 永久删除，不可恢复 |

> MinIO 不支持单对象 ACL，访问控制依赖**对象物理位置**（原桶 vs 隔离桶）而非权限标志。

## 工作流程

```
待处理违规 (blocked=0/1，在原桶)
    │
    ├─→ quarantine --suggestion Block   直接隔离（blocked → 2，移入隔离桶）
    │   ↓
    │   [blocked=2，在隔离桶]
    │   ├─→ restore --ids ...   误判恢复（移回原桶，blocked=0）
    │   └─→ delete  --ids ...   彻底删除（不可恢复）
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
| `quarantine` | 物理隔离到隔离桶 | → blocked=2 |
| `list-quarantined` | 查看已隔离的 | blocked=2 |
| `restore` | 从隔离桶移回原桶（误判） | → blocked=0 |
| `delete` | 从隔离桶彻底删除 | 记录删除 |

## 输出格式

所有列表命令输出统一列格式：

```
ID     violation_type    suggestion  label_cn    sub_label_cn          置信度    路径
1      Gamble            Block       违法         赌博                  0.95      images/uploads/photo_1.jpg
```

**列说明**：
- `ID`：数据库记录 ID，用于后续操作
- `violation_type`：违规类型（直接取 SubLabel 或 Label 的原始值）
- `suggestion`：IMS 建议（Block=建议拦截、Review=需人工审核）
- `label_cn`：一级 Label 中文名
- `sub_label_cn`：二级 SubLabel 中文名
- `置信度`：0–1 之间，越接近 1 越确定违规
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
# 查看所有待处理违规
python handle_violations.py list

# 只看 IMS 建议拦截的
python handle_violations.py list --suggestion Block

# 只看赌博类违规
python handle_violations.py list --sub-label Gamble

# 查看所有违法内容
python handle_violations.py list --label Illegal

# 查看高置信度违规
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
- `--dry-run`：预演，不实际执行

**示例**：

```bash
# 预演：查看将要隔离的 Block 建议图片
python handle_violations.py quarantine --suggestion Block --dry-run

# 直接隔离 IMS 建议拦截的所有违规
python handle_violations.py quarantine --suggestion Block

# 隔离所有违法内容（含赌博/毒品等）
python handle_violations.py quarantine --label Illegal

# 精细隔离赌博内容
python handle_violations.py quarantine --sub-label Gamble

# 组合过滤：高置信度赌博内容
python handle_violations.py quarantine --sub-label Gamble --confidence 0.9

# 按 ID 直接隔离
python handle_violations.py quarantine --ids 1,2,3
```

**执行效果**：
1. 对象从原桶**物理移动**到隔离桶（MinIO 层真正隔离，原 URL 失效）
2. 更新数据库 `blocked = 2`
3. 记录到 `violations.log`

### list-quarantined - 查看已隔离的

```bash
python handle_violations.py list-quarantined
```

列出所有已隔离（blocked=2）的图片。

**示例**：
```
已隔离的图片（隔离桶）（共 2 条）

ID     violation_type    suggestion  label_cn    sub_label_cn          置信度    路径
1      Gamble            Block       违法         赌博                  0.95      quarantine/images/photo_1.jpg
2      SexyBehavior      Block       色情         性行为                0.89      quarantine/images/photo_2.jpg
```

### restore - 误判恢复

```bash
python handle_violations.py restore --ids <ids> [--dry-run]
```

**选项**：
- `--ids <ids>`：要恢复的 ID，**必填**
- `--dry-run`：预演

**示例**：
```bash
python handle_violations.py restore --ids 3 --dry-run
python handle_violations.py restore --ids 3
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

**示例**：
```bash
# 预演
python handle_violations.py delete --ids 1,2 --dry-run

# 实际删除（需输入 DELETE 确认）
python handle_violations.py delete --ids 1,2
请输入 DELETE 确认删除：DELETE
已删除 ID 1 (photo_1.jpg)
已删除 ID 2 (photo_2.jpg)
```

**执行效果**：
1. 从隔离桶永久删除对象
2. 删除数据库记录
3. **不可恢复**
4. 记录到 `violations.log`

## 实际操作示例

### 批量处理 IMS 建议拦截的违规

```bash
# 1. 查看所有 Block 建议违规
$ python handle_violations.py list --suggestion Block

# 2. 预演隔离
$ python handle_violations.py quarantine --suggestion Block --dry-run

# 3. 实际隔离
$ python handle_violations.py quarantine --suggestion Block

# 4. 查看已隔离
$ python handle_violations.py list-quarantined

# 5. 彻底删除
$ python handle_violations.py delete --ids 1,2,3
请输入 DELETE 确认删除：DELETE
```

### 精细处理特定分类

```bash
# 隔离赌博内容
$ python handle_violations.py list --sub-label Gamble
$ python handle_violations.py quarantine --sub-label Gamble

# 处理所有违法内容（包含 Gamble/Drug 等子类）
$ python handle_violations.py quarantine --label Illegal --suggestion Block
```

### 发现误判后恢复

```bash
# 查看已隔离的图片
$ python handle_violations.py list-quarantined

# 预演恢复
$ python handle_violations.py restore --ids 3 --dry-run

# 实际恢复（图片从隔离桶移回原桶）
$ python handle_violations.py restore --ids 3
```

## 日志和记录

```bash
tail -f logs/violations.log
```

## 安全检查清单

- [ ] 先用 `list --suggestion Block` 查看待处理违规
- [ ] 用 `--dry-run` 预演操作
- [ ] 执行 `quarantine` 隔离（MinIO 层真正隔离）
- [ ] 用 `list-quarantined` 确认结果
- [ ] 最后执行 `delete`（需输入 DELETE 确认）

---

← [INDEX](./INDEX.md) | [USAGE](./USAGE.md) | [WORKFLOW](./WORKFLOW.md) →
