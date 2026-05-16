# 日志系统改进总结

## ✅ 完成的工作

### 1. 创建日志配置模块

**文件**: `logger_config.py`

**功能**:
- ✅ 双日志文件系统设计
- ✅ 自动日志轮转和压缩
- ✅ 异步日志写入（性能优化）
- ✅ 彩色控制台输出
- ✅ 违规图片专用日志

**日志文件**:
```
logs/
├── scan.log          # 运行日志（DEBUG级别，100MB轮转，保留30天）
├── error.log         # 错误日志（ERROR级别，50MB轮转，保留90天）
└── violations.log    # 违规日志（WARNING级别，50MB轮转，保留90天）
```

---

### 2. 增强scanner.py日志

**改进内容**:

#### 扫描开始阶段
```python
logger.info("="*80)
logger.info("开始扫描存储桶")
logger.info(f"  - 存储桶: {bucket}")
logger.info(f"  - 前缀: {prefix or '(无)'}")
logger.info(f"  - 强制重扫: {force_rescan}")
logger.info(f"  - 数量限制: {limit or '(无)'}")
logger.info("="*80)
```

#### 单图处理流程
```python
logger.debug(f"\n--- 开始处理图片 [{self.stats['total']+1}] ---")
logger.debug(f"  - Bucket: {bucket_name}")
logger.debug(f"  - Object: {object_name}")

# 步骤1: 下载图片
logger.debug("步骤1: 从 MinIO 下载图片数据...")
logger.debug(f"  - 图片大小: {len(image_data)} bytes")

# 步骤2: 计算Key
logger.debug("步骤2: 计算图片唯一标识Key...")
logger.debug(f"  - Key: {key[:50]}...")

# 步骤3: 查询数据库
logger.debug("步骤3: 查询数据库是否存在相同Key...")

# 步骤4: 提取特征
logger.debug("步骤4: 提取图片特征...")
logger.debug(f"  - pHash: {features['phash']}")
logger.debug(f"  - dHash: {features['dhash']}")
logger.debug(f"  - aHash: {features['ahash']}")

# 步骤5: IMS检测
logger.info(f"📡 步骤5: 调用腾讯云IMS API检测...")
logger.debug(f"  - IMS响应时间: {ims_duration:.2f}秒")
logger.debug(f"  - 是否违规: {ims_result['is_violation']}")

# 步骤6: 构建记录
logger.debug("步骤6: 构建数据库记录...")

# 步骤7: 保存数据库
logger.debug("步骤7: 保存记录到数据库...")
logger.debug(f"✓ 数据库记录保存成功")
```

#### 违规检测
```python
logger.warning(
    f"🚨 发现违规图片: {object_name} | "
    f"类型: {ims_result.get('violation_type')} | "
    f"置信度: {ims_result.get('confidence')}"
)
```

#### 错误处理
```python
logger.error(f"❌ 处理图片失败 [{bucket_name}/{object_name}]")
logger.error(f"  - 错误类型: {type(e).__name__}")
logger.error(f"  - 错误信息: {str(e)}")
logger.exception("详细堆栈信息:")  # 完整堆栈
```

---

### 3. 增强handle_violations.py日志

**改进内容**:

#### Block操作
```python
logger.info("="*80)
logger.info("开始标记违规图片为blocked状态")
logger.info(f"  - 待处理数量: {len(violations)}")
logger.info(f"  - Dry Run: {dry_run}")
logger.info("="*80)

for i, v in enumerate(violations, 1):
    logger.debug(f"\n[{i}/{len(violations)}] 处理: {object_key}")
    
    # 步骤1: 检查状态
    logger.debug("  步骤1: 检查MinIO对象当前状态...")
    logger.debug(f"    - is_blocked: {acl_info.get('is_blocked')}")
    
    # 步骤2: 设置标签
    logger.debug("  步骤2: 设置MinIO对象标签...")
    logger.debug(f"    ✓ MinIO标签设置成功")
    
    # 步骤3: 更新数据库
    logger.debug("  步骤3: 更新数据库记录...")
    logger.debug(f"    ✓ 数据库更新成功")
```

