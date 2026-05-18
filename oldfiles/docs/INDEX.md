# 📚 图片内容安全扫描系统 - 文档索引

## 🎯 核心文档（必读）

### 1. [SCANNING_LOGIC.md](SCANNING_LOGIC.md) ⭐⭐⭐
**系统核心逻辑说明**
- 完整的9步扫描流程
- 三层去重机制详解
- 特征缓存优化方案
- API节约策略
- 性能分析和配置建议

**适合人群**: 开发人员、架构师、运维人员

---

### 2. [QUICK_REFERENCE.md](QUICK_REFERENCE.md) ⭐⭐⭐
**快速参考手册**
- 常用命令速查
- 配置项说明
- 故障排查指南
- 性能调优参数

**适合人群**: 所有用户

---

### 3. [USAGE.md](USAGE.md) ⭐⭐
**详细使用说明**
- 安装部署步骤
- 环境配置
- 运行方式
- 常见问题

**适合人群**: 新用户、运维人员

---

### 4. [DOCKER_GUIDE.md](DOCKER_GUIDE.md) ⭐⭐
**Docker部署指南**
- Docker Compose配置
- 容器化部署
- 数据持久化
- 网络配置

**适合人群**: 使用Docker部署的用户

---

### 5. [MINIO_ACCESS_CONTROL.md](MINIO_ACCESS_CONTROL.md) ⭐⭐
**MinIO访问控制实现**
- Bucket Policy配置
- 对象标签管理
- 违规图片访问控制
- 安全策略说明

**适合人群**: 安全管理员、运维人员

---

### 6. [PERFORMANCE_OPTIMIZATION.md](PERFORMANCE_OPTIMIZATION.md) ⭐
**性能优化指南**
- LRU缓存策略
- 内存占用分析
- 大规模场景优化
- 配置调优建议

**适合人群**: 处理千万级图片的用户

---

### 7. [LOG_GUIDE.md](LOG_GUIDE.md) ⭐
**日志系统使用指南**
- 四种日志输出说明
- 日志查询命令
- 故障排查方法
- 性能分析方法

**适合人群**: 开发人员、运维人员

---

## 📖 其他资源

### 根目录文档
- **[README.md](../README.md)** - 项目总览和快速开始
- **[schema.sql](../schema.sql)** - 数据库表结构
- **[.env.example](../.env.example)** - 环境变量模板

### 测试文件
- `test_ims_sdk.py` - SDK配置测试
- `test_ims_api_structure.py` - API结构测试
- `test_simple.py` - 简单功能测试
- `test_system.py` - 系统完整性测试

---

## 🔍 如何查找文档

### 按场景查找

#### 🚀 我要快速开始
→ 阅读 [README.md](../README.md) → [USAGE.md](USAGE.md)

#### 🔧 我要理解系统原理
→ 阅读 [SCANNING_LOGIC.md](SCANNING_LOGIC.md)

#### ⚡ 我要优化性能
→ 阅读 [PERFORMANCE_OPTIMIZATION.md](PERFORMANCE_OPTIMIZATION.md) → [QUICK_REFERENCE.md](QUICK_REFERENCE.md)

#### 🐳 我要用Docker部署
→ 阅读 [DOCKER_GUIDE.md](DOCKER_GUIDE.md)

#### 🔒 我要配置访问控制
→ 阅读 [MINIO_ACCESS_CONTROL.md](MINIO_ACCESS_CONTROL.md)

#### 🐛 我要排查问题
→ 阅读 [LOG_GUIDE.md](LOG_GUIDE.md) → [QUICK_REFERENCE.md](QUICK_REFERENCE.md)

#### 📊 我要查看违规图片
→ 阅读 [QUICK_REFERENCE.md](QUICK_REFERENCE.md) 中的"违规图片处理"章节

---

## 📝 文档维护

### 文档分类原则
- **核心文档**: 系统运行必需的知识
- **进阶文档**: 特定场景下的深入说明
- **参考文档**: 快速查阅的手册

### 更新频率
- 核心文档: 每次重大更新后
- 进阶文档: 相关功能变更时
- 参考文档: 定期整理

---

## 💡 建议阅读顺序

### 新用户
1. README.md (5分钟)
2. USAGE.md (10分钟)
3. QUICK_REFERENCE.md (5分钟)
4. 开始使用！

### 开发人员
1. SCANNING_LOGIC.md (30分钟)
2. LOG_GUIDE.md (10分钟)
3. PERFORMANCE_OPTIMIZATION.md (15分钟)
4. 深入代码

### 运维人员
1. USAGE.md (10分钟)
2. DOCKER_GUIDE.md (15分钟)
3. MINIO_ACCESS_CONTROL.md (10分钟)
4. LOG_GUIDE.md (10分钟)

---

**最后更新**: 2026-05-16
