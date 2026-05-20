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
║   quarantine --suggestion Block   直接隔离建议拦截的  ║
║   quarantine --ids 1,2,3          按 ID 隔离          ║
╚═══════════════════════════════════════════════════════╝
        ↓
   blocked=2（对象在隔离桶）
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

`quarantine` 命令将对象从原桶**物理移动**到隔离桶，原 URL 立即失效。

```bash
# 直接隔离 IMS 建议拦截的（推荐）
python handle_violations.py quarantine --suggestion Block

# 预演（先看效果）
python handle_violations.py quarantine --suggestion Block --dry-run

# 按分类隔离
python handle_violations.py quarantine --label Illegal
python handle_violations.py quarantine --sub-label Gamble

# 组合过滤
python handle_violations.py quarantine --suggestion Block --label Illegal

# 按 ID 直接隔离
python handle_violations.py quarantine --ids 1,2,3
```

执行后：
- 对象从原桶移入隔离桶（MinIO 层真正隔离）
- 数据库 `blocked=2`
- 原 URL 失效

## 第三步：查看已隔离 / 误判恢复 / 删除

```bash
# 查看已隔离的图片
python handle_violations.py list-quarantined

# 误判恢复（从隔离桶移回原桶，标记为非违规）
python handle_violations.py restore --ids 3

# 彻底删除（需输入 DELETE 确认）
python handle_violations.py delete --ids 1,2 --dry-run
python handle_violations.py delete --ids 1,2
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

# 10:10 预演隔离
$ python handle_violations.py quarantine --suggestion Block --dry-run

# 10:15 实际隔离（IDs 1 和 2 的 Block 建议违规）
$ python handle_violations.py quarantine --suggestion Block

# Review 类需人工审核（ID 3）
$ python handle_violations.py quarantine --ids 3   # 确认违规 → 隔离
# 或
$ python handle_violations.py list   # 仍在原桶，暂不处理

# 11:00 查看已隔离
$ python handle_violations.py list-quarantined

# 用户反馈 ID 2 是误判
$ python handle_violations.py restore --ids 2   # 移回原桶，标记非违规

# 12:00 删除确认违规的
$ python handle_violations.py delete --ids 1,3 --dry-run
$ python handle_violations.py delete --ids 1,3
请输入 DELETE 确认删除：DELETE
```

---

← [INDEX](./INDEX.md) | [USAGE](./USAGE.md) | [DATABASE](./DATABASE.md) →
