# 工作流

## 概述

图片违规处置采用**两阶段工作流**：直接隔离（MinIO 物理移动）或恢复，无需观察期。

> **为什么去掉"私密观察期"？**
> MinIO 不支持单对象 ACL，旧版"标记私密"只更新数据库，并不能在 MinIO 层阻止访问。
> 新方案直接执行 `quarantine`（物理移到隔离桶），原 URL 立即失效，控制力更明确。

## 工作流示意图

```
扫描器发现违规 (is_violation=1, blocked=0，对象在原桶)
        ↓
╔═══════════════════════════════════════════════════════╗
║ 第一步：查看违规                                       ║
║   list --suggestion Block     查看 IMS 建议拦截的     ║
║   list --label Illegal        按分类过滤              ║
║   list --confidence 0.9       按置信度过滤            ║
╚═══════════════════════════════════════════════════════╝
        ↓
╔═══════════════════════════════════════════════════════╗
║ 第二步：隔离（MinIO 物理移动，原 URL 立即失效）         ║
║   quarantine --suggestion Block         自动生成批次ID ║
║   quarantine --suggestion Block \       手动指定批次ID ║
║     --batch gamble_20260520             (执行前确认)   ║
╚═══════════════════════════════════════════════════════╝
        ↓
   blocked=2（对象在隔离桶，quarantine_batch_id 已记录）
        │
    ┌───┴───┐
    ↓       ↓
[restore]  [delete]
误判恢复   彻底删除
blocked=0  记录删除
移回原桶   不可恢复
```

## MinIO 控制能力对照

| 命令 | MinIO 层操作 | 效果 |
|------|-------------|------|
| `quarantine` | ✅ 物理移入隔离桶 | 原 URL 立即失效，真正隔离 |
| `restore` | ✅ 物理移回原桶 | 图片恢复可访问 |
| `delete` | ✅ 从隔离桶删除 | 永久删除，不可恢复 |

## 第一步：查看违规

```bash
# 查看所有待处理违规
python handle_violations.py list

# 只看 IMS 明确建议拦截的（最常用起点）
python handle_violations.py list --suggestion Block

# 按分类查看
python handle_violations.py list --label Illegal        # 违法类（含赌博/毒品等）
python handle_violations.py list --sub-label Gamble     # 只看赌博
python handle_violations.py list --label Porn           # 色情类

# 按置信度查看
python handle_violations.py list --confidence 0.9
```

**输出示例**：
```
待处理的违规图片（原桶）（共 3 条）

ID     violation_type    suggestion  label_cn    sub_label_cn          置信度    路径
1      Gamble            Block       违法         赌博                  0.95      images/uploads/photo_1.jpg
2      SexyBehavior      Block       色情         性行为                0.89      images/uploads/photo_2.jpg
3      Blood             Review      暴恐         血腥                  0.72      images/uploads/photo_3.jpg
```

**列说明**：
- `suggestion`：IMS 建议（Block=建议拦截、Review=需人工审核、Pass=通过）
- `violation_type`：违规类型（直接取 SubLabel 或 Label 的原始值）

## 第二步：隔离

`quarantine` 命令将对象从原桶**物理移动**到隔离桶，原 URL 立即失效。每次隔离会关联一个**批次ID**，便于后续追溯和批量还原。

### 批次ID 说明

| 方式 | 命令 | 批次ID 格式 | 确认流程 |
|------|------|------------|---------|
| 自动生成 | `quarantine --suggestion Block` | `20260520_143022`（时间戳） | 直接输入 `yes` |
| 手动指定 | `quarantine --suggestion Block --batch gamble_20260520` | 自定义字符串 | 显示批次ID → 输入 `yes` |

```bash
# 自动批次ID（推荐日常使用）
python handle_violations.py quarantine --suggestion Block

# 手动批次ID（推荐批次语义明确时使用，如按类型分批）
python handle_violations.py quarantine --label Illegal --batch illegal_20260520
python handle_violations.py quarantine --sub-label Gamble --batch gamble_wave1

# 预演（先看效果，展示批次ID预览值）
python handle_violations.py quarantine --suggestion Block --dry-run

# 组合过滤
python handle_violations.py quarantine --suggestion Block --label Illegal

# 按 ID 直接隔离
python handle_violations.py quarantine --ids 1,2,3
```

**自动批次ID 执行示例**：
```
将要隔离的图片（共 2 条）
...

批次ID：自动生成（执行后打印实际值）

确认隔离 2 张图片（MinIO 层物理移动，原 URL 失效）？ (输入 yes 确认): yes

完成 - 成功: 2 失败: 0 跳过: 0  批次ID: 20260520_143022
```

