# Docker 部署指南

**目标受众：** 运维人员  
**最后更新：** 2026-05-19

---

## 快速开始（5 分钟）

### 前置条件

- Docker & Docker Compose 已安装
- MySQL 和 MinIO 已在宿主机运行（或容器中）
- `.env` 文件已正确配置

### 第一次使用

```bash
cd claude

# 1. 配置环境变量
cp .env.example .env
# 编辑 .env，填入实际的配置值

# 2. 构建镜像
docker-compose build

# 3. 运行扫描（第一次）
docker-compose run --rm scanner python scanner.py

# 4. 查看结果
docker-compose run --rm handler python handle_violations.py list
```

---

## 完整使用指南

### 🔍 基本命令

#### 构建镜像

```bash
# 构建镜像（首次或更新依赖后）
docker-compose build

# 构建特定服务
docker-compose build scanner
docker-compose build handler

# 显示构建进度
docker-compose build --progress=plain

# 忽略缓存重新构建
docker-compose build --no-cache
```

#### 运行扫描器

```bash
# 基本扫描（全量）
docker-compose run --rm scanner python scanner.py

# 扫描特定前缀
docker-compose run --rm scanner python scanner.py --scan-prefix photos/

# 强制重新扫描（不使用缓存）
docker-compose run --rm scanner sh -c "FORCE_RESCAN=true python scanner.py"

# 仅扫描前 100 张（测试）
docker-compose run --rm scanner sh -c "SCAN_LIMIT=100 python scanner.py"

# 查看实时日志
docker-compose run --rm scanner tail -f logs/scan.log
```

#### 运行处置工具

```bash
# 列出未处理的违规
docker-compose run --rm handler python handle_violations.py list

# 列出观察中的
docker-compose run --rm handler python handle_violations.py list-private

# 标记为私密
docker-compose run --rm handler python handle_violations.py mark-private --type gambling

# 标记为私密（干运行）
docker-compose run --rm handler python handle_violations.py mark-private --type gambling --dry-run

# 确认隔离
docker-compose run --rm handler python handle_violations.py confirm-quarantine --ids 1,2,3

# 改回公开
docker-compose run --rm handler python handle_violations.py restore-public --ids 4,5

# 彻底删除
docker-compose run --rm handler python handle_violations.py delete --ids 1,2,3

# 查看实时日志
docker-compose run --rm handler tail -f logs/violations.log
```

#### 日志查看

```bash
# 查看扫描日志
docker-compose logs scanner

# 查看处置日志
docker-compose logs handler

# 实时查看日志
docker-compose logs -f handler

# 查看最后 100 行
docker-compose logs --tail=100 scanner

# 保存日志到文件
docker-compose logs > all_logs.txt
```

#### 进入容器

```bash
# 进入 scanner 容器的 bash
docker-compose run --rm scanner bash

# 进入 handler 容器并执行命令
docker-compose run --rm handler python -c "import mysql.connector; print('MySQL 连接正常')"

# 运行 Python 交互式shell
docker-compose run --rm handler python
```

#### 清理

```bash
# 停止并删除所有容器
docker-compose down

# 删除镜像
docker-compose down --rmi all

# 清理未使用的资源
docker system prune
```

---

## 配置选项

### 网络模式

#### Host 模式（推荐用于宿主机服务）

```bash
DOCKER_NETWORK_MODE=host
```

**优点：**
- 容器直接访问 localhost 服务
- 无需额外配置
- 性能最好

**缺点：**
- 容器与宿主机共享网络命名空间
- 不能在容器中运行同端口的服务

**适用场景：**
- MySQL/MinIO 运行在宿主机
- 大多数生产环境

#### Bridge 模式（用于容器化服务）

```bash
DOCKER_NETWORK_MODE=bridge
```

**配置 DNS：**

Linux（Docker0 网桥）：
```env
MYSQL_HOST=172.17.0.1
MINIO_ENDPOINT=172.17.0.1:9000
```

