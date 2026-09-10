# 个人学习资料问答与复习助手 — 项目计划书

> 状态：待你确认后再进入代码实现  
> 日期：2026-09-10  
> 仓库建议名：`personal-learning-assistant`  
> 本地目录：`C:\ai agent\个人学习资料问答与复习助手`  
> 远程（已建空仓）：https://github.com/jidao-wang/personal-learning-assistant

---

## 1. 背景与定位

### 1.1 你是谁、学到哪

你正在按 **AI/Agent 应用开发 10 周 / 60 天** 路线学习，目标岗位是 **AI/Agent 应用开发 + Python 后端 AI 应用**。

已完成练习：

| 周次 | 能力 | 本地证据 |
|---|---|---|
| W1 | FastAPI / Pydantic / 配置 / 测试 | `agent-learning/week01_fastapi` |
| W2 | 手写 Tool Calling Agent Loop | `week02_agent_loop` |
| W3 | LangGraph State / 路由 / Checkpointer / HITL | `week03_langgraph` |
| W4 | 独立重建 RAG（Chroma + 引用） | `week04_rag` |
| W5 | Memory + Agent + RAG 综合验收 8/8 | `week05_memory` |

未开始：W6 服务化与 Trace、W7 评测、W8 Docker 交付、W9–10 原创项目与面试包装。

### 1.2 知识库内容（本项目的“个人资料”）

本助手不是泛泛 ChatPDF，而是服务你的 **固定学习语料**：

1. **路线与手册（权威大纲）**
   - `AI-Agent应用开发10周学习路线.md`
   - `AI-Agent应用开发60天每日学习手册.md`（目标 / 视频 / 练习 / 自测）
   - `AI-Agent应用开发60天动手练习详细步骤.md`
   - `AI-Agent应用开发60天每日自测题参考答案.md`
2. **个人笔记与扩展问答**
   - `agent-learning/notes/week01–05/*.txt`
   - `notes/扩展问答.txt`（Agent/Tool/RAG/Memory 流程、排错）
3. **练习代码与验收记录（可检索、可解释）**
   - 各 week 的关键实现与 `week05_acceptance.md`
4. **求职侧附属资料（可选第二知识域）**
   - 简历、面试追问、岗位 JD（后期再接，不进 MVP）

### 1.3 项目在路线中的角色

这不是“第 6 周作业”，而是 **把 W1–W5 能力整合成可投递的原创 Agent 应用**，同时反哺日常学习与复习。  
它可视为 **W9 原创 MVP 的提前启动版**；W6–W8 的服务化、评测、Docker 会在本项目上落地，而不是另起炉灶。

一句话产品定义：

> 基于我自己的 Agent 学习资料，提供 **有引用的问答、按日/按周复习、错题回流、进度感知** 的本地个人学习助手。

---

## 2. 需求对齐（MVP 范围）

### 2.1 核心用户故事

| ID | 故事 | 验收标准 |
|---|---|---|
| US1 | 作为学习者，我要问“LangGraph Checkpointer 是什么/怎么用”，得到基于手册+笔记的答案 | 答案带来源路径与片段；无资料时明确拒答 |
| US2 | 我要按「第 X 周第 Y 天」复习：看目标、自测 3 题、对照参考答案 | 能按 week/day 拉取手册内容并出题/对答 |
| US3 | 我要做一次「今日复习」：系统挑薄弱点或到期卡片 | 有简单调度（先 SM-2 简化版即可） |
| US4 | 我要保存学习偏好（如“回答要简洁、先给结论”）并跨会话生效 | SQLite 长期记忆；重启后仍可读 |
| US5 | 我要区分：普通闲聊 / 知识库问答 / 出题复习 | Agent 路由正确，不滥用 RAG |
| US6 | 我要有最小 API + 可演示界面 | FastAPI + 简单 Web/CLI；Swagger 可测 |

### 2.2 明确不做（YAGNI）

- 多用户账号体系、云端同步、移动端
- 多 Agent 协作 / Supervisor / MCP 深度
- 知识图谱可视化、播客生成、PDF OCR 全链路
- 完整 FSRS 商业级调度、Anki 完整生态
- 直接改写你的跟课 RAG 老项目代码

### 2.3 成功标准（可写进简历的证据）

