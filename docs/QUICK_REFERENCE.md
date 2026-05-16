# 图片内容安全扫描系统 - 快速参考卡

## 🚀 5分钟快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境
cp .env.example .env
vim .env  # 填写您的配置

# 3. 初始化数据库
mysql -u root -p < schema.sql

# 4. 运行扫描
python scanner.py
```

## 📋 必要配置项

在 `.env` 文件中必须设置：

```ini
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=你的密钥
MINIO_SECRET_KEY=你的密钥
MINIO_BUCKET_NAME=要扫描的桶名

TENCENT_SECRET_ID=你的ID
TENCENT_SECRET_KEY=你的密钥

MYSQL_PASSWORD=你的密码
```

## 🎯 常用命令

```bash
# 验证系统
./verify.sh

# 交互式扫描（推荐）
./run.sh

# 直接扫描
python scanner.py

# 扫描指定前缀
SCAN_PREFIX=uploads/2024/ python scanner.py

# 限制数量（测试用）
SCAN_LIMIT=100 python scanner.py

# 强制重扫
FORCE_RESCAN=true python scanner.py
```

## 📊 查看结果

### 控制台
实时显示扫描进度和违规图片

### 违规报告
```bash
cat violations.txt
```

### 数据库查询
```sql
-- 所有违规图片
SELECT * FROM image_scan_records WHERE is_violation = 1;

-- 棋牌类违规
SELECT * FROM image_scan_records WHERE violation_type = 'gambling';

-- 统计信息
SELECT violation_type, COUNT(*) FROM image_scan_records 
WHERE is_violation = 1 GROUP BY violation_type;
```

## 🔍 违规类型

| 类型 | 说明 | 重点 |
|------|------|------|
| gambling | 赌博/棋牌 | ⭐⭐⭐ |
| porn | 色情 | ⭐⭐⭐ |
| violence | 暴力 | ⭐⭐ |
| politics | 政治敏感 | ⭐⭐ |
| terrorism | 恐怖主义 | ⭐⭐⭐ |

## ⚙️ 环境变量

| 变量 | 说明 | 示例 |
|------|------|------|
| SCAN_BUCKET_NAME | 存储桶名称 | my-images |
| SCAN_PREFIX | 对象前缀 | uploads/ |
| SCAN_LIMIT | 限制数量 | 1000 |
| FORCE_RESCAN | 强制重扫 | true/false |

## 🐛 故障排查

### 问题1: 连接MinIO失败
- 检查 `MINIO_ENDPOINT` 是否正确
- 验证 `ACCESS_KEY` 和 `SECRET_KEY`
- 确认网络可达

### 问题2: 数据库连接失败
- 确认MySQL服务运行中
- 检查用户名密码
- 确认数据库已创建

### 问题3: IMS API调用失败
- 验证腾讯云密钥
- 检查账户余额
- 确认API配额充足

### 查看详细日志
```bash
tail -f scanner.log
```

## 📁 文件说明

| 文件 | 用途 |
|------|------|
| scanner.py | 主程序 |
| minio_client.py | MinIO操作 |
| image_feature.py | 特征提取 |
| tencent_ims.py | IMS检测 |
| database.py | 数据库操作 |
| schema.sql | 表结构 |
| .env | 配置文件 |
| run.sh | 启动脚本 |
| violations.txt | 违规报告 |
| scanner.log | 详细日志 |

## 💡 提示

1. **首次扫描**: 建议先用 `SCAN_LIMIT=100` 测试
2. **增量扫描**: 系统自动跳过已扫描图片
3. **相似检测**: 汉明距离≤5认为相似
4. **中断续扫**: 直接重新运行即可继续
5. **定期备份**: 备份MySQL数据库

## 📞 获取帮助

- 详细文档: 查看 `USAGE.md`
- 项目结构: 查看 `PROJECT_STRUCTURE.md`
- 交付说明: 查看 `DELIVERY.md`
- 日志文件: `scanner.log`

---
**快速参考 | 版本 1.0 | 2024**