Mac/Windows（特殊地址）：
```env
MYSQL_HOST=host.docker.internal
MINIO_ENDPOINT=host.docker.internal:9000
```

容器服务（使用服务名）：
```env
MYSQL_HOST=mysql
MINIO_ENDPOINT=minio:9000
```

---

## 部署场景

### 场景 1：开发环境（宿主机 MySQL/MinIO）

**配置：**
```bash
# .env
MYSQL_HOST=localhost
MYSQL_PASSWORD=root
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
DOCKER_NETWORK_MODE=host
```

**启动：**
```bash
# 在宿主机启动 MySQL 和 MinIO
# 然后运行

docker-compose build
docker-compose run --rm scanner python scanner.py
docker-compose run --rm handler python handle_violations.py list
```

---

### 场景 2：测试环境（完全容器化）

**启用容器化服务：**

编辑 `docker-compose.yml`，取消注释 `mysql` 和 `minio` 部分。

**配置：**
```bash
# .env
MYSQL_HOST=mysql
MYSQL_PASSWORD=testpass123
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=testuser
MINIO_SECRET_KEY=testpass
DOCKER_NETWORK_MODE=bridge
```

**启动：**
```bash
# 启动 MySQL
docker-compose up -d mysql
sleep 10  # 等待 MySQL 启动

# 初始化数据库
docker-compose exec -T mysql mysql -h mysql -u root -p"testpass123" \
  image_security < schema.sql

# 启动 MinIO
docker-compose up -d minio

# 运行应用
docker-compose run --rm scanner python scanner.py
docker-compose run --rm handler python handle_violations.py list

# 停止服务
docker-compose down
```

---

### 场景 3：生产环境（最小化配置）

**Docker 仅运行应用，依赖服务使用宿主机：**

```bash
# .env
DOCKER_NETWORK_MODE=host
MYSQL_HOST=localhost
MYSQL_PASSWORD=[SECURE_PASSWORD]
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=[SECURE_KEY]
MINIO_SECRET_KEY=[SECURE_SECRET]
```

**使用 systemd 定时运行扫描：**

`/etc/systemd/system/ims-scanner.service`:
```ini
[Unit]
Description=IMS Scanner Service
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
WorkingDirectory=/opt/ims/claude
ExecStart=/usr/bin/docker-compose run --rm scanner python scanner.py
# 失败时重试
Restart=on-failure
RestartSec=300

[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/ims-scanner.timer`:
```ini
[Unit]
Description=IMS Scanner Timer
Requires=ims-scanner.service

[Timer]
# 每天凌晨 2 点运行
OnCalendar=*-*-* 02:00:00
# 容器不存在时仍运行
Persistent=true

[Install]
WantedBy=timers.target
```

启用定时任务：
```bash
sudo systemctl daemon-reload
sudo systemctl enable ims-scanner.timer
sudo systemctl start ims-scanner.timer

# 查看定时任务状态
sudo systemctl list-timers --all

# 查看日志
sudo journalctl -u ims-scanner.service -f
```

---

## 故障排查

### 问题 1：无法连接 MySQL

**错误信息：**
```
mysql.connector.errors.DatabaseError: 2003: Can't connect to MySQL server on 'localhost:3306'
```

**解决方案：**

1. 检查 MySQL 是否运行
   ```bash
   docker-compose run --rm handler \
     python -c "import socket; socket.create_connection(('localhost', 3306), 5)"
   ```

2. 检查主机名配置
   ```bash
   # 如果使用 bridge 网络，需要用特殊地址
   MYSQL_HOST=host.docker.internal  # Mac/Windows
   MYSQL_HOST=172.17.0.1             # Linux
   ```

3. 检查 .env 文件
   ```bash
   # 确保 MYSQL_PASSWORD 正确
   docker-compose run --rm handler \
     python -c "import os; print(f'MYSQL_PASSWORD={os.getenv(\"MYSQL_PASSWORD\")}')"
   ```

---

### 问题 2：无法连接 MinIO

