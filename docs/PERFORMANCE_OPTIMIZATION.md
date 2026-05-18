# 大规模图片扫描性能优化方案

## 📊 场景分析

### 数据规模假设
- **总图片数**: 1000万张
- **违规图片比例**: 5% → 50万张违规图片
- **唯一特征哈希数**: 约30万个（有些图片内容相同）

---

## ⚠️ 当前实现的性能问题

### 问题1: 内存爆炸 💥

```python
# 当前实现
self.feature_cache = {
    'hash1': [record1, record2, ...],  # 50万条记录 × 2KB ≈ 1GB
    'hash2': [record3, record4, ...],
    ...
}
```

**实际内存占用**:
- 50万条违规记录 × 2KB = **1GB**（理论值）
- Python对象overhead + 字典结构 = **2-3GB**（实际值）
- 如果有1000万张图片全部扫描完，缓存会持续增长 ❌

---

### 问题2: 初始化时间长 ⏱️

```python
def _load_violations_to_cache(self):
    violations = self.db.get_all_violations()  # 查询50万条记录
    # 可能需要 30-60秒 才能加载完成
```

**时间分析**:
- 数据库查询: 10-20秒
- 数据传输: 5-10秒
- Python对象创建: 10-30秒
- **总计**: 30-60秒 ❌

---

### 问题3: 汉明距离计算慢 🔍

```python
def _find_similar_in_cache(self, feature_hash, max_distance=5):
    for cached_hash in self.feature_cache.keys():  # 30万次循环
        distance = calculate_hash_distance(feature_hash, cached_hash)
```

**时间复杂度**: O(M)，M = 唯一特征数量
- 每张图片都要遍历 **30万个特征**
- 如果扫描1000万张图片 = 30万亿次计算 ❌
- 即使每次计算只需1微秒，也需要 **8.3小时**

---

## ✅ 优化方案（分层设计）

### 方案A: LRU缓存 + 限制大小（推荐用于 <100万违规图片）

**核心思路**:
- 只缓存**最近发现的违规图片**
- 限制缓存大小为 **10,000个特征**
- 超出时自动淘汰最旧的

**实现**:
```python
from collections import OrderedDict

class LimitedFeatureCache:
    def __init__(self, max_size=10000):
        self.cache = OrderedDict()
        self.max_size = max_size
    
    def add(self, feature_hash, record):
        if feature_hash not in self.cache:
            # 如果缓存已满，删除最旧的
            if len(self.cache) >= self.max_size:
                self.cache.popitem(last=False)
            self.cache[feature_hash] = []
        
        self.cache[feature_hash].append(record)
        # 移动到末尾（最近使用）
        self.cache.move_to_end(feature_hash)
    
    def find_similar(self, feature_hash, max_distance=5):
        similar = []
        for cached_hash, records in self.cache.items():
            distance = calculate_hash_distance(feature_hash, cached_hash)
            if 0 <= distance <= max_distance:
                for record in records:
                    record_copy = record.copy()
                    record_copy['hash_distance'] = distance
                    similar.append(record_copy)
        return sorted(similar, key=lambda x: x['hash_distance'])[:10]
```

**优点**:
- ✅ 内存可控（最多10,000个特征 × 100条记录 ≈ 20MB）
- ✅ 速度快（只遍历10,000个特征）
- ✅ 适合增量扫描场景

**缺点**:
- ⚠️ 可能错过早期的违规图片
- ⚠️ 需要权衡缓存大小

---

### 方案B: 数据库索引优化（推荐用于 >100万违规图片）

**核心思路**:
- **不使用内存缓存**
- 直接在数据库中查询相似图片
- 通过**数据库索引**加速查询

#### 步骤1: 添加数据库索引

```sql
-- schema.sql
ALTER TABLE image_scan_records 
ADD INDEX idx_feature_hash (feature_hash(64)),
ADD INDEX idx_violation_hash (is_violation, feature_hash(64));
```

#### 步骤2: 优化查询方法

```python
# database.py
def find_similar_violations_optimized(self, feature_hash: str, max_distance: int = 5) -> List[Dict]:
    """
    使用数据库索引查找相似违规图片
    """
    # 获取所有违规图片的特征哈希
    query = """
        SELECT id, bucket_name, object_key, feature_hash, 
               violation_type, confidence
        FROM image_scan_records 
        WHERE is_violation = 1 AND feature_hash IS NOT NULL
    """
    violations = self.execute_query(query, fetch=True)
    
    # 在Python中计算汉明距离（但只处理违规图片）
    similar = []
    for v in violations:
        distance = calculate_hash_distance(feature_hash, v['feature_hash'])
        if 0 <= distance <= max_distance:
            v['hash_distance'] = distance
            similar.append(v)
    
    return sorted(similar, key=lambda x: x['hash_distance'])[:10]
```

**优点**:
- ✅ 无内存限制
- ✅ 数据一致性高
- ✅ 支持任意规模

**缺点**:
- ⚠️ 每次都要查询数据库（较慢）
- ⚠️ 需要优化索引

---

