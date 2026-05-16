# 项目结构说明

## 目录结构

```
imsminioimgs/
├── scanner.py              # 主程序入口
├── minio_client.py         # MinIO客户端模块
├── image_feature.py        # 图片特征提取模块
├── tencent_ims.py          # 腾讯云IMS API模块
├── database.py             # MySQL数据库操作模块
├── schema.sql              # 数据库表结构定义
├── requirements.txt        # Python依赖包列表
├── .env.example            # 环境变量配置模板
├── .gitignore             # Git忽略文件配置
├── run.sh                 # 快速启动脚本
├── README.md              # 项目说明文档
├── USAGE.md               # 详细使用指南
└── PROJECT_STRUCTURE.md   # 本文件
```

## 核心模块说明

### 1. scanner.py (主程序)

**功能**：整合所有模块，实现完整的扫描流程

**主要类**：
- `ImageSecurityScanner`: 图片安全扫描器主类

**关键方法**：
- `scan_all()`: 扫描所有图片
- `_process_single_image()`: 处理单个图片
- `get_violation_report()`: 生成违规报告

**工作流程**：
```
遍历MinIO → 计算Key → 检查缓存 → 提取特征 → 调用IMS → 保存结果
```

### 2. minio_client.py (MinIO客户端)

**功能**：封装MinIO操作，提供图片遍历和数据读取

**主要类**：
- `MinIOClient`: MinIO客户端封装

**关键方法**：
- `list_objects()`: 遍历存储桶中的对象
- `get_object_data()`: 获取对象数据
- `_is_image_file()`: 判断是否为图片文件

**支持格式**：
jpg, jpeg, png, gif, bmp, webp, tiff, tif, svg, ico

### 3. image_feature.py (图片特征提取)

**功能**：计算图片的感知哈希特征，用于相似图片识别

**主要类**：
- `ImageFeatureExtractor`: 图片特征提取器

**关键方法**：
- `calculate_key()`: 计算图片唯一标识 (MD5-文件大小)
- `extract_features()`: 提取多种哈希特征
- `calculate_hash_distance()`: 计算汉明距离
- `is_similar()`: 判断图片是否相似

**特征类型**：
- **pHash** (Perceptual Hash): 感知哈希，对缩放、亮度变化鲁棒
- **dHash** (Difference Hash): 差异哈希，对梯度变化敏感
- **aHash** (Average Hash): 平均哈希，简单快速
- **wHash** (Wavelet Hash): 小波哈希，结合频率和空间信息

**相似度判断**：
- 汉明距离 0-5: 非常相似
- 汉明距离 5-10: 相似
- 汉明距离 >10: 不相似

### 4. tencent_ims.py (腾讯云IMS)

**功能**：调用腾讯云图片内容安全API进行检测

**主要类**：
- `TencentIMSScanner`: 腾讯云IMS扫描器

**关键方法**：
- `scan_image()`: 扫描单张图片
- `scan_image_batch()`: 批量扫描图片
- `_parse_response()`: 解析API响应

**检测类型**：
- Porn (色情)
- Gambling (赌博/棋牌) ⭐重点
- Violence (暴力)
- Politics (政治敏感)
- Ads (广告)
- Terrorism (恐怖主义)
- Contraband (违禁品)
- Vulgar (低俗)
- Qrcode (二维码)

**返回结果**：
```python
{
    'is_violation': True/False,
    'violation_type': 'gambling',
    'violation_label': '具体标签',
    'violation_description': '详细描述',
    'confidence': 0.95,
    'suggestion': 'Block/Review/Pass',
    'raw_result': {...},
    'request_id': '请求ID'
}
```

### 5. database.py (数据库操作)

**功能**：MySQL数据库的增删改查操作

**主要类**：
- `ImageDatabase`: 数据库管理类

**关键方法**：
- `find_by_key()`: 根据key查找记录
- `find_by_feature_hash()`: 根据特征哈希查找
- `insert_record()`: 插入记录
- `update_record()`: 更新记录
- `upsert_record()`: 插入或更新
- `get_violation_images()`: 获取违规图片列表
- `get_statistics()`: 获取统计信息

### 6. schema.sql (数据库表结构)

包含三个表的定义：

**image_scan_records** (主表)
- 存储所有扫描记录
- 包含图片特征、检测结果、MinIO路径等
- 建立多个索引优化查询性能

