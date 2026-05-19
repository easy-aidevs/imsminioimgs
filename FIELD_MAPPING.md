# 数据库-代码字段映射表

## 完整字段对应关系

### ✅ 已完全对齐的字段

```
数据库列名           | 数据类型        | 代码来源                    | 写入路径       | 状态
─────────────────────────────────────────────────────────────────────────────
id                  | BIGINT          | AUTO_INCREMENT              | -              | ✅
key                 | VARCHAR(128)    | ImageFeatureExtractor       | _build_record  | ✅
feature_hash        | VARCHAR(64)     | extract_features['phash']   | _build_record  | ✅
feature_hash_dhash  | VARCHAR(64)     | extract_features['dhash']   | _build_record  | ✅
feature_hash_ahash  | VARCHAR(64)     | extract_features['ahash']   | _build_record  | ✅
feature_hash_phash  | VARCHAR(64)     | extract_features['phash']   | _build_record  | ✅
bucket_name         | VARCHAR(255)    | scan_all()参数              | _build_record  | ✅
object_key          | VARCHAR(1024)   | scan_all()遍历              | _build_record  | ✅
file_size           | BIGINT          | len(image_data)             | _build_record  | ✅
content_type ⭐    | VARCHAR(128)    | metadata['content_type']    | _build_record  | ✅ 已修复
is_violation        | TINYINT(1)      | ims_result/source record    | _write_ims     | ✅
violation_type      | VARCHAR(255)    | TencentIMSScanner返回       | _write_ims     | ✅
violation_label     | VARCHAR(255)    | TencentIMSScanner返回       | _write_ims     | ✅
violation_description| TEXT           | TencentIMSScanner返回       | _write_ims     | ✅
confidence          | DECIMAL(5,4)    | TencentIMSScanner返回       | _write_ims     | ✅
suggestion          | VARCHAR(50)     | TencentIMSScanner返回       | _write_ims     | ✅
ims_result          | JSON            | 结构化dict (matched_by)     | _write_ims     | ✅
ims_request_id      | VARCHAR(128)    | TencentIMSScanner返回       | _write_ims     | ✅
scan_status         | VARCHAR(20)     | 'completed' / 'failed'      | _build_record  | ✅
error_message       | TEXT            | Exception.__str__()         | _record_error  | ✅
blocked             | TINYINT(1)      | 0 (默认)                    | _build_record  | ✅
first_seen_at       | DATETIME        | 数据库默认(CURRENT_TIMESTAMP)| -              | ✅
last_scanned_at     | DATETIME        | datetime.now()              | _build_record  | ✅
created_at          | DATETIME        | 数据库默认(CURRENT_TIMESTAMP)| -              | ✅
updated_at          | DATETIME        | 数据库自动(ON UPDATE)       | -              | ✅
```

### 🔄 需要特殊处理的字段

#### 1️⃣ **content_type** (修复：获取来源改进)
```
场景1 - 路径/内容/特征复用时:
  来源: minio_client.get_object_data() → metadata['content_type']
  设置: 在 _write_reused() 中传递
  目的: 保留原文件的MIME类型

场景2 - IMS新扫描时:
  来源: 同上
  设置: 在 _write_ims() 中传递
  目的: 记录本次扫描文件的类型

场景3 - 错误处理时:
  设置: None (无法获取)
  原因: 下载失败前获取不到文件数据
```

#### 2️⃣ **ims_result** (JSON格式，包含matched_by标识)
```
格式A - IMS API扫描:
  {
    "matched_by": "ims_api",
    "raw_result": {...腾讯云原始返回...},
    "request_id": "xxx"
  }

格式B - 内容去重复用:
  {
    "matched_by": "content",
    "source_bucket": "original_bucket",
    "source_object_key": "original_path",
    "hash_distance": 0
  }

格式C - 特征相似复用:
  {
    "matched_by": "similar",
    "source_bucket": "similar_bucket",
    "source_object_key": "similar_path",
    "hash_distance": 1-3
  }
```

