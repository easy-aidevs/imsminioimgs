# 使用指南

## 概览

本系统有两个主要入口：

| 工具 | 功能 | 命令 |
|------|------|------|
| **scanner.py** | 扫描图片并检测违规 | `python scanner.py` |
| **handle_violations.py** | 处置违规图片 | `python handle_violations.py <command>` |

## 工作流（两阶段）

```
违规图片 (blocked=0，在原桶)
    │
    ↓ quarantine（MinIO 物理移动，原 URL 立即失效）
    │
隔离图片 (blocked=2，在隔离桶)
    │
    ├─→ restore --ids ...   误判恢复：移回原桶，标记为非违规
    │
    └─→ delete  --ids ...   彻底删除（不可恢复）
```

> **MinIO 控制说明**：`quarantine` 命令将对象从原桶物理移动到隔离桶，原 URL 立即失效。`restore` 将对象移回原桶。两者都是 MinIO 层真正的隔离/恢复操作。

## 快速开始

```bash
# 1. 扫描图片（需要腾讯云凭据）
python scanner.py

# 2. 查看新增违规
python handle_violations.py list

# 3. 直接隔离 IMS 建议拦截的违规
python handle_violations.py quarantine --suggestion Block

# 4. 或按指定 ID 隔离
python handle_violations.py quarantine --ids 1,2,3
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

**场景 2：增量扫描（新增图片）**
```bash
python scanner.py  # 自动跳过已扫描的图片（路径去重）
```

**场景 3：强制重新扫描**
```bash
FORCE_RESCAN=true python scanner.py
```

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

所有列表和隔离命令支持以下过滤维度：

| 选项 | 说明 | 示例 |
|------|------|------|
| `--label <Label>` | 按 IMS 一级 Label 过滤 | `--label Illegal` |
| `--sub-label <SubLabel>` | 按 IMS 二级 SubLabel 精细过滤 | `--sub-label Gamble` |
| `--type <type>` | 按 violation_type 过滤 | `--type Gamble` |
| `--suggestion <s>` | 按 IMS 建议过滤 | `--suggestion Block` |
| `--confidence <float>` | 按最低置信度过滤 | `--confidence 0.9` |

**IMS 建议值**：`Block`（建议拦截）/ `Review`（需人工审核）/ `Pass`（通过）

**IMS 一级 Label 值**：`Polity`（政治）/ `Porn`（色情）/ `Sexy`（性感）/ `Terror`（暴恐）/ `Illegal`（违法）/ `Religion`（宗教识别）/ `Ad`（广告）/ `Teenager`（未成年识别）/ `Abuse`（谩骂）

**常见 SubLabel 值**：`Gamble`（赌博）/ `SexyBehavior`（性行为）/ `NationalOfficial`（国家公职人员）/ `Drug`（毒品）/ `Blood`（血腥）/ `QrCode`（二维码）

> **提示**：SubLabel 值直接来自 IMS API，请先用 `list` 命令查看实际的 `violation_type` / `sub_label` 值，再带入 `--sub-label` 过滤。

### 命令列表

#### 1. list - 查看待处理违规

```bash
python handle_violations.py list [--type <type>] [--sub-label <sub_label>] [--label <label>] [--suggestion <s>] [--confidence <float>] [--ids <ids>]
```

**输出示例**：

```
待处理的违规图片（原桶）（共 3 条）

ID     violation_type    suggestion  label_cn    sub_label_cn          置信度    路径
1      Gamble            Block       违法         赌博                  0.95      images/uploads/photo_1.jpg
2      SexyBehavior      Block       色情         性行为                0.89      images/uploads/photo_2.jpg
3      Blood             Review      暴恐         血腥                  0.72      images/uploads/photo_3.jpg
```

**过滤示例**：
```bash
# 只看 IMS 建议拦截的（最常用）
python handle_violations.py list --suggestion Block

# 只看赌博类违规
python handle_violations.py list --sub-label Gamble

# 查看所有违法内容（Illegal Label 下所有子类）
python handle_violations.py list --label Illegal

