# Task 6 实现报告

## 实现概览

- 新增 `app/memory/store.py`：只解析以“记住我喜欢/希望”开头的显式偏好请求；保存前拒绝 API key、密码、token、secret、身份证、手机号、银行卡和明显数字敏感信息；使用 `user_preferences` 的 `ON CONFLICT(key) DO UPDATE`；提供偏好读取。
- 新增 `app/storage/plan_store.py`：持久化、读取和编辑 `learning_plans`，校验知识库、标题、内容和范围。没有新增每日任务或完成率字段。
- 新增 `app/plan/service.py`：缺少 `goal`、`deadline`、`daily_minutes` 时直接返回 `needs_input`，不构造模型客户端；字段完整时检索所选文件资料，加入已保存偏好，要求模型生成可编辑 Markdown，并保存计划。
- 新增 `app/progress/service.py`：只查询 `review_sessions.status = 'submitted'` 关联的题目和答案；客观题兼容现有未写入 score 的 review seed，短答使用 score；计算复习数、题数、正确率、平均分、错题、弱点和题型统计，支持指定知识库及全部知识库。
- 修改 `app/agent/tools.py`：真实注册 `save_preference`、`get_progress`、`generate_plan`、`generate_review`，保留 `TOOLS` 可替换能力，并从工具参数/`request_options` 转发运行时依赖。
- 修改 `app/agent/nodes.py`：显式偏好在聊天节点保存并确认，普通偏好描述仍走普通聊天；计划节点返回 `workspace_type=plan` 和计划 ID，缺字段只列出缺失字段；统计节点返回 `statistics` 和 `workspace_type=statistics`。

## TDD 记录

### RED

先创建 `tests/test_memory_plan_progress.py`，再运行：

```text
pytest tests/test_memory_plan_progress.py -q
FFFFFFFFFFFF                                                             [100%]
12 failed in 0.57s
```

失败原因为目标 `app.memory`、`app.plan`、`app.progress`、`app.storage.plan_store` 及 Agent 接线尚不存在，符合预期的功能缺失失败。

### GREEN

实现最小功能后运行：

```text
pytest tests/test_memory_plan_progress.py -q
............                                                             [100%]
12 passed in 0.70s

pytest tests/test_memory_plan_progress.py tests/test_agent.py -q
..............................................                           [100%]
46 passed in 0.96s
```

## 最终验证

运行用户要求的回归命令：

```text
pytest tests/test_database.py tests/test_ingest.py tests/test_retrieval.py tests/test_agent.py tests/test_review.py tests/test_memory_plan_progress.py -q
........................................................................ [ 60%]
...............................................                          [100%]
119 passed in 3.79s
```

运行：

```text
python -m compileall -q app tests
```

结果：退出码 0，无编译错误。

运行：

```text
git diff --check
```

结果：退出码 0；Git 仅提示 `app/agent/nodes.py` 和 `app/agent/tools.py` 的工作副本 LF/CRLF 转换，不是空白错误。

## 文件清单

新增：

- `app/memory/__init__.py`
- `app/memory/store.py`
- `app/plan/__init__.py`
- `app/plan/service.py`
- `app/storage/plan_store.py`
- `app/progress/__init__.py`
- `app/progress/service.py`
- `tests/test_memory_plan_progress.py`

修改：

- `app/agent/tools.py`
- `app/agent/nodes.py`

## 自审

- [x] 普通聊天路径不会调用 `save_preference`；只有匹配“记住我喜欢/希望”的请求才保存。
- [x] 敏感偏好拒绝保存，且使用统一的面向用户错误。
- [x] 计划缺少必填字段时不检索、不调用模型、不写入计划。
- [x] 完整计划使用知识库检索结果和偏好生成 Markdown，只写入计划本身。
- [x] 计划服务没有每日任务、完成率或其他臆造进度字段。
- [x] 统计过滤 submitted review session，不读取草稿、聊天、文件或计划数据；聚合模式可覆盖全部知识库。
- [x] Agent 工具保持真实注册，并保留测试替换 `TOOLS` 的接口。
- [x] 计划、统计、聊天节点分别返回要求的 workspace 信息和偏好确认。
- [x] 未修改 Task 1-5 的 QA、路由、review store 或数据库 schema 行为。
- [x] 未运行时读取 `C:\ai agent\agent-learning`。

## Task 6 复审修复追加记录

### 修复内容

- `app/memory/store.py`：敏感检查同时覆盖偏好键名；增加明显 `sk-...` 和 `Bearer ...` 凭据格式拦截，普通 `answer_style` 偏好仍可保存。
- `app/progress/service.py`：使用独立查询统计符合筛选条件的 `submitted` 复习会话，因此无答案会话也计入 `review_count`；题数、分数和题型统计继续只基于真实答案行。
- `app/progress/service.py`：删除未使用的 `rs.total_score` 查询列、无用途的会话 ID 聚合和契约外的固定 `draft_review_count` 字段。
- 未修改 `tests/test_memory_plan_progress.py`；其未提交回归测试仍保持原状。

### TDD RED/GREEN

复审修复前运行：

```text
pytest tests/test_memory_plan_progress.py -q
..FF......F.F...                                                         [100%]
4 failed, 12 passed in 0.95s
```

四个失败分别覆盖敏感键名、`sk-` 凭据、`draft_review_count` 不应存在和无答案 submitted 会话计数，失败原因均为生产代码缺口。

修复后运行：

```text
pytest tests/test_memory_plan_progress.py -q
................                                                         [100%]
16 passed in 0.88s
```

### 实际验证输出

```text
pytest tests/test_memory_plan_progress.py tests/test_agent.py -q
..................................................                       [100%]
50 passed in 1.24s

pytest tests/test_database.py tests/test_ingest.py tests/test_retrieval.py tests/test_agent.py tests/test_review.py tests/test_memory_plan_progress.py -q
........................................................................ [ 58%]
...................................................                      [100%]
123 passed in 4.17s

python -m compileall -q app tests
exit code 0, no output

git diff --check
exit code 0; only LF/CRLF conversion warnings, no whitespace errors
```
