# Docker 部署指南

## 概述

使用 Docker 和 Docker Compose 可以快速部署和运行图片安全扫描系统，避免本地依赖配置问题。

## 前置条件

- Docker 20.10+
- Docker Compose 1.29+

**检查版本**：
```bash
docker --version
docker-compose --version
```

## 快速开始（5 分钟）

### 1. 配置环境

```bash
cd claude
cp .env.example .env
# 编辑 .env，填入实际的 MinIO 和 MySQL 配置
vim .env
```

### 2. 构建镜像

```bash
docker-compose build
```

### 3. 运行扫描器

```bash
docker-compose run --rm scanner python scanner.py
```

### 4. 运行处置工具

```bash
docker-compose run --rm handler python handle_violations.py list
```

## Docker 镜像详解

### Dockerfile 结构

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
HEALTHCHECK CMD python -c "import mysql.connector, minio"
```

**特点**：
- 基于官方 Python 镜像
- 精简大小（slim 版本）
- 包含健康检查
- 完整的依赖安装

### 构建镜像

```bash
# 构建（会创建 imsminioimgs-scanner:latest 等镜像）
docker-compose build

# 或单独构建
docker build -t imsminioimgs:latest .
```

## Docker Compose 配置

### 服务

```yaml
services:
  scanner:
    # 扫描器服务
    build: .
    container_name: imsminioimgs-scanner
    environment:
      # 环境变量来自 .env 文件
      - MYSQL_HOST=host.docker.internal  # Docker 访问宿主机的地址
      - MINIO_ENDPOINT=minio:9000
      # ... 其他配置
    volumes:
      - ./logs:/app/logs  # 日志输出目录
    depends_on:
      mysql:
        condition: service_healthy

  handler:
    # 处置工具服务
    build: .
    container_name: imsminioimgs-handler
    # ... 配置同上
```

### 网络

Docker Compose 自动创建网络，使服务间可通信：

```
scanner ←→ MySQL (host.docker.internal:3306)
handler ←→ MinIO (host.docker.internal:9000)
```

## 使用方式

### 方式 1：一次性执行

```bash
# 运行扫描器，执行后自动停止
docker-compose run --rm scanner python scanner.py

# 运行处置工具
docker-compose run --rm handler python handle_violations.py list
```

### 方式 2：后台运行

```bash
# 启动容器（后台）
docker-compose up -d scanner

# 查看日志
docker-compose logs -f scanner

# 停止容器
docker-compose down
```

### 方式 3：交互式 Shell

```bash
# 进入容器 Shell
docker-compose run --rm scanner /bin/bash

# 在容器内运行命令
$ python scanner.py
$ python handle_violations.py list
$ exit
```

## 日志管理

### 查看日志

```bash
# 实时查看 scanner 日志
docker-compose logs -f scanner

# 实时查看 handler 日志
docker-compose logs -f handler

# 查看最后 100 行
docker-compose logs --tail=100 scanner
```

### 本地日志文件

容器内的日志输出到本地 `logs/` 目录：

```bash
# 查看本地日志文件
tail -f logs/scan.log
tail -f logs/violations.log
tail -f logs/error.log
```

## 常见命令

### 扫描器

```bash
# 标准扫描（增量）
docker-compose run --rm scanner python scanner.py

# 强制重新扫描
docker-compose run --rm scanner python scanner.py --force-rescan

# 跳过 IMS 扫描（仅去重）
docker-compose run --rm scanner python scanner.py --skip-ims

# 指定桶
docker-compose run --rm scanner python scanner.py --bucket images
```

### 处置工具

```bash
# 查看新增违规
docker-compose run --rm handler python handle_violations.py list

# 标记为私密
docker-compose run --rm handler python handle_violations.py mark-private --type gambling

# 查看观察中的图片
docker-compose run --rm handler python handle_violations.py list-private

# 确认隔离
docker-compose run --rm handler python handle_violations.py confirm-quarantine --ids 1,2,3

