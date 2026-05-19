# Docker 配置分析与改进方案

**分析日期：** 2026-05-19

---

## 📋 目录

1. [当前配置问题分析](#当前配置问题分析)
2. [改进方案](#改进方案)
3. [改进后的文件](#改进后的文件)
4. [使用指南](#使用指南)
5. [生产部署建议](#生产部署建议)

---

## 当前配置问题分析

### 🔴 问题 1：docker-compose.yml 不完整

**现状：**
```yaml
services:
  scanner:
    build: ...
    command: ["python", "scanner.py"]
```

**问题：**
- ❌ 只定义了 `scanner` 服务
- ❌ 没有定义 `handle_violations` 服务
- ❌ 没有定义 MySQL/MinIO 等依赖服务
- ❌ 无法通过 Docker 运行 handle_violations.py
- ❌ 运维人员必须手动在容器外部维护 MySQL 和 MinIO

**影响：**
- 两个工具无法通过统一的 Docker 环境管理
- 运维人员需要分别处理依赖服务
- 无法快速部署完整的开发/测试环境

---

### 🔴 问题 2：Dockerfile 启动方式过于简单

**现状：**
```dockerfile
CMD ["sleep", "infinity"]
```

**问题：**
- ❌ 容器启动后什么都不做，只睡眠
- ❌ 不支持灵活的命令执行
- ❌ 运维人员必须手动 `docker exec` 进入容器执行命令
- ❌ 难以自动化和编排

**影响：**
- 无法一键启动扫描或处置任务
- 容器使用体验差

---

### 🟡 问题 3：缺少依赖服务配置

**现状：**
- MySQL 和 MinIO 都运行在宿主机
- docker-compose 没有定义这些服务
- 新部署时需要手动配置

**问题：**
- ❌ 完全依赖宿主机上的服务
- ❌ 无法快速初始化整个环境
- ❌ 如果使用容器化 MySQL 需要手动配置

---

### 🟡 问题 4：缺少 Docker 使用文档

**现状：**
- README 中提到 `docker-compose up`，但没有具体说明
- 没有专门的 Docker 使用指南

**问题：**
- ❌ 运维人员不知道如何使用 Docker
- ❌ 没有说明环境变量配置
- ❌ 没有说明如何运行两个不同的工具

---

## 改进方案

### ✅ 方案总览

```
改进前：                      改进后：
───────────────────────────────────────
单服务 (scanner 只)    →    多服务支持
                           ├─ scanner（扫描）
                           ├─ handler（处置）
                           ├─ mysql（可选）
                           └─ minio（可选）

简陋的启动方式         →    灵活的启动方式
(sleep infinity)            ├─ 扫描：docker-compose run
                           ├─ 处置：docker-compose run
                           └─ 交互：docker-compose exec

宿主机依赖             →    完整的容器化
(mysql/minio on host)       ├─ 可选择宿主机服务
                           └─ 或使用容器化服务
```

---

## 改进后的文件

### 1. 改进的 Dockerfile

**关键改进：**
- 移除 `sleep infinity` 命令
- 增加启动脚本支持灵活的命令执行
- 添加健康检查
- 优化镜像大小

**新 Dockerfile：**

```dockerfile
# 使用Python 3.9 slim镜像作为基础
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# 复制应用代码
COPY . .

# 创建日志和数据目录
RUN mkdir -p /app/logs /app/data && \
    chmod 777 /app/logs /app/data

# 设置卷挂载点
VOLUME ["/app/logs"]

# 健康检查（检查Python是否可用）
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import mysql.connector; print('OK')" || exit 1

# 默认命令：显示帮助（可被覆盖）
# 运维人员通过 docker-compose run 或 command 指定具体命令
CMD ["python", "-c", "print('请通过 docker-compose run 执行具体命令，或参考 README 使用说明')"]
```

---

### 2. 改进的 docker-compose.yml

**关键改进：**
- 添加 `scanner` 服务（扫描）
- 添加 `handler` 服务（处置）
- 添加可选的 `mysql` 和 `minio` 服务
- 支持环境变量覆盖
- 清晰的服务依赖关系

**新 docker-compose.yml：**

```yaml
version: '3.8'

services:
  # ================================================================
  # 依赖服务（可选，如果宿主机已有可跳过）
  # ================================================================
  
  # MySQL 数据库（可选）
  # 取消注释此部分来启用容器化 MySQL
  # mysql:
  #   image: mysql:8.0
  #   container_name: ims-mysql
  #   restart: unless-stopped
  #   environment:
  #     MYSQL_ROOT_PASSWORD: ${MYSQL_PASSWORD:-root}
  #     MYSQL_DATABASE: ${MYSQL_DATABASE:-image_security}
  #     TZ: Asia/Shanghai
  #   ports:
  #     - "3306:3306"
  #   volumes:
  #     - mysql_data:/var/lib/mysql
  #     - ./schema.sql:/docker-entrypoint-initdb.d/schema.sql:ro
  #   healthcheck:
  #     test: ["CMD", "mysqladmin", "ping", "-h", "localhost"]
  #     interval: 10s
  #     timeout: 5s
  #     retries: 5

  # MinIO 对象存储（可选）
  # 取消注释此部分来启用容器化 MinIO
  # minio:
  #   image: minio/minio:latest
  #   container_name: ims-minio
  #   restart: unless-stopped
  #   environment:
  #     MINIO_ROOT_USER: ${MINIO_ACCESS_KEY:-minioadmin}
  #     MINIO_ROOT_PASSWORD: ${MINIO_SECRET_KEY:-minioadmin}
  #     TZ: Asia/Shanghai
  #   ports:
  #     - "9000:9000"
  #     - "9001:9001"
  #   volumes:
  #     - minio_data:/data
  #   command: server /data --console-address ":9001"
  #   healthcheck:
  #     test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
  #     interval: 10s
  #     timeout: 5s
  #     retries: 5

  # ================================================================
  # 应用服务
  # ================================================================

  # 扫描器服务
  scanner:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: ims-scanner
    restart: "no"
    environment:
      # MinIO 配置
      MINIO_ENDPOINT: ${MINIO_ENDPOINT:-localhost:9000}
      MINIO_ACCESS_KEY: ${MINIO_ACCESS_KEY}
      MINIO_SECRET_KEY: ${MINIO_SECRET_KEY}
      MINIO_SECURE: ${MINIO_SECURE:-false}
      MINIO_BUCKET_NAME: ${MINIO_BUCKET_NAME:-images}
      QUARANTINE_BUCKET_NAME: ${QUARANTINE_BUCKET_NAME:-quarantine}

      # 腾讯云 IMS 配置
      TENCENT_SECRET_ID: ${TENCENT_SECRET_ID}
      TENCENT_SECRET_KEY: ${TENCENT_SECRET_KEY}
      TENCENT_REGION: ${TENCENT_REGION:-ap-guangzhou}

      # MySQL 配置
      MYSQL_HOST: ${MYSQL_HOST:-host.docker.internal}
      MYSQL_PORT: ${MYSQL_PORT:-3306}
      MYSQL_USER: ${MYSQL_USER:-root}
      MYSQL_PASSWORD: ${MYSQL_PASSWORD}
      MYSQL_DATABASE: ${MYSQL_DATABASE:-image_security}

      # 扫描参数
      HASH_SIZE: ${HASH_SIZE:-8}
      SCAN_PREFIX: ${SCAN_PREFIX:-}
      FORCE_RESCAN: ${FORCE_RESCAN:-false}
      SCAN_LIMIT: ${SCAN_LIMIT:-}

      TZ: Asia/Shanghai
    volumes:
      - ./logs:/app/logs
      - ./.env:/app/.env:ro
    # 使用 host 网络模式可以访问宿主机的服务
    network_mode: ${DOCKER_NETWORK_MODE:-host}
    # 默认命令：显示帮助
    command: ["python", "-c", "print('请使用 docker-compose run scanner python scanner.py')"]
    # 取消注释以下行来自动运行扫描（生产环境不建议）
    # command: ["python", "scanner.py"]

  # 违规处置服务
  handler:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: ims-handler
    restart: "no"
    environment:
      # MinIO 配置
      MINIO_ENDPOINT: ${MINIO_ENDPOINT:-localhost:9000}
      MINIO_ACCESS_KEY: ${MINIO_ACCESS_KEY}
      MINIO_SECRET_KEY: ${MINIO_SECRET_KEY}
      MINIO_SECURE: ${MINIO_SECURE:-false}
      MINIO_BUCKET_NAME: ${MINIO_BUCKET_NAME:-images}
      QUARANTINE_BUCKET_NAME: ${QUARANTINE_BUCKET_NAME:-quarantine}

      # MySQL 配置
      MYSQL_HOST: ${MYSQL_HOST:-host.docker.internal}
      MYSQL_PORT: ${MYSQL_PORT:-3306}
      MYSQL_USER: ${MYSQL_USER:-root}
      MYSQL_PASSWORD: ${MYSQL_PASSWORD}
      MYSQL_DATABASE: ${MYSQL_DATABASE:-image_security}

      TZ: Asia/Shanghai
    volumes:
      - ./logs:/app/logs
      - ./.env:/app/.env:ro
    network_mode: ${DOCKER_NETWORK_MODE:-host}
    # 默认命令：显示帮助
    command: ["python", "-c", "print('请使用 docker-compose run handler python handle_violations.py [command]')"]

# 命名卷（如果使用容器化 MySQL/MinIO）
# volumes:
#   mysql_data:
#   minio_data:
```

---

### 3. 改进的 .env.example（Docker 部分）

添加以下说明：

```ini
# ================================================================
# Docker 相关配置
# ================================================================

# Docker 网络模式
# host   - 容器共享宿主机网络，可直接访问 localhost
# bridge - 需要用特殊地址 host.docker.internal (Mac/Windows) 或宿主机IP (Linux)
DOCKER_NETWORK_MODE=host

# 当 DOCKER_NETWORK_MODE=bridge 时，使用以下地址访问宿主机服务
# MYSQL_HOST=host.docker.internal    # Mac/Windows
# MYSQL_HOST=172.17.0.1               # Linux（Docker0网桥IP）
# MINIO_ENDPOINT=host.docker.internal:9000
```

---

## 使用指南

### 🚀 快速开始（宿主机 MySQL/MinIO）

```bash
cd claude

# 1. 配置环境
cp .env.example .env
vim .env

# 2. 构建镜像（首次或更新依赖后）
docker-compose build

# 3. 运行扫描
docker-compose run --rm scanner python scanner.py

# 4. 运行处置工具
docker-compose run --rm handler python handle_violations.py list
docker-compose run --rm handler python handle_violations.py mark-private --type gambling
```

### 🔧 完整部署（包括 MySQL 和 MinIO）

```bash
# 1. 取消注释 docker-compose.yml 中的 mysql 和 minio 服务

# 2. 初始化数据库
docker-compose up -d mysql
docker-compose run --rm mysql \
  mysql -h mysql -u root -p"${MYSQL_PASSWORD}" \
  < schema.sql

# 3. 启动 MinIO
docker-compose up -d minio

# 4. 运行应用
docker-compose run --rm scanner python scanner.py
docker-compose run --rm handler python handle_violations.py list
```

### 🎯 常用命令

```bash
# 查看日志
docker-compose logs scanner
docker-compose logs handler
docker-compose logs -f handler  # 实时日志

# 进入容器交互式 shell
docker-compose run --rm handler bash

# 运行具体命令
docker-compose run --rm scanner python scanner.py --scan-prefix photos/
docker-compose run --rm handler python handle_violations.py mark-private --type gambling --dry-run

# 清理容器和镜像
docker-compose down
docker system prune
```

---

## 生产部署建议

### 部署架构

```
┌─────────────────────────────────────┐
│ 生产环境                             │
├─────────────────────────────────────┤
│                                      │
│  ┌─ Scanner Docker Container ─┐   │
│  │ python scanner.py           │   │
│  │ (定时任务触发)              │   │
│  └─────────────────────────────┘   │
│           ↓                          │
│  ┌─ Handler Docker Container ─┐   │
│  │ python handle_violations.py │   │
│  │ (人工操作或自动化)          │   │
│  └─────────────────────────────┘   │
│           ↓                          │
│  ┌───────────────────────────────┐  │
│  │  MySQL (宿主机或容器)         │  │
│  │  MinIO (宿主机或容器)         │  │
│  └───────────────────────────────┘  │
│                                      │
└─────────────────────────────────────┘
```

### 推荐配置

**选项 1：宿主机服务 + Docker 应用**（推荐）
```
优势：
  ✓ 应用容器化，易于更新和部署
  ✓ 依赖服务独立管理，稳定性高
  ✓ 不受容器网络问题影响

缺点：
  ✗ 需要维护宿主机上的 MySQL/MinIO

使用场景：
  - 企业级部署
  - MySQL/MinIO 已经稳定运行
```

**选项 2：完全容器化**
```
优势：
  ✓ 一键部署完整环境
  ✓ 易于跨机器迁移

缺点：
  ✗ 所有服务共享主机资源
  ✗ 调试网络问题更复杂

使用场景：
  - 开发/测试环境
  - 快速演示
  - 单机部署
```

### 使用 systemd 定时运行扫描

```bash
# /etc/systemd/system/ims-scanner.service
[Unit]
Description=Image Security Scanner
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
WorkingDirectory=/path/to/project/claude
ExecStart=/usr/bin/docker-compose run --rm scanner python scanner.py
User=root

[Install]
WantedBy=multi-user.target
```

```bash
# /etc/systemd/system/ims-scanner.timer
[Unit]
Description=Run IMS Scanner daily
Requires=ims-scanner.service

[Timer]
OnCalendar=daily
OnCalendar=*-*-* 02:00:00  # 每天凌晨 2 点
Persistent=true

[Install]
WantedBy=timers.target
```

启用定时任务：
```bash
sudo systemctl daemon-reload
sudo systemctl enable ims-scanner.timer
sudo systemctl start ims-scanner.timer
sudo systemctl list-timers
```

### Kubernetes 部署（可选）

对于更大规模的部署，可以转换为 Kubernetes Deployment：

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ims-scanner
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ims-scanner
  template:
    metadata:
      labels:
        app: ims-scanner
    spec:
      containers:
      - name: scanner
        image: ims:latest
        imagePullPolicy: Always
        env:
        - name: MYSQL_HOST
          value: mysql-service
        - name: MINIO_ENDPOINT
          value: minio-service:9000
        command: ["python", "scanner.py"]
        volumeMounts:
        - name: logs
          mountPath: /app/logs
      volumes:
      - name: logs
        emptyDir: {}
```

---

## 改进总结

| 方面 | 原配置 | 改进后 |
|------|--------|--------|
| 服务数量 | 1 个（scanner） | 2+ 个（scanner + handler） |
| 依赖服务 | 不支持 | 支持容器化依赖 |
| 启动方式 | sleep infinity | 灵活的命令执行 |
| 文档 | 无 | 完整的使用指南 |
| 生产部署 | 不适合 | 支持完整的部署建议 |
| 扩展性 | 有限 | 支持 systemd/K8s |

---

**建议行动：**
1. 替换 Dockerfile（支持灵活启动）
2. 替换 docker-compose.yml（支持两个服务）
3. 新增 DOCKER_DEPLOYMENT.md（完整的部署指南）
4. 更新 .env.example（添加 Docker 相关说明）
5. 为运维人员提供快速开始指南
