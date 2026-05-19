# 违规图片处置工具改造总结

## 🔄 三阶段工作流

### 原始流程（已弃用）
```
违规图片 → 直接移到隔离桶（无观察期）
```

### 新流程（三阶段）
```
第一阶段：mark-private   → 标记为私密（原桶，隐藏观察）
   ↓ [观察期：业务正常？]
第二阶段：confirm-quarantine → 观察正常，移到隔离桶
   或者  restore-public   → 观察异常，改回公开（误判）
   ↓
第三阶段：delete → 确认后彻底删除
```

---

## 🗂️ 代码改造详情

### 1. MinIO 客户端 (`minio_client.py`)

新增两个权限控制方法：
- `set_object_private(bucket, key)` - 设置对象为私密（无法公开访问）
- `set_object_public(bucket, key)` - 设置对象为公开访问

### 2. 违规处理器 (`handle_violations.py`)

#### 新增方法

**第一阶段：标记私密**
```python
mark_private(records, dry_run=False) -> Dict
  - 原桶中的违规图片设置为 private
  - 更新 DB: blocked = 1
  - 图片仍在原位置，但无法公开访问
```

**查询工具**
```python
list_private(violation_type=None, confidence=0.0, ids=None) -> List[Dict]
  - 查看当前在观察期的图片（blocked=1）
```

**第二阶段-A：确认隔离**
```python
confirm_quarantine(records, dry_run=False) -> Dict
  - 观察正常，从原桶移到隔离桶
  - 更新 DB: blocked = 2
  - 不可再恢复
```

**第二阶段-B：改回公开**
```python
restore_public(records, dry_run=False) -> Dict
  - 观察异常（误判），改回 public
  - 更新 DB: blocked = 0, is_violation = 0
  - 从观察期脱离，重新分析
```

**查询工具**
```python
list_quarantined(ids=None) -> List[Dict]
  - 查看已隔离的图片（blocked=2）
```

#### 数据库字段语义变化

**blocked 字段含义：**
| 值 | 状态 | 说明 |
|---|------|------|
| 0 | public | 未处理，正常公开 |
| 1 | private | 隐藏观察期（原桶，无法访问） |
| 2 | quarantined | 已隔离（隔离桶，彻底处理） |

#### 已删除/重构方法

- ❌ `list_blocked()` → 拆分为 `list_private()` + `list_quarantined()`
- ❌ `block()` → 内部逻辑转移到 `confirm_quarantine()`
- ❌ `restore()` → 重构为 `restore_public()`（语义不同）
- ❌ `_mark_blocked()` → 拆分为 `_mark_private()` + `_mark_quarantined()`
- ❌ `_mark_restored()` → 改为 `_restore_public()`

---

## 📋 CLI 命令对应表

### 第一阶段：发现 & 标记私密

```bash
# 查看新增违规图片
python handle_violations.py list
python handle_violations.py list --type gambling --confidence 0.8

# 标记为私密（开始观察期）
python handle_violations.py mark-private --type gambling
python handle_violations.py mark-private --ids 10,11,12
python handle_violations.py mark-private --ids 10,11,12 --dry-run

# 查看当前观察中的图片
python handle_violations.py list-private
python handle_violations.py list-private --type gambling
```

### 第二阶段：观察决策

```bash
# 选择 A：观察正常 → 隔离
python handle_violations.py confirm-quarantine --ids 1,2,3
python handle_violations.py confirm-quarantine --ids 1,2,3 --dry-run

# 或选择 B：观察异常 → 改回公开
python handle_violations.py restore-public --ids 4,5
python handle_violations.py restore-public --ids 4,5 --dry-run
```

### 第三阶段：彻底删除

```bash
# 查看已隔离的
python handle_violations.py list-quarantined

# 彻底删除（不可恢复）
python handle_violations.py delete --ids 1,2,3
python handle_violations.py delete --ids 1,2,3 --dry-run
```

---

## 🎯 使用建议

### 观察期最佳实践

1. **标记为私密后**
   - 观察应用是否在业务日志中有异常
   - 检查用户是否投诉找不到某些图片
   - 通常观察 24-48 小时

2. **观察正常 → 隔离**
   ```bash
   python handle_violations.py confirm-quarantine --ids 10,11,12
   ```
   - 此后无法恢复，仅可删除

3. **观察异常 → 改回公开**
   ```bash
   python handle_violations.py restore-public --ids 13,14
   ```
   - 图片重新可访问
   - 标记为误判，不再参与违规处理

---

## 📊 数据流示意

```
┌─────────────────────┐
│  新增违规图片       │ blocked=0
│  (原桶，公开)       │
└──────────┬──────────┘
           │ mark-private
           ↓
┌─────────────────────┐
│  私密观察期         │ blocked=1
│  (原桶，隐藏)       │ [应用层过滤/MinIO权限]
└──┬──────────────────┘
   │
   ├─→ confirm-quarantine → ┌─────────────────────┐
   │                        │  已隔离             │ blocked=2
   │                        │  (隔离桶)           │
   │                        └──────────┬──────────┘
   │                                   │ delete
   │                                   ↓ (彻底删除)
   │                                   ∅
   │
   └─→ restore-public → ┌─────────────────────┐
                        │  改回公开           │ blocked=0
                        │  (原桶，视为误判)   │ is_violation=0
                        └─────────────────────┘
```

---

## ⚠️ 迁移说明

### 现有数据的处理

如果系统中已有使用旧流程（`blocked=1` 表示隔离）的数据：

```sql
-- 方案 1: 重新映射（推荐，需要验证）
-- UPDATE image_scan_records SET blocked=2 WHERE blocked=1 AND is_violation=1;

-- 方案 2: 手工审查
-- SELECT * FROM image_scan_records WHERE blocked=1;
-- 确认后再迁移

-- 新系统将使用：
-- 0 = public（未处理）
-- 1 = private（观察期）
-- 2 = quarantined（隔离）
```

### 向后兼容性

- ❌ 旧脚本中的 `block` 命令已删除
- ❌ 旧脚本中的 `restore` 命令已删除
- ⚠️ 需要更新所有引用的脚本

---

## 🔍 常见问题

### Q: 如何查看一个图片的当前状态？
```bash
# 查询数据库
mysql> SELECT id, bucket_name, object_key, blocked FROM image_scan_records WHERE id=123;

# blocked 值：
# 0 = 未处理（公开）
# 1 = 观察中（私密）
# 2 = 已隔离
```

### Q: 私密图片用户怎么看不到？
目前有两个实现方式：
1. **应用层过滤**：查询时添加 `WHERE blocked=0`
2. **MinIO 权限**：`set_object_private()` 设置对象权限

### Q: 能回到隔离前的状态吗？
❌ 不能。一旦进入隔离（blocked=2），只有删除一条路。  
✅ 在观察期（blocked=1）可以改回公开（blocked=0）。

### Q: 观察期需要多长时间？
根据业务需要自行决定，无硬性要求。建议：
- 高优先级威胁：24小时
- 普通违规：48-72小时

---

## 🚀 后续优化方向

可考虑的未来改进：
- [ ] 观察期自动过期机制（加 `marked_at` 字段）
- [ ] 审核人员标记和备注（加 `reviewed_by`, `note` 字段）
- [ ] 自动化决策策略（基于违规类型和置信度）
- [ ] 隔离后定期清理（自动删除 30 天未审查的）
