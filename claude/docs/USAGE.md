# 使用指南

## 概览

本系统有两个主要入口：

| 工具 | 功能 | 命令 |
|------|------|------|
| **scanner.py** | 扫描图片并检测违规 | `python scanner.py` |
| **handle_violations.py** | 处置违规图片 | `python handle_violations.py <command>` |

## 快速开始

```bash
# 1. 扫描图片（可选，需要腾讯云凭据）
python scanner.py

# 2. 查看新增违规
python handle_violations.py list

# 3. 标记为私密（第一阶段）
python handle_violations.py mark-private --type gambling

# 4. 观察期后做决策
python handle_violations.py confirm-quarantine --ids 1,2,3
# 或恢复为公开
python handle_violations.py restore-public --ids 4,5
```

## Scanner.py（扫描器）

### 基本用法

```bash
python scanner.py [选项]
```

### 主要选项

| 选项 | 说明 | 示例 |
|------|------|------|
| `--bucket` | 指定要扫描的桶（可多个） | `--bucket images --bucket photos` |
| `--force-rescan` | 强制重新扫描已扫描的图片 | `--force-rescan` |
| `--skip-ims` | 跳过 IMS 扫描（只做去重） | `--skip-ims` |

### 场景

**场景 1：首次全量扫描**
```bash
python scanner.py
```
- 扫描所有配置的桶
- 对每张图片调用腾讯云 IMS
- 结果存入数据库

**场景 2：增量扫描（新增图片）**
```bash
python scanner.py
```
- 自动跳过已扫描的图片（第1层去重）
- 只扫描新增图片

**场景 3：强制重新扫描**
```bash
python scanner.py --force-rescan
```
- 忽略已有扫描记录
- 重新扫描所有图片
- 用于更新违规信息或调整阈值

### 输出

```
[2026-05-19 10:00:00] | INFO | 扫描器初始化完成
[2026-05-19 10:00:01] | INFO | 遍历完成，共 100 张图片
[2026-05-19 10:00:10] | INFO | 扫描完成
  - 总数：100
  - 已扫描：95
  - 复用结果：5
  - 检出违规：3 张
```

## Handle_violations.py（处置工具）

### 基本用法

```bash
python handle_violations.py <command> [选项]
```

### 命令列表

#### 1. list - 查看新增违规

```bash
python handle_violations.py list
```

输出：
```
未处理的违规图片（blocked=0）（共 3 条）

ID  | 对象名                  | 类型    | 置信度 | 首次发现
----|------------------------|--------|--------|----------
1   | uploads/photo_1.jpg     | gambling| 0.95   | 2026-05-19
2   | uploads/photo_2.jpg     | porn   | 0.89   | 2026-05-19
3   | uploads/photo_3.jpg     | violence| 0.92   | 2026-05-19
```

#### 2. mark-private - 标记为私密（第一阶段）

```bash
python handle_violations.py mark-private --type <type> [选项]
```

**选项**：
- `--type <type>`：违规类型（gambling/porn/violence/politics/terrorism/ads/contraband/vulgar/qrcode）
- `--ids <ids>`：指定 ID，如 `--ids 1,2,3`（不指定则处理该类型的所有）
- `--dry-run`：预演，不实际执行

**示例**：
```bash
# 查看将要标记的赌博图片
python handle_violations.py mark-private --type gambling --dry-run

# 实际标记所有赌博图片为私密
python handle_violations.py mark-private --type gambling

# 标记指定 ID 为私密
python handle_violations.py mark-private --ids 1,2,3
```

**执行后**：
- 图片权限改为私密，无法公开访问
- 数据库记录 `blocked=1`
- 开始观察期（24-48 小时）

#### 3. list-private - 查看观察中的图片

```bash
python handle_violations.py list-private
```

输出观察期内（blocked=1）的所有图片。

#### 4. confirm-quarantine - 确认隔离（第二阶段）

```bash
python handle_violations.py confirm-quarantine --ids <ids>
```

**选项**：
- `--ids <ids>`：要隔离的图片 ID，必需