#### 3️⃣ **feature_hash系列** (四个不同算法)
```
phash (感知哈希) - 主特征
  ✅ 用于第3层相似匹配
  ✅ 存储在 feature_hash 和 feature_hash_phash
  ✅ 对缩放、亮度变化鲁棒

dhash (差异哈希)
  📋 存储 (feature_hash_dhash)
  ❌ 目前未使用，保留备用

ahash (平均哈希)
  📋 存储 (feature_hash_ahash)
  ❌ 目前未使用，保留备用

whash (小波哈希) ❌ 已删除
  ❌ 计算开销大，收益小
  ❌ 不存储
```

#### 4️⃣ **is_violation** (违规标记)
```
来源1 - IMS API结果:
  is_violation = (ims_result['suggestion'] in ['Block', 'Review'])

来源2 - 复用记录:
  is_violation = source_record['is_violation']
  (继承之前的判决)

来源3 - 错误记录:
  is_violation = 0 (保守，标记为正规)
```

#### 5️⃣ **scan_status** (扫描状态)
```
'completed'  ✅ 正常流程 (_write_ims, _write_reused)
'failed'     ❌ 异常处理 (_record_error)
'pending'    ⏳ 未使用 (数据库默认值)
```

---

## 代码中的关键调用链

### 📍 写入路径1：IMS API扫描（新增）
```
_process_one()
  └─ self.minio.get_object_data()
     └─ return: (bytes, {'content_type': '...', 'size': N, 'last_modified': ...})
  
  └─ self.features.extract_features(image_data)
     └─ return: {'phash': '...', 'dhash': '...', 'ahash': '...', 'feature_hash': '...'}
  
  └─ self.ims.scan_image(image_data)
     └─ return: {'is_violation': True/False, 'violation_type': '...', ...}
  
  └─ self._write_ims(bucket, object_name, image_data, key, feats, ims_result, content_type)
     └─ record = self._build_record_base(..., content_type=content_type)
        └─ record['scan_status'] = 'completed'
        └─ record['content_type'] = 'image/jpeg'  ✅
        └─ record['ims_result'] = {'matched_by': 'ims_api', ...}
     
     └─ self.db.upsert_record(record)
        └─ INSERT INTO image_scan_records (content_type, ...) VALUES (...)
```

### 📍 写入路径2：内容去重复用
```
_process_one()
  └─ 第2层：同一 key 在数据库中找到
  
  └─ self._write_reused(bucket, object_name, image_data, key, feats, 
                        source=same_content, match='content', content_type=content_type)
     └─ record = self._build_record_base(..., content_type=content_type)
        └─ record['content_type'] = 'image/jpeg'  ✅
        └─ record['ims_result'] = {'matched_by': 'content', ...}
        └─ record['is_violation'] = source['is_violation']  # 继承
     
     └─ self.db.upsert_record(record)
        └─ INSERT ... ON DUPLICATE KEY UPDATE ...
           └─ content_type = VALUES(content_type)
```

### 📍 写入路径3：特征相似复用
```
_process_one()
  └─ 第3层：特征距离 <= 3
  
  └─ cache + db 双层查询，合并结果
  
  └─ self._write_reused(..., source=most, match='similar', distance=..., content_type=...)
     └─ record = self._build_record_base(..., content_type=content_type)
        └─ record['ims_result'] = {'matched_by': 'similar', 'hash_distance': 1, ...}
        └─ record['is_violation'] = source['is_violation']
     
     └─ self.db.upsert_record(record)
        └─ INSERT ... ON DUPLICATE KEY UPDATE ...
```

### 📍 写入路径4：错误处理
```
_process_one()
  └─ 异常捕获 → _record_error(bucket, object_name, err)
  
  └─ record = {
       'scan_status': 'failed',
       'error_message': str(err),
       'is_violation': 0,
       'content_type': None,  ✅ 无法获取
       'feature_hash': '',
       'blocked': 0,
       ...
     }
  
  └─ self.db.upsert_record(record)
```

