# Task 7 API 子任务报告

## 实现内容

- 新增 `app/api/schemas.py`，实现知识库、聊天、会话、复习、计划请求模型及字段边界。
- 新增 `app/api/routes.py`，实现 brief 中全部 API 路由：知识库和文件 CRUD、会话和聊天、复习生成/草稿/提交、计划生成/读取/更新、进度查询。
- 多文件上传对每个 `UploadFile` 只调用一次 `read()`，逐个调用 `ingest_file`；单文件异常转为独立 failed 结果并继续处理后续文件。
- chat 调用 Agent 时先读取已有历史，避免把当前用户消息重复传入；Agent 返回后持久化用户和 assistant 消息。Agent 异常时仍保存用户消息。
- 复习响应只返回题目展示字段，不返回 `correct_answer`、`reference_answer` 或 `rubric` 等内部答案材料。
- 新增 `app/main.py`，提供 `create_app()` 和默认 `app`。导入时只加载配置、初始化 SQLite，不创建或调用外部模型；无 `web/` 目录时仍可导入并访问 API。
- 注册 `AppError` 的 400 响应，以及不暴露堆栈、密钥和本地路径的通用 500 响应。
- API 测试通过 `app.state.runtime` 使用临时 SQLite，并替换 Agent、LLM、向量库或 ingest 依赖，不写入真实 `data/`。

## TDD 证据

### RED

1. 首次运行 API 测试时，环境缺少 `fastapi`，先补齐 `requirements.txt` 已声明的 API 测试依赖。
2. 依赖可用后运行 `pytest tests/test_api.py -q`，得到预期失败：`ModuleNotFoundError: No module named 'app.main'`。
3. 为 chat 重复上下文添加回归断言后，旧实现得到失败：Agent 调用时 session 已包含一条当前 user 消息。

### GREEN

- 实现 API 后，修正上传替换结果序列化、题型计数错误映射及 Pydantic 1/2 的 schema 导出兼容性，API 测试达到 `13 passed`。
- chat 调整为 Agent 先运行、随后持久化用户和 assistant；重复上下文回归测试通过。

## 测试命令与结果

- `pytest tests/test_api.py -q`：`13 passed`，4 个依赖弃用警告。
- `pytest -q`：`135 passed, 1 failed`。
- `python -m compileall -q app tests`：退出码 `0`。
- 最终测试环境：Python 3.10、Pydantic `1.10.26`、FastAPI `0.95.2`、httpx `0.27.2`。

## 全量测试唯一失败及判断

失败测试为 `tests/test_review.py::test_short_answer_rubric_none_is_rejected`。既有测试期望 fallback dataclass 的中文错误 `评分标准不能为空`，而当前环境安装 Pydantic 后，`GeneratedQuestion` 在进入既有自定义校验前就由 Pydantic 拒绝 `rubric=None`，实际消息为 `none is not an allowed value`。

该判断由以下结果复现：

- 安装 API 依赖前，既有基线为 `123 passed`，当时未安装 FastAPI/Pydantic，Task 1-6 的 review schema 走 fallback 分支。
- 安装 Pydantic 2 时，该测试仍失败，实际为 Pydantic 2 的 `Input should be a valid string`。
- 恢复到 FastAPI 0.95.2 + Pydantic 1.10.26 后，该测试仍失败，实际为 Pydantic 1 的 `none is not an allowed value`。

因此这是运行环境触发的既有 Pydantic 分支兼容问题，不是本次 API 变更导致的行为回归。本阶段未修改 Task 1-6 生产代码，也未修改该测试。

## 文件清单

- `app/api/__init__.py`
- `app/api/schemas.py`
- `app/api/routes.py`
- `app/main.py`
- `tests/test_api.py`
- `.superpowers/sdd/task-7-api-report.md`

未修改 `web/`、`eval/`、`README.md` 或 Task 1-6 既有模块。

## 自审与风险

- 已核对 brief 中列出的 20 个路由均注册。
- API 导入路径没有模型实例化或外部网络调用；模型依赖只在请求处理阶段创建。
- AppError 响应保留用户可理解消息；未知异常统一返回通用消息。
- 复习创建在计数校验后才进入服务，缺少计划字段时不会创建模型客户端。
- 当前仓库全量测试仍有 1 个既有 Pydantic 兼容失败，需后续在依赖策略或 Task 1-6 review schema 中统一 Pydantic/fallback 行为；本阶段按范围保留该问题。