#### 错误处理
```python
logger.error(f"[{i}/{len(violations)}] ✗ {object_key} - 操作失败")
logger.error(f"  - 错误类型: {type(e).__name__}")
logger.error(f"  - 错误信息: {str(e)}")
logger.exception("  - 详细堆栈:")
```

---

### 4. 创建日志使用指南

**文件**: `docs/LOG_GUIDE.md`

**内容**:
- ✅ 日志文件说明
- ✅ 典型日志示例
- ✅ 调试场景分析
- ✅ 常用查询命令
- ✅ 性能数据分析
- ✅ 反馈格式指南

---

### 5. 更新文档

**修改的文件**:
- ✅ `docs/INDEX.md` - 添加LOG_GUIDE.md链接
- ✅ `README.md` - 添加日志系统说明章节

---

## 🎯 日志系统特性

### 1. 分级记录

| 级别 | 用途 | 输出位置 |
|------|------|---------|
| DEBUG | 详细流程、状态检查 | scan.log |
| INFO | 重要事件、进度 | 控制台 + scan.log |
| WARNING | 违规图片、警告 | 控制台 + scan.log + violations.log |
| ERROR | 错误、异常 | 控制台 + scan.log + error.log |

### 2. 自动管理

- **轮转**: 达到大小限制自动创建新文件
- **压缩**: 旧日志自动zip压缩
- **清理**: 超过保留期限自动删除
- **异步**: 不阻塞主程序执行

### 3. 详细信息

- **错误日志**: 包含完整异常堆栈
- **诊断模式**: 显示变量值（diagnose=True）
- **回溯**: 记录完整的调用链（backtrace=True）

---

## 📊 日志示例

### 运行日志 (scan.log)

```
2024-01-15 10:23:45.123 | DEBUG    | scanner:_process_single_image:170 | 
--- 开始处理图片 [1] ---
2024-01-15 10:23:45.124 | DEBUG    | scanner:_process_single_image:171 |   - Bucket: my-bucket
2024-01-15 10:23:45.125 | DEBUG    | scanner:_process_single_image:172 |   - Object: images/photo1.jpg
2024-01-15 10:23:45.126 | DEBUG    | scanner:_process_single_image:175 | 步骤1: 从 MinIO 下载图片数据...
2024-01-15 10:23:45.234 | DEBUG    | scanner:_process_single_image:177 |   - 图片大小: 245678 bytes
2024-01-15 10:23:45.235 | DEBUG    | scanner:_process_single_image:179 | 步骤2: 计算图片唯一标识Key...
2024-01-15 10:23:45.456 | DEBUG    | scanner:_process_single_image:181 |   - Key: abc123def456...
2024-01-15 10:23:45.457 | DEBUG    | scanner:_process_single_image:184 | 步骤3: 查询数据库是否存在相同Key...
2024-01-15 10:23:45.567 | DEBUG    | scanner:_process_single_image:187 | ✓ 图片已扫描过（Key重复），跳过IMS检测
2024-01-15 10:23:45.568 | DEBUG    | scanner:_process_single_image:188 |   - 原始记录ID: 123
2024-01-15 10:23:45.569 | DEBUG    | scanner:_process_single_image:189 |   - 原始路径: images/photo1_copy.jpg
2024-01-15 10:23:45.570 | DEBUG    | scanner:_process_single_image:190 |   - 是否违规: 0
2024-01-15 10:23:45.571 | DEBUG    | scanner:_process_single_image:193 | 步骤4: 计算当前图片特征码...
2024-01-15 10:23:45.678 | DEBUG    | scanner:_process_single_image:194 |   - pHash: 1a2b3c4d5e6f7890
2024-01-15 10:23:45.679 | DEBUG    | scanner:_process_single_image:195 |   - dHash: 9f8e7d6c5b4a3210
2024-01-15 10:23:45.680 | DEBUG    | scanner:_process_single_image:196 |   - aHash: 5a6b7c8d9e0f1234
2024-01-15 10:23:45.681 | DEBUG    | scanner:_process_single_image:245 | 步骤5: 插入数据库记录...
2024-01-15 10:23:45.789 | DEBUG    | scanner:_process_single_image:248 | ✓ 数据库记录插入成功, ID: 456
2024-01-15 10:23:45.790 | DEBUG    | scanner:_process_single_image:251 | --- 处理完成 [跳过IMS] ---
```