# 恢复公开
docker-compose run --rm handler python handle_violations.py restore-public --ids 4

# 查看已隔离的
docker-compose run --rm handler python handle_violations.py list-quarantined

# 删除
docker-compose run --rm handler python handle_violations.py delete --ids 1
```

## 可选：本地 MySQL 和 MinIO

如果想在 Docker 中运行 MySQL 和 MinIO，修改 `docker-compose.yml` 取消注释相关部分：

```yaml
services:
  mysql:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: root
      MYSQL_DATABASE: image_security
    ports:
      - "3306:3306"
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
      timeout: 20s
      retries: 10

  minio:
    image: minio/minio:latest
    ports:
      - "9000:9000"
      - "9001:9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    command: server /data --console-address ":9001"
```

然后修改 `.env` 配置：

```ini
MYSQL_HOST=mysql         # 使用 Docker 服务名
MINIO_ENDPOINT=minio:9000

# 注意：在 Docker 网络内，使用服务名代替 localhost
```

启动：

```bash
# 启动所有服务（包括 MySQL 和 MinIO）
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止所有服务
docker-compose down
```

## 故障排查

### 问题：容器启动失败

```bash
# 查看错误日志
docker-compose logs scanner

# 检查容器状态
docker-compose ps

# 清理和重建
docker-compose down
docker-compose build --no-cache
docker-compose run --rm scanner python scanner.py
```

### 问题：MySQL 连接失败

**原因**：Docker 容器内无法连接宿主机的 MySQL

**解决**：
```bash
# 在 .env 中使用特殊 IP
MYSQL_HOST=host.docker.internal   # Mac/Windows
# 或
MYSQL_HOST=172.17.0.1              # Linux（Docker 宿主网关 IP）
```

### 问题：MinIO 连接失败

**原因**：端口映射或 IP 配置错误

**解决**：
```bash
# 确保 MinIO 正在运行
docker ps | grep minio

# 检查 .env 中的 MINIO_ENDPOINT
# 宿主机上运行容器：使用 host.docker.internal:9000
# Docker 网络内运行容器：使用 minio:9000
```

### 问题：权限问题

```bash
# 确保 logs 目录可写
chmod 777 logs

# 或在容器内创建
docker-compose run --rm scanner mkdir -p logs && chmod 777 logs
```

## 部署到生产环境

### 使用 systemd（Linux）

创建 `/etc/systemd/system/imsminioimgs.service`：

```ini
[Unit]
Description=Image Security Scanning System
After=docker.service
Requires=docker.service

[Service]
Type=simple
WorkingDirectory=/opt/imsminioimgs/claude
ExecStart=/usr/bin/docker-compose up
ExecStop=/usr/bin/docker-compose down
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启动服务：

```bash
sudo systemctl start imsminioimgs
sudo systemctl enable imsminioimgs
sudo systemctl status imsminioimgs
```

### 定时扫描（cron）

```bash
# 每天凌晨 2 点运行扫描
0 2 * * * cd /opt/imsminioimgs/claude && docker-compose run --rm scanner python scanner.py >> /var/log/imsminioimgs-scan.log 2>&1
```

## 性能优化

### 1. 内存和 CPU 限制

在 `docker-compose.yml` 中添加资源限制：

```yaml
services:
  scanner:
    # ...
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          cpus: '1'
          memory: 2G
```

### 2. 并发处理

修改代码中的并发数（如果实现了），或通过启动多个容器。

### 3. 日志轮转

配置 Docker 日志驱动：

```yaml
services:
  scanner:
    # ...
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

## 清理和维护

```bash
# 停止所有容器
docker-compose down

# 删除未使用的镜像
docker image prune

# 查看镜像占用空间
docker images

# 删除所有停止的容器
docker container prune

# 完整清理（谨慎）
docker system prune -a
```

---

← [INDEX](./INDEX.md) | [INSTALLATION](./INSTALLATION.md) | [PRODUCTION](./PRODUCTION.md) →
