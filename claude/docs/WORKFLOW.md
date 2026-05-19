# 三阶段工作流

## 概述

图片违规处置采用**三阶段渐进式工作流**，在确认隔离前提供 24-48 小时的观察期，降低误判风险。

## 工作流示意图

```
扫描器发现违规 (is_violation=1)
        ↓
╔═══════════════════════════════════════════════════╗
║ 🔸 第一阶段：发现 & 标记私密                        ║
║   (原桶，隐藏观察，可随时恢复)                      ║
╚═══════════════════════════════════════════════════╝
        ↓
    [观察期 24-48 小时]
    [监控业务日志 & 用户反馈]
        ↓
    ┌─────────┬──────────┐
    ↓         ↓          ↓
║════════════════════════════════════════════════════╗║
║ 🟡 第二阶段：观察决策                                ║
║   基于监控结果，确认隔离或恢复                        ║
╚════════════════════════════════════════════════════╝
    ↓              ↓
[确认隔离]      [恢复公开]
    ↓              ↓
blocked=2      blocked=0
(移到隔离桶)    (视为误判)
    ↓              ↓
╔═══════════════════════════════════════════════════╗
║ 🔴 第三阶段：彻底删除(仅限隔离状态)                 ║
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
- 图片**保留在原桶**
- 使用 MinIO 权限控制：`set_object_private()`
- 无法通过公开链接访问
- 数据库记录 `blocked=1`

### 步骤

#### 1. 查看新增违规

```bash
python handle_violations.py list
```

输出所有尚未处理的违规图片（blocked=0）：

```
未处理的违规图片（共 3 条）

ID  | 对象名                  | 类型      | 置信度 | 首次发现
----|------------------------|----------|--------|----------
1   | uploads/photo_1.jpg     | gambling  | 0.95   | 2026-05-19
2   | uploads/photo_2.jpg     | porn      | 0.89   | 2026-05-19
3   | uploads/photo_3.jpg     | violence  | 0.92   | 2026-05-19
```

#### 2. 标记为私密

根据违规类型或指定 ID 标记为私密：

```bash
# 方法 1：按类型标记（如赌博）
python handle_violations.py mark-private --type gambling

# 方法 2：指定 ID 标记
python handle_violations.py mark-private --ids 2,3

# 方法 3：预演（不实际执行）
python handle_violations.py mark-private --type gambling --dry-run
```

执行后：
- 图片权限改为私密
- 用户无法通过公开链接访问
- 数据库更新 `blocked=1`

#### 3. 查看观察中的图片

```bash
python handle_violations.py list-private
```

输出所有处于观察期的图片（blocked=1）：

```
观察中的违规（共 3 条）

ID  | 对象名                  | 类型      | 标记时间
----|------------------------|----------|----------
1   | uploads/photo_1.jpg     | gambling  | 2026-05-19 10:00
2   | uploads/photo_2.jpg     | porn      | 2026-05-19 10:05
3   | uploads/photo_3.jpg     | violence  | 2026-05-19 10:10
```

### 观察期内的操作

**建议流程**：
1. **第 1 步**：监控业务日志（如用户反馈、访问日志）
2. **第 2 步**：观察应用是否报错或异常
3. **第 3 步**：确认观察结果（24-48 小时后）

**监控要点**：
- ✓ 标记后应用是否报错（如 404 错误过多）
- ✓ 业务日志是否有异常访问请求
- ✓ 用户反馈是否有申诉恢复的请求
- ✓ 数据一致性是否受影响

## 第二阶段：观察决策

### 目标
根据观察结果，决定是确认隔离还是恢复为公开。

### 决策标准

#### 情景 A：观察正常 → 确认隔离

**条件**：
- ✓ 24-48 小时内无应用异常
- ✓ 无业务日志报错
- ✓ 确信图片违规

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
- ✗ 标记后出现异常（应用报错、用户投诉等）
- ✗ 判断为误判
- ✗ 需要保留图片

**执行**：
```bash
python handle_violations.py restore-public --ids 2
```

**效果**：
- 图片权限改回**公开**
- 数据库更新 `blocked=0`
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

输出：
✓ 已隔离 ID 1 (uploads/photo_1.jpg)
  - 从 'images' 移到 'quarantine' 桶
  - 数据库更新 blocked=2
  - 此后仅能删除，不可恢复
```

#### 3. 恢复公开（可逆）

```bash
python handle_violations.py restore-public --ids 2

输出：
✓ 已恢复 ID 2 为公开 (uploads/photo_2.jpg)
  - 权限改回公开
  - 数据库更新 blocked=0
  - 视为误判，图片可再次访问
```

