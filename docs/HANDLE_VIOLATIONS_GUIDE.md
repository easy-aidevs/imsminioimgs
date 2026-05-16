# 违规图片处理工具使用指南

## 📖 概述

`handle_violations.py` 是一个安全的违规图片处理工具，采用**三步走策略**：

1. **重命名阶段** - 将违规图片重命名为 `.__del__` 后缀（可恢复）
2. **确认阶段** - 检查重命名的文件，确认无误判
3. **清理阶段** - 彻底删除 `.__del__` 文件（或恢复误判文件）

---

## 🎯 核心优势

### ✅ 安全性

- **可恢复** - 重命名而非直接删除，发现误判可随时恢复
- **二次确认** - 删除操作需要输入 `DELETE` 确认
- **预览模式** - 所有操作支持 `--dry-run` 预览

### ✅ 灵活性

- **按类型筛选** - 可只处理特定类型的违规图片
- **按置信度筛选** - 可跳过低置信度的图片
- **批量/单独操作** - 支持批量处理或指定ID处理

### ✅ 可追溯

- **数据库同步** - 所有操作同步更新数据库记录
- **日志记录** - 详细记录每个操作步骤
- **状态标记** - 清晰区分正常文件和待删除文件

---

## 🚀 快速开始

### 1. 查看帮助

```bash
python handle_violations.py --help
```

### 2. 工作流程

```
第1步: python handle_violations.py list                    # 查看所有违规图片
第2步: python handle_violations.py rename --dry-run        # 预览重命名
第3步: python handle_violations.py rename                  # 执行重命名
第4步: python handle_violations.py list-del                # 查看已标记文件
第5步: python handle_violations.py restore --ids 1,2       # 恢复误判文件（如有）
第6步: python handle_violations.py delete-del              # 彻底删除确认的文件
```

---

## 📋 命令详解

### 命令1: list - 列出违规图片

查看所有被标记为违规的图片。

#### 基本用法

```bash
# 查看所有违规图片
python handle_violations.py list

# 只查看赌博类违规图片
python handle_violations.py list --type gambling

# 只查看置信度>0.9的违规图片
python handle_violations.py list --confidence 0.9

# 组合条件
python handle_violations.py list --type gambling --confidence 0.95
```

#### 输出示例

```
找到 15 张违规图片:

ID     类型         置信度   文件路径
--------------------------------------------------------------------------------
1      gambling     0.95     images/poker1.jpg
2      gambling     0.95     images/poker_copy.jpg
3      porn         0.98     images/adult_content.png
4      violence     0.87     images/fight_scene.jpg
...
```

---

### 命令2: rename - 重命名为 .__del__

将违规图片重命名为 `.__del__` 后缀，这是**安全删除的第一步**。

#### 基本用法

```bash
# 预览重命名（不实际执行）
python handle_violations.py rename --dry-run

# 重命名所有违规图片
python handle_violations.py rename

# 只重命名赌博类图片
python handle_violations.py rename --type gambling

# 只重命名高置信度的图片
python handle_violations.py rename --confidence 0.9
```

#### 操作流程

```bash
$ python handle_violations.py rename --type gambling

找到 10 张违规图片:

ID     类型         置信度   文件路径
--------------------------------------------------------------------------------
1      gambling     0.95     images/poker1.jpg
2      gambling     0.95     images/poker_copy.jpg
...

确认重命名 10 张图片为 .__del__？(yes/no): yes

开始重命名 10 张图片为 .__del__ 后缀
[1/10] ✓ images/poker1.jpg → images/poker1.jpg.__del__
[2/10] ✓ images/poker_copy.jpg → images/poker_copy.jpg.__del__
...

重命名完成:
  成功: 10
  失败: 0
  跳过: 0
```

#### 重命名后的效果

**MinIO中**：
```
images/
├── poker1.jpg.__del__      ← 原 poker1.jpg
├── poker_copy.jpg.__del__  ← 原 poker_copy.jpg
└── normal.jpg              ← 未受影响
```

**数据库中**：
```sql
SELECT object_key FROM image_scan_records WHERE id = 1;
-- 结果: 'images/poker1.jpg.__del__'
```

---

### 命令3: list-del - 查看已标记文件

查看所有已重命名为 `.__del__` 的文件。

#### 基本用法

```bash
python handle_violations.py list-del
```

#### 输出示例

```
找到 10 个 .__del__ 文件:

ID     类型         置信度   文件路径
--------------------------------------------------------------------------------
1      gambling     0.95     images/poker1.jpg.__del__
2      gambling     0.95     images/poker_copy.jpg.__del__
...
```

---

### 命令4: restore - 恢复文件

如果发现有误判的图片，可以恢复到原始名称。

#### 基本用法

```bash
# 预览恢复（不实际执行）
python handle_violations.py restore --dry-run

# 恢复所有 .__del__ 文件
python handle_violations.py restore

# 恢复指定的文件（通过ID）
python handle_violations.py restore --ids 1,2,3

# 恢复单个文件
python handle_violations.py restore --ids 5
```

