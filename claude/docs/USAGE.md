# 使用指南

## 概览

本系统有两个主要入口：

| 工具 | 功能 | 命令 |
|------|------|------|
| **scanner.py** | 扫描图片并检测违规 | `python scanner.py` |
| **handle_violations.py** | 处置违规图片 | `python handle_violations.py <command>` |

## 快速开始

```bash
# 1. 扫描图片（需要腾讯云凭据）
python scanner.py

# 2. 查看新增违规
python handle_violations.py list

# 3. 标记为私密（第一阶段）
python handle_violations.py mark-private --sub-label Gamble

# 4. 观察期后做决策
python handle_violations.py confirm-quarantine --ids 1,2,3
# 或恢复为公开
python handle_violations.py restore-public --ids 4,5
```

## Scanner.py（扫描器）

### 基本用法

```bash
python scanner.py
```

Scanner.py 没有命令行参数，所有配置通过环境变量（`.env` 文件）控制。

### 环境变量

| 环境变量 | 说明 | 示例 |
|----------|------|------|
| `SCAN_BUCKET_NAME` | 覆盖要扫描的桶名 | `SCAN_BUCKET_NAME=photos` |
| `SCAN_PREFIX` | 路径前缀过滤（默认空） | `SCAN_PREFIX=uploads/` |
| `FORCE_RESCAN=true` | 强制重新扫描所有图片 | `FORCE_RESCAN=true` |
| `SCAN_LIMIT` | 限制扫描数量 | `SCAN_LIMIT=100` |

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
FORCE_RESCAN=true python scanner.py
```
- 忽略已有扫描记录
- 重新扫描所有图片
- 用于更新违规信息或调整阈值

**场景 4：限量扫描（测试）**
```bash
SCAN_LIMIT=50 python scanner.py
```

### 输出

```
统计 - 总:100 | IMS扫描:80 | 路径复用:10 | 内容复用:5 | 特征复用:5 | 复用合计:20 | 违规:3 | 错误:0
```

## Handle_violations.py（处置工具）

### 基本用法

```bash
python handle_violations.py <command> [选项]
```

### IMS 标签过滤

所有列表和标记命令支持三种 IMS 标签维度过滤：

| 选项 | 说明 | 示例 |
|------|------|------|
| `--label <Label>` | 按 IMS 一级 Label 过滤 | `--label Illegal` |
| `--sub-label <SubLabel>` | 按 IMS 二级 SubLabel 精细过滤 | `--sub-label Gamble` |
| `--type <type>` | 按 violation_type 过滤 | `--type Gambling` |
| `--confidence <float>` | 按最低置信度过滤 | `--confidence 0.9` |

**IMS 一级 Label 值**：`Polity`（政治）/ `Porn`（色情）/ `Sexy`（性感）/ `Terror`（暴恐）/ `Illegal`（违法）/ `Religion`（宗教识别）/ `Ad`（广告）/ `Teenager`（未成年识别）/ `Abuse`（谩骂）

**常见 SubLabel 值**：`Gamble`（赌博）/ `SexyBehavior`（性行为）/ `NationalOfficial`（国家公职人员）/ `Drug`（毒品）/ `Blood`（血腥）/ `QrCode`（二维码）

> **提示**：SubLabel 值直接来自 IMS API，请先用 `list` 命令查看实际的 `violation_type` / `sub_label` 值，再带入 `--sub-label` 过滤。

### 命令列表

#### 1. list - 查看新增违规

```bash
python handle_violations.py list [--type <type>] [--sub-label <sub_label>] [--label <label>] [--confidence <float>]
```

**输出示例**：

```
未处理的违规图片（blocked=0）（共 3 条）

ID     violation_type    label        label_cn    sub_label_cn          置信度    路径
1      Gamble            Illegal      违法         赌博                  0.95      images/uploads/photo_1.jpg
2      SexyBehavior      Porn         色情         性行为                0.89      images/uploads/photo_2.jpg
3      Blood             Terror       暴恐         血腥                  0.92      images/uploads/photo_3.jpg
```

**过滤示例**：
```bash
# 只查看赌博类违规
python handle_violations.py list --sub-label Gamble

# 查看所有违法内容（Illegal Label 下所有子类）
python handle_violations.py list --label Illegal