1. 固定 **20 条** 评测题（手册事实、笔记概念、边界拒答、复习流程）自动跑通  
2. 回答 **必须可引用**；无证据则拒答或降级说明  
3. 端到端：导入资料 → 问答 → 出题 → 记分 → 下次优先复习错题  
4. README + 架构图 + `.env.example` + 本地一键启动说明  
5. 能 3 分钟讲清：数据流、工具边界、Memory vs RAG

---

## 3. 开源调研与可复用点

调研来源：GitHub 同类仓库 + X 上个人知识库/RAG 讨论。

### 3.1 高参考价值方案

| 项目 | 为什么值得看 | 建议怎么用 |
|---|---|---|
| [StudyTutor](https://github.com/anuragdhar-tech/studytutor) | **产品形态最贴**：Q&A / Revise / Interview 三模式 + 引用 chips；LangGraph 做模式路由 | **产品与交互蓝本**；技术栈改为你的 Python/FastAPI/Chroma |
| [ai-study-assistant](https://github.com/wangkeyu-u/ai-study-assistant) | FastAPI + Chroma + SQLite FTS 混合检索、拒答门控、评测脚本、Debug Panel | **工程与 RAG 质量蓝本**；MVP 只借思路，不抄复杂 multi-hop |
| [OpenTutor](https://github.com/zijinz456/OpenTutor) | 本地优先、测验/闪卡、FSRS、Tutor/Planner 分 Agent | 后期复习调度可参考 FSRS；MVP 用简化 SM-2 |
| [PageLM](https://github.com/CaviraOSS/PageLM) | NotebookLM 开源向：笔记/闪卡/测验 | 功能清单参考，避免一次做满 |
| [Cortex / daxgandhi](https://github.com/daxgandhi/ai-second-brain-for-students) | RAG + SRS + 薄弱点 + 测验 | 复习闭环结构可参考 |
| X: Karpathy 式 markdown wiki + agent | 小规模资料可先靠结构化 md + 索引，不必一上来上重型图谱 | 你的语料规模适合「结构化目录 + RAG」，不必上图数据库 |
| X: freeCodeCamp 本地 RAG 教程 | Python + Chroma + 本地/兼容 API | 与你 W4 栈一致，降低迁移成本 |

### 3.2 不建议当主骨架的

- 纯 Next.js + Supabase 云栈（StudyTutor 原栈）：与你路线/简历叙事不一致  
- 巨型多 Agent 学习平台（功能过多）：交付与讲解成本过高  
- 只做闪卡 App：缺少你要的 Agent + RAG + Memory 叙事  

### 3.3 必须避开的坑

1. **资料混存**：聊天历史、用户偏好、知识库塞同一张表/同一集合 → 权限乱、检索脏  
2. **无引用就敢答**：模型用预训练知识“补全”学习手册 → 面试时讲不清可信度  
3. **Embedding 换了不重建索引** → 维度/语义错乱  
4. **永远调用 RAG**：闲聊、算数也检索 → 慢且答案漂  
5. **从零复制跟课项目**：简历会被问“哪里是你独立写的”  
6. **Scope 膨胀**：知识图谱 + 多 Agent + Docker 全上 → MVP 完不成  
7. **Key 进代码/日志/截图**  
8. **只 Demo 一次成功**：没有 20 题固定集 → 无法证明稳定性  
9. **中文专名检索只靠向量**：周次、文件名、API 名应用关键词/元数据过滤补强  
10. **把“助手”做成另一套课程**：应以现有手册为 source of truth，而不是再生成一套冲突大纲  

### 3.4 三种实现路径（取舍）

| 方案 | 描述 | 优点 | 缺点 | 结论 |
|---|---|---|---|---|
| A. Streamlit 单文件 Demo | 最快出界面 | 快 | 难测、难 Docker、简历像课程作业 | 否 |
| B. FastAPI + LangGraph + Chroma + SQLite + 极简前端 | 与学习栈一致，可分层演进 | 可测、可 Trace、可讲 | 前端一般 | **推荐** |
| C. 直接二次开发 ai-study-assistant | 功能强 | 你对代码不熟、难讲“我写的” | 否（只参考） |

**推荐 B**：把你 W1–W5 真正“拼成产品”，并在本项目上完成 W6–W8 能力。

---

## 4. 技术选型（推荐）

| 层 | 选型 | 理由 |
|---|---|---|
| 语言 | Python 3.10+ | 与现有练习一致 |
| API | FastAPI + Pydantic | W1 成果直接复用模式 |
| 编排 | LangGraph | W3 能力；模式路由：chat / qa / review / quiz |
| LLM | OpenAI 兼容（DashScope/Qwen 等） | 你已在用；`.env` 配置 |
| Embedding | 与聊天分离的 embedding 模型 | W4/W5 踩过坑：禁止混用 chat 模型名 |
| 向量库 | Chroma（本地目录） | 已掌握；个人规模足够 |
| 元数据/记忆/复习 | SQLite | 会话、偏好、卡片、错题、进度 |
| 检索 | 向量 + 元数据过滤（week/day/source_type）；可选 FTS 二期 | 中文专名与“第3周”类查询更稳 |
| 前端 MVP | 简单 HTML/JS 或 Streamlit 薄壳；主路径仍是 API | 先证明后端正确 |
| 测试 | pytest + 固定 JSONL 评测集 | 对齐路线 W7 |
| 配置 | python-dotenv + Settings | 无硬编码 Key |
| 日志 | 结构化 JSON 日志（request_id） | 为 W6 Trace 预留 |
| 部署（二期） | Docker Compose | W8 |

**刻意不用（MVP）**：Neo4j、多向量库、Celery、复杂前端框架、云 pgvector。

---

## 5. 系统架构

### 5.1 逻辑架构

```text
                    ┌──────────────────────┐
  资料源 ─────────► │ Ingest Pipeline      │
  手册/笔记/代码     │ parse → chunk → embed│
                    │ → Chroma + SQLite meta│
                    └──────────┬───────────┘
                               │
  用户 ──► FastAPI ──► LangGraph Agent
                         │
          ┌──────────────┼──────────────────┐
          ▼              ▼                  ▼
     chat_node      rag_qa_node        review_node
     (无检索)     (检索+引用+拒答)    (抽题/判分/调度)
          │              │                  │
          └──────────────┴────────┬─────────┘
                                  ▼
                    Memory Store (SQLite)
                    - threads / messages
                    - user preferences
                    - flashcards / reviews
                    - weak_points
```

### 5.2 关键模块

| 模块 | 职责 |
|---|---|
| `ingest` | 扫描指定目录，按文件类型切分，写入元数据（source, week, day, title） |
| `retriever` | top-k + 过滤；空结果信号 |
| `agent/graph` | 意图路由；工具：`search_kb`、`get_day_plan`、`make_quiz`、`grade_answer`、`save_pref` |
| `memory` | 短期 thread 消息 + 长期偏好 |
| `review` | 卡片表、下次复习时间、对错统计 |
| `api` | `/health` `/ingest` `/chat` `/review/today` `/progress` |
| `eval` | 20 题脚本与报告 |

### 5.3 数据边界（硬规则）

| 数据类型 | 存哪 | 不存哪 |
|---|---|---|
| 手册/笔记知识 | Chroma + docs 元数据 | 不进 user_memories |
| 会话消息 | SQLite threads | 不进向量库（MVP） |
| 用户偏好 | SQLite user_memories | 不进 RAG |
| 复习卡片 | SQLite cards | 可从笔记生成，原文仍在知识库 |
| API Key | `.env` only | 永不进 Git/日志 |

### 5.4 知识切片策略（贴合你的资料）

- 手册：按 `### 第X周·第Y天` 为一级块，块内再按二级标题切  
- 笔记：按日文件整页 + 问答对切分  
- 元数据必带：`source_type`（manual/notes/code/acceptance）、`week`、`day`、`path`  
- 查询“第3周第4天学什么” → **先元数据过滤再向量**，避免纯相似度跑偏  

---

## 6. MVP 功能清单与非目标

### 6.1 MVP（P0）

1. 本地导入：手册三件套 + notes week01–05 + 扩展问答  
2. 带引用问答 + 无命中拒答  
3. 三种模式：闲聊 / 知识问答 / 复习（按周天或今日到期）  
4. 从自测题生成/抽取卡片；简单 SM-2（Again/Hard/Good）  
5. 会话历史 + 偏好记忆  
6. FastAPI + 最小 UI  
7. 10–20 条黄金评测题与一键脚本  
8. README / 架构说明 / `.env.example`

### 6.2 一期增强（P1，W6–W8 对齐）

- 结构化日志 + Langfuse/简易 Trace  
- 混合检索（SQLite FTS5）  
- Docker Compose  
- 进度看板：完成周次、薄弱知识点  
- 面试追问模式（基于笔记与扩展问答）

### 6.3 二期（P2）

- 简历/JD 第二知识域  
- Anki 导出  
- 更好前端  
- 引用句级校验  

---

## 7. 开发顺序（建议 7 个里程碑）

| 阶段 | 目标 | 完成定义 | 预计（按你 ~2h/天） |
|---|---|---|---|
| M0 | 工程骨架 | git 绑定远程、目录、config、health、gitignore | 0.5 天 |
| M1 | Ingest | 指定目录入库，可查 chunk 数与元数据 | 1–2 天 |
| M2 | RAG QA | `/chat` 知识问答 + 引用 + 拒答 | 1–2 天 |
| M3 | Agent 路由 | LangGraph：chat/qa/review 分流 + tools | 1–2 天 |
| M4 | 复习闭环 | 抽题、作答、评分、下次复习时间 | 2 天 |
| M5 | Memory | thread 恢复 + 偏好读写 | 1 天 |
| M6 | API 打磨 + 最小 UI + 评测 20 题 + README | 可演示、可回归 | 2 天 |
| M7 | P1：日志/Trace/Docker | 对齐 W6–W8 | 后续 |

**总 MVP 日历粗估：约 8–12 个有效学习日。**

每日纪律沿用路线原则：能演示、有测试、不堆无关视频。

---

## 8. 目录结构（拟）

```text
个人学习资料问答与复习助手/
├── app/
│   ├── main.py                 # FastAPI 入口
│   ├── api/                    # routes + schemas
│   ├── core/                   # config, logging, exceptions
│   ├── ingest/
│   ├── rag/
│   ├── agent/                  # state, nodes, graph, tools
│   ├── memory/
│   ├── review/
│   └── eval/
├── data/
│   ├── raw/                    # 可选：拷贝或软链说明
│   ├── chroma/
│   └── app.db
├── tests/
├── eval/
│   └── golden_questions.jsonl
├── docs/
│   └── superpowers/specs/      # 本计划书
├── web/                        # 最小前端（可后置）
├── .env.example
├── requirements.txt
└── README.md
```

资料默认 **读取你现有路径**（配置项），避免复制两份手册导致不同步。

---

## 9. 风险与对策

| 风险 | 对策 |
|---|---|
| 手册与笔记表述冲突 | 引用时标明 source_type；优先级：手册 > 笔记 > 模型 |
| 中文路径/编码 | 全项目 UTF-8；测试含中文路径 |
| 评测不稳定 | 事实题看关键字+引用；生成题允许多答案或人工抽检 |
| 范围再次膨胀 | P0 清单外一律 backlog |
| 与 W6 学习冲突 | 本项目即 W6–W8 载体，不再平行开第三个大项目 |

---

## 10. 待你确认的假设

以下默认成立；若有一条否，请直接改：

1. **主用户只有你自己**（单用户本地工具）  
2. **知识库以 Agent 学习资料为主**，简历面试资料二期再加  
3. **技术栈走 Python FastAPI + LangGraph + Chroma + SQLite**（方案 B）  
4. **MVP 要能写进简历**，因此必须有引用、评测集、README  
5. **先做计划与确认，再写代码**（本阶段不实现）  
6. UI 先极简，正确性优先于美观  

---

## 11. 确认后的第一步（仍不提前写业务代码）

你回复 **OK / 要改的点** 后，实现阶段按：

1. 写更细的 implementation plan（按 M0–M6 拆任务）  
2. 初始化工程与远程 git 绑定（若尚未 push）  
3. 从 M1 Ingest 开始垂直切片  

---

## 12. 参考链接

- StudyTutor: https://github.com/anuragdhar-tech/studytutor
- AI Study Assistant: https://github.com/wangkeyu-u/ai-study-assistant
- OpenTutor: https://github.com/zijinz456/OpenTutor
- PageLM: https://github.com/CaviraOSS/PageLM
- 你的 10 周路线：`C:\Users\29553\Desktop\codex\agent学习\AI-Agent应用开发10周学习路线.md`
- 练习与笔记：`C:\ai agent\agent-learning`
