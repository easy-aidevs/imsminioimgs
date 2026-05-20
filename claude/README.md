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
| `handle_violations.py` | **处置**：直接隔离（物理移桶）→ 恢复/删除 |

详见 [使用指南](./docs/USAGE.md)

## 处置工作流（两阶段）

```
扫描器写库（is_violation=1，对象在原桶）
        │
        ▼
  ═══════════════════════════════════════════════════════════
   第一步：查看 & 隔离（MinIO 物理移动，原 URL 立即失效）
  ═══════════════════════════════════════════════════════════
        │
        ├─→ list --suggestion Block        查看 IMS 建议拦截的违规
        │
        ├─→ quarantine --suggestion Block  直接隔离（对象移入隔离桶）
        │   blocked=2，原 URL 失效
        │
        ├─→ quarantine --label Illegal     按分类隔离
        │
        └─→ quarantine --ids 1,2,3         按 ID 直接隔离
        │
  ═══════════════════════════════════════════════════════════
   第二步：审查 → 恢复误判 / 彻底删除
  ═══════════════════════════════════════════════════════════
        │
        ├─→ list-quarantined    查看已隔离的
        │
        ├─→ restore --ids x,y   误判恢复（从隔离桶移回原桶，标记非违规）
        │
        └─→ delete  --ids x,y   彻底删除（不可恢复，需输入 DELETE 确认）
```

**核心机制：**
- **隔离状态**（blocked=2）：对象从原桶**物理移动**到隔离桶，原 URL 立即失效
- **误判恢复**：`restore` 将对象从隔离桶物理移回原桶，并清除违规标记
- MinIO 不支持单对象 ACL，访问控制依赖**对象所在桶**（原桶 vs 隔离桶）

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

# 5. 处置违规图片

# 查看 IMS 建议拦截的违规
python handle_violations.py list --suggestion Block

# 直接隔离（MinIO 物理移桶，原 URL 立即失效）
python handle_violations.py quarantine --suggestion Block

# 或按分类隔离
python handle_violations.py quarantine --label Illegal
python handle_violations.py quarantine --sub-label Gamble

# 查看已隔离
python handle_violations.py list-quarantined

# 误判恢复（从隔离桶移回原桶）
python handle_violations.py restore --ids 4,5

# 彻底删除（需输入 DELETE 确认）
python handle_violations.py delete --ids 1,2,3
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
  `Gamble`（赌博）/ `SexyBehavior`（性行为）/ `NationalOfficial`（国家公职人员）/ `Drug`（毒品）/ `Blood`（血腥）/ `QrCode`（二维码）等

- **`violation_type`**：直接取 `sub_label`（如 `Gamble`）；若 SubLabel 为空则取 `violation_label`（如 `Porn`）。
  无自定义映射，无 `other` 类型，完全使用 IMS API 返回的原始值。

> **提示**：SubLabel 值直接来自 IMS API，过滤前请先用 `list` 命令查看实际的 `violation_type` / `sub_label` 值。

**过滤示例**：
- 过滤所有违法内容：`--label Illegal`
- 过滤赌博内容：`--sub-label Gamble`
- 按 violation_type 过滤：`--type Gamble`（与 sub_label 相同）

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