**示例**：
```bash
# 隔离 ID 为 1, 2, 3 的图片
python handle_violations.py confirm-quarantine --ids 1,2,3
```

**执行后**：
- 图片从原桶移到隔离桶
- 数据库记录 `blocked=2`
- 不可恢复，只能删除

#### 5. restore-public - 恢复为公开（第二阶段）

```bash
python handle_violations.py restore-public --ids <ids>
```

**选项**：
- `--ids <ids>`：要恢复的图片 ID，必需

**示例**：
```bash
# 恢复 ID 为 4, 5 的图片为公开
python handle_violations.py restore-public --ids 4,5
```

**执行后**：
- 图片权限改回公开
- 数据库记录 `blocked=0`
- 视为误判，可再次扫描

#### 6. list-quarantined - 查看已隔离的图片

```bash
python handle_violations.py list-quarantined
```

输出所有已隔离（blocked=2）的图片。

#### 7. delete - 彻底删除（第三阶段）

```bash
python handle_violations.py delete --ids <ids>
```

**选项**：
- `--ids <ids>`：要删除的图片 ID，必需
- `--dry-run`：预演，不实际执行

**示例**：
```bash
# 预演删除
python handle_violations.py delete --ids 1,2,3 --dry-run

# 实际删除
python handle_violations.py delete --ids 1,2,3
```

**执行后**：
- 图片从隔离桶永久删除
- 数据库记录删除
- **不可恢复**

## 三阶段工作流示例

### 第一天：发现并标记私密

```bash
# 1. 查看新增违规
$ python handle_violations.py list
未处理的违规图片（共 3 条）
ID | 对象名 | 类型 | 置信度
1 | photo_1.jpg | gambling | 0.95
2 | photo_2.jpg | porn | 0.89
3 | photo_3.jpg | violence | 0.92

# 2. 标记赌博图片为私密
$ python handle_violations.py mark-private --type gambling
✓ 已标记 ID 1 为私密 (photo_1.jpg)
✓ 已标记 ID 3 为私密 (photo_3.jpg)

# 3. 监控业务日志，观察是否有报错
[观察期内：24-48 小时]
```

### 第二天：观察并决策

```bash
# 1. 查看观察中的图片
$ python handle_violations.py list-private
观察中的违规（共 2 条）
ID | 对象名 | 类型 | 标记时间
1 | photo_1.jpg | gambling | 2026-05-19 10:00
3 | photo_3.jpg | violence | 2026-05-19 10:10

# 2. 根据业务日志和反馈决策：
#    - ID 1（赌博）：日志正常 → 确认隔离
#    - ID 3（暴力）：有用户投诉 → 恢复公开

$ python handle_violations.py confirm-quarantine --ids 1
✓ 已隔离 ID 1

$ python handle_violations.py restore-public --ids 3
✓ 已恢复 ID 3 为公开
```

### 第三天：彻底删除

```bash
# 1. 查看已隔离的图片
$ python handle_violations.py list-quarantined
已隔离的违规（共 1 条）
ID | 对象名 | 类型 | 隔离时间
1 | photo_1.jpg | gambling | 2026-05-19 11:00

# 2. 删除已隔离的图片
$ python handle_violations.py delete --ids 1
✓ 已删除 ID 1 (photo_1.jpg)
```

## 日志查看

运行时生成的日志位置：`logs/`

```bash
# 查看完整运行日志
tail -f logs/scan.log

# 查看错误日志
tail -f logs/error.log

# 查看违规处置日志
tail -f logs/violations.log
```

## 环境配置

关键的环境变量（`.env` 文件）：

```ini
# MinIO 配置
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET_NAME=images
QUARANTINE_BUCKET_NAME=quarantine

# MySQL 配置
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASSWORD=password
MYSQL_DATABASE=image_security

# 腾讯云配置（仅 scanner.py 需要）
TENCENT_SECRET_ID=xxx
TENCENT_SECRET_KEY=xxx
TENCENT_REGION=ap-beijing
```

详见 `.env.example`。

---

← [INDEX](./INDEX.md) | [QUICK_START](./QUICK_START.md) | [ARCHITECTURE](./ARCHITECTURE.md) →
