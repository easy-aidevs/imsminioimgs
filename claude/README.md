# 图片内容安全扫描系统

基于腾讯云 IMS 的图片内容安全检测系统。两个入口、隔离桶处置、感知哈希去重节省 API 费用。

## 两个入口

| 入口 | 作用 |
|------|------|
| `scanner.py` | **分析**：遍历 MinIO 桶 → 调用腾讯云 IMS → 写库 |
| `handle_violations.py` | **操作**：基于扫描结果，对违规图片做 block / restore / delete |

## 处置工作流（三阶段）

```
扫描器写库（is_violation=1）
        │
        ▼
  ═══════════════════════════════════════════════════════════
   🔸 第一阶段：发现 & 标记私密（原桶，隐藏观察）
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
   │   🟡 第二阶段：观察决策                               │
   │  ═══════════════════════════════════════════════════ │
   │                                                       │
   ├─→ confirm-quarantine     观察正常 → 移到隔离桶      │
   │   (blocked=2, 不可逆)                               │
   │                                                       │
   └─→ restore-public         观察异常 → 改回公开        │
       (blocked=0, 视为误判)                            │
        │
        ├─→ list-quarantined    查看已隔离的
        │
  ═══════════════════════════════════════════════════════════
   🔴 第三阶段：彻底删除（不可恢复）
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

# 4. 扫描（可选，仅需腾讯云 IMS）
python scanner.py

# 5. 处置违规图片（三阶段流程）

# 第一阶段：标记为私密
python handle_violations.py list               # 查看新增违规
python handle_violations.py mark-private --type gambling  # 标记为私密

# 第二阶段：观察并决策
python handle_violations.py list-private       # 查看观察中的
python handle_violations.py confirm-quarantine --ids 1,2,3    # 确认隔离
# 或
python handle_violations.py restore-public --ids 4,5          # 改回公开

# 第三阶段：彻底删除
python handle_violations.py list-quarantined   # 查看已隔离
python handle_violations.py delete --ids 1,2,3              # 删除
```

**详见 [`SETUP_AND_USAGE.md`](SETUP_AND_USAGE.md) 完整使用说明。**

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

**详见 [`SETUP_AND_USAGE.md`](SETUP_AND_USAGE.md#配置详解) 的配置详解部分。**

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
├── .env.example             # 配置模板
│
├── Dockerfile               # 容器镜像
├── docker-compose.yml       # 容器编排
├── .dockerignore
├── .gitignore
│
├── README.md                # 本文件
├── docs/
│   └── SCANNING_LOGIC.md    # 扫描流程详解（去重逻辑、统计字段含义）
│
└── logs/                    # 运行时生成（容器/本地都挂这里）
    ├── scan.log
    ├── error.log
    └── violations.log
```

## 违规类型

腾讯云 IMS 支持的类型：`gambling`（赌博，重点）、`porn`、`violence`、`politics`、`terrorism`、`ads`、`contraband`、`vulgar`、`qrcode`。

## 日志

| 文件 | 内容 |
|------|------|
| `logs/scan.log` | 完整运行日志（DEBUG） |
| `logs/error.log` | 错误日志（ERROR） |
| `logs/violations.log` | 违规图片日志（WARNING） |

## 与历史版本的关键差异

- 旧方案用 `set_object_tags` 当作访问控制 → 实际只是打标签，并未阻止访问。**新方案明确：tag 仅标记，访问控制靠隔离桶**。
- 旧的内存特征缓存（LRU/full/none 三种策略）已移除。相似检测直接查库，逻辑更简单；大规模场景请在 `feature_hash` 上加索引或换向量检索。
- 扫描器不再生成 `violations.txt`，查违规统一走 `handle_violations.py list`。

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

## License

MIT