**手动批次ID 执行示例**：
```
将要隔离的图片（共 3 条）
...

批次ID（手动指定）：gamble_wave1

确认以批次ID [gamble_wave1] 隔离 3 张图片（MinIO 层物理移动，原 URL 失效）？ (输入 yes 确认): yes

完成 - 成功: 3 失败: 0 跳过: 0  批次ID: gamble_wave1
```

## 第三步：查看已隔离 / 误判恢复 / 删除

### 查看已隔离

```bash
# 查看全部已隔离（含批次ID列）
python handle_violations.py list-quarantined

# 查看某批次
python handle_violations.py list-quarantined --batch 20260520_143022
```

**输出示例**（含批次ID列）：
```
已隔离的图片（隔离桶）（共 3 条）

ID     violation_type    suggestion  label_cn    sub_label_cn    置信度   批次ID              路径
1      Gamble            Block       违法         赌博            0.95     gamble_wave1        images/photo_1.jpg
2      Gamble            Block       违法         赌博            0.88     gamble_wave1        images/photo_2.jpg
3      SexyBehavior      Block       色情         性行为          0.89     20260520_150010     images/photo_3.jpg
```

### 误判恢复

restore 根据操作范围采用**不同强度的确认机制**，防止误操作：

| 模式 | 命令 | 确认方式 | 适用场景 |
|------|------|---------|---------|
| 按 ID | `restore --ids 3,4` | 输入 `yes` | 单条/少量误判 |
| 按批次 | `restore --batch <批次ID>` | **重新输入批次ID** | 整批还原 |
| 全部 | `restore --all` | 输入 `RESTORE-ALL` | 紧急大规模还原 |

**按批次恢复示例**（需输入批次ID二次确认）：
```bash
python handle_violations.py restore --batch gamble_wave1
```
```
将要恢复到原桶的图片（视为误判）— 批次 gamble_wave1（共 2 条）
...

⚠  即将恢复批次 [gamble_wave1] 的 2 张图片到原桶（不可撤销）
请输入批次ID确认 (输入 gamble_wave1 确认): gamble_wave1

完成 - 成功: 2 失败: 0 跳过: 0
```

**预演（不需要确认）**：
```bash
python handle_violations.py restore --batch gamble_wave1 --dry-run
python handle_violations.py restore --all --dry-run
```

### 彻底删除

```bash
python handle_violations.py delete --ids 1,2 --dry-run
python handle_violations.py delete --ids 1,2    # 需输入 DELETE 确认
```

## 完整示例

```bash
# 09:00 扫描新增图片
$ python scanner.py

# 10:00 查看 IMS 建议拦截的违规
$ python handle_violations.py list --suggestion Block
待处理的违规图片（原桶）（共 3 条）
ID  violation_type  suggestion  label_cn  sub_label_cn  置信度  路径
1   Gamble          Block       违法       赌博          0.95    images/photo_1.jpg
2   SexyBehavior    Block       色情       性行为        0.89    images/photo_2.jpg
3   Blood           Review      暴恐       血腥          0.72    images/photo_3.jpg

# 10:10 预演隔离（查看批次ID预览值）
$ python handle_violations.py quarantine --suggestion Block --dry-run
[DRY-RUN] 预计成功: 2  批次ID预览: 20260520_101022_preview

# 10:15 按语义命名批次隔离赌博内容
$ python handle_violations.py quarantine --sub-label Gamble --batch gamble_20260520
将要隔离的图片（共 1 条）...
批次ID（手动指定）：gamble_20260520
确认以批次ID [gamble_20260520] 隔离 1 张图片... (输入 yes 确认): yes
完成 - 成功: 1 失败: 0 跳过: 0  批次ID: gamble_20260520

# 10:16 其余 Block 建议自动批次
$ python handle_violations.py quarantine --suggestion Block
完成 - 成功: 1 失败: 0 跳过: 0  批次ID: 20260520_101622

# Review 类需人工审核（ID 3）
$ python handle_violations.py quarantine --ids 3   # 确认违规 → 隔离

# 11:00 查看已隔离（含批次ID列）
$ python handle_violations.py list-quarantined

# 运营反馈 gamble_20260520 整批为误判
$ python handle_violations.py restore --batch gamble_20260520 --dry-run
$ python handle_violations.py restore --batch gamble_20260520
⚠  即将恢复批次 [gamble_20260520] 的 1 张图片到原桶（不可撤销）
请输入批次ID确认 (输入 gamble_20260520 确认): gamble_20260520
完成 - 成功: 1 失败: 0 跳过: 0

# 12:00 删除确认违规的
$ python handle_violations.py delete --ids 1,3 --dry-run
$ python handle_violations.py delete --ids 1,3
请输入 DELETE 确认删除：DELETE
```

---

← [INDEX](./INDEX.md) | [USAGE](./USAGE.md) | [DATABASE](./DATABASE.md) →
