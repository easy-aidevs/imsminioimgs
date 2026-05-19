# 图片内容安全扫描系统

基于腾讯云 IMS 的图片内容安全检测系统。两个入口、隔离桶处置、感知哈希去重节省 API 费用。

## 文档导航

> 新用户？请先阅读 **[文档导航中心](./docs/INDEX.md)** 快速找到你需要的文档！

| 角色 | 推荐文档 | 时间 |
|------|---------|------|
| 我要快速开始 | [快速开始](./docs/QUICK_START.md) | 5 分钟 |
| 我是第一次用 | [快速开始](./docs/QUICK_START.md) → [使用指南](./docs/USAGE.md) | 30 分钟 |
| 我是开发者 | [系统架构](./docs/ARCHITECTURE.md) → [扫描逻辑](./docs/SCANNING_LOGIC.md) | 1 小时 |
| 我是运维 | [Docker 部署](./docs/DOCKER.md) → [生产部署](./docs/PRODUCTION.md) | 1 小时 |

## 两个工具

| 工具 | 作用 |
|------|------|
| `scanner.py` | **扫描**：遍历 MinIO 桶 → 调用腾讯云 IMS → 结果写库 |
| `handle_violations.py` | **处置**：标记私密 → 观察决策 → 隔离/恢复/删除 |

详见 [使用指南](./docs/USAGE.md)

## 处置工作流（三阶段）

```
扫描器写库（is_violation=1）
        │
        ▼
  ═══════════════════════════════════════════════════════════
   第一阶段：发现 & 标记私密（原桶，隐藏观察）
  ═══════════════════════════════════════════════════════════
        │
        ├─→ list               查看新增违规
        │
        ├─→ mark-private       标记为私密（原桶，无法访问）
        │                      ↓
        │                   [观察期 24-48 小时]
        │                   [监控业务日志]
        │
        ├─→ list-private       查看观察中的
        │
   ┌────┴────────────────────────────────────────────────┐
   │                                                       │
   │  ═══════════════════════════════════════════════════ │
   │   第二阶段：观察决策                                  │
   │  ═══════════════════════════════════════════════════ │
   │                                                       │
   ├─→ confirm-quarantine     观察正常 → 移到隔离桶        │
   │   (blocked=2, 不可逆)                                │
   │                                                       │
   └─→ restore-public         观察异常 → 改回公开          │
       (blocked=0, 视为误判)                              │
        │
        ├─→ list-quarantined    查看已隔离的
        │
  ═══════════════════════════════════════════════════════════
   第三阶段：彻底删除（不可恢复）
  ═══════════════════════════════════════════════════════════
        │
        ├─→ delete --ids x,y    从隔离桶删除，清除记录
        │
        ▼
       完成
```

**核心机制：**
- **私密状态**（blocked=1）：原桶中的对象，通过 MinIO 权限无法公开访问，但仍可随时恢复
- **隔离状态**（blocked=2）：对象移入隔离桶，只能删除，不可恢复
- **观察期**：充分验证后再确认隔离，降低误判风险

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境
cp .env.example .env
vim .env

# 3. 初始化数据库
mysql -u root -p < schema.sql

# 4. 扫描（需要腾讯云 IMS 凭据）
python scanner.py

# 5. 处置违规图片（三阶段流程）

# 第一阶段：标记为私密
python handle_violations.py list                                  # 查看新增违规
python handle_violations.py mark-private --sub-label Gambling     # 标记赌博图片为私密

# 第二阶段：观察并决策
python handle_violations.py list-private                          # 查看观察中的
python handle_violations.py confirm-quarantine --ids 1,2,3        # 确认隔离
# 或
python handle_violations.py restore-public --ids 4,5              # 改回公开