**similar_images** (相似图片表)
- 记录相似图片关系
- 用于快速查找相似违规图片

**scan_statistics** (统计表)
- 汇总扫描统计数据
- 按日期和存储桶分组

## 数据流转

```
┌─────────────┐
│   MinIO     │ 图片存储
└──────┬──────┘
       │ list_objects()
       ▼
┌─────────────┐
│minio_client │ 遍历图片
└──────┬──────┘
       │ get_object_data()
       ▼
┌─────────────┐
│image_feature│ 计算特征
│   Extractor │ 
└──────┬──────┘
       │ calculate_key()
       │ extract_features()
       ▼
┌─────────────┐
│  database   │ 检查缓存
└──────┬──────┘
       │ find_by_key()
       ▼
   已存在？
   ┌─Yes─→ 跳过
   └─No
       │
       ▼
┌─────────────┐
│tencent_ims  │ 内容检测
│   Scanner   │
└──────┬──────┘
       │ scan_image()
       ▼
┌─────────────┐
│  database   │ 保存结果
└──────┬──────┘
       │ upsert_record()
       ▼
┌─────────────┐
│violations   │ 生成报告
│    .txt     │
└─────────────┘
```

## 配置流程

1. **复制配置文件**
   ```bash
   cp .env.example .env
   ```

2. **编辑.env文件**
   - 填写MinIO连接信息
   - 填写腾讯云密钥
   - 填写MySQL连接信息

3. **初始化数据库**
   ```bash
   mysql -u root -p < schema.sql
   ```

4. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

5. **运行扫描**
   ```bash
   ./run.sh
   # 或
   python scanner.py
   ```

## 关键技术点

### 1. 图片去重机制

**两级去重**：

1. **精确去重**（基于Key）
   - Key = MD5(文件内容) + "-" + 文件大小
   - 完全相同的图片只扫描一次

2. **相似去重**（基于特征哈希）
   - 计算pHash/dHash/aHash
   - 汉明距离 <= 5 认为相似
   - 发现相似违规图片时给出警告

### 2. 增量扫描

- 首次扫描：全量扫描所有图片
- 后续扫描：只扫描新上传的图片
- 强制重扫：设置 `FORCE_RESCAN=true`

### 3. 错误处理

- 单张图片失败不影响整体扫描
- 错误信息记录到数据库
- 详细日志保存到 scanner.log

### 4. 进度追踪

- 使用 tqdm 显示进度条
- 每100张图片输出统计
- 实时显示发现的违规图片

## 性能指标

**预期性能**（取决于网络和服务器配置）：

- 单张图片扫描时间：1-3秒
- 1000张图片：约30分钟
- 10000张图片：约5小时
- 内存占用：50-200MB
- CPU占用：20-50%

**优化建议**：

1. 网络优化：确保MinIO和腾讯云API网络畅通
2. 分批处理：大量图片使用 SCAN_LIMIT 分批
3. 并发处理：可改造为多进程并行扫描
4. 缓存利用：充分利用数据库缓存避免重复扫描

## 扩展方向

1. **Web界面**：开发管理后台查看扫描结果
2. **定时任务**：设置cron定期自动扫描
3. **消息通知**：发现违规图片时发送告警
4. **批量删除**：一键删除所有违规图片
5. **人工审核**：标记需要人工复核的图片
6. **统计分析**：更丰富的数据可视化报表

## 依赖包说明

| 包名 | 版本 | 用途 |
|------|------|------|
| minio | 7.2.0 | MinIO客户端SDK |
| Pillow | 10.2.0 | 图片处理库 |
| imagehash | 4.3.1 | 感知哈希算法 |
| numpy | 1.26.4 | 数值计算（imagehash依赖） |
| tencentcloud-sdk-python-ims | 3.0.1076 | 腾讯云IMS SDK |
| mysql-connector-python | 8.3.0 | MySQL驱动 |
| python-dotenv | 1.0.1 | 环境变量加载 |
| requests | 2.31.0 | HTTP请求库 |
| loguru | 0.7.2 | 日志记录 |
| tqdm | 4.66.2 | 进度条显示 |

---

**开发完成！** 🎉

如有问题，请查看：
- README.md - 项目概述
- USAGE.md - 详细使用指南
- scanner.log - 运行日志
