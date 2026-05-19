# 系统架构

## 概述

图片内容安全扫描系统采用**两个独立入口**的架构：

```
MinIO (图片存储)
  ↓
┌─────────────────────────────┐
│   scanner.py (扫描器)        │  → 调用腾讯云 IMS
│  遍历桶 → 提取特征 → 存库    │
└─────────────────────────────┘
  ↓
  MySQLImageScanRecords 表
  (is_violation=1/0)
  ↓
┌─────────────────────────────┐
│ handle_violations.py (处置)  │  ← 人工决策
│ mark → quarantine/restore    │
└─────────────────────────────┘
  ↓
MinIO (隔离桶或原桶)
```

## 两个工具

### 1. scanner.py（扫描器）

**职责**：
- 遍历 MinIO 桶中的所有图片
- 对每张图片提取特征哈希（phash/dhash/ahash）
- 调用腾讯云 IMS API 进行内容检测
- 检测结果写入数据库

**关键特性**：
- **三层去重机制**，节省 API 费用：
  1. 路径去重：同一 MinIO 路径已扫描，直接跳过
  2. 内容去重：相同内容（md5），复用已有扫描结果
  3. 特征相似：phash 距离 ≤ 3，复用相似图片的结果

- **缓存管理**：内存缓存相似图片特征，加速查询

### 2. handle_violations.py（处置工具）

**职责**：
- 查询数据库中的违规图片
- 管理图片的生命周期（标记、隔离、删除）
- 支持观察期内的恢复

**三阶段工作流**：
1. **发现 & 标记私密**（blocked=1）：图片在原桶，但无法公开访问
2. **观察决策**：等待观察期后，确认隔离或恢复
3. **彻底删除**（blocked=2）：移到隔离桶后的最终删除

## 数据流

```
输入: MinIO 对象 (bucket, key)
  ↓
[特征提取] 提取 pHash / dHash / aHash
  ↓
[三层去重] 检查是否需要调用 IMS API
  1. 路径检查
  2. 内容检查（md5）
  3. 相似检查（phash 距离）
  ↓
[IMS 扫描] (可能跳过)
  返回: is_violation, violation_label, sub_label, confidence
  ↓
[数据库写入]
  image_scan_records 表
  - key: 内容哈希标识
  - feature_hash: phash
  - is_violation: 0/1
  - violation_type: SubLabel或Label直接值（如Gambling/SexyBehavior/Porn）
  - violation_label: IMS 一级 Label（Polity/Porn/Sexy/Terror/Illegal/…）
  - violation_label_cn: 一级 Label 中文名
  - sub_label: IMS 二级 SubLabel（Gambling/SexyBehavior/…）
  - sub_label_cn: 二级 SubLabel 中文名
  - blocked: 0=public, 1=private, 2=quarantined
  ↓
[处置操作] (由 handle_violations.py 执行)
  - 标记私密：修改 blocked=1
  - 确认隔离：移动到隔离桶，修改 blocked=2
  - 恢复公开：修改 blocked=0
  ↓
输出: MinIO 原桶或隔离桶
```

## 核心概念

### blocked 字段的三个状态

| 值 | 状态 | 说明 |
|----|------|------|
| 0 | public（未处理） | 图片正常，或误判已恢复 |
| 1 | private（隐藏观察） | 标记为私密，无法公开访问，观察期 24-48 小时 |
| 2 | quarantined（已隔离） | 已移到隔离桶，不可恢复，仅可删除 |

### 权限控制机制

- **私密状态（blocked=1）**：使用 MinIO 的 `set_object_private()` 限制访问权限
  - 对象保留在原桶
  - 权限管制，无法通过公开链接访问
  - 随时可恢复为 `set_object_public()`

- **隔离状态（blocked=2）**：对象移到隔离桶
  - 不同的桶隔离，物理分离
  - 只能删除，不可恢复
  - 隔离桶权限严格限制

## 数据库设计

**核心表**：`image_scan_records`

关键字段：
- `key`：内容唯一标识（md5-size），用于去重
- `bucket_name`, `object_key`：MinIO 位置
- `feature_hash`：phash 特征，用于相似检测
- `is_violation`：是否违规
- `violation_type`：违规类型（直接取 SubLabel 或 Label 原始值）
- `violation_label`, `violation_label_cn`：IMS 一级 Label 及中文名
- `sub_label`, `sub_label_cn`：IMS 二级 SubLabel 及中文名
- `blocked`：处置状态（0/1/2）
- `content_type`：MIME 类型

关键索引：
- `uk_bucket_object`：同一路径唯一
- `idx_is_violation`：快速查询违规
- `idx_blocked`：快速查询处置状态
- `idx_feature_hash`：相似图片检测

## 集成点

### 与应用层的集成

1. **查询接口**：应用从 `image_scan_records` 读取图片状态
   - 过滤 `blocked != 0` 的图片（不显示私密和隔离的）
   - 根据 `is_violation` 决定是否展示

2. **日志监控**：
   - `logs/scan.log`：扫描过程日志
   - `logs/violations.log`：违规图片处置日志
   - `logs/error.log`：错误日志

3. **触发方式**：
   - `scanner.py`：定时任务或手动执行
   - `handle_violations.py`：人工运维操作

## 系统特点

1. **高效去重**：三层机制最小化 API 调用，节省费用
2. **安全决策**：私密观察期降低误判风险
3. **灵活部署**：两个独立工具，可分别部署或一起运行
4. **可追溯**：完整的数据库记录，支持审计
5. **容错能力**：失败记录独立处理，不阻断整体流程

---

← [INDEX](./INDEX.md) | [系统架构](./ARCHITECTURE.md) →
