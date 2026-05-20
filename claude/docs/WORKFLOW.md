# 三阶段工作流

## 概述

图片违规处置采用**三阶段渐进式工作流**，在确认隔离前提供 24-48 小时的观察期，降低误判风险。

## 工作流示意图

```
扫描器发现违规 (is_violation=1)
        ↓
╔═══════════════════════════════════════════════════╗
║ 第一阶段：发现 & 标记私密                           ║
║   (原桶，隐藏观察，可随时恢复)                      ║
╚═══════════════════════════════════════════════════╝
        ↓
    [观察期 24-48 小时]
    [监控业务日志 & 用户反馈]
        ↓
    ┌─────────┬──────────┐
    ↓         ↓          ↓
╔════════════════════════════════════════════════════╗
║ 第二阶段：观察决策                                   ║
║   基于监控结果，确认隔离或恢复                        ║
╚════════════════════════════════════════════════════╝
    ↓              ↓
[确认隔离]      [恢复公开]
    ↓              ↓
blocked=2      blocked=0
(移到隔离桶)    (视为误判)
    ↓              ↓
╔═══════════════════════════════════════════════════╗
║ 第三阶段：彻底删除(仅限隔离状态)                    ║
║   已隔离的图片，确认删除后彻底移除                   ║
╚═══════════════════════════════════════════════════╝
    ↓
[删除]
    ↓
记录删除，不可恢复
```

## 第一阶段：发现 & 标记私密

### 目标
发现违规图片，标记为私密以隐藏，同时保留恢复能力。

### 核心机制

**私密状态 (blocked=1)**：
- 图片**保留在原桶**（MinIO 不支持单对象 ACL，无法在存储层隔离）
- 数据库记录 `blocked=1`
- **访问控制由应用层承担**：业务代码需检查 `blocked` 字段，拒绝对外提供该图片的 URL 或代理下载

### 步骤

#### 1. 查看新增违规

```bash
python handle_violations.py list
```

输出所有尚未处理的违规图片（blocked=0）：

```
未处理的违规图片（共 3 条）

ID     violation_type    label        label_cn    sub_label_cn          置信度    路径
1      Gamble            Illegal      违法         赌博                  0.95      images/uploads/photo_1.jpg
2      SexyBehavior      Porn         色情         性行为                0.89      images/uploads/photo_2.jpg
3      Blood             Terror       暴恐         血腥                  0.92      images/uploads/photo_3.jpg
```

可以按标签过滤：

```bash
# 只看赌博类
python handle_violations.py list --sub-label Gamble

# 只看违法内容（Illegal Label）
python handle_violations.py list --label Illegal

# 只看色情
python handle_violations.py list --label Porn
```

#### 2. 标记为私密

根据违规类型或指定 ID 标记为私密：

```bash
# 方法 1：按 SubLabel 标记（推荐，精细）
python handle_violations.py mark-private --sub-label Gamble

# 方法 2：按 Label 标记（包含该 Label 下所有子类）
python handle_violations.py mark-private --label Illegal

# 方法 3：指定 ID 标记
python handle_violations.py mark-private --ids 2,3

# 方法 4：预演（不实际执行）
python handle_violations.py mark-private --sub-label Gamble --dry-run
```

执行后：
- 数据库更新 `blocked=1`（应用层须检查该字段并拦截访问）
- 图片仍在原桶，MinIO 层无访问限制

#### 3. 查看观察中的图片

```bash
python handle_violations.py list-private
```

输出所有处于观察期的图片（blocked=1）：

```
观察中的违规（共 3 条）

ID     violation_type    label        label_cn    sub_label_cn          置信度    路径
1      Gamble            Illegal      违法         赌博                  0.95      images/uploads/photo_1.jpg
2      SexyBehavior      Porn         色情         性行为                0.89      images/uploads/photo_2.jpg
3      Blood             Terror       暴恐         血腥                  0.92      images/uploads/photo_3.jpg
```

### 观察期内的操作

**建议流程**：
1. **第 1 步**：监控业务日志（如用户反馈、访问日志）
2. **第 2 步**：观察应用是否报错或异常
3. **第 3 步**：确认观察结果（24-48 小时后）

**监控要点**：
- 标记后应用是否报错（如 404 错误过多）
- 业务日志是否有异常访问请求
- 用户反馈是否有申诉恢复的请求
- 数据一致性是否受影响

## 第二阶段：观察决策

### 目标
根据观察结果，决定是确认隔离还是恢复为公开。

### 决策标准

#### 情景 A：观察正常 → 确认隔离

**条件**：
- 24-48 小时内无应用异常
- 无业务日志报错
- 确信图片违规

**执行**：
```bash
python handle_violations.py confirm-quarantine --ids 1,3
```

**效果**：
- 图片从原桶**移到隔离桶**
- 数据库更新 `blocked=2`
- **不可恢复**，仅能删除

#### 情景 B：观察异常 → 恢复公开

**条件**：
- 标记后出现异常（应用报错、用户投诉等）
- 判断为误判
- 需要保留图片

**执行**：
```bash
python handle_violations.py restore-public --ids 2
```