### 查看隔离中的图片

```bash
python handle_violations.py list-quarantined
```

输出所有已隔离的图片（blocked=2）：

```
已隔离的违规（共 1 条）

ID  | 对象名                  | 类型      | 隔离时间
----|------------------------|----------|----------
1   | uploads/photo_1.jpg     | gambling  | 2026-05-20 12:00
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

输出：
[预演] 将删除以下图片：
  - ID 1: uploads/photo_1.jpg (gambling, 隔离于 2026-05-20 12:00)
```

#### 2. 实际删除

```bash
python handle_violations.py delete --ids 1

输出：
✓ 已删除 ID 1 (uploads/photo_1.jpg)
  - 从隔离桶 'quarantine' 永久删除
  - 数据库记录移除
  - 不可恢复
```

### 批量删除

```bash
# 删除多张图片
python handle_violations.py delete --ids 1,3,5

# 删除一个时间范围内的图片（需在代码中实现）
# python handle_violations.py delete --before 2026-05-15
```

## 完整示例：3 天处理流程

### 第一天（发现阶段）

```bash
# 09:00 - 扫描新增图片
$ python scanner.py
[INFO] 扫描完成
  - 总数：50
  - 已扫描：45
  - 检出违规：3 张

# 10:00 - 查看违规
$ python handle_violations.py list
未处理的违规图片（共 3 条）
ID | 对象名 | 类型 | 置信度
1 | photo_1.jpg | gambling | 0.95
2 | photo_2.jpg | porn | 0.89
3 | photo_3.jpg | violence | 0.92

# 10:30 - 标记赌博图片为私密
$ python handle_violations.py mark-private --type gambling
✓ 已标记 ID 1 为私密

# 11:00 - 标记其他违规为私密
$ python handle_violations.py mark-private --ids 2,3
✓ 已标记 ID 2 为私密
✓ 已标记 ID 3 为私密

# 17:00 - 监控：确认应用日志正常
[应用日志] 正常，无 404 或其他错误
[用户反馈] 无投诉
```

### 第二天（观察决策）

```bash
# 09:00 - 查看观察中的图片
$ python handle_violations.py list-private
观察中的违规（共 3 条）
ID | 对象名 | 类型 | 标记时间
1 | photo_1.jpg | gambling | 2026-05-19 10:30
2 | photo_2.jpg | porn | 2026-05-19 11:00
3 | photo_3.jpg | violence | 2026-05-19 11:00

# 12:00 - 监控 24 小时：
#   - ID 1（赌博）：日志正常，无异常 ✓
#   - ID 2（色情）：日志正常，无异常 ✓
#   - ID 3（暴力）：有 1 个用户投诉，可能误判 ✗

# 14:00 - 确认隔离 ID 1 和 2
$ python handle_violations.py confirm-quarantine --ids 1,2
✓ 已隔离 ID 1
✓ 已隔离 ID 2

# 15:00 - 恢复 ID 3（误判）
$ python handle_violations.py restore-public --ids 3
✓ 已恢复 ID 3 为公开
```

### 第三天（删除）

```bash
# 09:00 - 查看已隔离的图片
$ python handle_violations.py list-quarantined
已隔离的违规（共 2 条）
ID | 对象名 | 类型 | 隔离时间
1 | photo_1.jpg | gambling | 2026-05-20 14:00
2 | photo_2.jpg | porn | 2026-05-20 14:00

# 10:00 - 再次确认隔离内容，然后删除
$ python handle_violations.py delete --ids 1,2 --dry-run
[预演] 将删除：
  - ID 1: photo_1.jpg (gambling)
  - ID 2: photo_2.jpg (porn)

# 11:00 - 实际删除
$ python handle_violations.py delete --ids 1,2
✓ 已删除 ID 1
✓ 已删除 ID 2
```

## 关键设计原则

### 1. 安全第一
- 没有直接删除操作，必须经过三个阶段
- 观察期内可随时恢复
- 每个操作都有日志记录

### 2. 人工决策
- 系统标记，人工审核
- 观察期提供反馈机会
- 确认隔离前需明确决策

### 3. 可追溯
- 完整的数据库记录
- 所有操作有日志记录
- 支持审计和问责

### 4. 灵活恢复
- blocked=1 时可恢复
- blocked=2 时不可恢复（仅删除）
- 清晰的状态转移

---

← [INDEX](./INDEX.md) | [USAGE](./USAGE.md) | [DATABASE](./DATABASE.md) →
