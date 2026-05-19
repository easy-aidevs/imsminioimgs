# 📚 文档整理和迁移指南

本文档说明了最近的文档结构整理，以及如何找到旧文档中的内容。

---

## 📋 整理概要

我们将散落在根目录的多个 `.md` 文件重新组织到 `docs/` 目录中，形成清晰的文档体系：

### 变化总结

| 改变 | 说明 |
|------|------|
| ✅ 创建导航中心 | `docs/INDEX.md` - 一个入口找到所有文档 |
| ✅ 创建快速开始 | `docs/QUICK_START.md` - 5分钟快速体验 |
| ✅ 创建文档结构说明 | `docs/STRUCTURE.md` - 理解文档组织 |
| ✅ 清理根目录 | 将文档归纳到 `docs/` |
| ✅ 更新主 README | 添加文档导航指向 `docs/` |

---

## 🔄 文档迁移映射

### 旧文件 → 新位置

如果你之前有书签或收藏的文档，这个表格告诉你新位置：

#### 原根目录文档

```
原有文件                        新位置
────────────────────────────────────────────────────

SETUP_AND_USAGE.md       →  docs/INSTALLATION.md + docs/USAGE.md
TWO_ENTRY_POINTS.md      →  docs/USAGE.md + docs/SCANNER.md + docs/HANDLER.md
VIOLATIONS_WORKFLOW.md   →  docs/WORKFLOW.md
DOCKER_DEPLOYMENT.md     →  docs/DOCKER.md
DOCKER_ANALYSIS.md       →  保留在根目录（深层分析）
FINAL_SUMMARY.md         →  保留在根目录（改造总结）
DELIVERY_CHECKLIST.md    →  保留在根目录（交接清单）
```

#### 现有 docs/ 目录文件

```
docs/SCANNING_LOGIC.md   →  保留在 docs/（扫描逻辑）
```

---

## 🎯 从旧文档找到新位置

### 如果你要找...

| 需求 | 原文档 | 新位置 |
|------|--------|--------|
| 快速上手 | SETUP_AND_USAGE.md | **docs/QUICK_START.md** |
| 完整安装步骤 | SETUP_AND_USAGE.md | **docs/INSTALLATION.md** |
| 两个工具的使用 | TWO_ENTRY_POINTS.md | **docs/USAGE.md** |
| scanner.py 详解 | TWO_ENTRY_POINTS.md | **docs/SCANNER.md** |
| handle_violations.py 详解 | TWO_ENTRY_POINTS.md | **docs/HANDLER.md** |
| 三阶段工作流 | VIOLATIONS_WORKFLOW.md | **docs/WORKFLOW.md** |
| Docker 使用 | DOCKER_DEPLOYMENT.md | **docs/DOCKER.md** |
| 生产部署 | DOCKER_DEPLOYMENT.md | **docs/PRODUCTION.md** |
| 数据库结构 | SETUP_AND_USAGE.md | **docs/DATABASE.md** |
| 扫描逻辑 | docs/SCANNING_LOGIC.md | **docs/SCANNING_LOGIC.md** |
| 所有命令参考 | SETUP_AND_USAGE.md + TWO_ENTRY_POINTS.md | **docs/COMMANDS.md** |

---

## 📂 新的目录结构

