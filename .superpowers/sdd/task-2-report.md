# Task 2 完成报告

## 修改文件

- `app/storage/__init__.py`
- `app/storage/knowledge_base_store.py`
- `app/knowledge/__init__.py`
- `app/knowledge/validation.py`
- `app/knowledge/chunking.py`
- `app/knowledge/embeddings.py`
- `app/knowledge/vector_store.py`
- `app/knowledge/ingest.py`
- `app/core/database.py`（沿用 Task 1 数据库表结构）
- `tests/conftest.py`
- `tests/fixtures/sample_learning.md`
- `tests/test_ingest.py`

## 实现摘要

- 支持 UTF-8 `.txt` / `.md` 上传，拒绝空文件、非法扩展名、非法编码和超过 10 MB 的文件。
- 使用安全文件名边界和 UUID 内部存储路径，不把用户文件名直接用于路径拼接。
- 清洗文本、保留 Markdown 标题、按配置切片并保证长段落切片不超过 `chunk_size`。
- 支持知识库和文件 CRUD、同知识库同名文件覆盖、覆盖失败隔离、文件删除和知识库清空。
- 使用 SHA-256、稳定向量 ID 和包含知识库/文件/来源信息的 metadata 持久化切片。
- 每个知识库使用独立 Chroma collection；测试使用 fake embedding/vector store，避免外部网络调用。
- 修复并确认 `upsert_file` 在 `(knowledge_base_id, original_name)` 冲突更新后按冲突键查询，返回数据库中已有的逻辑文件记录，而不是新传入的 `file_record['id']`。

## 测试命令及实际输出

```text
C:\Python3.10\python.exe -m pytest tests/test_ingest.py -q
....................                                                     [100%]
20 passed in 0.92s
```

```text
C:\Python3.10\python.exe -m pytest tests/test_database.py tests/test_ingest.py -q
.......................                                                  [100%]
23 passed in 1.00s
```

覆盖范围包括上传校验、10 MB 边界、UTF-8、清洗切片和重叠、长段落上限、知识库 CRUD、同名覆盖、失败隔离、删除、清空、跨知识库 Chroma collection 隔离及 `upsert_file` 同名冲突回归。

## 疑虑

- 本次测试未调用真实 DashScope Embedding 或真实 Chroma 后端，外部服务行为仍需配置 API Key 后进行人工 smoke test。
- `ingest_file` 在向量写入成功但后续应用副本或 SQLite 写入失败时，可能需要后续增加事务式补偿清理；当前测试覆盖了 embedding/校验失败时不替换旧版本。

## 审核修复（Task 2 persistence rollback gaps）

### 修改文件

- `app/knowledge/ingest.py`
- `app/storage/knowledge_base_store.py`
- `tests/test_ingest.py`

### 行为摘要

- `delete_knowledge_base` 在删除 SQLite 知识库行前清理该知识库的应用上传副本、向量 ID 和 Chroma collection；资源快照用于失败补偿。
- `ingest_file` 的向量写入、应用副本或 SQLite/chunk 后置持久化失败时，会删除新向量并恢复旧向量、旧副本和旧数据库记录；首次上传失败不留下新资源，覆盖失败保留旧 ready 版本。
- `delete_file` 删除前保存向量、文件和数据库记录；SQLite 删除失败时恢复外部资源及 file/chunk 记录，并继续抛出 `AppError`。
- `NotFoundError` 不再被 `ingest_file` 转换为 `failed`；删除了未使用的 `ValidatedUpload` 导入。

### 测试命令及实际输出

```text
pytest tests/test_ingest.py tests/test_database.py -q
...........................                                              [100%]
27 passed in 2.13s
```

### 仍存在的风险

- 测试使用 fake embedding/vector store，未连接真实 DashScope 或 Chroma；真实后端的 collection 删除 API 仍需环境 smoke test。
- 补偿流程是同步的 best-effort 操作，没有引入持久化恢复队列；若底层文件系统、SQLite 或向量后端在补偿本身持续不可用，错误会以 `AppError` 暴露，残留状态需要运维处理。
