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

## 模型依赖

本项目通过 OpenAI 兼容接口调用 DashScope（通义）。除 `requirements.txt` 一键安装外，请确认：

1. `.env` 中已填写 `DASHSCOPE_API_KEY`
2. 已安装 `openai` 与 `langgraph`：`pip install openai langgraph`
3. 浏览器打开后若顶部出现黄色提示，按提示补齐依赖后 **重启 uvicorn** 并 **Ctrl+F5**

知识库上传/删除不依赖大模型；聊天资料问答、复习出题、学习计划需要模型可用。

## 测试

```powershell
pytest -q
python eval/run_eval.py
```
