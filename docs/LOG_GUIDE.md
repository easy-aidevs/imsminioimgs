# 日志系统使用指南

## 📋 概述

本系统采用**双日志文件**设计，分别记录运行日志和错误日志，方便调试和问题排查。

---

## 📁 日志文件说明

### 1. 运行日志 - `logs/scan.log`

**用途**: 记录程序运行的完整流程，用于确认程序逻辑是否正确

**特点**:
- 📝 **级别**: DEBUG（最详细）
- 🔄 **轮转**: 每100MB自动轮转
- 💾 **保留**: 30天
- 📦 **压缩**: 旧日志自动zip压缩
- 🔍 **内容**: 包含所有操作步骤、状态检查、决策过程

**典型内容**:
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
```

---

### 2. 错误日志 - `logs/error.log`

**用途**: 专门记录所有错误信息，用于修复程序bug

**特点**:
- ❌ **级别**: ERROR（只记录错误）
- 🔄 **轮转**: 每50MB自动轮转
- 💾 **保留**: 90天（更久）
- 📦 **压缩**: 旧日志自动zip压缩
- 🔍 **内容**: 包含完整异常堆栈、变量值、上下文信息

**典型内容**:
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

---

### 3. 违规日志 - `logs/violations.log`

**用途**: 专门记录发现的违规图片，便于快速查看违规情况

**特点**:
- ⚠️ **级别**: WARNING（仅违规相关）
- 🎯 **过滤**: 只包含"违规"关键字的WARNING日志
- 📝 **格式**: 简洁明了，一行一条
- 💾 **保留**: 90天

**典型内容**:
```
2024-01-15 10:30:15 | 🚨 发现违规图片: images/gambling1.jpg | 类型: gambling | 置信度: 0.95
2024-01-15 10:31:22 | 🚨 发现违规图片: images/porn2.jpg | 类型: pornography | 置信度: 0.88
2024-01-15 10:32:45 | 🔍 发现相似违规图片: images/similar1.jpg | 相似于: images/gambling1.jpg | 违规类型: gambling | 汉明距离: 2
```

---

### 4. 控制台输出

**用途**: 实时查看重要信息

**特点**:
- 🎨 **彩色显示**: 不同级别不同颜色
- 📊 **级别**: INFO（重要信息）
- ⚡ **实时**: 立即显示
- 📱 **友好**: 适合人工阅读

---

## 🔍 如何使用日志进行调试

### 场景1: 程序运行缓慢

**问题**: 扫描速度太慢

**分析方法**:
```bash
# 查看scan.log中的时间戳
grep "步骤5: 调用腾讯云IMS API检测" logs/scan.log | head -20

# 查看IMS响应时间
grep "IMS响应时间" logs/scan.log | awk -F': ' '{print $2}' | sort -n | tail -10
```

**可能原因**:
- IMS API响应慢 → 考虑增加并发或优化网络
- 图片下载慢 → 检查MinIO连接
- 特征计算慢 → 检查CPU性能

---

### 场景2: 某些图片未被正确识别

**问题**: 应该违规的图片没有被标记

**分析方法**:
```bash
# 查找特定图片的处理日志
grep "photo123.jpg" logs/scan.log

# 查看该图片的完整处理流程
grep -A 30 "photo123.jpg" logs/scan.log
```

**检查点**:
1. ✅ 图片是否成功下载？
2. ✅ Key是否正确计算？
3. ✅ 是否命中缓存（Key重复）？
4. ✅ 是否找到相似违规图片？
5. ✅ IMS检测结果是什么？
6. ✅ 数据库记录是否正确保存？

---

### 场景3: 程序报错崩溃

**问题**: 程序运行中突然退出

**分析方法**:
```bash
# 查看最后的错误
tail -100 logs/error.log

# 查看错误发生前的操作
grep -B 50 "ERROR" logs/scan.log | tail -100
```

**关键信息**:
- 错误类型（ConnectionError, TimeoutError等）
- 错误信息（具体描述）
- 堆栈跟踪（代码位置）
- 变量值（diagnose模式会显示）

---

### 场景4: 违规图片数量不对

**问题**: 统计的违规数量与预期不符

**分析方法**:
```bash
# 查看所有违规记录
cat logs/violations.log

# 按类型统计
grep "类型:" logs/violations.log | awk -F'类型: ' '{print $2}' | awk -F' |' '{print $1}' | sort | uniq -c

# 查看相似匹配的数量
grep "相似违规图片" logs/scan.log | wc -l

# 查看直接IMS检测的数量
grep "调用腾讯云IMS API检测" logs/scan.log | wc -l
```

---

## 🛠️ 常用日志查询命令

### 查看最近的错误
```bash
tail -50 logs/error.log
```

### 搜索特定图片的处理
```bash
grep "image_name.jpg" logs/scan.log
```

### 统计各种事件数量
```bash
# 总处理数量
grep "开始处理图片" logs/scan.log | wc -l