# 查看高置信度违规
python handle_violations.py list --confidence 0.9
```

#### 2. mark-private - 标记为私密（第一阶段）

```bash
python handle_violations.py mark-private [--type <type>] [--sub-label <sub_label>] [--label <label>] [--confidence <float>] [--ids <ids>] [--dry-run]
```

**选项**：
- `--sub-label <sub_label>`：按 IMS SubLabel 标记（推荐）
- `--label <label>`：按 IMS 一级 Label 标记
- `--type <type>`：按 violation_type 标记
- `--confidence <float>`：按最低置信度过滤
- `--ids <ids>`：指定 ID，如 `--ids 1,2,3`
- `--dry-run`：预演，不实际执行

**示例**：
```bash
# 预演：查看将要标记的赌博图片
python handle_violations.py mark-private --sub-label Gamble --dry-run

# 实际标记所有赌博图片为私密
python handle_violations.py mark-private --sub-label Gamble

# 标记所有违法内容
python handle_violations.py mark-private --label Illegal

# 标记指定 ID 为私密
python handle_violations.py mark-private --ids 1,2,3
```

**执行后**：
- 数据库记录 `blocked=1`（MinIO 不支持单对象 ACL，图片仍在原桶）
- **应用层须检查 `blocked` 字段**，拒绝返回 `blocked=1` 的图片 URL
- 开始观察期（24-48 小时）

#### 3. list-private - 查看观察中的图片

```bash
python handle_violations.py list-private [--type <type>] [--sub-label <sub_label>] [--label <label>] [--confidence <float>]
```

输出观察期内（blocked=1）的图片，支持同样的过滤选项。

#### 4. confirm-quarantine - 确认隔离（第二阶段）

```bash
python handle_violations.py confirm-quarantine --ids <ids> [--dry-run]
```

**选项**：
- `--ids <ids>`：要隔离的图片 ID，**必需**
- `--dry-run`：预演

**示例**：
```bash
python handle_violations.py confirm-quarantine --ids 1,2,3 --dry-run
python handle_violations.py confirm-quarantine --ids 1,2,3
```

**执行后**：
- 图片从原桶移到隔离桶
- 数据库记录 `blocked=2`
- 不可恢复，只能删除

#### 5. restore-public - 恢复为公开（第二阶段）

```bash
python handle_violations.py restore-public --ids <ids> [--dry-run]
```

**示例**：
```bash
python handle_violations.py restore-public --ids 4,5
```

**执行后**：
- 数据库记录 `blocked=0`，应用层恢复正常返回图片
- 视为误判，可再次扫描

#### 6. list-quarantined - 查看已隔离的图片

```bash
python handle_violations.py list-quarantined
```

输出所有已隔离（blocked=2）的图片，无过滤选项。

#### 7. delete - 彻底删除（第三阶段）

```bash
python handle_violations.py delete --ids <ids> [--dry-run]
```

**选项**：
- `--ids <ids>`：要删除的图片 ID，**必需**
- `--dry-run`：预演，不实际执行

**重要**：实际删除时需在终端输入 `DELETE` 进行确认，而非 y/n。

**示例**：
```bash
# 预演删除
python handle_violations.py delete --ids 1,2,3 --dry-run

# 实际删除（会提示输入 DELETE 确认）
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
ID     violation_type    label     label_cn  sub_label_cn  置信度  路径
1      Gamble            Illegal   违法       赌博          0.95    images/photo_1.jpg
2      SexyBehavior      Porn      色情       性行为        0.89    images/photo_2.jpg
3      Blood             Terror    暴恐       血腥          0.92    images/photo_3.jpg

# 2. 标记赌博图片为私密
$ python handle_violations.py mark-private --sub-label Gamble

# 3. 标记其他违规
$ python handle_violations.py mark-private --ids 2,3

# 4. 监控业务日志，观察是否有报错
[观察期内：24-48 小时]
```

### 第二天：观察并决策

```bash
# 1. 查看观察中的图片
$ python handle_violations.py list-private

# 2. 根据业务日志和反馈决策：
#    - ID 1（赌博）：日志正常 → 确认隔离
#    - ID 3（血腥）：有用户投诉 → 恢复公开

$ python handle_violations.py confirm-quarantine --ids 1,2
$ python handle_violations.py restore-public --ids 3
```

### 第三天：彻底删除

```bash
# 1. 查看已隔离的图片
$ python handle_violations.py list-quarantined

# 2. 删除已隔离的图片
$ python handle_violations.py delete --ids 1,2
请输入 DELETE 确认删除：DELETE
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
