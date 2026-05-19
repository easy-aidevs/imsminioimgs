# 📁 文档结构说明

本文档解释了文档的组织结构，帮助你快速找到所需的内容。

---

## 整体结构

```
claude/
│
├── README.md                    # 项目简介和导航
│
├── docs/                        # 📚 文档目录（你在这里）
│   ├── INDEX.md                # 📍 导航中心（首先读这个）
│   ├── STRUCTURE.md            # 本文件
│   │
│   ├── 快速开始
│   │   └── QUICK_START.md      # 5分钟快速开始
│   │
│   ├── 核心概念
│   │   ├── ARCHITECTURE.md     # 系统架构设计
│   │   ├── WORKFLOW.md         # 三阶段工作流
│   │   ├── DATABASE.md         # 数据库结构
│   │   └── SCANNING_LOGIC.md   # 扫描逻辑详解
│   │
│   ├── 安装和配置
│   │   ├── INSTALLATION.md     # 完整安装指南
│   │   ├── LOCAL_SETUP.md      # 本地开发环境
│   │   ├── DOCKER.md           # Docker 部署
│   │   └── PRODUCTION.md       # 生产环境部署
│   │
│   ├── 使用指南
│   │   ├── USAGE.md            # 使用概览
│   │   ├── SCANNER.md          # 扫描器详解
│   │   ├── HANDLER.md          # 处置工具详解
│   │   └── COMMANDS.md         # 命令完整参考
│   │
│   ├── 支持
│   │   ├── FAQ.md              # 常见问题解答
│   │   ├── TROUBLESHOOTING.md  # 故障排查指南
│   │   ├── PERFORMANCE.md      # 性能优化
│   │   └── SECURITY.md         # 安全建议
│   │
│   └── 开发
│       └── API_REFERENCE.md    # API 代码文档
│
├── schema.sql                   # 数据库结构定义
├── Dockerfile                   # Docker 镜像配置
├── docker-compose.yml          # Docker 编排配置
└── requirements.txt            # Python 依赖
```

---

## 📖 文档分类说明

### 🎯 快速开始

**用途：** 快速了解和运行系统

- **QUICK_START.md** - 5 分钟快速开始，包含两种运行方式

### 📚 核心概念

**用途：** 深入理解系统设计

- **ARCHITECTURE.md** - 系统整体架构，两个工具的关系
- **WORKFLOW.md** - 三阶段工作流详解
- **DATABASE.md** - 数据库表结构和字段说明
- **SCANNING_LOGIC.md** - 图片扫描和去重的详细逻辑

### 🔧 安装和配置

**用途：** 部署系统到不同环境

- **INSTALLATION.md** - 完整的手动安装步骤
- **LOCAL_SETUP.md** - 本地开发环境配置
- **DOCKER.md** - Docker 和 Docker Compose 使用
- **PRODUCTION.md** - 生产环境部署建议

### 💡 使用指南

**用途：** 学习如何使用两个工具

- **USAGE.md** - 使用指南概览（对应现有的 TWO_ENTRY_POINTS.md）
- **SCANNER.md** - scanner.py 详细使用说明
- **HANDLER.md** - handle_violations.py 详细使用说明
- **COMMANDS.md** - 所有命令的完整参考

### 📞 支持

**用途：** 解决问题和优化

- **FAQ.md** - 常见问题和解答
- **TROUBLESHOOTING.md** - 故障诊断和解决
- **PERFORMANCE.md** - 性能优化建议
- **SECURITY.md** - 安全注意事项

### 💻 开发

**用途：** 代码级别的参考

- **API_REFERENCE.md** - Python 类和方法文档

---

## 🎯 按需求快速导航

### 🆕 新用户 - 30 分钟体验

```
1. README.md          （项目概览）
    ↓
2. QUICK_START.md     （运行系统）
    ↓
3. WORKFLOW.md        （理解流程）
    ↓
4. USAGE.md           （学习操作）
```

### 💻 开发者 - 2 小时学习

```
1. ARCHITECTURE.md    （系统设计）
    ↓
2. DATABASE.md        （数据结构）
    ↓
3. SCANNING_LOGIC.md  （核心算法）
    ↓
4. API_REFERENCE.md   （代码文档）
```

### 🛠️ 运维 - 1 小时上手

```
1. QUICK_START.md     （快速开始）
    ↓
2. DOCKER.md          （容器部署）
    ↓
3. PRODUCTION.md      （生产配置）
    ↓
4. TROUBLESHOOTING.md （故障处理）
```

### 🆘 遇到问题

```
1. FAQ.md             （常见问题）
    ↓
2. TROUBLESHOOTING.md （详细排查）
    ↓
3. 仍未解决？
   → 查看 logs/ 下的日志文件
   → 参考 PERFORMANCE.md 或 SECURITY.md
```

---

## 📝 文档内容对应表

| 旧文档 | 新位置 | 说明 |
|--------|--------|------|
| SETUP_AND_USAGE.md | INSTALLATION.md + USAGE.md | 拆分为安装和使用两部分 |
| TWO_ENTRY_POINTS.md | USAGE.md + SCANNER.md + HANDLER.md | 拆分为概览和详解 |
| VIOLATIONS_WORKFLOW.md | WORKFLOW.md | 重命名并简化 |
| DOCKER_DEPLOYMENT.md | DOCKER.md | 改名并内容精简 |
| DOCKER_ANALYSIS.md | 本地参考 | 可选阅读深层分析 |

---

## 💡 使用建议

### 快速查找

1. **不知道从哪开始？**
   → 打开 [INDEX.md](./INDEX.md)，按角色选择

2. **遇到特定问题？**
   → 先查 [FAQ.md](./FAQ.md)，再看 [TROUBLESHOOTING.md](./TROUBLESHOOTING.md)

3. **想全面学习？**
   → 按照 "推荐阅读路线" 系统学习

4. **需要查命令？**
   → 打开 [COMMANDS.md](./COMMANDS.md)

### 在线阅读

每个文档顶部和底部都有快速导航：

```markdown
# 文档标题

← 上一篇 | [INDEX](./INDEX.md) | 下一篇 →

...文档内容...

← 上一篇 | [INDEX](./INDEX.md) | 下一篇 →
```

---

## 🎨 文档统计

| 类别 | 数量 | 总行数 |
|------|------|--------|
| 快速开始 | 1 | 100 |
| 核心概念 | 4 | 1500 |
| 安装配置 | 4 | 2000 |
| 使用指南 | 4 | 2500 |
| 支持 | 4 | 1500 |
| 开发 | 1 | 500 |
| **合计** | **18** | **~8000** |

---

## 🔄 文档维护

### 更新日志

| 日期 | 改动 |
|------|------|
| 2026-05-19 | 创建新的文档结构和导航 |

### 贡献文档

如果你想改进文档：

1. 找到相关文档
2. 提交 Pull Request
3. 说明改进内容和原因

---

## 📞 有其他问题？

- **查不到内容？** → 使用 [INDEX.md](./INDEX.md) 的搜索功能
- **文档不清楚？** → 提交问题或建议改进
- **需要示例？** → 查看 [COMMANDS.md](./COMMANDS.md) 中的命令示例

---

**祝你使用愉快！** 😊

如有问题，请参考 [FAQ.md](./FAQ.md) 或 [TROUBLESHOOTING.md](./TROUBLESHOOTING.md)
