# 快速开始（5 分钟）

**目标：** 第一次运行系统，看到实际效果

---

## 前置条件

- Python 3.8+ 或 Docker
- MySQL 已启动并有可用的数据库
- MinIO 已启动并有可用的存储桶
- 网络能访问腾讯云 API（仅扫描器需要）

---

## 方案 A：本地运行（推荐快速试验）

### 1. 安装依赖（3 分钟）

```bash
cd claude
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# 或 .venv\Scripts\activate  Windows

pip install -r requirements.txt
```

### 2. 配置环境（1 分钟）

```bash
cp .env.example .env
# 编辑 .env，填入实际的配置值
```

**最关键的几个配置：**

```ini
MYSQL_HOST=localhost
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=image_security

MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET_NAME=images

TENCENT_SECRET_ID=your_secret_id        # 仅扫描器需要
TENCENT_SECRET_KEY=your_secret_key      # 仅扫描器需要
```

### 3. 初始化数据库（1 分钟）

```bash
mysql -u root -p < schema.sql
```

### 4. 运行扫描器（可选）

```bash
python scanner.py
```

**输出示例：**
```
[2026-05-19 10:00:00] | INFO | 扫描器初始化完成
[2026-05-19 10:00:01] | INFO | 遍历完成，共 100 张图片
统计 - 总:100 | IMS扫描:95 | 路径复用:0 | 内容复用:3 | 特征复用:2 | 复用合计:5 | 违规:3 | 错误:0
```

### 5. 运行处置工具

```bash
# 查看新增违规
python handle_violations.py list

# 预演：标记赌博图片为私密
python handle_violations.py mark-private --sub-label Gambling --dry-run

# 实际执行
python handle_violations.py mark-private --sub-label Gambling
```

---

## 方案 B：Docker 运行（推荐生产）

### 1. 配置环境（1 分钟）

```bash
cd claude
cp .env.example .env
# 编辑 .env
```

### 2. 构建镜像（2 分钟）

```bash
docker-compose build
```

### 3. 运行扫描

```bash
docker-compose run --rm scanner python scanner.py
```

### 4. 运行处置工具

```bash
docker-compose run --rm handler python handle_violations.py list
docker-compose run --rm handler python handle_violations.py mark-private --sub-label Gambling
```

---

## 验证成功

如果你看到以下结果，说明配置正确：

### 扫描器正常

```bash
$ python scanner.py

[时间] | INFO | 扫描器初始化完成
[时间] | INFO | 扫描完成 ...
```

### 处置工具正常

```bash
$ python handle_violations.py list

未处理的违规图片（blocked=0）（共 N 条）
```

### 数据库正常

```bash
$ mysql image_security -e "SELECT COUNT(*) FROM image_scan_records"
| COUNT(*) |
|----------|
|   N      |
```

---

## 常见问题（遇到问题？）

| 问题 | 解决 |
|------|------|
| `DatabaseError: Access denied` | 检查 MYSQL_PASSWORD 是否正确 |
| `S3Error: Access Denied` | 检查 MINIO_ACCESS_KEY/SECRET_KEY |
| `ModuleNotFoundError: No module named ...` | 运行 `pip install -r requirements.txt` |
| `mkdir logs 权限被拒` | 运行 `chmod 777 logs` 或使用 `sudo` |

---

## 下一步

- 想了解工作流？→ [三阶段工作流](./WORKFLOW.md)
- 想深入使用？→ [使用指南](./USAGE.md)
- 想理解系统设计？→ [系统架构](./ARCHITECTURE.md)
- 想部署到生产？→ [生产部署](./PRODUCTION.md)

---

详细的说明请参考完整文档：[文档导航](./INDEX.md)
