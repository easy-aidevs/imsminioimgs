# 图片内容安全扫描系统 - 详细说明

## 📖 项目概述

这是一个基于Python的图片内容安全检测系统，集成了腾讯云IMS（图像内容安全）服务和MinIO对象存储，专门用于识别违规图片，特别是棋牌类赌博内容。

### 核心价值

💰 **节约API费用** - 通过感知哈希特征匹配，智能跳过相似图片的IMS检测，节约30-50%的API调用费用

## ✨ 核心功能

### 1. 智能去重机制

**两级去重策略**：

1. **精确去重**（基于MD5）
   - Key = MD5(文件内容) + "-" + 文件大小
   - 完全相同的图片只扫描一次
   - 即使文件名不同也能识别

2. **相似检测**（基于感知哈希）⭐核心功能
   - 计算pHash/dHash/aHash三种特征
   - 汉明距离 ≤ 3 认为高度相似
   - 直接标记为违规，**跳过IMS检测**

### 2. API费用节约机制

**智能分级策略**：

| 汉明距离 | 相似度 | 处理方式 | API节约 |
|---------|-------|---------|--------|
| 0-1 | 几乎相同 | ⚡ 直接标记违规 | 100% |
| 2-3 | 高度相似 | ⚡ 直接标记违规 | 100% |
| 4-5 | 中度相似 | 🔍 调用IMS确认 | 0% |
| >5 | 不相似 | 🔍 调用IMS检测 | 0% |

**实际效果**：
- 假设10,000张图片中有30%与已有违规图片相似
- 优化前：10,000次API调用，约¥100
- 优化后：6,500-7,000次API调用，约¥65-70
- **节省**：3,000-3,500次调用 + ¥30-35

### 3. 多维度特征提取

每个图片计算4种哈希特征：

- **pHash** (Perceptual Hash): 感知哈希，对缩放、亮度变化鲁棒（主要特征）
- **dHash** (Difference Hash): 差异哈希，对梯度变化敏感
- **aHash** (Average Hash): 平均哈希，简单快速
- **wHash** (Wavelet Hash): 小波哈希，结合频率和空间信息

### 4. 腾讯云IMS集成

调用腾讯云官方图片内容安全API，可识别：

| 违规类型 | 说明 | 重点关注 |
|---------|------|---------|
| gambling | 赌博/棋牌类 | ⭐⭐⭐ 重点监控 |
| porn | 色情内容 | ⭐⭐⭐ |
| violence | 暴力内容 | ⭐⭐ |
| politics | 政治敏感 | ⭐⭐ |
| terrorism | 恐怖主义 | ⭐⭐⭐ |
| ads | 广告 spam | ⭐ |
| contraband | 违禁品 | ⭐⭐ |
| vulgar | 低俗内容 | ⭐ |
| qrcode | 可疑二维码 | ⭐ |

### 5. 详细报告生成

扫描完成后自动生成：
- **violations.txt** - 违规图片清单（按类型分组）
- **scanner.log** - 详细日志文件
- **MySQL数据库** - 所有扫描记录可查询

### 6. 实时进度追踪

- 使用tqdm显示进度条
- 每100张图片输出统计
- 实时显示发现的违规图片
- 显示节约的API调用次数

## 🏗️ 系统架构

```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│   MinIO     │─────▶│  Python扫描器 │─────▶│   MySQL     │
│  图片存储    │      │              │      │  结果存储    │
└─────────────┘      └──────┬───────┘      └─────────────┘
                            │
                            ▼
                     ┌──────────────┐
                     │  腾讯云 IMS   │
                     │  内容检测API  │
                     └──────────────┘
```

### 工作流程

```
1. 遍历MinIO → 2. 计算Key → 3. 检查缓存
                                    ↓
                              已存在？
                              ├─ Yes → 跳过
                              └─ No
                                  ↓
4. 提取特征 → 5. 查找相似违规
                        ↓
                  找到且距离≤3？
                  ├─ Yes → ⚡ 直接标记（节约API）
                  └─ No  → 6. 调用IMS检测
                              ↓
                         7. 保存结果
```