**错误信息：**
```
minio.error.S3Error: Access Denied. User: ...
```

**解决方案：**

1. 检查 MinIO 是否运行
   ```bash
   curl -v http://localhost:9000
   ```

2. 检查访问密钥
   ```bash
   # 确保 MINIO_ACCESS_KEY 和 MINIO_SECRET_KEY 正确
   docker-compose run --rm handler \
     python -c "import os; print(f'KEY={os.getenv(\"MINIO_ACCESS_KEY\")}')"
   ```

3. 检查端点配置
   ```bash
   # 检查网络连通性
   docker-compose run --rm handler \
     python -c "import socket; socket.create_connection(('localhost', 9000), 5)"
   ```

---

### 问题 3：日志写入失败

**错误信息：**
```
PermissionError: [Errno 13] Permission denied: 'logs/scan.log'
```

**解决方案：**

1. 检查 logs 目录权限
   ```bash
   ls -la logs/
   chmod 777 logs/
   ```

2. 检查卷挂载
   ```bash
   # 确保 docker-compose.yml 中有
   volumes:
     - ./logs:/app/logs
   ```

---

### 问题 4：镜像构建失败

**错误信息：**
```
error: externally-managed-environment
```

**解决方案：**

```bash
# 重新构建，忽略缓存
docker-compose build --no-cache

# 或手动删除镜像后重建
docker rmi ims:scanner
docker rmi ims:handler
docker-compose build
```

---

### 问题 5：容器占用磁盘空间

**清理步骤：**

```bash
# 查看 Docker 磁盘使用
docker system df

# 清理未使用的镜像
docker image prune

# 清理未使用的卷
docker volume prune

# 清理一切（谨慎使用）
docker system prune -a
```

---

## 高级用法

### 使用 Docker 卷持久化数据

```yaml
volumes:
  mysql_data:
    driver: local
  minio_data:
    driver: local
```

### 使用自定义网络

```yaml
networks:
  ims-net:
    driver: bridge

services:
  scanner:
    networks:
      - ims-net
```

### 使用 .dockerignore 优化镜像

已配置（见 `.dockerignore`）：
- Python 缓存
- Git 文件
- IDE 文件
- 日志
- 文档

### 多阶段构建（优化镜像大小）

可选：如果需要进一步优化镜像大小，可使用多阶段构建。

---

## 监控和日志

### 日志轮转配置

日志已在 `logger_config.py` 中配置：

```python
rotation="100 MB"      # 每 100MB 轮转
retention="30 days"    # 保留 30 天
compression="zip"      # 压缩旧日志
```

### 在 Docker 中查看日志

```bash
# 实时查看
docker-compose logs -f handler

# 查看特定时间范围
docker-compose logs --since 2026-05-19T10:00:00 scanner

# 查看最后 N 行
docker-compose logs --tail=50 handler
```

---

## 性能优化建议

1. **使用 host 网络模式**
   - 避免 bridge 模式的网络开销

2. **配置资源限制**
   ```yaml
   services:
     scanner:
       deploy:
         resources:
           limits:
             cpus: '2'
             memory: 2G
   ```

3. **使用 BuildKit 加速构建**
   ```bash
   DOCKER_BUILDKIT=1 docker-compose build
   ```

4. **定期清理日志**
   ```bash
   find logs/ -name "*.log.zip" -mtime +30 -delete
   ```

---

## 安全建议

1. **保护 .env 文件**
   ```bash
   chmod 600 .env
   git add .env.example  # 提交示例，不提交实际值
   ```

2. **使用强密码**
   - MYSQL_PASSWORD 应该强度高
   - MINIO_SECRET_KEY 应该长且复杂

3. **限制容器权限**
   ```yaml
   services:
     scanner:
       read_only: true
       security_opt:
         - no-new-privileges:true
   ```

4. **使用镜像签名**
   ```bash
   docker trust inspect ims:scanner
   ```

---

**更多信息请参考：** [TWO_ENTRY_POINTS.md](TWO_ENTRY_POINTS.md)