#### 操作流程

```bash
$ python handle_violations.py restore --ids 1,2

准备恢复 2 个文件:

  images/poker1.jpg.__del__ → images/poker1.jpg
  images/poker_copy.jpg.__del__ → images/poker_copy.jpg

确认恢复 2 个文件？(yes/no): yes

开始恢复 2 张 .__del__ 文件
[1/2] ✓ images/poker1.jpg.__del__ → images/poker1.jpg
[2/2] ✓ images/poker_copy.jpg.__del__ → images/poker_copy.jpg

恢复完成:
  成功: 2
  失败: 0
  跳过: 0
```

#### 恢复后的效果

**MinIO中**：
```
images/
├── poker1.jpg              ← 已恢复
├── poker_copy.jpg          ← 已恢复
└── other.jpg.__del__       ← 其他文件仍保持标记
```

**数据库中**：
```sql
-- is_violation 会被设置为 0
SELECT object_key, is_violation FROM image_scan_records WHERE id = 1;
-- 结果: ('images/poker1.jpg', 0)
```

---

### 命令5: delete-del - 彻底删除

**危险操作！** 彻底删除 `.__del__` 文件，不可恢复。

#### 基本用法

```bash
# 预览删除（不实际执行）
python handle_violations.py delete-del --dry-run

# 删除所有 .__del__ 文件
python handle_violations.py delete-del

# 删除指定的文件（通过ID）
python handle_violations.py delete-del --ids 1,2,3
```

#### 操作流程

```bash
$ python handle_violations.py delete-del

⚠️  警告：即将彻底删除 10 个文件（不可恢复！）

  images/poker1.jpg.__del__
  images/poker_copy.jpg.__del__
  ...

输入 DELETE 确认彻底删除: DELETE

开始彻底删除 10 张 .__del__ 文件
[1/10] ✓ 已删除: images/poker1.jpg.__del__
[2/10] ✓ 已删除: images/poker_copy.jpg.__del__
...

删除完成:
  成功: 10
  失败: 0
```

#### ⚠️ 重要提示

- 此操作**不可恢复**
- 需要输入 `DELETE` 才能执行
- 建议先用 `--dry-run` 预览
- 建议先检查是否有误判文件

---

## 💡 使用场景

### 场景1: 常规清理流程

```bash
# 第1步: 查看所有违规图片
python handle_violations.py list

# 第2步: 重命名为 .__del__（预览）
python handle_violations.py rename --dry-run

# 第3步: 执行重命名
python handle_violations.py rename

# 第4步: 检查是否有误判
python handle_violations.py list-del

# 第5步: 如有误判，恢复文件
python handle_violations.py restore --ids 3,7

# 第6步: 确认无误后，彻底删除
python handle_violations.py delete-del
```

---

### 场景2: 只清理赌博类图片

```bash
# 查看赌博类违规图片
python handle_violations.py list --type gambling

# 重命名赌博类图片
python handle_violations.py rename --type gambling

# 检查
python handle_violations.py list-del

# 确认无误后删除
python handle_violations.py delete-del
```

---

### 场景3: 谨慎清理（高置信度优先）

```bash
# 只处理置信度>0.95的图片
python handle_violations.py rename --confidence 0.95

# 检查
python handle_violations.py list-del

# 删除
python handle_violations.py delete-del

# 后续再处理置信度较低的图片
python handle_violations.py rename --confidence 0.8
```

---

### 场景4: 恢复误判文件

```bash
# 发现ID为5和8的文件是误判
python handle_violations.py restore --ids 5,8

# 验证恢复结果
python handle_violations.py list

# 确认这些文件不再出现在违规列表中
```

---

### 场景5: 批量处理不同违规类型

```bash
# 第1批: 处理赌博类
python handle_violations.py rename --type gambling
python handle_violations.py delete-del

# 第2批: 处理色情类
python handle_violations.py rename --type porn
python handle_violations.py delete-del

# 第3批: 处理暴力类
python handle_violations.py rename --type violence
python handle_violations.py delete-del
```

---

## 🔍 高级技巧

### 技巧1: 结合SQL查询

```bash
# 先在数据库中查询
mysql -u root -p -e "
SELECT violation_type, COUNT(*) as count 
FROM image_scan_records 
WHERE is_violation = 1 
  AND object_key NOT LIKE '%.__del__%'
GROUP BY violation_type;
"

# 根据统计结果决定处理顺序
python handle_violations.py rename --type gambling  # 数量最多的先处理
```

---

### 技巧2: 分批处理大量文件

```bash
# 假设有1000张违规图片，分批处理

# 第1批: ID 1-100
python handle_violations.py rename --confidence 0.95

# 第2批: ID 101-200
python handle_violations.py rename --confidence 0.9

# ...依此类推
```

---