### 错误日志 (error.log)

```
2024-01-15 10:25:30.456 | ERROR    | scanner:_process_single_image:400 | ❌ 处理图片失败 [my-bucket/images/bad.jpg]
2024-01-15 10:25:30.457 | ERROR    | scanner:_process_single_image:401 |   - 错误类型: ConnectionError
2024-01-15 10:25:30.458 | ERROR    | scanner:_process_single_image:402 |   - 错误信息: Failed to connect to MinIO server
2024-01-15 10:25:30.459 | ERROR    | scanner:_process_single_image:403 | 详细堆栈信息:
Traceback (most recent call last):
  File "/app/scanner.py", line 175, in _process_single_image
    image_data = self.minio_client.get_object_data(bucket_name, object_name)
  File "/app/minio_client.py", line 85, in get_object_data
    response = self.client.get_object(bucket_name, object_name)
  ...
================================================================================
```

### 违规日志 (violations.log)

```
2024-01-15 10:30:15 | 🚨 发现违规图片: images/gambling1.jpg | 类型: gambling | 置信度: 0.95
2024-01-15 10:31:22 | 🚨 发现违规图片: images/porn2.jpg | 类型: pornography | 置信度: 0.88
2024-01-15 10:32:45 | 🔍 发现相似违规图片: images/similar1.jpg | 相似于: images/gambling1.jpg | 违规类型: gambling | 汉明距离: 2
```

---

## 🔧 使用方法

### 1. 安装依赖

```bash
pip install loguru
```

### 2. 运行程序

```bash
# 运行扫描器
python scanner.py

# 日志会自动生成到 logs/ 目录
```

### 3. 查看日志

```bash
# 实时查看运行日志
tail -f logs/scan.log

# 查看最近的错误
tail -50 logs/error.log

# 查看所有违规记录
cat logs/violations.log
```

### 4. 测试日志系统

```bash
python test_logging.py
```

---

## 💡 优势

### 对比之前的日志系统

| 特性 | 之前 | 现在 |
|------|------|------|
| 日志文件 | 单一文件 | 三个专用文件 |
| 日志级别 | 混合 | 分级清晰 |
| 轮转机制 | 无 | 自动轮转+压缩 |
| 错误详情 | 简单消息 | 完整堆栈+变量值 |
| 性能影响 | 同步写入 | 异步写入 |
| 调试便利性 | 低 | 高 |
| 问题定位 | 困难 | 容易 |

---

## 📝 下一步建议

### 正式运行前的准备

1. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

2. **测试日志系统**
   ```bash
   python test_logging.py
   cat logs/scan.log
   cat logs/error.log
   ```

3. **小规模测试**
   ```bash
   # 先扫描少量图片
   python scanner.py --limit 10
   
   # 检查日志是否正常
   tail -100 logs/scan.log
   ```

4. **正式运行**
   ```bash
   # 全量扫描
   python scanner.py
   
   # 实时监控
   tail -f logs/scan.log
   ```

### 反馈给AI助手

当遇到问题时，请提供：

```bash
# 对于错误
tail -50 logs/error.log

# 对于逻辑问题
grep "problem_image.jpg" logs/scan.log

# 对于性能问题
echo "总处理数: $(grep '开始处理图片' logs/scan.log | wc -l)"
echo "IMS调用数: $(grep '调用腾讯云IMS' logs/scan.log | wc -l)"
echo "违规数: $(wc -l < logs/violations.log)"
```

---

## ✅ 验证清单

- [x] logger_config.py 创建完成
- [x] scanner.py 日志增强完成
- [x] handle_violations.py 日志增强完成
- [x] LOG_GUIDE.md 文档创建完成
- [x] README.md 更新完成
- [x] docs/INDEX.md 更新完成
- [x] test_logging.py 测试脚本创建完成
- [ ] 依赖安装（用户执行）
- [ ] 日志测试（用户执行）
- [ ] 正式运行（用户执行）

---

**日志系统改进完成！现在可以开始正式运行并收集日志进行迭代优化。** 🎉