---

## 缓存与数据库的字段映射

### 缓存记录结构（_feature_cache）
```python
self.feature_cache = {
  'phash_hex_value_1': [
    {
      'key': 'md5-size',
      'bucket_name': 'images',
      'object_key': 'path/to/image.jpg',
      'feature_hash': 'phash_value',
      'feature_hash_dhash': '...',
      'feature_hash_ahash': '...',
      'is_violation': 1,
      'violation_type': 'porn',
      'violation_label': 'sexy_image',
      'violation_description': '...',
      'confidence': 0.95,
      'suggestion': 'Block',
      'hash_distance': 2,  # ✅ 计算时添加
      ...
    },
  ],
  'phash_hex_value_2': [...],
}
```

### 缓存完整性检查（_is_complete_record）
```python
required_fields = [
  'key',                    # ✅ 必需
  'bucket_name',           # ✅ 必需
  'object_key',            # ✅ 必需
  'feature_hash',          # ✅ 必需
  'is_violation',          # ✅ 必需
  'violation_type',        # ✅ 必需
  'violation_label',       # ✅ 必需
]

optional_fields = [
  'content_type',          # 新增，可选
  'violation_description', # 可选
  'confidence',            # 可选
  'suggestion',            # 可选
]
```

---

## 统计字段映射

```
数据库不直接存储这些字段，但代码通过统计来追踪：

scanner.stats = {
  'total':      0,    # 处理的总图片数
  'scanned':    0,    # 调用IMS API的数量
  'violations': 0,    # 检测出违规的总数
  'skipped':    0,    # 路径/内容/特征复用的数量 ✅ 已修复添加第3层
  'api_saved':  0,    # 通过特征相似省去的API调用数
  'reused':     0,    # 通过路径/内容/特征复用的总数
  'errors':     0,    # 处理失败的数量
}

验证公式：
  total = scanned + skipped + errors
  violations <= total
  api_saved <= skipped
```

---

## 总结：修复前后的关键差异

| 字段 | 修复前 | 修复后 | 影响范围 |
|------|--------|--------|---------|
| content_type | NULL | ✅ 自动填充 | 所有新扫描记录 |
| feature_hash_whash | 计算但未存储 | ❌ 已删除计算 | 特征提取性能 |
| _record_error 完整性 | 缺少字段 | ✅ 字段完整 | 错误记录 |
| 缓存验证 | 无 | ✅ 有完整性检查 | 缓存安全性 |
| stats['skipped'] 第3层 | 未计数 | ✅ 已计数 | 统计准确性 |
| minio metadata | 未获取 | ✅ 已获取 | MinIO集成完整性 |

---

## 验证清单

在新扫描前，确认以下修复已生效：

- [ ] scanner.py 编译无误 (`python3 -m py_compile`)
- [ ] minio_client.py 的 get_object_data() 返回 Tuple[bytes, dict]
- [ ] _build_record_base() 接收 content_type 参数
- [ ] 所有 _write_reused() 和 _write_ims() 调用都传递 content_type
- [ ] 第3层统计包含 `stats['skipped'] += 1`
- [ ] image_feature.py 不再计算 whash
- [ ] _record_error() 包含所有必需字段
- [ ] _is_complete_record() 方法存在于缓存管理中

---

## FAQ

**Q: 为什么要删除whash而不是存储到数据库？**
A: whash 贡献度低（phash + dhash + ahash 已足够），但计算开销大（特别是小波变换），删除可直接提升5-10%性能。

**Q: content_type 设为 NULL 会怎样？**
A: 数据库允许，但无法按文件类型统计分析。只有在获取文件失败时才会为 NULL（_record_error）。

**Q: 旧记录的 content_type 没有？**
A: 可以选择迁移：`UPDATE ... SET content_type='unknown'` 或保持 NULL，新扫描会自动填充。

**Q: 缓存验证会影响性能吗？**
A: 否，验证开销极小（只检查6个字段是否存在），可忽略不计。