# 第三阶段：彻底删除
python handle_violations.py list-quarantined                      # 查看已隔离
python handle_violations.py delete --ids 1,2,3                    # 删除
```

Docker 部署：`docker-compose up`

## 必填配置

| 配置 | 说明 | 示例 |
|------|------|------|
| `MINIO_ENDPOINT` | MinIO 地址 | `localhost:9000` |
| `MINIO_ACCESS_KEY` | MinIO 访问密钥 | - |
| `MINIO_SECRET_KEY` | MinIO 密钥 | - |
| `MINIO_BUCKET_NAME` | 业务图片桶 | `images` |
| `QUARANTINE_BUCKET_NAME` | 隔离桶 | `quarantine` |
| `MYSQL_HOST` | MySQL 地址 | `localhost` |
| `MYSQL_PASSWORD` | MySQL 密码 | - |
| `MYSQL_DATABASE` | 数据库名 | `image_security` |
| `TENCENT_SECRET_ID` | 腾讯云 ID（仅 scanner.py 需要） | - |
| `TENCENT_SECRET_KEY` | 腾讯云密钥（仅 scanner.py 需要） | - |

## IMS 标签体系

腾讯云 IMS API 返回两级标签：

- **`violation_label`**（一级 Label）：IMS 返回的顶层分类，共 8 个值：
  `Polity`（政治）/ `Porn`（色情）/ `Sexy`（性感）/ `Terror`（暴恐）/ `Illegal`（违法）/ `Religion`（宗教识别）/ `Ad`（广告）/ `Teenager`（未成年识别）/ `Abuse`（谩骂）

- **`sub_label`**（二级 SubLabel）：精细子类，直接取 IMS 返回的原始字符串，如：
  `Gambling`（赌博）/ `SexyBehavior`（性行为）/ `NationalOfficial`（国家公职人员）/ `Drug`（毒品）/ `Blood`（血腥）/ `QrCode`（二维码）等

- **`violation_type`**：直接取 `sub_label`（如 `Gambling`）；若 SubLabel 为空则取 `violation_label`（如 `Porn`）。
  无自定义映射，无 `other` 类型，完全使用 IMS API 返回的原始值。

**过滤示例**：
- 过滤所有违法内容：`--label Illegal`
- 过滤赌博内容：`--sub-label Gambling`
- 按 violation_type 过滤：`--type Gambling`（与 sub_label 相同）

## 三层去重（节省 API 费用）

```
路径 (bucket+key) ──┬─ 命中 → 完全跳过
                    │
内容 Key (md5+size)─┼─ 命中 → 复用已有结果，不调用 IMS
                    │
特征 pHash 距离 ≤ 3 ┴─ 命中 → 复用已有结果，不调用 IMS
                       否    → 调用 IMS
```

## 项目结构

```
.
├── scanner.py               # 入口①：分析（扫描 MinIO，写库）
├── handle_violations.py     # 入口②：操作（block / restore / delete）
│
├── minio_client.py          # MinIO 操作：列举、下载、跨桶移动、打标签
├── image_feature.py         # 感知哈希 + 汉明距离
├── tencent_ims.py           # 腾讯云 IMS API 封装
├── database.py              # MySQL 数据库层
├── logger_config.py         # 日志配置（scan / error / violations）
│
├── schema.sql               # 数据库表结构
├── requirements.txt         # Python 依赖
├── labels.txt               # IMS 标签参考列表
├── .env.example             # 配置模板
│
├── Dockerfile               # 容器镜像
├── docker-compose.yml       # 容器编排
├── .dockerignore
├── .gitignore
│
├── README.md                # 本文件
├── docs/                    # 文档目录
│   ├── INDEX.md
│   ├── QUICK_START.md
│   ├── ARCHITECTURE.md
│   ├── DATABASE.md
│   ├── SCANNING_LOGIC.md
│   ├── SCANNER.md
│   ├── HANDLER.md
│   ├── USAGE.md
│   ├── WORKFLOW.md
│   ├── DOCKER.md
│   ├── INSTALLATION.md
│   ├── PRODUCTION.md
│   ├── MIGRATION_GUIDE.md
│   └── STRUCTURE.md
│
└── logs/                    # 运行时生成（容器/本地都挂这里）
    ├── scan.log
    ├── error.log
    └── violations.log
```

## 测试

```bash
# 建虚拟环境装依赖
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt pytest

# 跑全部测试（不需要 MySQL / MinIO / 腾讯云凭据，全部 mock）
.venv/bin/python -m pytest tests/ -v
```

| 测试文件 | 关注点 |
|---------|--------|
| `test_image_feature.py` | Key 确定性、特征哈希、汉明距离边界（含 `""` 异常输入） |
| `test_tencent_ims_parse.py` | confidence 0–100 → 0–1 归一化、Suggestion 映射、违规类型映射 |
| `test_database_queries.py` | upsert 字段数对齐、空 hash 防御过滤、ON DUPLICATE 子句 |
| `test_scanner_logic.py` | 三层去重的分支路径、`force_rescan` 行为、错误记录 key 长度有界 |
| `test_handle_violations.py` | block/restore/delete 的 MinIO+DB 调用顺序、源缺失分支、tag 失败容错 |
| `test_minio_client.py` | move_object 顺序、`object_exists` 错误码分支、tag 操作 |

所有审计修复都有对应回归测试（confidence 截断、空 hash 误用、key 溢出）。

## 详细文档

- [docs/SCANNING_LOGIC.md](docs/SCANNING_LOGIC.md)：扫描流程详解（三层去重、相似检测的查库策略、统计字段含义、强制重扫）

## 与历史版本的关键差异

- 旧方案用 `set_object_tags` 当作访问控制 → 实际只是打标签，并未阻止访问。**新方案明确：tag 仅标记，访问控制靠隔离桶**。
- 旧的内存特征缓存（LRU/full/none 三种策略）已移除。相似检测直接查库，逻辑更简单；大规模场景请在 `feature_hash` 上加索引或换向量检索。
- 扫描器不再生成 `violations.txt`，查违规统一走 `handle_violations.py list`。

## License

MIT
