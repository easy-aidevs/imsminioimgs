# 图片扫描系统快速参考

## 🚀 快速开始

### 1. 环境配置

```bash
# 复制示例配置
cp .env.example .env

# 编辑 .env 文件，填写必要配置
vim .env
```

**必填配置**:
```bash
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=your_key
MINIO_SECRET_KEY=your_secret
MINIO_BUCKET_NAME=images

MYSQL_HOST=localhost
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=image_security

TENCENT_SECRET_ID=your_id
TENCENT_SECRET_KEY=your_secret
```

---

### 2. 初始化数据库

```bash
mysql -u root -p < schema.sql
```

---

### 3. 运行扫描器

```bash
# 方式1: 直接运行
python3 scanner.py

# 方式2: Docker 运行
docker-compose up scanner

# 方式3: 限制扫描数量（测试用）
SCAN_LIMIT=100 python3 scanner.py
```

---

## 📊 核心逻辑速查

### 三层去重机制

```
第1层: 路径去重 (bucket + object_key)
  → 同一路径完全跳过 ✅

第2层: 内容去重 (Key = md5 + size)
  → 相同内容不同路径，复用结果，插入新记录 ✅

第3层: 相似去重 (Feature Hash)
  → 高度相似违规图片，直接标记，跳过 API ✅
```

---

### 扫描流程（9步）

```
1. 下载图片 (MinIO)
2. 计算 Key (md5 + size)
3. 检查路径重复 → 是则跳过
4. 提取特征 (pHash/dHash/aHash)
5. 检查内容重复 → 是则复用结果
6. 查询相似违规 → 是且距离≤3则直接标记
7. 调用 IMS API
8. 保存记录 (upsert)
9. 更新缓存 (如果违规)
```

---

## ⚙️ 性能优化配置

### 根据数据规模选择策略

| 违规图片数 | CACHE_STRATEGY | CACHE_MAX_SIZE | 内存占用 |
|-----------|---------------|----------------|---------|
| < 10万 | full | - | ~200MB |
| 10万-100万 | lru | 10000 | ~20MB |
| > 100万 | lru | 5000 | ~10MB |
| > 1000万 | none | - | 0MB |

### 配置示例

```bash
# 小规模（追求命中率）
CACHE_ENABLED=true
CACHE_STRATEGY=full

# 中规模（平衡性能和内存）⭐ 推荐
CACHE_ENABLED=true
CACHE_STRATEGY=lru
CACHE_MAX_SIZE=10000

# 大规模（优先稳定性）
CACHE_ENABLED=true
CACHE_STRATEGY=lru
CACHE_MAX_SIZE=5000

# 超大规模（禁用缓存）
CACHE_ENABLED=false
```

---

## 🔍 监控与调试

### 查看缓存统计

扫描结束时日志输出：
```
📦 特征缓存统计 - 缓存大小: 8542个特征, 命中率: 87.3% (8734/10000), 数据库查询: 1266次
```

**调优指南**:
- 命中率 < 50% → 增大 `CACHE_MAX_SIZE`
- 命中率 > 90% → 可适当减小 `CACHE_MAX_SIZE`
- 内存紧张 → 减小 `CACHE_MAX_SIZE` 或改用 `none`

---

### 查看日志文件

```bash
# 实时日志
tail -f logs/scan.log

# 错误日志
tail -f logs/error.log

# 违规图片日志
tail -f logs/violations.log
```

---

## 🛠️ 常见问题速查

### Q1: 重复扫描同一文件？
**解决**: 检查数据库唯一约束
```sql
SHOW INDEX FROM image_scan_records;
-- 应该看到 uk_bucket_object
```

---

### Q2: 内存占用过高？
**解决**: 减小缓存或禁用
```bash
CACHE_MAX_SIZE=5000        # 减小缓存
# 或
CACHE_STRATEGY=none        # 禁用缓存
```

---

### Q3: 初始化太慢？
**解决**: 使用 LRU 策略
```bash
CACHE_STRATEGY=lru         # 只加载最近 N 条
CACHE_MAX_SIZE=10000       # 限制数量
```

---

### Q4: 如何强制重新扫描？
**解决**: 设置环境变量
```bash
FORCE_RESCAN=true python3 scanner.py
```

---

### Q5: 如何限制扫描数量？
**解决**: 设置 SCAN_LIMIT
```bash
SCAN_LIMIT=100 python3 scanner.py  # 只扫描 100 张
```

---

## 📈 关键指标

### 统计信息示例

```
统计信息 - 总数: 10000, 已扫描: 8500, 违规: 450, 跳过: 1000, 错误: 50, 节约API: 1200次
📦 特征缓存统计 - 缓存大小: 8542个特征, 命中率: 87.3% (8734/10000), 数据库查询: 1266次
```

**关键指标**:
- **总数**: 处理的图片总数
- **已扫描**: 实际调用 API 的数量
- **违规**: 发现的违规图片数
- **跳过**: 通过去重跳过的数量
- **节约API**: 通过去重和相似检测节约的 API 调用次数 💰

---

## 🔧 高级用法

### 指定存储桶和前缀

```bash
# 扫描特定存储桶
MINIO_BUCKET_NAME=my-bucket python3 scanner.py

# 扫描特定前缀
SCAN_PREFIX=uploads/2024/ python3 scanner.py
```

---

### 批量处理违规图片

```bash
# 生成违规报告
python3 handle_violations.py --report

# 批量删除违规图片
python3 handle_violations.py --delete --confirm

# 移动违规图片到隔离桶
python3 handle_violations.py --move --target-bucket quarantined
```

---

## 📚 相关文档

- [完整逻辑说明](SCANNING_LOGIC.md) - 详细的扫描流程和去重机制
- [性能优化方案](PERFORMANCE_OPTIMIZATION.md) - 大规模场景优化
- [去重逻辑详解](DEDUPLICATION_LOGIC.md) - Key 的作用和去重原理
- [数据库优化](DATABASE_OPTIMIZATION.md) - 表结构设计和索引优化

---

**最后更新**: 2026-05-16
