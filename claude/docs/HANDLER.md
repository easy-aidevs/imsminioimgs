# 处置工具详解（handle_violations.py）

## 概述

`handle_violations.py` 是系统的处置入口，负责管理违规图片的生命周期，实现三阶段工作流：标记私密 → 观察决策 → 确认隔离/恢复 → 彻底删除。

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

## 输出格式

所有列表命令输出统一列格式：

```
ID     violation_type    label        label_cn    sub_label_cn          置信度    路径
6      Gambling          Illegal      违法         赌博                  0.95      bucket/path.jpg
```

**列说明**：
- `ID`：数据库记录 ID，用于后续操作
- `violation_type`：违规类型（直接取 SubLabel 或 Label 的原始值）
- `label`：IMS 一级 Label（Polity/Porn/Sexy/Terror/Illegal/Religion/Ad/Teenager/Abuse）
- `label_cn`：一级 Label 中文名
- `sub_label_cn`：二级 SubLabel 中文名
- `置信度`：0–1 之间，越接近 1 越确定违规
- `路径`：`桶名/对象键`

## IMS 标签过滤说明

所有列表和标记命令支持三种过滤维度：

| 选项 | 过滤字段 | 示例 | 说明 |
|------|----------|------|------|
| `--label <Label>` | violation_label | `--label Illegal` | 按一级 Label 过滤，包含该 Label 下所有子类 |
| `--sub-label <SubLabel>` | sub_label | `--sub-label Gambling` | 按精细子类过滤 |
| `--type <type>` | violation_type | `--type Gambling` | 按 violation_type 过滤（SubLabel 有值时与 sub_label 相同） |
| `--confidence <float>` | confidence | `--confidence 0.9` | 按最低置信度过滤 |

**常用过滤示例**：
```bash
# 查看所有违法内容（包含赌博、毒品等）
python handle_violations.py list --label Illegal

# 只查看赌博内容
python handle_violations.py list --sub-label Gambling

# 查看色情内容（一级 Label）
python handle_violations.py list --label Porn

# 查看高置信度违规
python handle_violations.py list --confidence 0.9
```

## 第一阶段：发现 & 标记私密

### list - 查看新增违规

```bash
python handle_violations.py list [选项]
```

**选项**：
- `--type <violation_type>`：按 violation_type 过滤
- `--sub-label <sub_label>`：按 IMS SubLabel 过滤
- `--label <violation_label>`：按 IMS 一级 Label 过滤
- `--confidence <float>`：按最低置信度过滤

**示例**：

```bash
# 查看所有新增违规
$ python handle_violations.py list

未处理的违规图片（blocked=0）（共 3 条）

ID     violation_type    label        label_cn    sub_label_cn          置信度    路径
1      Gambling          Illegal      违法         赌博                  0.95      images/uploads/photo_1.jpg
2      SexyBehavior      Porn         色情         性行为                0.89      images/uploads/photo_2.jpg
3      Blood             Terror       暴恐         血腥                  0.92      images/uploads/photo_3.jpg

# 只查看赌博类违规
$ python handle_violations.py list --sub-label Gambling

# 查看所有违法内容
$ python handle_violations.py list --label Illegal

# 查看高置信度违规
$ python handle_violations.py list --confidence 0.9
```

### mark-private - 标记为私密

```bash
python handle_violations.py mark-private [选项]
```

**选项**（至少指定一个过滤条件或 --ids）：
- `--type <violation_type>`：按 violation_type 标记
- `--sub-label <sub_label>`：按 IMS SubLabel 标记
- `--label <violation_label>`：按 IMS 一级 Label 标记
- `--confidence <float>`：按最低置信度过滤
- `--ids <1,2,3>`：指定 ID，逗号分隔
- `--dry-run`：预演，不实际执行

**示例**：

```bash
# 按 SubLabel 标记赌博图片为私密（推荐方式）
$ python handle_violations.py mark-private --sub-label Gambling

# 预演（不实际执行）
$ python handle_violations.py mark-private --sub-label Gambling --dry-run

# 按一级 Label 标记所有违法内容
$ python handle_violations.py mark-private --label Illegal

# 指定 ID 标记
$ python handle_violations.py mark-private --ids 2,3
```

**执行效果**：
1. 修改 MinIO 对象权限为私密（`set_object_private`）
2. 更新数据库 `blocked = 1`
3. 记录到 `violations.log`
4. **图片在原桶，但无法公开访问**

### list-private - 查看观察中的

```bash
python handle_violations.py list-private [选项]
```

**选项**：
- `--type <violation_type>`：按 violation_type 过滤
- `--sub-label <sub_label>`：按 IMS SubLabel 过滤
- `--label <violation_label>`：按 IMS 一级 Label 过滤
- `--confidence <float>`：按最低置信度过滤

**示例**：

```bash
$ python handle_violations.py list-private

观察中的违规（blocked=1）（共 3 条）

ID     violation_type    label        label_cn    sub_label_cn          置信度    路径
1      Gambling          Illegal      违法         赌博                  0.95      images/uploads/photo_1.jpg
2      SexyBehavior      Porn         色情         性行为                0.89      images/uploads/photo_2.jpg
3      Blood             Terror       暴恐         血腥                  0.92      images/uploads/photo_3.jpg
```