### 方案C: 混合策略（最佳方案 ⭐）

**核心思路**:
- **热数据**: 最近10,000个特征 → 内存缓存（快速）
- **冷数据**: 历史违规图片 → 数据库查询（完整）
- **两级查找**: 先查缓存，再查数据库

**实现**:
```python
class HybridFeatureCache:
    def __init__(self, cache_size=10000, db=None):
        self.hot_cache = OrderedDict()  # 热数据
        self.cache_size = cache_size
        self.db = db  # 数据库连接
    
    def find_similar(self, feature_hash, max_distance=5):
        # 第1级: 查热缓存（极快）
        similar = self._search_hot_cache(feature_hash, max_distance)
        
        if similar:
            logger.debug(f"✅ 在热缓存中找到 {len(similar)} 个相似图片")
            return similar
        
        # 第2级: 查数据库（较慢，但完整）
        logger.debug("  - 热缓存未命中，查询数据库...")
        similar = self.db.find_similar_violations(feature_hash, max_distance)
        
        return similar
    
    def add(self, feature_hash, record):
        # 添加到热缓存
        if feature_hash not in self.hot_cache:
            if len(self.hot_cache) >= self.cache_size:
                self.hot_cache.popitem(last=False)
            self.hot_cache[feature_hash] = []
        
        self.hot_cache[feature_hash].append(record)
        self.hot_cache.move_to_end(feature_hash)
```

**优点**:
- ✅ 兼顾速度和完整性
- ✅ 内存可控
- ✅ 适应不同规模

**缺点**:
- ⚠️ 实现稍复杂

---

### 方案D: 使用专门的向量数据库（超大规模）

**适用场景**: >1000万张图片

**技术方案**:
- 使用 **Faiss** (Facebook AI Similarity Search)
- 使用 **Milvus** 或 **Pinecone**
- 使用 **Elasticsearch** 的向量搜索

**示例** (Faiss):
```python
import faiss
import numpy as np

class FaissSimilaritySearch:
    def __init__(self, dimension=64):
        # 创建索引
        self.index = faiss.IndexFlatL2(dimension)
        self.records = []  # 存储对应的记录
    
    def add(self, feature_hash, record):
        # 将16进制哈希转换为向量
        vector = self._hash_to_vector(feature_hash)
        self.index.add(vector.reshape(1, -1))
        self.records.append(record)
    
    def search(self, feature_hash, k=10):
        vector = self._hash_to_vector(feature_hash)
        distances, indices = self.index.search(vector.reshape(1, -1), k)
        
        results = []
        for i, idx in enumerate(indices[0]):
            if idx != -1:
                result = self.records[idx].copy()
                result['distance'] = distances[0][i]
                results.append(result)
        
        return results
```

**优点**:
- ✅ 极速（毫秒级查询百万级数据）
- ✅ 内存效率高
- ✅ 支持近似搜索

**缺点**:
- ⚠️ 需要额外依赖
- ⚠️ 学习成本高

---

## 🎯 推荐方案选择

| 数据规模 | 推荐方案 | 原因 |
|---------|---------|------|
| < 10万违规图片 | **方案A** (LRU缓存) | 简单高效，内存占用小 |
| 10万-100万 | **方案C** (混合策略) | 平衡速度和完整性 |
| 100万-1000万 | **方案B** (数据库索引) | 无内存限制，稳定性好 |
| > 1000万 | **方案D** (向量数据库) | 专业工具，性能最优 |

---

## 📝 立即改进建议

### 1. 添加配置项控制缓存行为

```python
# config.yaml
cache:
  enabled: true              # 是否启用缓存
  max_size: 10000            # 最大缓存特征数
  strategy: "lru"            # 缓存策略: lru / hybrid / none
```

### 2. 修改初始化逻辑

```python
def _load_violations_to_cache(self):
    """根据配置决定加载策略"""
    cache_config = self.config.get('cache', {})
    strategy = cache_config.get('strategy', 'lru')
    
    if strategy == 'none':
        logger.info("⚠️ 缓存已禁用，将直接查询数据库")
        return
    
    if strategy == 'lru':
        # 只加载最近的N条记录
        limit = cache_config.get('max_size', 10000)
        violations = self.db.get_recent_violations(limit=limit)
    else:
        # 加载全部
        violations = self.db.get_all_violations()
    
    # 加载到缓存...
```

### 3. 添加监控指标

```python
# 统计缓存命中率
self.cache_stats = {
    'hits': 0,      # 缓存命中次数
    'misses': 0,    # 缓存未命中次数
    'db_queries': 0 # 数据库查询次数
}

def _find_similar_in_cache(self, feature_hash, max_distance=5):
    similar = self._search_cache(feature_hash, max_distance)
    
    if similar:
        self.cache_stats['hits'] += 1
    else:
        self.cache_stats['misses'] += 1
        self.cache_stats['db_queries'] += 1
        similar = self.db.find_similar_violations(...)
    
    return similar
```

---

## 🔧 代码改进示例

让我为你实现**方案C（混合策略）**的改进版本：