# 查看高置信度违规
python handle_violations.py list --confidence 0.9
```

#### 2. quarantine - 隔离（MinIO 物理移动）

```bash
python handle_violations.py quarantine [--ids <ids>] [--suggestion <s>] [--label <label>] [--sub-label <sub_label>] [--type <type>] [--confidence <float>] [--dry-run]
```

**选项**：
- `--ids <ids>`：指定 ID，如 `--ids 1,2,3`
- `--suggestion <s>`：按 IMS 建议过滤（`Block`/`Review`/`Pass`）
- `--label <label>`：按 IMS 一级 Label 过滤
- `--sub-label <sub_label>`：按 IMS SubLabel 过滤
- `--confidence <float>`：按最低置信度过滤
- `--dry-run`：预演，不实际执行

**示例**：
```bash
# 预演：查看将要隔离的 Block 建议图片
python handle_violations.py quarantine --suggestion Block --dry-run

# 直接隔离 IMS 建议拦截的所有违规（最常用）
python handle_violations.py quarantine --suggestion Block

# 隔离所有违法内容
python handle_violations.py quarantine --label Illegal

# 隔离赌博图片（精细过滤）
python handle_violations.py quarantine --sub-label Gamble

# 隔离高置信度赌博图片
python handle_violations.py quarantine --sub-label Gamble --confidence 0.9

# 按 ID 直接隔离（跳过观察期）
python handle_violations.py quarantine --ids 1,2,3
```

**执行后**：
- 图片从原桶**物理移动**到隔离桶（MinIO 层真正隔离，原 URL 失效）
- 数据库记录 `blocked=2`
- 只能 `restore` 或 `delete`，不可自动恢复

#### 3. list-quarantined - 查看已隔离的图片

```bash
python handle_violations.py list-quarantined
```

输出所有已隔离（blocked=2）的图片。

#### 4. restore - 误判恢复

```bash
python handle_violations.py restore --ids <ids> [--dry-run]
```

**选项**：
- `--ids <ids>`：要恢复的图片 ID，**必填**
- `--dry-run`：预演

**示例**：
```bash
python handle_violations.py restore --ids 3 --dry-run
python handle_violations.py restore --ids 3
```

**执行后**：
- 图片从隔离桶**物理移回**原桶（MinIO 层恢复）
- 数据库记录 `blocked=0, is_violation=0`（清除违规标记，视为误判）

#### 5. delete - 彻底删除（第三阶段）

```bash
python handle_violations.py delete --ids <ids> [--dry-run]
```

**选项**：
- `--ids <ids>`：要删除的图片 ID，**必填**
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

## 典型操作示例

### 场景 1：批量处理 IMS 建议拦截的违规

```bash
# 1. 查看 IMS 明确建议拦截的违规
$ python handle_violations.py list --suggestion Block
待处理的违规图片（原桶）（共 5 条）
ID     violation_type    suggestion  label_cn    sub_label_cn  置信度  路径
1      Gamble            Block       违法         赌博          0.95    images/photo_1.jpg
2      SexyBehavior      Block       色情         性行为        0.89    images/photo_2.jpg
...

# 2. 预演
$ python handle_violations.py quarantine --suggestion Block --dry-run

# 3. 实际隔离
$ python handle_violations.py quarantine --suggestion Block

# 4. 查看已隔离
$ python handle_violations.py list-quarantined

# 5. 确认后删除
$ python handle_violations.py delete --ids 1,2 --dry-run
$ python handle_violations.py delete --ids 1,2
请输入 DELETE 确认删除：DELETE
```

### 场景 2：精细处理特定分类

```bash
# 只处理赌博内容
$ python handle_violations.py list --sub-label Gamble
$ python handle_violations.py quarantine --sub-label Gamble

# 处理整个违法大类（含赌博、毒品等所有子类）
$ python handle_violations.py quarantine --label Illegal
```

### 场景 3：发现误判，恢复图片

```bash
# 1. 查看已隔离的图片
$ python handle_violations.py list-quarantined

# 2. 预演恢复
$ python handle_violations.py restore --ids 3 --dry-run

# 3. 实际恢复（图片从隔离桶移回原桶，标记为非违规）
$ python handle_violations.py restore --ids 3
```

## 日志查看

```bash
tail -f logs/scan.log        # 扫描日志
tail -f logs/error.log       # 错误日志
tail -f logs/violations.log  # 违规处置日志
```

## 环境配置

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
