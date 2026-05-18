# Docker部署指南

## 概述

本系统已完全容器化，使用Docker Compose一键部署MySQL、MinIO和图片扫描应用。

## 前置要求

- Docker 20.10+
- Docker Compose 2.0+
- 至少4GB可用内存
- 至少10GB可用磁盘空间

## 快速开始

### 1. 配置环境变量

```bash
# 复制Docker环境配置模板
cp .env.docker .env

# 编辑.env文件，填写腾讯云密钥
vim .env
```

**必须修改的配置**：
```ini
TENCENT_SECRET_ID=你的腾讯云SecretId
TENCENT_SECRET_KEY=你的腾讯云SecretKey
```

**可选修改**：
```ini
# MySQL密码（建议修改）
MYSQL_ROOT_PASSWORD=your_secure_password
MYSQL_PASSWORD=your_scanner_password

# MinIO密码（建议修改）
MINIO_ROOT_PASSWORD=your_minio_password

# 存储桶名称
MINIO_BUCKET_NAME=my-images
```

### 2. 启动所有服务

```bash
# 构建并启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps
```

首次启动会：
- 自动构建Python应用镜像
- 启动MySQL数据库（自动初始化表结构）
- 启动MinIO对象存储
- 自动创建存储桶
- 运行图片扫描任务

### 3. 查看日志

```bash
# 查看所有服务日志
docker-compose logs -f

# 只查看扫描器日志
docker-compose logs -f scanner

# 查看MySQL日志
docker-compose logs -f mysql

# 查看MinIO日志
docker-compose logs -f minio
```

### 4. 访问服务

#### MinIO控制台
- URL: http://localhost:9001
- 用户名: minioadmin（或你在.env中设置的值）
- 密码: minioadmin123（或你在.env中设置的值）

#### MySQL数据库
- 主机: localhost
- 端口: 3306
- 用户名: scanner
- 密码: scanner_password（或你在.env中设置的值）
- 数据库: image_security

### 5. 上传测试图片

通过MinIO控制台或mc客户端上传图片到存储桶：

```bash
# 使用mc客户端（需要安装minio/mc）
mc alias set myminio http://localhost:9000 minioadmin minioadmin123
mc cp ./test-image.jpg myminio/images/
```

### 6. 重新运行扫描

```bash
# 停止当前扫描器
docker-compose stop scanner

# 重新运行扫描
docker-compose up scanner

# 或者强制重扫
FORCE_RESCAN=true docker-compose up scanner
```

## 常用命令

### 服务管理

```bash
# 启动所有服务
docker-compose up -d

# 停止所有服务
docker-compose down

# 重启某个服务
docker-compose restart scanner

# 查看服务状态
docker-compose ps

# 查看资源使用
docker stats
```

### 扫描控制

```bash
# 限制扫描数量（测试用）
SCAN_LIMIT=100 docker-compose up scanner

# 扫描特定前缀
SCAN_PREFIX=uploads/2024/ docker-compose up scanner

# 强制重新扫描
FORCE_RESCAN=true docker-compose up scanner

# 后台运行扫描
docker-compose up -d scanner
```

### 数据管理

```bash
# 进入MySQL容器
docker-compose exec mysql mysql -u scanner -p image_security

# 进入MinIO容器
docker-compose exec minio sh

# 进入扫描器容器
docker-compose exec scanner bash

# 查看违规报告
docker-compose exec scanner cat /app/data/violations.txt

# 拷贝违规报告到本地
docker-compose cp scanner:/app/data/violations.txt ./violations.txt
```

### 清理和重置

```bash
# 停止并删除容器（保留数据卷）
docker-compose down

# 停止并删除容器和数据卷（危险！）
docker-compose down -v

# 重建应用镜像
docker-compose build --no-cache scanner

# 清理未使用的镜像
docker image prune -f
```

## 架构说明

```
┌─────────────────────────────────────────┐
│         Docker Compose Network          │
│                                         │
│  ┌──────────┐    ┌──────────┐          │
│  │  MinIO   │◄──►│  Scanner │          │
│  │  :9000   │    │  (Python)│          │
│  └──────────┘    └────┬─────┘          │
│                       │                 │
│                  ┌────▼─────┐          │
│                  │  MySQL   │          │
│                  │  :3306   │          │
│                  └──────────┘          │
└─────────────────────────────────────────┘
           │              │
      Port 9000     Port 3306
           │              │
      ┌────▼──────────────▼────┐
      │      Host Machine      │
      └────────────────────────┘
```

### 服务说明

1. **mysql**: MySQL 8.0数据库
   - 自动初始化表结构
   - 数据持久化在 `mysql_data` 卷
   - 健康检查确保就绪

2. **minio**: MinIO对象存储
   - 提供S3兼容API
   - 数据持久化在 `minio_data` 卷
   - Web控制台在9001端口

3. **scanner**: Python扫描应用
   - 等待MySQL和MinIO就绪后启动
   - 执行扫描任务后自动退出
   - 日志和报告挂载到本地目录