```
claude/
├── README.md                          # 项目简介 ← 从这里开始
├── requirements.txt                   # Python 依赖
├── schema.sql                         # 数据库结构
├── Dockerfile                         # Docker 配置
├── docker-compose.yml                # Docker 编排
│
├── docs/                              # 📚 新的文档目录
│   ├── INDEX.md                      # 📍 导航中心（推荐首先阅读）
│   ├── STRUCTURE.md                  # 文档结构说明
│   ├── MIGRATION_GUIDE.md            # 本文件
│   │
│   ├── QUICK_START.md                # 5分钟快速开始
│   ├── INSTALLATION.md               # 完整安装指南
│   ├── USAGE.md                      # 使用指南概览
│   ├── SCANNER.md                    # scanner.py 详解
│   ├── HANDLER.md                    # handle_violations.py 详解
│   ├── COMMANDS.md                   # 所有命令参考
│   │
│   ├── ARCHITECTURE.md               # 系统架构
│   ├── WORKFLOW.md                   # 三阶段工作流
│   ├── DATABASE.md                   # 数据库设计
│   ├── SCANNING_LOGIC.md             # 扫描逻辑
│   │
│   ├── DOCKER.md                     # Docker 部署
│   ├── LOCAL_SETUP.md                # 本地开发
│   ├── PRODUCTION.md                 # 生产部署
│   │
│   ├── FAQ.md                        # 常见问题
│   ├── TROUBLESHOOTING.md            # 故障排查
│   ├── PERFORMANCE.md                # 性能优化
│   ├── SECURITY.md                   # 安全建议
│   └── API_REFERENCE.md              # API 文档
│
└── 源代码和其他文件...
```

---

## 🚀 如何使用新结构

### 步骤 1：了解整体

1. 阅读 `README.md`（项目概述）
2. 打开 `docs/INDEX.md`（导航中心）

### 步骤 2：按需求选择

根据你的角色，选择推荐的文档：

- 🎯 **新用户** → `docs/QUICK_START.md`
- 💻 **开发者** → `docs/ARCHITECTURE.md`
- 🛠️ **运维** → `docs/DOCKER.md`
- 🔍 **有问题** → `docs/FAQ.md` 或 `docs/TROUBLESHOOTING.md`

### 步骤 3：深入学习

在每个文档的顶部和底部都有导航链接，可以轻松在相关文档间跳转。

---

## ✨ 新结构的好处

| 改进 | 说明 |
|------|------|
| 📍 **清晰的导航** | `docs/INDEX.md` 是一个统一入口 |
| 🎯 **按需求分类** | 快速、安装、使用、开发、支持 5 大类 |
| 📖 **减少阅读量** | 快速开始只需 5 分钟 |
| 🔗 **相互链接** | 文档间有清晰的导航，不迷路 |
| 🆕 **新用户友好** | 清晰的学习路线建议 |

---

## 🔗 快速链接

新用户必读：
- 👉 **[导航中心](./INDEX.md)** - 快速找到你需要的文档
- 👉 **[快速开始](./QUICK_START.md)** - 5 分钟体验系统
- 👉 **[文档结构](./STRUCTURE.md)** - 理解文档组织方式

---

## ❓ 常见问题

### Q: 旧的文档还在吗？

**A:** 绝大多数旧文档的内容已整合到新结构中。部分深层分析文档（如 `DOCKER_ANALYSIS.md`）保留在根目录供参考。

### Q: 我的书签还能用吗？

**A:** 不能。请使用新的文档路径。参考本文档的"文档迁移映射"表格找到新位置。

### Q: 我应该从哪里开始？

**A:** 
1. 打开 `README.md`
2. 打开 `docs/INDEX.md`
3. 根据你的角色选择推荐文档

### Q: 如何快速查找特定话题？

**A:** 
1. 打开 `docs/INDEX.md` 的"按功能快速查找"部分
2. 或使用你的 IDE/编辑器的搜索功能在 `docs/` 目录中搜索

### Q: 文档更新了吗？

**A:** 是的，所有文档都已整理和优化。内容和信息都是最新的。

---

## 📞 需要帮助？

- **不知道从何开始** → 打开 [`docs/INDEX.md`](./INDEX.md)
- **遇到错误** → 查看 [`docs/TROUBLESHOOTING.md`](./TROUBLESHOOTING.md)
- **想学深度技术** → 查看 [`docs/ARCHITECTURE.md`](./ARCHITECTURE.md) 或相关深层文档
- **找不到某个话题** → 使用编辑器的全局搜索功能，或查看 [`docs/STRUCTURE.md`](./STRUCTURE.md)

---

**更新日期：** 2026-05-19

**祝你使用愉快！** 😊