### 技巧3: 自动化脚本

创建 `auto_cleanup.sh`:

```bash
#!/bin/bash

echo "=== 自动清理违规图片 ==="

# 1. 重命名
echo "步骤1: 重命名违规图片..."
python handle_violations.py rename --type gambling --confidence 0.9

# 2. 等待人工确认
echo "请检查 list-del 的输出，确认无误后继续..."
read -p "按回车继续..."

# 3. 删除
echo "步骤2: 彻底删除..."
python handle_violations.py delete-del

echo "清理完成！"
```

---

## 📊 状态说明

### 文件状态流转

```
正常文件
  ↓ [rename]
.__del__ 文件（可恢复）
  ↓ [restore]
正常文件（is_violation=0）
  
或
  
.__del__ 文件
  ↓ [delete-del]
已删除（不可恢复）
```

### 数据库字段变化

| 操作 | object_key | is_violation | 说明 |
|------|-----------|--------------|------|
| 初始扫描 | `image.jpg` | 1 | 标记为违规 |
| rename后 | `image.jpg.__del__` | 1 | 重命名，仍标记违规 |
| restore后 | `image.jpg` | 0 | 恢复，取消违规标记 |
| delete-del后 | （记录删除） | - | 记录从数据库移除 |

---

## ⚠️ 注意事项

### 1. 数据安全

- ✅ **始终先用 `--dry-run` 预览**
- ✅ **定期检查是否有误判**
- ✅ **保留备份后再执行删除**
- ❌ **不要跳过确认步骤**
- ❌ **不要在未检查的情况下直接删除**

### 2. 性能考虑

- 大量文件时建议分批处理
- 每次操作后会提交数据库事务
- MinIO操作可能较慢，耐心等待

### 3. 权限要求

- 需要对MinIO有读写权限
- 需要对MySQL有更新权限
- 建议使用专用账号

---

## 🐛 故障排查

### 问题1: 重命名失败

**可能原因**：
- MinIO连接失败
- 文件不存在
- 权限不足

**解决方法**：
```bash
# 检查MinIO连接
python -c "from minio_client import MinIOClient; print('OK')"

# 检查文件是否存在
python handle_violations.py list
```

---

### 问题2: 恢复失败

**可能原因**：
- .__del__ 文件已被手动删除
- 数据库记录不一致

**解决方法**：
```bash
# 检查数据库和MinIO的一致性
python handle_violations.py list-del

# 手动修复数据库
mysql -u root -p -e "
UPDATE image_scan_records 
SET object_key = 'correct_path.jpg' 
WHERE id = 123;
"
```

---

### 问题3: 删除后仍有记录

**可能原因**：
- 数据库事务未提交
- 有多个相同key的记录

**解决方法**：
```bash
# 检查是否有残留记录
mysql -u root -p -e "
SELECT * FROM image_scan_records 
WHERE object_key LIKE '%.__del__%';
"

# 手动清理
mysql -u root -p -e "
DELETE FROM image_scan_records 
WHERE object_key LIKE '%.__del__%';
"
```

---

## 📝 最佳实践

### 1. 定期清理流程

```bash
# 每周执行一次
0 2 * * 0 /path/to/handle_violations.py rename --type gambling >> /var/log/cleanup.log
0 3 * * 0 /path/to/handle_violations.py delete-del >> /var/log/cleanup.log
```

### 2. 监控告警

```python
# 监控 .__del__ 文件数量
import subprocess

result = subprocess.run(
    ['python', 'handle_violations.py', 'list-del'],
    capture_output=True, text=True
)

count = int(result.stdout.split('\n')[0].split()[1])

if count > 100:
    send_alert(f"有 {count} 个文件待删除")
```

### 3. 审计日志

```bash
# 记录所有操作
python handle_violations.py rename --type gambling 2>&1 | tee -a /var/log/violations.log
python handle_violations.py delete-del 2>&1 | tee -a /var/log/violations.log
```

---

## 🎉 总结

### 核心要点

1. **安全第一** - 始终使用重命名→确认→删除的三步走策略
2. **预览先行** - 所有操作先用 `--dry-run` 预览
3. **及时恢复** - 发现误判立即使用 `restore` 恢复
4. **分批处理** - 大量文件时分批处理，降低风险
5. **定期清理** - 建立定期清理机制，避免积压

### 常用命令速查

```bash
# 查看违规图片
python handle_violations.py list
python handle_violations.py list --type gambling

# 重命名（安全删除第一步）
python handle_violations.py rename --dry-run  # 预览
python handle_violations.py rename            # 执行

# 查看已标记文件
python handle_violations.py list-del

# 恢复误判文件
python handle_violations.py restore --ids 1,2,3

# 彻底删除（危险！）
python handle_violations.py delete-del --dry-run  # 预览
python handle_violations.py delete-del            # 执行
```

---

**祝您使用愉快！如有疑问，请查看详细日志或联系技术支持。** 🎉

