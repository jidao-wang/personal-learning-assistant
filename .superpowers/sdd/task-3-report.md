# Task 3 报告

## 修改文件

- `app/core/llm_client.py`
  - 新增 OpenAI-compatible `LLMClient`。
  - OpenAI 导入延迟到首次 `chat`/`chat_json` 调用。
  - 无 `DASHSCOPE_API_KEY` 或未安装 `openai` 时抛出可读的 `ConfigurationError`。
- `app/knowledge/retriever.py`
  - 新增按 `knowledge_base_id` 获取独立 Chroma store 的检索函数。
  - 支持非空 `file_ids` 的当前 collection 内过滤、top-k 和 score threshold。
  - 新增 context 与 citation 格式化，引用只取实际检索结果。
- `app/knowledge/answer.py`
  - 新增 `AnswerPolicy`、`AnswerResult`、答案构造和问题回答流程。
  - strict 模式无命中不调用模型；default/general 模式无命中明确标注通用知识回答。
  - 有命中时提示模型只依据 context，并说明资料不足；不会采用模型返回的引用。
- `tests/test_retrieval.py`
  - 覆盖确定性格式化、检索过滤/阈值/知识库隔离、显式零值参数、三种答案边界、无 key 延迟检查、缺少 openai 的错误行为和 fake OpenAI client 注入。

## 测试

TDD 红灯确认：

```text
pytest tests/test_retrieval.py -q
ERROR collecting tests/test_retrieval.py
ModuleNotFoundError: No module named 'app.knowledge.answer'
```

通过：

```text
pytest tests/test_retrieval.py -q
13 passed in 0.03s
```

```text
pytest tests/test_database.py tests/test_ingest.py tests/test_retrieval.py -q
49 passed in 2.03s
```

```text
python -m compileall -q app tests
exit code 0
```

## 接口和边界行为

- `retrieve` 在未注入 store 时调用 `get_vector_store(knowledge_base_id, settings)`；注入 store 时严格使用注入对象。
- `file_ids` 为空或为 `None` 时不传 filter；非空时只传当前 collection 的 `file_id` `$in` 条件。
- `top_k=0` 和 `score_threshold=0` 等显式零值会被保留，只有 `None` 才回退到 settings 默认值。
- 检索结果固定返回 `text`、`source`、`title`、`chunk_id`、`file_id`、`knowledge_base_id`、`score` 七个字段。
- citation 由检索结果生成，包含 source、chunk_id、file_id、score，不接受模型生成的 citation。
- strict 无命中返回资料不足提示；default/general 无命中调用模型后加通用知识标记且 citations 为空。
- 普通聊天没有接入 RAG。

## Concerns

- 当前 Python 3.10 环境未安装 `openai`，真实模型调用前仍需按 `requirements.txt` 安装依赖并配置 API key；本任务未为测试联网安装依赖。