**效果**：
- 数据库更新 `blocked=0`，应用层恢复返回图片
- 视为误判，可重新分析或接受

### 步骤

#### 1. 收集观察数据

在观察期内收集：

```
时间线示例（赌博图片 ID=1）：

2026-05-19 10:00 - 标记为私密
           10:05 - 应用日志正常
           14:30 - 监控告警：无异常
2026-05-20 09:00 - 再次检查日志
           11:00 - 确认 24 小时无异常
           12:00 - 业务人员确认无投诉
           ↓
决策：观察正常，确认隔离
```

#### 2. 确认隔离（不可逆）

```bash
python handle_violations.py confirm-quarantine --ids 1
```

#### 3. 恢复公开（可逆）

```bash
python handle_violations.py restore-public --ids 2
```

### 查看隔离中的图片

```bash
python handle_violations.py list-quarantined
```

输出所有已隔离的图片（blocked=2）：

```
已隔离的违规（共 1 条）

ID     violation_type    label        label_cn    sub_label_cn          置信度    路径
1      Gamble            Illegal      违法         赌博                  0.95      quarantine/photo_1.jpg
```

## 第三阶段：彻底删除

### 目标
从隔离桶中彻底删除图片，不可恢复。

### 条件

仅能删除处于隔离状态（blocked=2）的图片。

### 步骤

#### 1. 预演删除（安全检查）

```bash
python handle_violations.py delete --ids 1 --dry-run
```

#### 2. 实际删除

执行时需要在终端输入 `DELETE` 进行确认：

```bash
python handle_violations.py delete --ids 1
请输入 DELETE 确认删除：DELETE
```

### 批量删除

```bash
# 删除多张图片
python handle_violations.py delete --ids 1,3,5
```

## 完整示例：3 天处理流程

### 第一天（发现阶段）

```bash
# 09:00 - 扫描新增图片
$ python scanner.py

# 10:00 - 查看违规
$ python handle_violations.py list
未处理的违规图片（共 3 条）
ID     violation_type    label     label_cn  sub_label_cn  置信度  路径
1      Gamble            Illegal   违法       赌博          0.95    images/photo_1.jpg
2      SexyBehavior      Porn      色情       性行为        0.89    images/photo_2.jpg
3      Blood             Terror    暴恐       血腥          0.92    images/photo_3.jpg

# 10:30 - 标记赌博图片为私密
$ python handle_violations.py mark-private --sub-label Gamble

# 11:00 - 标记其他违规为私密
$ python handle_violations.py mark-private --ids 2,3

# 17:00 - 监控：确认应用日志正常
[应用日志] 正常，无 404 或其他错误
[用户反馈] 无投诉
```

### 第二天（观察决策）

```bash
# 09:00 - 查看观察中的图片
$ python handle_violations.py list-private

# 12:00 - 监控 24 小时：
#   - ID 1（赌博）：日志正常，无异常 ✓
#   - ID 2（性行为）：日志正常，无异常 ✓
#   - ID 3（血腥）：有 1 个用户投诉，可能误判 ✗

# 14:00 - 确认隔离 ID 1 和 2
$ python handle_violations.py confirm-quarantine --ids 1,2

# 15:00 - 恢复 ID 3（误判）
$ python handle_violations.py restore-public --ids 3
```

### 第三天（删除）

```bash
# 09:00 - 查看已隔离的图片
$ python handle_violations.py list-quarantined

# 10:00 - 预演
$ python handle_violations.py delete --ids 1,2 --dry-run

# 11:00 - 实际删除
$ python handle_violations.py delete --ids 1,2
请输入 DELETE 确认删除：DELETE
```

## 关键设计原则

### 1. MinIO 控制能力

| 状态 | MinIO 层控制 | 访问能力 |
|------|-------------|---------|
| blocked=0 | 无（正常） | 可访问 |
| blocked=1 | **无**（仅 DB 标记） | 仍可通过直链访问；应用层检查后拒绝 |
| blocked=2 | **有**（移入隔离桶） | MinIO 层真正隔离，原 URL 失效 |

**快速路径（跳过观察期）**：对于 `suggestion=Block`、置信度 ≥ 0.9 的明确违规，可以直接 `confirm-quarantine`，无需经过 `mark-private` 观察期。

```bash
# 查出高置信度赌博内容
python handle_violations.py list --sub-label Gamble --confidence 0.9
# 直接隔离（MinIO 层立即生效）
python handle_violations.py confirm-quarantine --ids 1,2,3
```

### 2. 安全第一
- 没有直接删除操作，必须经过三个阶段
- 观察期（blocked=1）内可随时恢复
- 每个操作都有日志记录

### 3. 人工决策
- 系统标记，人工审核
- 观察期提供反馈机会
- 确认隔离前需明确决策

### 4. 可追溯
- 完整的数据库记录
- 所有操作有日志记录
- 支持审计和问责

### 5. 灵活恢复
- blocked=1 时可恢复（restore-public）
- blocked=2 时不可恢复（仅 delete）
- 清晰的状态转移

---

← [INDEX](./INDEX.md) | [USAGE](./USAGE.md) | [DATABASE](./DATABASE.md) →
