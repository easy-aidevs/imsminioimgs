# 图片内容安全扫描系统

基于腾讯云 IMS 的图片内容安全检测系统。两个入口、隔离桶处置、感知哈希去重节省 API 费用。

## 两个入口

| 入口 | 作用 |
|------|------|
| `scanner.py` | **分析**：遍历 MinIO 桶 → 调用腾讯云 IMS → 写库 |
| `handle_violations.py` | **操作**：基于扫描结果，对违规图片做 block / restore / delete |

## 处置工作流

```
扫描器写库（is_violation=1）
        │
        ▼
   list   查看违规清单
        │
        ▼
   block  把违规图片从业务桶移到 隔离桶  ← URL 失效，用户无法访问
        │                              ← 同时打 violation 标签做资源标记
        ▼
  人工复核
        │
   ┌────┴────┐
   ▼         ▼
restore    delete
移回原桶    从隔离桶彻底删除
```

**"禁止访问"的本质是迁移，不是 ACL/policy**：业务桶用户能拿到的 URL 在隔离桶里不存在，自然无法访问。tag 仅用于标记资源属性。

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境
cp .env.example .env
vim .env

# 3. 初始化数据库
mysql -u root -p < schema.sql

# 4. 扫描
python scanner.py

# 5. 处置违规图片
python handle_violations.py list
python handle_violations.py block --type gambling
python handle_violations.py list-blocked
python handle_violations.py restore --ids 1,2   # 误判恢复
python handle_violations.py delete --ids 3,4    # 彻底删除
```

Docker 部署：`docker-compose up`

## 必填配置

```ini
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=...
MINIO_SECRET_KEY=...
MINIO_BUCKET_NAME=images          # 业务桶
QUARANTINE_BUCKET_NAME=quarantine # 隔离桶（不公开访问）

MYSQL_HOST=localhost
MYSQL_PASSWORD=...
MYSQL_DATABASE=image_security

TENCENT_SECRET_ID=...
TENCENT_SECRET_KEY=...
```

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