**观察期建议**（24–48 小时）：
- 监控业务日志（用户反馈、访问异常）
- 验证应用是否报错（404 等）
- 检查数据一致性（缓存是否清理）

## 第二阶段：观察决策

### confirm-quarantine - 确认隔离

```bash
python handle_violations.py confirm-quarantine --ids <ids> [选项]
```

**选项**：
- `--ids <ids>`：要隔离的 ID，**必需**（如 1,2,3）
- `--dry-run`：预演

**注意：此操作不可逆。** 执行后对象从原桶移到隔离桶，无法恢复。

**示例**：

```bash
# 预演
$ python handle_violations.py confirm-quarantine --ids 1,2 --dry-run

# 实际隔离
$ python handle_violations.py confirm-quarantine --ids 1,2
```

**执行效果**：
1. 将对象从原桶移到隔离桶
2. 更新数据库 `blocked = 2`
3. **此后仅能删除，不可恢复**
4. 记录到 `violations.log`

### restore-public - 恢复公开

```bash
python handle_violations.py restore-public --ids <ids> [选项]
```

**选项**：
- `--ids <ids>`：要恢复的 ID，**必需**
- `--dry-run`：预演

**示例**：

```bash
$ python handle_violations.py restore-public --ids 3 --dry-run
$ python handle_violations.py restore-public --ids 3
```

**执行效果**：
1. 修改 MinIO 对象权限为公开
2. 更新数据库 `blocked = 0`
3. **图片可再次访问**，视为误判

### list-quarantined - 查看已隔离的

```bash
python handle_violations.py list-quarantined
```

此命令不支持过滤选项，列出所有 blocked=2 的记录。

**示例**：

```bash
$ python handle_violations.py list-quarantined

已隔离的违规（blocked=2）（共 2 条）

ID     violation_type    label        label_cn    sub_label_cn          置信度    路径
1      Gambling          Illegal      违法         赌博                  0.95      quarantine/photo_1.jpg
2      SexyBehavior      Porn         色情         性行为                0.89      quarantine/photo_2.jpg
```

## 第三阶段：彻底删除

### delete - 删除隔离的图片

```bash
python handle_violations.py delete --ids <ids> [选项]
```

**选项**：
- `--ids <ids>`：要删除的 ID，**必需**
- `--dry-run`：预演

**注意：delete 需要在终端输入 `DELETE` 进行确认，而非 y/n。此操作永久不可恢复。**

**示例**：

```bash
# 预演
$ python handle_violations.py delete --ids 1,2 --dry-run

# 实际删除（需输入 DELETE 确认）
$ python handle_violations.py delete --ids 1,2
请输入 DELETE 确认删除：DELETE
已删除 ID 1 (photo_1.jpg)
已删除 ID 2 (photo_2.jpg)
```

**执行效果**：
1. 从隔离桶永久删除对象
2. 删除数据库记录
3. **不可恢复**
4. 记录到 `violations.log`

## 实际操作示例：3 天工作流

### 第一天：发现阶段

```bash
# 09:00 查看新增违规
$ python handle_violations.py list

未处理的违规图片（共 3 条）
ID     violation_type    label        label_cn    sub_label_cn          置信度    路径
1      Gambling          Illegal      违法         赌博                  0.95      images/photo_1.jpg
2      SexyBehavior      Porn         色情         性行为                0.89      images/photo_2.jpg
3      Blood             Terror       暴恐         血腥                  0.92      images/photo_3.jpg

# 10:00 预演：标记赌博图片为私密
$ python handle_violations.py mark-private --sub-label Gambling --dry-run

# 10:30 确认后执行
$ python handle_violations.py mark-private --sub-label Gambling

# 11:00 标记其他违规
$ python handle_violations.py mark-private --ids 2,3

# 17:00 查看观察中的
$ python handle_violations.py list-private
```

### 第二天：观察决策

```bash
# 09:00 查看观察中的
$ python handle_violations.py list-private

# 14:00 检查业务日志后：
#   - ID 1（赌博）：正常 → 确认隔离
#   - ID 2（性行为）：正常 → 确认隔离
#   - ID 3（血腥）：有用户投诉 → 恢复公开

$ python handle_violations.py confirm-quarantine --ids 1,2 --dry-run
$ python handle_violations.py confirm-quarantine --ids 1,2

$ python handle_violations.py restore-public --ids 3
```

### 第三天：删除

```bash
# 09:00 查看已隔离的
$ python handle_violations.py list-quarantined

# 10:00 预演
$ python handle_violations.py delete --ids 1,2 --dry-run

# 11:00 实际删除
$ python handle_violations.py delete --ids 1,2
请输入 DELETE 确认删除：DELETE
```

## 日志和记录

### 违规处置日志

```bash
tail -f logs/violations.log
```

### 数据库查询

```sql
-- 查看所有处置历史
SELECT id, object_key, violation_type, violation_label, sub_label, blocked, updated_at
FROM image_scan_records
ORDER BY updated_at DESC
LIMIT 100;
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
- [ ] 最后删除（`delete`，需输入 DELETE 确认）

---

← [INDEX](./INDEX.md) | [USAGE](./USAGE.md) | [WORKFLOW](./WORKFLOW.md) →
