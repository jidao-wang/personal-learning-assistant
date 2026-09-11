# 个人学习资料问答与复习助手

## 功能

- 上传 txt/md 资料并维护多个独立知识库
- 普通聊天和带引用的资料问答
- 选择题、判断题、简答题复习与评分
- 学习计划编辑保存
- 基于真实答题记录的学习进度统计

## 启动

```powershell
py -3.10 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# 在 .env 中填写 DASHSCOPE_API_KEY
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

浏览器访问 `http://127.0.0.1:8000`。

## 数据和安全

应用只读取用户在页面上传的 txt/md 文件。运行时数据在 `data/`，API Key 在 `.env`，这些内容不会提交到 GitHub。删除应用中的文件不会删除电脑上的原文件。

## 架构

FastAPI → LangGraph 单主 Agent → chat/qa/review/plan/statistics；SQLite 保存业务记录，Chroma 按知识库持久化向量。

## 测试

```powershell
pytest -q
python eval/run_eval.py
```
