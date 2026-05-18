# 快速修复指南

## 🐛 当前问题

错误信息：
```
code:UnknownParameter message:未定义参数 Ontent
```

**原因**: Docker容器中运行的是旧版本代码，还没有应用最新的修复。

---

## ✅ 解决方案

### 方案1: 重新构建Docker镜像（推荐）

```bash
# 1. 停止当前容器
docker-compose down

# 2. 重新构建镜像（不使用缓存）
docker-compose build --no-cache scanner

# 3. 启动容器
docker-compose up -d scanner

# 4. 查看日志确认
docker-compose logs -f scanner
```

### 方案2: 如果直接运行Python

```bash
# 确保使用的是最新代码
python scanner.py --limit 5
```

---

## 🔍 验证修复

### 检查容器中的代码

```bash
# 进入容器
docker-compose exec scanner bash

# 查看tencent_ims.py的关键部分
cat /app/tencent_ims.py | grep -A 5 "req.Content"

# 应该看到：
# req.Content = image_base64
# req.BizType = biz_type or "default"
```

### 查看实时日志

```bash
# 成功的情况
docker-compose logs -f scanner | grep "图片扫描完成"

# 失败的情况
docker-compose logs -f scanner | grep "ERROR"
```

---

## 📝 正确的代码应该是

```python
# tencent_ims.py 第83-84行
req.Content = image_base64  # ✅ 注意是 Content，不是 Ontent
req.BizType = biz_type or "default"
```

---

## ⚠️ 常见陷阱

### 1. Docker缓存问题

即使你修改了本地代码，Docker可能还在使用旧的镜像层。

**解决**: 使用 `--no-cache` 强制重新构建

```bash
docker-compose build --no-cache scanner
```

### 2. 容器未重启

修改代码后，必须重启容器才能生效。

**解决**: 
```bash
docker-compose restart scanner
# 或者
docker-compose up -d scanner
```

### 3. 多个容器实例

可能有多个scanner容器在运行。

**解决**:
```bash
# 查看所有容器
docker ps -a | grep scanner

# 停止所有旧容器
docker-compose down

# 重新启动
docker-compose up -d
```

---

## 🎯 完整操作流程

```bash
# 1. 确认本地代码已修复
cat tencent_ims.py | grep -A 2 "req.Content"

# 2. 停止所有服务
docker-compose down

# 3. 清理旧镜像
docker rmi imsminioimgs_scanner 2>/dev/null || true

# 4. 重新构建（无缓存）
docker-compose build --no-cache scanner

# 5. 启动服务
docker-compose up -d

# 6. 等待容器启动
sleep 5

# 7. 查看日志
docker-compose logs scanner

# 8. 实时监控
docker-compose logs -f scanner
```

---

## ✅ 成功的标志

日志中应该看到：

```
[2026-05-18 12:20:00.123] [INFO    ] 准备调用IMS API - 图片大小: 555750 bytes, Base64长度: 741000
[2026-05-18 12:20:01.456] [DEBUG   ] 图片扫描完成 - 违规: False, 类型: None, 置信度: 0.0
```

**不再出现**:
```
❌ 腾讯云IMS扫描失败
  - API错误码: UnknownParameter
  - API错误消息: 未定义参数 Ontent
```

---

## 🆘 如果还有问题

### 检查清单

- [ ] 本地代码是否正确？（`req.Content` 不是 `req.Ontent`）
- [ ] 是否重新构建了镜像？（`docker-compose build --no-cache`）
- [ ] 是否重启了容器？（`docker-compose up -d`）
- [ ] 是否有多个容器在运行？（`docker ps | grep scanner`）
- [ ] 日志是否显示最新时间？（确认是新容器）

### 获取帮助

提供以下信息：

```bash
# 1. 本地代码
cat tencent_ims.py | grep -B 2 -A 2 "req.Content"

# 2. 容器中的代码
docker-compose exec scanner cat /app/tencent_ims.py | grep -B 2 -A 2 "req.Content"

# 3. 镜像信息
docker images | grep scanner

# 4. 容器状态
docker ps -a | grep scanner

# 5. 最新日志
docker-compose logs --tail=50 scanner
```

---

**执行完上述步骤后，问题应该就能解决了！** 🎉
