# 文档导航中心

欢迎使用图片内容安全扫描系统！本页面帮助你快速找到所需的文档。

---

## 按角色快速导航

### 我是第一次使用者

**目标：** 快速了解系统并运行起来

1. [快速开始](./QUICK_START.md)（5 分钟）
   - 最小化配置
   - 一键启动
   
2. [系统架构](./ARCHITECTURE.md)（10 分钟）
   - 了解两个工具
   - 理解数据流

3. [安装指南](./INSTALLATION.md)（15 分钟）
   - 详细的安装步骤
   - 环境配置

**然后选择**：
- Docker 部署？→ [Docker 指南](./DOCKER.md)

---

### 我是开发者

**目标：** 快速理解代码，进行二次开发

1. [系统架构](./ARCHITECTURE.md)
   - 代码组织
   - 模块说明

2. [扫描逻辑](./SCANNING_LOGIC.md)
   - 三层去重机制
   - 特征提取算法

3. [数据库设计](./DATABASE.md)
   - 表结构说明
   - 字段含义

---

### 我是运维人员

**目标：** 快速部署和维护

1. [Docker 部署](./DOCKER.md)（推荐）
   - Docker 使用指南
   - 常用命令
   - 故障排查

2. [生产部署](./PRODUCTION.md)
   - 生产级别建议
   - 监控告警
   - 日志管理

---

### 我是业务使用者

**目标：** 了解如何处置违规图片

1. [快速开始](./QUICK_START.md)
   - 最基本的使用

2. [三阶段工作流](./WORKFLOW.md)
   - 详细的处置流程
   - 每个命令说明

---

## 完整文档列表

### 入门（开始这里）

| 文档 | 适合 | 阅读时间 |
|------|------|---------|
| [快速开始](./QUICK_START.md) | 所有人 | 5 分钟 |
| [项目概述](../README.md) | 所有人 | 5 分钟 |

### 核心概念

| 文档 | 内容 | 深度 |
|------|------|------|
| [系统架构](./ARCHITECTURE.md) | 系统整体设计 | ⭐⭐ |
| [三阶段工作流](./WORKFLOW.md) | 处置流程详解 | ⭐⭐ |
| [数据库设计](./DATABASE.md) | 数据表结构 | ⭐⭐⭐ |
| [扫描逻辑](./SCANNING_LOGIC.md) | 图片检测机制 | ⭐⭐⭐ |

### 安装和配置

| 文档 | 用途 |
|------|------|
| [安装指南](./INSTALLATION.md) | 完整安装步骤 |
| [Docker 部署](./DOCKER.md) | 容器化部署 |
| [生产部署](./PRODUCTION.md) | 生产环境建议 |

### 使用指南

| 文档 | 说明 |
|------|------|
| [使用指南](./USAGE.md) | 两个工具的使用说明 |
| [扫描器详解](./SCANNER.md) | scanner.py 详细使用 |
| [处置工具详解](./HANDLER.md) | handle_violations.py 详细使用 |

### 其他

| 文档 | 内容 |
|------|------|
| [迁移指南](./MIGRATION_GUIDE.md) | 版本迁移说明 |
| [项目结构](./STRUCTURE.md) | 目录结构说明 |

---

## 目录结构

```
claude/
├── README.md                        # 项目概述
├── requirements.txt                 # 依赖列表
├── schema.sql                       # 数据库结构
├── labels.txt                       # IMS 标签参考
├── Dockerfile                       # Docker 镜像
├── docker-compose.yml               # Docker 编排
│
├── scanner.py                       # 入口①：扫描器
├── handle_violations.py             # 入口②：处置工具
├── minio_client.py                  # MinIO 操作封装
├── image_feature.py                 # 感知哈希 + 汉明距离
├── tencent_ims.py                   # 腾讯云 IMS API 封装
├── database.py                      # MySQL 数据库层
├── logger_config.py                 # 日志配置
│
├── docs/                            # 文档目录
│   ├── INDEX.md                    # 本文件（导航中心）
│   ├── QUICK_START.md              # 快速开始
│   ├── INSTALLATION.md             # 安装指南
│   ├── USAGE.md                    # 使用指南（总览）
│   ├── ARCHITECTURE.md             # 系统架构
│   ├── WORKFLOW.md                 # 三阶段工作流
│   ├── DATABASE.md                 # 数据库设计
│   ├── SCANNING_LOGIC.md           # 扫描逻辑
│   ├── SCANNER.md                  # 扫描器详解
│   ├── HANDLER.md                  # 处置工具详解
│   ├── DOCKER.md                   # Docker 部署指南
│   ├── PRODUCTION.md               # 生产部署
│   ├── MIGRATION_GUIDE.md          # 迁移指南
│   └── STRUCTURE.md                # 项目结构说明
│
├── tests/                           # 测试
│   └── ...
│
└── logs/                            # 日志（运行时）
    ├── scan.log
    ├── violations.log
    └── error.log
```

---

## 按功能快速查找

### 安装和部署

- 想快速试用？→ [快速开始](./QUICK_START.md)
- 需要详细安装步骤？→ [安装指南](./INSTALLATION.md)
- 想用 Docker 部署？→ [Docker 指南](./DOCKER.md)
- 准备生产环境？→ [生产部署](./PRODUCTION.md)

### 使用和操作

- 第一次运行工具？→ [快速开始](./QUICK_START.md)
- 想了解两个工具？→ [使用指南](./USAGE.md)
- 想深入了解扫描器？→ [扫描器详解](./SCANNER.md)
- 想深入了解处置工具？→ [处置工具详解](./HANDLER.md)

### 理解和学习

- 想了解整体设计？→ [系统架构](./ARCHITECTURE.md)
- 想了解处置流程？→ [三阶段工作流](./WORKFLOW.md)
- 想了解数据存储？→ [数据库设计](./DATABASE.md)
- 想了解图片检测？→ [扫描逻辑](./SCANNING_LOGIC.md)

---

**提示：** 每个文档底部都有快速导航链接，方便你在文档间跳转。