## 🛠️ 技术栈

| 组件 | 技术 | 版本 | 用途 |
|------|------|------|------|
| 语言 | Python | 3.7+ | 主开发语言 |
| MinIO SDK | minio | 7.2.0 | 对象存储客户端 |
| 图片处理 | Pillow | 10.2.0 | 图片读取和处理 |
| 哈希算法 | imagehash | 4.3.1 | 感知哈希计算 |
| 云服务SDK | tencentcloud-sdk-python-ims | 3.0.1076 | 腾讯云IMS API |
| 数据库驱动 | mysql-connector-python | 8.3.0 | MySQL连接 |
| 日志 | loguru | 0.7.2 | 日志记录 |
| 进度条 | tqdm | 4.66.2 | 进度显示 |
| 容器化 | Docker | 20.10+ | 应用部署 |

## 📊 性能指标

### 扫描速度

| 图片数量 | 预计耗时 | 说明 |
|---------|---------|------|
| 100张 | 2-5分钟 | 测试规模 |
| 1,000张 | 30-50分钟 | 小规模 |
| 10,000张 | 5-8小时 | 中等规模 |
| 100,000张 | 2-3天 | 大规模 |

### 资源占用

- **内存**: 50-200MB
- **CPU**: 20-50%
- **网络**: 取决于图片大小和数量
- **磁盘**: 主要用于日志和报告

### API节约效果

| 场景 | 重复率 | API节约率 | 费用节约 |
|------|-------|----------|---------|
| 少量重复 | 10% | ~15% | ¥15/万张 |
| 中等重复 | 30% | ~35% | ¥35/万张 |
| 大量重复 | 50% | ~50% | ¥50/万张 |

## 🎯 适用场景

### 推荐使用

✅ **电商平台** - 检测用户上传的商品图片  
✅ **社交平台** - 审核用户发布的图片内容  
✅ **游戏平台** - 特别关注棋牌类违规图片  
✅ **内容社区** - 自动识别违规图片  
✅ **企业内网** - 监控内部图片存储  

### 不适用

❌ 图片数量极少（<100张）  
❌ 不需要内容审核  
❌ 没有MinIO或MySQL环境  

## 🔧 配置说明

### 必要配置项

在 `.env` 文件中必须设置：

```ini
# MinIO配置
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=your_access_key
MINIO_SECRET_KEY=your_secret_key
MINIO_BUCKET_NAME=images

# MySQL配置
MYSQL_HOST=localhost
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=image_security

# 腾讯云IMS配置（必填）
TENCENT_SECRET_ID=your_secret_id
TENCENT_SECRET_KEY=your_secret_key
```

### 可选配置项

```ini
# 扫描控制
SCAN_PREFIX=uploads/        # 只扫描特定前缀
SCAN_LIMIT=1000             # 限制扫描数量
FORCE_RESCAN=false          # 强制重新扫描

# 网络配置
DOCKER_NETWORK_MODE=host    # host或bridge
MINIO_SECURE=false          # 是否使用HTTPS

# 特征配置
HASH_SIZE=8                 # 哈希大小（8=64位）
```

## 📈 使用建议

### 首次使用

1. **建立违规样本库**
   - 先扫描一批已知违规图片
   - 让系统学习违规特征
   - 后续扫描可大幅节约API

2. **分批扫描**
   - 首次使用 `SCAN_LIMIT=100` 测试
   - 确认配置正确后全量扫描
   - 大量图片分批次处理

3. **监控节约效果**
   - 查看日志中的"节约API"统计
   - 评估API费用节省情况
   - 调整相似度阈值（如需）

### 生产环境

1. **定时扫描**
   - 设置cron任务定期扫描
   - 只扫描新增图片
   - 避免重复扫描

2. **告警通知**
   - 发现违规图片时发送告警
   - 特别关注棋牌类违规
   - 及时处理高风险内容

3. **数据备份**
   - 定期备份MySQL数据库
   - 保留扫描历史记录
   - 便于审计和追溯

## ❓ 常见问题

### Q1: 如何最大化节约API费用？