# 跳过数量（Key重复）
grep "图片已扫描过" logs/scan.log | wc -l

# 相似匹配数量
grep "发现相似违规图片" logs/scan.log | wc -l

# IMS检测数量
grep "调用腾讯云IMS API检测" logs/scan.log | wc -l

# 违规数量
grep "发现违规图片" logs/violations.log | wc -l
```

### 查看某个时间段的日志
```bash
# 查看10:00-11:00之间的日志
grep "2024-01-15 10:" logs/scan.log | head -100
```

### 提取性能数据
```bash
# 平均IMS响应时间
grep "IMS响应时间" logs/scan.log | awk -F': ' '{sum+=$2; count++} END {print sum/count}'

# 最慢的10次IMS调用
grep "IMS响应时间" logs/scan.log | awk -F': ' '{print $2}' | sort -rn | head -10
```

---

## 📊 日志分析示例

### 完整的图片处理流程日志

```
--- 开始处理图片 [1] ---
  - Bucket: my-bucket
  - Object: images/test.jpg
步骤1: 从 MinIO 下载图片数据...
  - 图片大小: 123456 bytes
步骤2: 计算图片唯一标识Key...
  - Key: a1b2c3d4e5f6...
步骤3: 查询数据库是否存在相同Key...
✓ 图片已扫描过（Key重复），跳过IMS检测
  - 原始记录ID: 456
  - 原始路径: images/test_original.jpg
  - 是否违规: 1
步骤4: 计算当前图片特征码...
  - pHash: 1a2b3c4d5e6f7890
  - dHash: 9f8e7d6c5b4a3210
  - aHash: 5a6b7c8d9e0f1234
步骤5: 插入数据库记录...
✓ 数据库记录插入成功, ID: 789
🚨 发现违规图片（Key重复）: images/test.jpg | 类型: gambling | 置信度: 0.92
--- 处理完成 [跳过IMS] ---
```

### 错误日志示例

```
2024-01-15 10:45:30.123 | ERROR    | minio_client:get_object_data:90 | ❌ 下载图片失败 [my-bucket/corrupted.jpg]
2024-01-15 10:45:30.124 | ERROR    | minio_client:get_object_data:91 |   - 错误类型: InvalidImageError
2024-01-15 10:45:30.125 | ERROR    | minio_client:get_object_data:92 |   - 错误信息: Image file is corrupted or not a valid image format
2024-01-15 10:45:30.126 | ERROR    | minio_client:get_object_data:93 | 详细堆栈信息:
Traceback (most recent call last):
  File "/app/minio_client.py", line 85, in get_object_data
    image = Image.open(BytesIO(data))
  File "/usr/lib/python3.9/site-packages/PIL/Image.py", line 2953, in open
    raise UnidentifiedImageError(msg)
PIL.UnidentifiedImageError: cannot identify image file
================================================================================
```

---

## 💡 最佳实践

### 1. 定期清理日志
```bash
# 手动清理30天前的日志
find logs/ -name "*.gz" -mtime +30 -delete

# 或者依赖自动轮转（推荐）
```

### 2. 监控日志文件大小
```bash
# 查看日志文件大小
ls -lh logs/

# 如果scan.log过大，可以临时清空
> logs/scan.log  # 谨慎使用
```

### 3. 实时监控日志
```bash
# 实时查看运行日志
tail -f logs/scan.log

# 实时查看错误日志
tail -f logs/error.log

# 实时查看违规日志
tail -f logs/violations.log
```

### 4. 导出日志进行分析
```bash
# 导出今天的违规记录
grep "$(date +%Y-%m-%d)" logs/violations.log > today_violations.txt

# 导出所有错误
cp logs/error.log errors_backup.log
```

---

## 🎯 反馈给AI助手的日志格式

当你需要我帮助分析问题时，请提供以下日志：

### 对于程序错误
```bash
# 提供最近的50行错误日志
tail -50 logs/error.log
```

### 对于逻辑问题
```bash
# 提供特定图片的完整处理日志
grep "problem_image.jpg" logs/scan.log
```

### 对于性能问题
```bash
# 提供统计数据
echo "总处理数: $(grep '开始处理图片' logs/scan.log | wc -l)"
echo "跳过数: $(grep '图片已扫描过' logs/scan.log | wc -l)"
echo "IMS调用数: $(grep '调用腾讯云IMS' logs/scan.log | wc -l)"
echo "违规数: $(wc -l < logs/violations.log)"
```

### 对于违规检测问题
```bash
# 提供最近的违规记录
tail -20 logs/violations.log
```

---

## 📝 总结

- ✅ **scan.log**: 看流程，确认逻辑
- ❌ **error.log**: 找错误，修复bug
- ⚠️ **violations.log**: 查违规，快速浏览
- 🎨 **控制台**: 看进度，实时监控

合理使用这些日志，可以快速定位问题、优化性能、确保程序正确运行！
