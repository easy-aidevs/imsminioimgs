# 违规图片处理 - 快速参考

## 🎯 三步走策略

```
第1步: rename    → 重命名为 .__del__（可恢复）
第2步: restore   → 如有误判，恢复文件
第3步: delete-del → 确认无误，彻底删除
```

---

## 📋 常用命令

### 查看违规图片

```bash
# 查看所有违规图片
python handle_violations.py list

# 按类型筛选
python handle_violations.py list --type gambling

# 按置信度筛选
python handle_violations.py list --confidence 0.9
```

---

### 重命名（安全删除第一步）

```bash
# 预览（不实际执行）
python handle_violations.py rename --dry-run

# 执行重命名
python handle_violations.py rename

# 只处理特定类型
python handle_violations.py rename --type gambling

# 只处理高置信度
python handle_violations.py rename --confidence 0.95
```

---

### 查看已标记文件

```bash
python handle_violations.py list-del
```

---

### 恢复误判文件

```bash
# 预览恢复
python handle_violations.py restore --dry-run

# 恢复所有
python handle_violations.py restore

# 恢复指定ID
python handle_violations.py restore --ids 1,2,3
```

---

### 彻底删除（危险！）

```bash
# 预览删除
python handle_violations.py delete-del --dry-run

# 删除所有
python handle_violations.py delete-del

# 删除指定ID
python handle_violations.py delete-del --ids 1,2,3
```

---

## ⚠️ 安全提示

1. **始终先用 `--dry-run` 预览**
2. **定期检查是否有误判**
3. **删除前必须输入 `DELETE` 确认**
4. **建议分批处理大量文件**

---

## 🔄 完整流程示例

```bash
# 1. 查看违规图片
python handle_violations.py list --type gambling

# 2. 预览重命名
python handle_violations.py rename --type gambling --dry-run

# 3. 执行重命名
python handle_violations.py rename --type gambling

# 4. 检查已标记文件
python handle_violations.py list-del

# 5. 如有误判，恢复
python handle_violations.py restore --ids 5,8

# 6. 确认无误后删除
python handle_violations.py delete-del
```

---

## 📊 文件状态

| 状态 | object_key | is_violation | 说明 |
|------|-----------|--------------|------|
| 正常违规 | `image.jpg` | 1 | 刚扫描发现违规 |
| 已标记 | `image.jpg.__del__` | 1 | 已重命名，待删除 |
| 已恢复 | `image.jpg` | 0 | 从.__del__恢复 |
| 已删除 | （无记录） | - | 已从数据库移除 |

---

## 💡 提示

- **重命名是可逆的** - 随时可以恢复
- **删除是不可逆的** - 务必谨慎
- **支持批量操作** - 可按类型、置信度筛选
- **数据库同步更新** - 所有操作都会更新记录

---

**详细文档**: [HANDLE_VIOLATIONS_GUIDE.md](HANDLE_VIOLATIONS_GUIDE.md)
