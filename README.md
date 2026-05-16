# 图片内容安全扫描系统

基于腾讯云IMS和感知哈希算法的图片内容安全检测系统，专门用于识别违规图片（特别是棋牌类），通过智能特征匹配大幅节约API调用费用。

## ✨ 核心特性

- 🎯 **智能去重**: 基于MD5的精确去重，避免重复扫描
- 💰 **节约API费用**: 感知哈希特征匹配，高度相似图片直接标记，节省30-50% API调用
- 🔍 **多维度特征**: pHash/dHash/aHash三种特征算法，准确识别相似图片
- ☁️ **腾讯云IMS**: 集成官方API，准确识别违规内容
- 🎲 **重点监控**: 特别关注棋牌类(gambling)等违规图片
- 📊 **详细报告**: 自动生成违规图片清单和统计信息
- 🐳 **Docker部署**: 一键容器化部署，支持外部MySQL和MinIO

## 🚀 快速开始

### 方式1: Docker部署（推荐）

```bash
# 1. 克隆项目
git clone <your-repo>
cd imsminioimgs

# 2. 配置环境
cp .env.example .env
vim .env  # 填写您的配置

# 3. 初始化数据库（首次使用）
mysql -h YOUR_MYSQL_HOST -u root -p < schema.sql

# 4. 启动扫描
docker-compose up
```

### 方式2: 本地运行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境
cp .env.example .env
vim .env

# 3. 运行扫描
python scanner.py
```

### 方式3: 处理违规图片

扫描完成后，使用专用工具处理违规图片（基于MinIO权限控制）：

```bash
# 第1步: 查看所有违规图片
python handle_violations.py list

# 第2步: 标记违规图片为blocked（设置MinIO标签）
python handle_violations.py block --type gambling

# 第3步: 查看被blocked的文件
python handle_violations.py list-blocked

# 第4步: 如有误判，恢复文件
python handle_violations.py restore --ids 1,2,3

# 第5步: 确认无误后，彻底删除
python handle_violations.py delete-blocked
```

**优势**：
- ✅ 文件路径保持不变
- ✅ URL不受影响
- ✅ 可快速恢复
- ✅ 性能更好

**详细说明**: [docs/VIOLATION_HANDLING_PERMISSIONS.md](docs/VIOLATION_HANDLING_PERMISSIONS.md)

## 📋 必要配置

编辑 `.env` 文件，至少填写以下配置：

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

## 💡 API费用节约机制

本系统通过**感知哈希特征匹配**智能节约API调用：

```
新图片 → 计算特征哈希 → 查询数据库
                              ↓
                    找到相似违规图片？
                    ├─ 是 → 汉明距离 ≤ 3?
                    │        ├─ 是 → ⚡ 直接标记违规（节省100% API费用）
                    │        └─ 否 → 调用IMS确认
                    └─ 否 → 调用IMS检测
```

**节约效果**：
- 汉明距离 0-1: 几乎相同，直接标记
- 汉明距离 2-3: 高度相似，直接标记
- 汉明距离 4-5: 中度相似，仍调用IMS保证准确性

**实际案例**（10,000张图片，30%重复/相似）：
- 优化前: 10,000次API调用，约¥100
- 优化后: 7,000次API调用，约¥70
- **节省**: 3,000次调用 + ¥30

## 📊 系统架构

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

## 📁 项目结构

```
imsminioimgs/
├── scanner.py              # 主程序
├── minio_client.py         # MinIO客户端
├── image_feature.py        # 特征提取
├── tencent_ims.py          # 腾讯云IMS
├── database.py             # 数据库操作
├── docker-compose.yml      # Docker配置
├── Dockerfile              # Docker镜像
├── .env.example            # 配置模板
├── schema.sql              # 数据库表结构
├── requirements.txt        # Python依赖
├── docker-start.sh         # 启动脚本
└── docs/                   # 文档目录
    ├── INDEX.md            # 文档索引
    ├── README.md           # 详细说明
    ├── USAGE.md            # 使用指南
    ├── QUICK_REFERENCE.md  # 快速参考
    └── ...
```

## 📖 详细文档

所有详细文档都在 `docs/` 目录中：

- **[docs/INDEX.md](docs/INDEX.md)** - 文档导航索引 ⭐从这里开始
- **[docs/README.md](docs/README.md)** - 项目详细说明
- **[docs/USAGE.md](docs/USAGE.md)** - 完整使用指南
- **[docs/QUICK_REFERENCE.md](docs/QUICK_REFERENCE.md)** - 快速参考卡片
- **[docs/DOCKER_GUIDE.md](docs/DOCKER_GUIDE.md)** - Docker部署指南

## 🔧 常用命令

```bash
# 启动扫描
docker-compose up

# 查看日志
docker-compose logs -f scanner

# 限制扫描数量（测试用）
SCAN_LIMIT=100 docker-compose up

# 强制重新扫描
FORCE_RESCAN=true docker-compose up

# 查看违规报告
cat data/violations.txt

# 进入数据库
docker-compose exec mysql mysql -u root -p
```

## 🎯 违规类型

系统可识别以下违规类型：

| 类型 | 说明 | 重点关注 |
|------|------|----------|
| gambling | 赌博/棋牌类 | ⭐⭐⭐ 重点监控 |
| porn | 色情内容 | ⭐⭐⭐ |
| violence | 暴力内容 | ⭐⭐ |
| politics | 政治敏感 | ⭐⭐ |
| terrorism | 恐怖主义 | ⭐⭐⭐ |
| ads | 广告 spam | ⭐ |
| contraband | 违禁品 | ⭐⭐ |
| vulgar | 低俗内容 | ⭐ |

## 💻 技术栈

- **Python 3.7+**
- **MinIO SDK** - 对象存储客户端
- **Pillow + ImageHash** - 图片处理和特征提取
- **腾讯云IMS SDK** - 内容安全检测
- **MySQL Connector** - 数据库驱动
- **Docker + Docker Compose** - 容器化部署

## 📈 性能指标

| 指标 | 数值 |
|------|------|
| 单张图片扫描时间 | 1-3秒 |
| 1000张图片耗时 | 约30分钟 |
| API费用节约 | 30-50% |
| 内存占用 | 50-200MB |

## ❓ 常见问题

### Q: 如何最大化节约API费用？

A: 
1. 确保数据库中有足够的已标记违规图片样本
2. 首次扫描时建立违规图片库
3. 后续扫描会自动利用特征匹配节约API

### Q: 相似度阈值可以调整吗？

A: 可以，修改 `scanner.py` 中的距离判断逻辑：
```python
if distance <= 3:  # 调整为其他值
    # 直接标记违规
```

### Q: 如何查看节约了多少API调用？

A: 扫描过程中会实时显示：
```
统计信息 - 总数: 100, 已扫描: 95, 违规: 3, 
跳过: 5, 错误: 0, 节约API: 25次
```

更多问题请查看 [docs/USAGE.md](docs/USAGE.md)

## 📄 许可证

MIT License

## 🤝 支持

- 📖 文档: [docs/INDEX.md](docs/INDEX.md)
- 🐛 问题: 查看日志 `docker-compose logs scanner`
- 📧 联系: 查看详细文档获取支持

---

**开始使用**: `docker-compose up` 🚀
