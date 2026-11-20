# 用户标签画像与行为分析平台

面向用户行为埋点采集、标签体系构建、人群圈选与行为特征分析的数据应用平台。

这是一个前后端分离的管理平台：前端 Vue 3 + Vite + TypeScript，后端 FastAPI（Python）。
两边各自独立启动，前端 dev server 已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 目录结构

```text
.
├── frontend/                 Vue 3 + Vite + TypeScript 前端
│   ├── src/views/            每个业务模块一个页面
│   ├── src/api/              统一请求封装
│   ├── src/stores/           会话与筛选状态
│   └── vite.config.ts        dev server 配置（open: false）
├── backend/                  FastAPI（Python） 后端
│   ├── app/routers/          每个业务模块一组接口
│   ├── app/services/         业务规则与状态流转
│   └── app/store.py          内存数据仓库与示例数据
├── .gitignore
└── docker-compose.yml
```

## 启动

### 后端

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh
```

健康检查：`curl http://127.0.0.1:8000/api/health`

### 前端

```bash
cd frontend
npm ci
npm run dev
```

前端默认监听 `http://127.0.0.1:5173/`，dev server 不会自动打开浏览器，
需要自己访问。`/api` 由 vite 代理到后端 `http://127.0.0.1:8000`。

## 业务模块

| 模块 | 目录 | 业务对象 | 主要字段 |
| --- | --- | --- | --- |
| 事件埋点 | `event_track` | 埋点事件 | 事件编号、事件名称、事件分类 |
| 标签定义 | `tag_define` | 标签规则 | 标签编号、标签名称、标签层级 |
| 标签计算 | `tag_compute` | 计算任务 | 任务编号、关联标签、计算范围 |
| 人群圈选 | `crowd_select` | 圈选条件 | 条件编号、条件名称、标签组合 |
| 行为路径 | `behavior_path` | 路径模型 | 模型编号、起始事件、目标事件 |
| 留存计算 | `retention_calc` | 留存配置 | 配置编号、初始行为、回访行为 |
| 用户分群 | `user_segment` | 分群定义 | 分群编号、分群名称、基准行为 |
| 生命周期价值 | `lifetime_value` | LTV模型 | 模型编号、用户分群、价值指标 |
| 漏斗分析 | `funnel_analyze` | 漏斗定义 | 漏斗编号、漏斗名称、步骤序列 |
| 事件清洗 | `event_cleanse` | 清洗规则 | 规则编号、事件名称、校验字段 |
| 会话切割 | `session_split` | 切割策略 | 策略编号、策略名称、超时阈值 |
| 画像卡片 | `profile_card` | 卡片配置 | 卡片编号、卡片名称、展示标签 |
| 属性字典 | `attr_dict` | 属性定义 | 属性编号、属性名称、数据类型 |
| 交集分析 | `overlap_analysis` | 交集任务 | 任务编号、人群A、人群B |
| 标签下钻 | `tag_drill` | 下钻配置 | 配置编号、父标签、子标签集 |
| 事件聚合 | `event_aggregate` | 聚合配置 | 配置编号、事件名称、聚合维度 |
| 标签快照 | `tag_snapshot` | 快照记录 | 快照编号、快照日期、用户基数 |
| 行为热力 | `behavior_heatmap` | 热力配置 | 配置编号、行为事件、时间范围 |

## 约定

- 每个模块的前端页面在 `frontend/src/views/<模块>/index.vue`，后端接口在
  `backend/app/routers/<模块>.py`，业务规则在 `backend/app/services/<模块>.py`。
- 列表接口统一返回 `{ items, total, page, size }`，动作接口统一返回 `{ ok, message }`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。
- 前端页面按模块名使用下划线路径（`/api/funnel_analyze`），后端路由使用连字符
  （`/api/funnel-analyze`）；`app/main.py` 里有一段只改写模块名前缀的兼容中间件。

## 漏斗第 2 版本结果数据

漏斗 v1 用数组位置和事件编号表达步骤，同一个事件出现两次就无法区分。v2 给每个
步骤分配稳定 `step_id`，结果按 `data_version` 分版本存放，并用一个活动版本指针控制
线上读取：

| 接口 | 作用 |
| --- | --- |
| `POST /api/funnel-analyze/{funnel_id}/run?data_version=` | 产出 v2 结果版本 |
| `POST /api/funnel-analyze/{funnel_id}/steps` | 调整步骤/步序，旧定义归档为修订快照 |
| `POST /api/funnel-analyze/{funnel_id}/migrate?source_version=` | 把历史 v1 报告迁移成 v2 |
| `POST /api/funnel-analyze/{funnel_id}/switch?version=` | 切换活动版本（只移动指针） |
| `POST /api/funnel-analyze/{funnel_id}/rollback?version=` | 回滚到历史版本（不覆盖数据） |
| `GET /api/funnel-analyze/{funnel_id}/versions` | 版本列表 + 发布/切换/回滚审计事件 |
| `GET /api/funnel-analyze/{funnel_id}/versions/{version}` | 按版本号读结果（历史报告走这里） |
| `GET /api/funnel-analyze/{funnel_id}/versions/{version}/consistency` | 核对步序/分组归因是否同版本 |
| `GET /api/funnel-analyze/{funnel_id}/versions/{version}/steps/{step_id}` | 路径按版本+步骤标识取归因 |
| `GET /api/funnel-analyze/legacy/{funnel_id}?version=` | 读历史 v1 报告（事件合计口径） |

行为路径模型通过 `funnel_id` + `funnel_result_version` + `funnel_step_id` 固定归因版本；
切换/回滚期间路径引用不会漂移。历史 v1 分组只有事件合计，迁移与归因都标记为
`legacy_event_total_only`，不会把合计人数当成某一步的转化人数。

验证环境复现“切换后、路径取数前回滚”：

```bash
B=http://127.0.0.1:8000/api
curl -X POST "$B/funnel-analyze/FN-003/run?data_version=v2-r2"
curl -X POST "$B/funnel-analyze/FN-003/migrate?source_version=v1-2026-11-10&target_version=v2-mig"
curl -X POST "$B/funnel-analyze/FN-003/switch?version=v2-r2"
curl -X POST "$B/funnel-analyze/FN-003/rollback?version=v2-mig"
curl "$B/funnel-analyze/FN-003/versions/v2-mig/consistency"
curl "$B/behavior-path/BP-001/result"        # funnel_step_attribution 仍指 v1-2026-11-10
curl "$B/funnel-analyze/legacy/FN-003?version=v1-2026-11-10"
```

对应的回归用例在 `backend/tests/test_funnel_v2_migration.py`，覆盖迁移不拆步骤人数、
换序后迁移仍按历史修订绑定、切换后回滚不覆盖新版本、路径步序与分组同版本等断言。

领域：数据工程
子方向：数据分析与数据应用