**A**: 
1. 确保数据库中有足够的已标记违规图片样本
2. 首次扫描时建立违规图片库
3. 后续扫描会自动利用特征匹配节约API
4. 相似度阈值可根据实际情况调整（默认≤3）

### Q2: 相似度阈值可以调整吗？

**A**: 可以，修改 `scanner.py` 第197行：
```python
if distance <= 3:  # 调整为其他值，如2或4
```
- 调小（如2）：更严格，准确性高，节约少
- 调大（如4）：更宽松，节约多，可能误判

### Q3: 如何查看节约了多少API调用？

**A**: 扫描过程中会实时显示：
```
统计信息 - 总数: 100, 已扫描: 95, 违规: 3, 
跳过: 5, 错误: 0, 节约API: 25次
```

### Q4: 误判如何处理？

**A**: 
1. 查看置信度（confidence），低置信度的可能是误判
2. suggestion为"Review"的建议人工复核
3. 可以在数据库中标记误判图片
4. 联系腾讯云技术支持优化模型

### Q5: 扫描中断后如何继续？

**A**: 直接重新运行即可，系统会自动跳过已扫描的图片：
```bash
docker-compose up
```

### Q6: 如何只扫描特定目录？

**A**: 设置 `SCAN_PREFIX` 环境变量：
```bash
SCAN_PREFIX=uploads/2024/ docker-compose up
```

### Q7: 数据库表结构如何初始化？

**A**: 
```bash
mysql -h YOUR_MYSQL_HOST -u root -p < schema.sql
```

### Q8: 如何查看违规报告？

**A**: 
```bash
# 查看文本报告
cat data/violations.txt

# 查询数据库
docker-compose exec mysql mysql -u root -p
SELECT * FROM image_scan_records WHERE is_violation = 1;
```

## 🔍 故障排查

### 问题1: 连接MinIO失败

**检查**：
- `MINIO_ENDPOINT` 是否正确
- `ACCESS_KEY` 和 `SECRET_KEY` 是否有效
- 网络是否可达

**解决**：
```bash
# 测试连接
docker-compose run --rm scanner python -c "
from minio_client import MinIOClient
import os
client = MinIOClient(
    endpoint=os.getenv('MINIO_ENDPOINT'),
    access_key=os.getenv('MINIO_ACCESS_KEY'),
    secret_key=os.getenv('MINIO_SECRET_KEY')
)
print(client.list_buckets())
"
```

### 问题2: MySQL连接失败

**检查**：
- MySQL服务是否运行
- 用户名密码是否正确
- 数据库是否已创建

**解决**：
```bash
# 测试连接
docker-compose run --rm scanner python -c "
from database import ImageDatabase
import os
db = ImageDatabase(
    host=os.getenv('MYSQL_HOST'),
    port=int(os.getenv('MYSQL_PORT', '3306')),
    user=os.getenv('MYSQL_USER'),
    password=os.getenv('MYSQL_PASSWORD'),
    database=os.getenv('MYSQL_DATABASE')
)
print('连接成功')
db.close()
"
```

### 问题3: IMS API调用失败

**检查**：
- 腾讯云密钥是否正确
- 账户余额是否充足
- API配额是否用完

**查看日志**：
```bash
docker-compose logs scanner | grep -i error
```

### 问题4: 扫描速度慢

**可能原因**：
- 网络带宽不足
- 图片数量巨大
- IMS API限流

**优化建议**：
- 使用 `SCAN_LIMIT` 分批处理
- 检查网络连接
- 联系腾讯云提升API配额

## 📚 相关文档

- **[INDEX.md](INDEX.md)** - 文档导航索引
- **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** - 快速参考卡片
- **[USAGE.md](USAGE.md)** - 详细使用指南
- **[DOCKER_GUIDE.md](DOCKER_GUIDE.md)** - Docker部署指南
- **[PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)** - 项目结构说明
- **[DELIVERY.md](DELIVERY.md)** - 项目交付说明

---

**祝您使用愉快！** 🎉

如有问题，请查看详细文档或检查日志文件。