4. **mc**: MinIO客户端工具
   - 自动创建存储桶
   - 设置访问策略
   - 完成后自动退出

## 数据持久化

### 数据卷

- `mysql_data`: MySQL数据库文件
- `minio_data`: MinIO存储的图片数据

### 本地挂载

- `./logs`: 扫描日志目录
- `./data`: 扫描结果和报告

```bash
# 查看数据卷
docker volume ls | grep ims

# 备份数据卷
docker run --rm -v ims_mysql_data:/data -v $(pwd):/backup alpine tar czf /backup/mysql-backup.tar.gz -C /data .

# 恢复数据卷
docker run --rm -v ims_mysql_data:/data -v $(pwd):/backup alpine tar xzf /backup/mysql-backup.tar.gz -C /data
```

## 性能优化

### 资源配置

在 `docker-compose.yml` 中添加资源限制：

```yaml
services:
  scanner:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
```

### 批量扫描

对于大量图片，建议分批处理：

```bash
# 每次扫描1000张
SCAN_LIMIT=1000 docker-compose up scanner

# 扫描完成后，继续下一批
SCAN_LIMIT=1000 SCAN_PREFIX=batch2/ docker-compose up scanner
```

## 故障排查

### 问题1: 容器启动失败

```bash
# 查看详细日志
docker-compose logs scanner

# 检查容器状态
docker-compose ps

# 检查网络连接
docker network inspect ims_ims-network
```

### 问题2: MySQL连接失败

```bash
# 检查MySQL是否就绪
docker-compose exec mysql mysqladmin ping -u root -p${MYSQL_ROOT_PASSWORD}

# 查看MySQL日志
docker-compose logs mysql

# 重启MySQL
docker-compose restart mysql
```

### 问题3: MinIO连接失败

```bash
# 检查MinIO健康状态
curl http://localhost:9000/minio/health/live

# 查看MinIO日志
docker-compose logs minio

# 检查存储桶是否存在
docker-compose exec mc mc ls myminio
```

### 问题4: 扫描器无响应

```bash
# 查看扫描器日志
docker-compose logs -f scanner

# 进入容器调试
docker-compose exec scanner bash

# 手动运行扫描
docker-compose exec scanner python scanner.py
```

### 问题5: 磁盘空间不足

```bash
# 查看Docker磁盘使用
docker system df

# 清理未使用的资源
docker system prune -a

# 清理日志
docker-compose logs --tail=0
```

## 安全建议

1. **修改默认密码**
   ```ini
   MYSQL_ROOT_PASSWORD=强密码
   MINIO_ROOT_PASSWORD=强密码
   ```

2. **不要提交.env文件到Git**
   ```bash
   # 已添加到.gitignore
   echo ".env" >> .gitignore
   ```

3. **限制网络访问**
   ```yaml
   # 只暴露必要的端口
   ports:
     - "127.0.0.1:3306:3306"  # 只允许本地访问
   ```

4. **定期更新镜像**
   ```bash
   docker-compose pull
   docker-compose up -d --build
   ```

## 生产环境部署

### 使用外部MinIO和MySQL

如果已有MinIO和MySQL，可以只运行scanner：

```yaml
# docker-compose.scanner-only.yml
version: '3.8'
services:
  scanner:
    build: .
    environment:
      MINIO_ENDPOINT: your-minio-server:9000
      MYSQL_HOST: your-mysql-server
      # ... 其他配置
```

```bash
docker-compose -f docker-compose.scanner-only.yml up
```

### 使用Docker Swarm

```bash
# 初始化Swarm
docker swarm init

# 部署服务
docker stack deploy -c docker-compose.yml ims-stack

# 查看服务
docker stack services ims-stack
```

### 使用Kubernetes

需要编写Kubernetes manifests，参考 `docker-compose.yml` 中的配置。

## 监控和告警

### 健康检查

```bash
# 检查所有服务健康状态
docker-compose ps

# 查看资源使用
docker stats ims-scanner ims-mysql ims-minio
```

### 日志轮转

在 `docker-compose.yml` 中配置：

```yaml
services:
  scanner:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

## 常见问题

### Q: 如何修改扫描参数？

编辑 `.env` 文件，然后重新运行：

```bash
docker-compose up scanner
```

### Q: 数据存在哪里？

- MySQL数据: Docker卷 `ims_mysql_data`
- MinIO数据: Docker卷 `ims_minio_data`
- 扫描日志: `./logs` 目录
- 扫描报告: `./data` 目录

### Q: 如何备份数据？

```bash
# 备份MySQL
docker-compose exec mysqldump -u scanner -p image_security > backup.sql

# 备份MinIO
docker-compose exec mc mc mirror myminio/images /backup
```

### Q: 如何升级版本？

```bash
# 拉取最新代码
git pull

# 重新构建
docker-compose build --no-cache

# 重启服务
docker-compose down
docker-compose up -d
```

---

**Docker部署完成！** 🎉

如有问题，请查看日志：
```bash
docker-compose logs -f
```
