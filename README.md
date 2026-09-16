# 智能仓库多 Agent 运营平台

面向仓库库存、作业、设备、安全、需求预测和业务文档场景的多智能体协作平台。

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.120+-009688.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19+-61dafb.svg)](https://react.dev/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-14+-336791.svg)](https://www.postgresql.org/)
[![Milvus](https://img.shields.io/badge/Milvus-2.4+-00D4AA.svg)](https://milvus.io/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg)](https://www.docker.com/)

> 本项目基于 NVIDIA Multi-Agent Intelligent Warehouse 开源项目持续扩展，保留 Apache 2.0 许可证和上游提交历史。当前 SAP EWM 集成为协议兼容的 Mock Server 与可替换型预集成，尚未声明连接任何真实企业 SAP 租户。

<a id="contents"></a>
## 目录

- [项目简介](#overview)
- [核心架构](#architecture)
- [核心功能](#features)
- [技术栈](#technology-stack)
- [快速开始](#quick-start)
- [多 Agent 体系](#multi-agent)
- [MCP 工具与受控执行](#mcp-execution)
- [SAP EWM 预集成](#sap-ewm)
- [Hybrid RAG 与证据链](#rag-evidence)
- [API 接口](#api-reference)
- [监控、安全与记忆](#operations)
- [测试](#testing)
- [项目结构](#repository-layout)
- [常见问题](#troubleshooting)
- [开源来源与许可证](#license)

<a id="overview"></a>
## 项目简介

传统仓库系统中的库存、订单、设备、人员、安全事件和作业文档通常分散在 WMS、SAP EWM、IoT、RFID/条码及其他业务平台中。用户需要在多个系统之间查询数据、判断异常并手动执行操作。

本项目提供统一的自然语言交互入口，将用户请求转换为可验证、可审批、可恢复的 Agent 工作流，主要覆盖：

- 使用 LangGraph 编排任务规划、能力路由、并行协作、结果反思和答案合成。
- 通过仓库运营、设备管理、安全管理、需求预测和文档处理五类专业 Agent 分工执行任务。
- 通过 MCP（Model Context Protocol，模型上下文协议）统一发现和调用业务工具。
- 通过 Hybrid RAG 同时检索关键词、向量和结构化数据，并生成可追溯引用。
- 通过人工审批、状态检查点、事务发件箱、幂等键和执行后回查控制高风险写操作。
- 通过 SAP OData V4 协议兼容 Mock 完成 Agent → MCP → WMS Service → SAP Adapter 的本地端到端链路。

### 当前实现边界

| 能力 | 当前状态 |
|---|---|
| Planner、Router、Coordinator、Reflection、答案合成 | 已实现 V2 主链路与特性开关 |
| 五类专业 Agent 与统一输入输出协议 | 已实现 |
| PostgreSQL、BM25、Milvus、RRF、精排组件 | 已实现可组合链路；实际效果取决于数据集、模型与部署配置 |
| MCP 工具注册、Schema 校验、权限与风险控制 | 已实现 |
| 审批、Checkpoint、Outbox、Celery 异步执行、幂等与回查 | 已实现核心链路 |
| SAP EWM | 已完成 Mock 与可替换预集成；真实租户仍需凭据、字段映射和验收测试 |
| 其他 WMS、ERP、IoT、RFID、考勤 | 提供适配器边界或演示路径；不等同于已连接生产系统 |

<a id="architecture"></a>
## 核心架构

![智能仓库多 Agent 平台架构](docs/architecture/diagrams/warehouse-assistant-architecture.png)

一次典型请求会依次经过以下组件：

1. **API 与会话层**：接收自然语言请求，加载用户身份、会话上下文和权限信息。
2. **复杂度判断**：区分简单查询、标准仓储流程和复杂跨领域任务。
3. **Planner（任务规划器）**：通过规则快速路径、HTN 模板或 LLM 结构化规划生成任务计划。
4. **Plan Compiler（计划校验与编译器）**：校验任务结构、依赖、能力、参数和循环上限，生成可执行 PlanGraph。
5. **Router（能力路由器）**：根据能力、权限、风险和可用状态选择 Agent 或 Tool。
6. **Coordinator（协同调度器）**：查找可执行节点、并行分发任务、汇总结果并唤醒下游节点。
7. **专业 Agent**：执行领域分析、检索数据或生成待审批动作。
8. **Reflection（结果校验）**：判断证据是否充分、结果是否冲突以及是否需要补充检索或局部重规划。
9. **受控执行层**：对高风险动作执行权限校验、人工审批、异步投递、幂等控制和结果回查。
10. **答案合成层**：依据证据和引用生成最终回复，并保存运行记录、指标和审计事件。

### 主要数据协议

- `AgentTask`：发送给专业 Agent 的标准任务，包含目标、输入参数、上下文、权限和依赖结果。
- `AgentResult`：Agent 的标准执行结果，包含状态、输出、证据、置信度、错误和待执行动作。
- `ProposedAction`：Agent 提出的外部系统操作建议，不代表操作已经执行。
- `EvidenceRef`：指向数据库记录、文档片段、工具结果或 Agent 分析结果的证据引用。
- `PlanGraph`：由任务节点、依赖边、条件分支、并行关系和有限循环组成的可执行任务图。

<a id="features"></a>
## 核心功能

### 1. 多 Agent 规划与协作

- 简单请求通过规则 Fast Path 直接路由，减少不必要的 LLM 调用。
- 标准仓储流程通过 HTN（层次任务网络）模板拆分为稳定步骤。
- 复杂请求由 LLM 生成结构化计划，并通过 Pydantic Schema 进行类型校验。
- 支持依赖执行、条件分支、并行节点、有限循环和失败节点局部重规划。
- Agent 之间通过统一的 `AgentTask`、`AgentResult` 和 LangGraph State 交换数据。

### 2. 专业 Agent

- **仓库运营 Agent**：任务创建、查询、分配、进度更新、工作量分析和仓库作业协调。
- **设备管理 Agent**：设备状态、遥测、调度、维护、位置和利用率分析。
- **安全管理 Agent**：事故记录、安全检查、风险分析、告警和整改建议。
- **需求预测 Agent**：需求预测、补货建议、模型表现和业务趋势分析。
- **文档处理 Agent**：PDF、Word、图片等文档解析、OCR、结构化抽取、检索和引用。

### 3. Hybrid RAG

- 文档解析后按正文、SOP、表格和图片实施差异化分块。
- 使用父子块关联兼顾小块精准召回和大块上下文完整性。
- 通过 BM25 关键词检索和 Milvus 稠密向量检索进行双路召回。
- 使用 RRF（倒数排名融合）合并候选，再通过 Cross-Encoder Reranker 进行精排。
- 支持结构化 SQL 查询、查询改写、元数据过滤、上下文回填和证据评分。

### 4. 证据、原子结论与引用

- 将数据库查询、文档片段、Agent 分析和 Tool 结果转换为统一证据对象。
- 对仓库、订单、任务、设备等业务实体进行标准化对齐。
- 区分数据发生时间、查询时间和有效版本，避免把过期数据当成当前状态。
- 基于来源优先级、数据新鲜度和一致性规则检测冲突。
- 在生成答案前检查关键结论的证据覆盖情况。
- 证据不足时可触发补充检索、降级表述、无答案或主动澄清。

### 5. 外部系统受控执行

- MCP Server 暴露标准化工具名称、说明、输入输出 Schema 和风险等级。
- Tool Handler 将工具参数转换为领域服务调用，而不是让 LLM 直接发送任意 HTTP 请求。
- WMS Service 负责业务校验，SAP Adapter 负责认证、URL、字段和错误模型转换。
- 高风险操作先生成 `ProposedAction`，经人工批准后才会进入执行队列。
- PostgreSQL Checkpoint 保存暂停状态，支持服务重启后的断点恢复。
- Transactional Outbox 与 Celery Worker 保证命令可靠投递。
- 幂等键、分类重试和执行后回查用于避免重复副作用并核验最终状态。

<a id="technology-stack"></a>
## 技术栈

| 分类 | 技术 |
|---|---|
| Agent 与编排 | LangGraph、LangChain Core、MCP、Pydantic |
| 大模型与安全 | NVIDIA NIM、OpenAI 兼容接口、NeMo Guardrails |
| 检索与文档 | Hybrid RAG、BM25、Milvus、Embedding、RRF、Cross-Encoder Rerank、OCR |
| 后端 | Python 3.11+、FastAPI、SQLAlchemy/AsyncPG、Celery |
| 数据与消息 | PostgreSQL、TimescaleDB、Redis、Kafka、Milvus、MinIO |
| 外部集成 | SAP EWM OData V4、REST API、IoT、RFID/Barcode 适配器边界 |
| 前端 | React 19、TypeScript、Material UI、React Query、Recharts |
| 部署与监控 | Docker Compose、Nginx、Prometheus、Grafana |

<a id="quick-start"></a>
## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18.17+（推荐 Node.js 20 LTS）
- npm 9+
- Docker 与 Docker Compose
- Git
- 可选：支持 CUDA 12.x 的 NVIDIA GPU

### 方式一：Docker Compose（推荐）

```bash
# 1. 克隆仓库
git clone https://github.com/R147-CMD/warehouse-agent-platform.git
cd warehouse-agent-platform

# 2. 创建环境变量文件
cp .env.example deploy/compose/.env

# 3. 按需编辑密码、JWT 密钥和模型 API Key
# Linux/macOS
nano deploy/compose/.env

# 4. 启动完整开发环境
docker compose --env-file deploy/compose/.env \
  -f deploy/compose/docker-compose.dev.yaml up -d

# 5. 查看服务状态
docker compose --env-file deploy/compose/.env \
  -f deploy/compose/docker-compose.dev.yaml ps
```

Windows PowerShell 可使用：

```powershell
Copy-Item .env.example deploy/compose/.env
docker compose --env-file deploy/compose/.env `
  -f deploy/compose/docker-compose.dev.yaml up -d
docker compose --env-file deploy/compose/.env `
  -f deploy/compose/docker-compose.dev.yaml ps
```

### 方式二：本地开发

```bash
# 检查 Node.js 版本
./scripts/setup/check_node_version.sh

# 创建 Python 环境并安装依赖
./scripts/setup/setup_environment.sh

# 启动数据库、缓存、消息队列和向量数据库
./scripts/setup/dev_up.sh

# 启动后端
source env/bin/activate
./scripts/start_server.sh

# 在另一个终端启动前端
cd src/ui/web
npm install
npm start
```

### 数据库初始化

项目的基础表和 V2 Agent 能力分别位于 `data/postgres/` 与 `data/postgres/migrations/`。首次部署时需要按照编号执行 SQL：

```bash
COMPOSE="docker compose --env-file deploy/compose/.env -f deploy/compose/docker-compose.dev.yaml"

for sql in \
  data/postgres/000_schema.sql \
  data/postgres/001_equipment_schema.sql \
  data/postgres/002_document_schema.sql \
  data/postgres/004_inventory_movements_schema.sql \
  data/postgres/migrations/001_initial_schema.sql \
  data/postgres/migrations/002_warehouse_tables.sql \
  data/postgres/migrations/003_timescale_hypertables.sql \
  data/postgres/migrations/004_agent_runtime_v2.sql \
  data/postgres/migrations/005_evidence_retrieval_v2.sql \
  data/postgres/migrations/006_command_outbox_v2.sql \
  data/postgres/migrations/007_memory_audit_v2.sql \
  data/postgres/migrations/008_execution_async_v2.sql; do
  $COMPOSE exec -T timescaledb \
    psql -U warehouse -d warehouse < "$sql"
done
```

如果 `.env` 修改了数据库用户名或数据库名，请同步调整示例中的 `warehouse`。

### 访问地址

| 服务 | 地址 |
|---|---|
| 中文前端 | <http://localhost:3001> |
| Nginx 统一入口 | <http://localhost:3000> |
| 后端 API | <http://localhost:8001> |
| Swagger API 文档 | <http://localhost:8001/docs> |
| SAP EWM Mock | <http://localhost:8010/health> |
| Milvus gRPC | `localhost:19530` |
| PostgreSQL/TimescaleDB | `localhost:5435` |
| Redis | `localhost:6379` |
| Kafka | `localhost:9092` |

演示环境默认管理员通常为 `admin` / `changeme`。请仅在本地开发中使用该密码，并在生产部署前通过 `DEFAULT_ADMIN_PASSWORD` 和 `JWT_SECRET_KEY` 替换。

### 关键环境变量

| 环境变量 | 作用 |
|---|---|
| `POSTGRES_USER`、`POSTGRES_PASSWORD`、`POSTGRES_DB` | PostgreSQL 连接信息 |
| `REDIS_HOST`、`REDIS_PORT` | Redis 连接信息 |
| `MILVUS_HOST`、`MILVUS_PORT` | Milvus 连接信息 |
| `JWT_SECRET_KEY` | JWT 签名密钥，生产环境必须设置 |
| `NVIDIA_API_KEY` | NVIDIA NIM/模型服务访问密钥 |
| `WAREHOUSE_AGENT_RUNTIME_V2_ENABLED` | 启用 V2 Agent 主链路 |
| `WAREHOUSE_RETRIEVAL_V2_ENABLED` | 启用 V2 检索链路 |
| `WAREHOUSE_EXECUTION_V2_ENABLED` | 启用 V2 受控执行链路 |
| `SAP_EWM_BASE_URL` | SAP EWM 或 Mock Server 地址 |
| `SAP_EWM_AUTH_MODE` | SAP 认证方式，例如 `basic` 或 OAuth2 |

<a id="multi-agent"></a>
## 多 Agent 体系

### 仓库运营 Agent

负责仓库任务规划、任务分派、进度跟踪、资源协调、KPI 查询和跨系统运营分析。涉及创建或修改任务的动作会进入审批链路。

### 设备管理 Agent

负责设备状态、位置、遥测、使用率、调度和维护建议。设备调度、停机或维护工单等高风险动作不会由模型直接执行。

### 安全管理 Agent

负责事故分析、安全检查、风险识别、SOP 查询、告警和整改建议。紧急通知、锁定挂牌等动作必须经过权限和风险策略判断。

### 需求预测 Agent

负责需求预测、补货建议、趋势分析和模型表现查询。预测结果可以作为业务建议，但不会未经审批直接创建采购或补货订单。

### 文档处理 Agent

负责多格式文档解析、OCR、结构化字段抽取、差异化分块、索引构建、知识检索和引用生成。

### 能力注册中心

Capability Registry（能力注册中心）统一管理：

- Agent 和 Tool 能解决什么问题。
- 输入输出 Schema 与必填字段。
- 所需用户权限和租户范围。
- 操作风险等级与是否需要审批。
- 当前可用状态、版本和降级策略。

Router 会先执行硬约束过滤，再根据任务语义选择最匹配的 Agent 或 Tool，避免只依赖 LLM 自由选择。

<a id="mcp-execution"></a>
## MCP 工具与受控执行

### 为什么 MCP 工具能够操作外部系统

工具定义本身只描述“名称、用途和参数”。真正控制外部系统的是工具后面的实现链路：

```text
用户自然语言
  → Planner 生成任务计划
  → Router 选择能力
  → Agent 生成 Tool Call 或 ProposedAction
  → MCP Gateway 校验 Schema、权限和风险
  → Tool Handler 调用领域 Service
  → Adapter 生成外部系统协议请求
  → HTTP/MQTT/Kafka Client 发送请求
  → 外部系统返回结果
  → 回读验证并生成 Evidence
```

LLM 不持有数据库连接或 SAP 凭据，也不能任意拼接请求。凭据、网络访问、字段映射和错误处理均位于受控的 Service 与 Adapter 层。

### 操作风险分级

- **低风险只读操作**：库存、订单、设备状态和文档查询，可在权限通过后直接执行。
- **中风险操作**：生成计划、建议或草稿，不立即修改外部系统。
- **高风险写操作**：任务分配、设备调度、SAP 状态修改等，需要人工审批。
- **禁止操作**：超出工具能力、权限不足或参数无法验证的请求直接拒绝。

### 审批与可靠执行

1. Agent 只生成包含业务参数、风险和依据的 `ProposedAction`。
2. LangGraph Interrupt 暂停工作流。
3. PostgreSQL 保存 Graph State、Checkpoint、审批记录和待执行命令。
4. 审批通过后写入 Transactional Outbox。
5. Celery Worker 异步调用外部系统。
6. 幂等键防止超时重试造成重复业务副作用。
7. 执行后重新查询外部系统，确认最终状态并写入审计证据。

<a id="sap-ewm"></a>
## SAP EWM 预集成

当前 SAP 模块用于在没有真实 SAP 测试环境时验证完整协议链路，Mock Server 遵循 OData V4 的路径和响应结构，并覆盖：

- Basic/OAuth2 认证配置。
- CSRF Token 获取与携带。
- ETag 与 `If-Match` 并发控制。
- OData 分页、过滤和响应解析。
- 标准错误、超时、重试与错误分类。
- 写操作审批、幂等执行与执行后回查。

### 本地启动

```bash
docker compose --env-file deploy/compose/.env \
  -f deploy/compose/docker-compose.dev.yaml \
  up -d sap-ewm-mock backend execution-worker

curl http://localhost:8010/health
pytest tests/integration/test_sap_ewm_agent_workflow.py -q
```

### 核心 SAP 能力

- 查询仓库实物库存。
- 查询仓库订单和仓库任务。
- 提议并审批仓库订单分配。
- 提议并审批仓库任务确认。

默认 V2 路径将写操作建模为“提议能力 + 审批后的命令处理器”。遗留的直接写工具默认不对 LLM 暴露，避免绕过审批。

切换真实 SAP 时主要需要修改地址、凭据、证书和字段映射，并完成网络连通性、权限、主数据、错误码和并发控制验收。详细说明参见 [SAP EWM/WMS 集成文档](docs/wms-integration.md)。

<a id="rag-evidence"></a>
## Hybrid RAG 与证据链

### 文档处理

- PDF：优先提取原生文本；扫描件进入 OCR；复杂版面可接入视觉解析。
- Word：保留标题层级、段落、列表和表格结构。
- SOP：按章节、步骤、前置条件、风险提示和操作结果切分。
- 表格：保留表头、行列关系和来源页码，避免普通文本切块破坏语义。
- 图片：保存 OCR 文本、视觉描述、页码和原文件引用。

### 检索流程

1. 查询理解：识别实体、时间、过滤条件和查询类型。
2. 查询改写：生成适合关键词、向量和结构化查询的子查询。
3. 双路召回：BM25 负责精确词匹配，Milvus Dense Retrieval 负责语义匹配。
4. 结构化检索：按需要查询 PostgreSQL/TimescaleDB 的实时业务数据。
5. RRF 融合：根据不同召回列表中的名次合并候选。
6. Cross-Encoder 精排：同时读取问题与候选文本，重新计算相关性。
7. 父块回填：使用命中的小块定位更完整的父级上下文。
8. 证据校验：进行实体、时间、来源和冲突检查。
9. 答案生成：只使用通过校验的证据，并建立结论到引用的映射。

<a id="api-reference"></a>
## API 接口

完整接口及请求 Schema 请访问 <http://localhost:8001/docs>。

### 健康与认证

- `GET /api/v1/health`：系统健康检查。
- `GET /api/v1/health/simple`：简单健康状态。
- `GET /api/v1/version`：API 版本。
- `POST /api/v1/auth/login`：用户登录。
- `GET /api/v1/auth/me`：当前用户信息。

### 对话与 Agent

- `POST /api/v1/chat`：原有多 Agent 对话入口。
- `POST /api/v2/chat`：V2 Agent 主链路入口。
- `/api/v1/runs`：Agent 运行记录、事件、取消与重试。
- `/api/v1/chat/approvals`：待审批动作查询与审批决策。
- `/api/v2/actions`、`/api/v2/approvals`、`/api/v2/commands`：受控执行审批与命令状态查询。

### 业务接口

- `/api/v1/equipment`：设备、状态、遥测、分配和维护。
- `/api/v1/forecasting`：预测看板、实时预测、补货建议和模型表现。
- `/api/v1/document`：文档上传、处理状态、结果和分析。
- `/api/v1/operations`：仓库任务和运营数据。
- `/api/v1/safety`：安全事件与安全管理。

<a id="operations"></a>
## 监控、安全与记忆

### 可观测性

系统通过运行事件、日志、Trace 和 Prometheus Metrics 记录：

- Planner 计划生成、校验和重规划次数。
- Router 的能力选择结果和回退原因。
- Agent 与 Tool 的耗时、状态和错误分类。
- 检索召回、融合、精排和证据覆盖情况。
- 审批状态、Outbox 投递、Celery 执行和回查结果。
- 外部系统请求耗时、超时、重试和最终状态。

```bash
# 启动监控组件
./scripts/setup/setup_monitoring.sh
```

- Grafana：<http://localhost:3000>
- Prometheus：<http://localhost:9090>
- Alertmanager：<http://localhost:9093>

### 安全

- JWT 身份认证与基于角色的访问控制（RBAC）。
- MCP Tool 级别的权限、租户、资源范围和风险校验。
- NeMo Guardrails 与规则降级路径用于输入输出安全检查。
- Prompt Injection 防护与不可信内容标记。
- 敏感字段脱敏、操作审计和外部请求边界控制。

生产环境必须设置强随机 `JWT_SECRET_KEY`，不得继续使用 `changeme`、示例 SAP 凭据或默认管理员密码。更多信息参见 [密钥管理](docs/secrets.md) 和 [安全策略](SECURITY.md)。

### 会话记忆

- 短期记忆保存当前对话、任务计划、中间结果和审批状态。
- 长期记忆通过 Memory Writer 抽取可复用事实，并进行权限、来源和有效期校验。
- PostgreSQL 负责持久化会话、运行、审计和长期记忆；Redis 用于热点缓存和短期状态加速。

<a id="testing"></a>
## 测试

```bash
# 全部测试
pytest tests/

# V2 单元、契约、集成和安全测试
pytest tests/unit/v2 tests/contract/v2 tests/integration/v2 tests/security -q

# SAP EWM Adapter 与 Agent 工作流
pytest \
  tests/unit/test_sap_ewm_adapter.py \
  tests/unit/test_sap_ewm_mcp_adapter.py \
  tests/integration/test_sap_ewm_agent_workflow.py -q

# 前端构建
cd src/ui/web
npm install
npm run build
```

评测数据与指标实现位于 `tests/evaluation/v2/`，覆盖 Planner、Router、检索、引用和工具调用等场景。README 不将示例目标值表述为生产实测结果，实际指标应以当前数据集和评测报告为准。

<a id="repository-layout"></a>
## 项目结构

```text
.
├─ src/
│  ├─ api/
│  │  ├─ agents/v2/             # 五类专业 Agent 与动作提议
│  │  ├─ graphs/                # LangGraph State 与主工作流
│  │  ├─ routers/               # Chat、Run、Approval、Execution API
│  │  └─ services/
│  │     ├─ orchestration/       # Planner、Compiler、Router、Coordinator、Reflection
│  │     ├─ mcp/                 # MCP Gateway、Manifest、Schema 校验
│  │     ├─ execution/           # 审批、Outbox、Worker、幂等、回查
│  │     ├─ evidence_v2/         # Evidence、Claim、Citation
│  │     ├─ document_v2/         # 解析、切块、质量门禁和索引
│  │     └─ memory_v2/           # 短期/长期记忆与 Memory Writer
│  ├─ retrieval/v2/              # BM25、Dense、RRF、Reranker、上下文构建
│  ├─ adapters/                  # 外部系统适配器
│  ├─ mock_servers/sap_ewm/      # SAP OData V4 协议兼容 Mock
│  └─ ui/web/                    # React 中文前端
├─ data/postgres/                # 数据库 Schema 与 V2 迁移
├─ deploy/compose/               # Docker Compose 与 Nginx 配置
├─ monitoring/                   # Prometheus、Grafana 与告警配置
├─ scripts/                      # 初始化、数据生成与运维脚本
├─ tests/                        # 单元、契约、集成、安全与评测测试
└─ docs/                         # 架构、集成与技术设计文档
```

<a id="troubleshooting"></a>
## 常见问题

### 前端提示 `Cannot find module 'node:path'`

Node.js 版本过低。请升级到 Node.js 18.17+，推荐使用 Node.js 20 LTS：

```bash
node --version
nvm install 20
nvm use 20
```

### 后端无法连接数据库

```bash
docker ps
docker logs wosa-timescaledb
```

确认宿主机端口 `5435` 未被占用，并检查 `deploy/compose/.env` 中的数据库配置。

### SAP Mock 无法访问

```bash
docker logs wosa-sap-ewm-mock
curl http://localhost:8010/health
```

### 前端无法登录

确认后端 `http://localhost:8001/api/v1/health` 正常、默认用户已经创建，并检查浏览器请求是否指向 `REACT_APP_API_URL=http://localhost:8001`。

### 查看完整部署说明

参见 [DEPLOYMENT.md](DEPLOYMENT.md)。

<a id="license"></a>
## 开源来源与许可证

本仓库保留 NVIDIA 上游项目提交历史，原始项目地址：

- [NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse](https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse)

项目代码按照 [Apache License 2.0](LICENSE) 使用。部分模型、容器和第三方软件拥有各自的许可证或服务条款，包括：

- [Llama-3.3-Nemotron-Super-49B-v1.5](https://catalog.ngc.nvidia.com/orgs/nim/teams/nvidia/containers/llama-3.3-nemotron-super-49b-v1.5)
- [Llama Nemotron Embed VL 1B v2](https://build.nvidia.com/nvidia/llama-nemotron-embed-vl-1b-v2/modelcard)
- [NeMo Retriever Extraction](https://catalog.ngc.nvidia.com/orgs/nvidia/teams/nemo-microservices/containers/nv-ingest)
- [Nemotron OCR](https://catalog.ngc.nvidia.com/orgs/nim/teams/nvidia/containers/nemotron-ocr-v1)
- [NeMo Guardrails](https://github.com/NVIDIA-NeMo/Guardrails)
- [RAPIDS cuML](https://github.com/rapidsai/cuml/blob/main/LICENSE)

在生产或商业环境使用前，请分别审查代码、模型、容器、数据和第三方依赖的许可条款。

## 贡献指南

欢迎提交 Issue 或 Pull Request：

1. Fork 本仓库。
2. 创建功能分支：`git checkout -b feature/your-feature`。
3. 使用 Conventional Commits 提交，例如 `feat:`、`fix:`、`docs:`、`test:`。
4. 推送分支并创建 Pull Request。

---

如果你希望了解某一条 Agent 请求如何从自然语言执行到 SAP EWM Mock，可从 `src/api/graphs/warehouse_graph_v2.py`、`src/api/services/orchestration/`、`src/api/services/mcp/` 和 `src/api/services/execution/` 开始阅读。
