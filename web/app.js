const state = {
  knowledgeBaseId: null,
  sessionId: null,
  reviewSessionId: null,
  planId: null,
  knowledgeBases: [],
  files: [],
  reviewQuestions: [],
};

const els = {
  views: {
    chat: document.getElementById("chat-view"),
    knowledge: document.getElementById("knowledge-view"),
    review: document.getElementById("review-view"),
    plan: document.getElementById("plan-view"),
    progress: document.getElementById("progress-view"),
  },
  knowledgeBaseSelect: document.getElementById("knowledge-base-select"),
  chatMessages: document.getElementById("chat-messages"),
  chatInput: document.getElementById("chat-input"),
  sendChat: document.getElementById("send-chat"),
  knowledgeBaseList: document.getElementById("knowledge-base-list"),
  knowledgeBaseName: document.getElementById("knowledge-base-name"),
  renameKnowledgeBaseName: document.getElementById("rename-knowledge-base-name"),
  createKnowledgeBase: document.getElementById("create-knowledge-base"),
  renameKnowledgeBase: document.getElementById("rename-knowledge-base"),
  deleteKnowledgeBase: document.getElementById("delete-knowledge-base"),
  fileInput: document.getElementById("file-input"),
  uploadFiles: document.getElementById("upload-files"),
  clearFiles: document.getElementById("clear-files"),
  fileList: document.getElementById("file-list"),
  reviewChoiceCount: document.getElementById("review-choice-count"),
  reviewJudgmentCount: document.getElementById("review-judgment-count"),
  reviewShortCount: document.getElementById("review-short-count"),
  reviewFileScope: document.getElementById("review-file-scope"),
  createReview: document.getElementById("create-review"),
  reviewForm: document.getElementById("review-form"),
  saveReviewDraft: document.getElementById("save-review-draft"),
  submitReview: document.getElementById("submit-review"),
  reviewResult: document.getElementById("review-result"),
  planGoal: document.getElementById("plan-goal"),
  planDeadline: document.getElementById("plan-deadline"),
  planDailyMinutes: document.getElementById("plan-daily-minutes"),
  planFileScope: document.getElementById("plan-file-scope"),
  generatePlan: document.getElementById("generate-plan"),
  planContent: document.getElementById("plan-content"),
  savePlan: document.getElementById("save-plan"),
  planStatus: document.getElementById("plan-status"),
  progressScope: document.getElementById("progress-scope"),
  progressMetrics: document.getElementById("progress-metrics"),
};

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;
  if (!isFormData && options.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(path, { ...options, headers });
  if (response.status === 204) {
    return null;
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.message || "请求失败");
  }
  return data;
}

function showView(name) {
  Object.entries(els.views).forEach(([key, node]) => {
    node.classList.toggle("active", key === name);
  });
  document.querySelectorAll(".nav-btn").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === name);
  });
}

function selectedFileIds(container) {
  return Array.from(container.querySelectorAll('input[type="checkbox"]:checked')).map(
    (input) => input.value
  );
}

function renderMessages(messages) {
  els.chatMessages.innerHTML = "";
  messages.forEach((message) => {
    const node = document.createElement("div");
    node.className = `message ${message.role}`;
    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = `${message.role} · ${message.task_type || "chat"}`;
    node.appendChild(meta);
    const body = document.createElement("div");
    body.textContent = message.content || "";
    node.appendChild(body);
    if (message.citations && message.citations.length) {
      const citations = document.createElement("div");
      citations.className = "citations";
      citations.textContent = message.citations
        .map((item) => `${item.source || "资料"}#${item.chunk_id || ""}`)
        .join(" · ");
      node.appendChild(citations);
    }
    if (message.workspace_type === "review" && message.workspace_id) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "secondary";
      button.textContent = "打开复习工作区";
      button.addEventListener("click", () => openReviewWorkspace(message.workspace_id));
      node.appendChild(button);
    }
    if (message.workspace_type === "plan" && message.workspace_id) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "secondary";
      button.textContent = "打开学习计划";
      button.addEventListener("click", () => openPlanWorkspace(message.workspace_id));
      node.appendChild(button);
    }
    els.chatMessages.appendChild(node);
  });
  els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
}

function appendLocalMessage(role, content, extra = {}) {
  const current = Array.from(els.chatMessages.children).map((node) => ({
    role: node.classList.contains("assistant") ? "assistant" : "user",
    content: node.querySelector("div:nth-child(2)")?.textContent || "",
  }));
  // Direct DOM append is simpler and avoids reconstructing full history.
  const node = document.createElement("div");
  node.className = `message ${role}`;
  const meta = document.createElement("div");
  meta.className = "meta";
  meta.textContent = `${role} · ${extra.task_type || "chat"}`;
  node.appendChild(meta);
  const body = document.createElement("div");
  body.textContent = content || "";
  node.appendChild(body);
  if (extra.citations && extra.citations.length) {
    const citations = document.createElement("div");
    citations.className = "citations";
    citations.textContent = extra.citations
      .map((item) => `${item.source || "资料"}#${item.chunk_id || ""}`)
      .join(" · ");
    node.appendChild(citations);
  }
  if (extra.workspace_type === "review" && extra.workspace_id) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary";
    button.textContent = "打开复习工作区";
    button.addEventListener("click", () => openReviewWorkspace(extra.workspace_id));
    node.appendChild(button);
  }
  if (extra.workspace_type === "plan" && extra.workspace_id) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary";
    button.textContent = "打开学习计划";
    button.addEventListener("click", () => openPlanWorkspace(extra.workspace_id));
    node.appendChild(button);
  }
  els.chatMessages.appendChild(node);
  els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
  return current;
}

function renderKnowledgeBases() {
  const options = ['<option value="">无知识库</option>']
    .concat(
      state.knowledgeBases.map(
        (item) =>
          `<option value="${item.id}" ${
            item.id === state.knowledgeBaseId ? "selected" : ""
          }>${item.name}</option>`
      )
    )
    .join("");
  els.knowledgeBaseSelect.innerHTML = options;
  els.progressScope.innerHTML = options;
  els.knowledgeBaseList.innerHTML = state.knowledgeBases
    .map(
      (item) => `
      <div class="kb-item ${item.id === state.knowledgeBaseId ? "active" : ""}" data-id="${item.id}">
        <strong>${item.name}</strong>
        <div class="meta">${item.id}</div>
      </div>`
    )
    .join("");
  els.knowledgeBaseList.querySelectorAll(".kb-item").forEach((node) => {
    node.addEventListener("click", () => switchKnowledgeBase(node.dataset.id));
  });
}

function renderFiles(targetList = els.fileList, selectable = false, container = null) {
  const host = container || targetList;
  if (!state.files.length) {
    host.innerHTML = '<div class="file-item">当前知识库没有文件</div>';
    return;
  }
  host.innerHTML = state.files
    .map((file) => {
      const statusClass = file.status === "ready" ? "status-ok" : "status-failed";
      const checkbox = selectable
        ? `<label><input type="checkbox" value="${file.id}" /> 纳入范围</label>`
        : `<button type="button" class="danger" data-delete-file="${file.id}">删除</button>`;
      return `
        <div class="file-item">
          <div><strong>${file.original_name || file.filename || file.id}</strong></div>
          <div class="${statusClass}">${file.status || "ready"}${
        file.error_message ? ` · ${file.error_message}` : ""
      }</div>
          ${checkbox}
        </div>`;
    })
    .join("");
  host.querySelectorAll("[data-delete-file]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!state.knowledgeBaseId) return;
      await api(
        `/api/knowledge-bases/${state.knowledgeBaseId}/files/${button.dataset.deleteFile}`,
        { method: "DELETE" }
      );
      await refreshFiles();
    });
  });
}

function renderReviewQuestions(questions, answers = []) {
  state.reviewQuestions = questions || [];
  const answerMap = Object.fromEntries(
    (answers || []).map((item) => [item.question_id, item])
  );
  els.reviewForm.innerHTML = state.reviewQuestions
    .map((question, index) => {
      const draft = answerMap[question.id]?.answer_text || "";
      let control = "";
      if (question.question_type === "choice") {
        control = (question.options || [])
          .map(
            (option) => `
            <label>
              <input type="radio" name="q-${question.id}" value="${option.label}" ${
              draft === option.label ? "checked" : ""
            } />
              ${option.label}. ${option.text}
            </label>`
          )
          .join("");
      } else if (question.question_type === "judgment") {
        control = ["正确", "错误"]
          .map(
            (value) => `
            <label>
              <input type="radio" name="q-${question.id}" value="${value}" ${
              draft === value ? "checked" : ""
            } />
              ${value}
            </label>`
          )
          .join("");
      } else {
        control = `<textarea name="q-${question.id}" rows="4">${draft}</textarea>`;
      }
      return `
        <div class="question-card" data-question-id="${question.id}">
          <div><strong>第 ${index + 1} 题 · ${question.question_type}</strong></div>
          <div>${question.prompt}</div>
          <div class="row" style="flex-direction:column;align-items:stretch">${control}</div>
        </div>`;
    })
    .join("");
}

function collectReviewAnswers() {
  return state.reviewQuestions.map((question) => {
    let answerText = "";
    if (question.question_type === "short_answer") {
      answerText = els.reviewForm.querySelector(`textarea[name="q-${question.id}"]`)?.value || "";
    } else {
      answerText =
        els.reviewForm.querySelector(`input[name="q-${question.id}"]:checked`)?.value || "";
    }
    return { question_id: question.id, answer_text: answerText };
  });
}

async function loadKnowledgeBases() {
  state.knowledgeBases = await api("/api/knowledge-bases");
  renderKnowledgeBases();
}

async function createKnowledgeBase() {
  const name = els.knowledgeBaseName.value.trim();
  if (!name) {
    alert("请输入知识库名称");
    return;
  }
  const created = await api("/api/knowledge-bases", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
  els.knowledgeBaseName.value = "";
  await loadKnowledgeBases();
  await switchKnowledgeBase(created.id);
  showView("knowledge");
}

async function renameKnowledgeBase() {
  if (!state.knowledgeBaseId) {
    alert("请先选择知识库");
    return;
  }
  const name = els.renameKnowledgeBaseName.value.trim();
  if (!name) {
    alert("请输入新名称");
    return;
  }
  await api(`/api/knowledge-bases/${state.knowledgeBaseId}`, {
    method: "PATCH",
    body: JSON.stringify({ name }),
  });
  els.renameKnowledgeBaseName.value = "";
  await loadKnowledgeBases();
}

async function deleteKnowledgeBase() {
  if (!state.knowledgeBaseId) {
    alert("请先选择知识库");
    return;
  }
  if (!confirm("确认删除当前知识库？只会删除应用内副本和索引。")) {
    return;
  }
  await api(`/api/knowledge-bases/${state.knowledgeBaseId}`, { method: "DELETE" });
  state.knowledgeBaseId = null;
  state.sessionId = null;
  state.files = [];
  await loadKnowledgeBases();
  await switchKnowledgeBase("");
}

async function refreshFiles() {
  if (!state.knowledgeBaseId) {
    state.files = [];
    renderFiles();
    renderFiles(null, true, els.reviewFileScope);
    renderFiles(null, true, els.planFileScope);
    return;
  }
  state.files = await api(`/api/knowledge-bases/${state.knowledgeBaseId}/files`);
  renderFiles();
  renderFiles(null, true, els.reviewFileScope);
  renderFiles(null, true, els.planFileScope);
}

async function switchKnowledgeBase(knowledgeBaseId) {
  state.knowledgeBaseId = knowledgeBaseId || null;
  const session = await api("/api/chat/sessions", {
    method: "POST",
    body: JSON.stringify({ knowledge_base_id: state.knowledgeBaseId }),
  });
  state.sessionId = session.id;
  renderKnowledgeBases();
  els.chatMessages.innerHTML = "";
  await refreshFiles();
}

async function uploadFiles(fileList) {
  if (!state.knowledgeBaseId) {
    alert("请先选择知识库");
    return;
  }
  const files = Array.from(fileList || []);
  if (!files.length) {
    alert("请选择要上传的文件");
    return;
  }
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  const results = await api(`/api/knowledge-bases/${state.knowledgeBaseId}/files`, {
    method: "POST",
    body: formData,
  });
  els.fileList.innerHTML = results
    .map((item) => {
      const statusClass = item.status === "ready" ? "status-ok" : "status-failed";
      return `
        <div class="file-item">
          <div><strong>${item.filename || item.original_name || "未命名文件"}</strong></div>
          <div class="${statusClass}">${item.status}${
        item.error_message ? ` · ${item.error_message}` : ""
      }</div>
        </div>`;
    })
    .join("");
  await refreshFiles();
}

async function sendChat() {
  const message = els.chatInput.value.trim();
  if (!message) return;
  appendLocalMessage("user", message);
  els.chatInput.value = "";
  try {
    const result = await api("/api/chat", {
      method: "POST",
      body: JSON.stringify({
        message,
        session_id: state.sessionId,
        knowledge_base_id: state.knowledgeBaseId,
      }),
    });
    state.sessionId = result.session_id;
    appendLocalMessage("assistant", result.answer, result);
    if (result.workspace_type === "review" && result.workspace_id) {
      await openReviewWorkspace(result.workspace_id);
    } else if (result.workspace_type === "plan" && result.workspace_id) {
      await openPlanWorkspace(result.workspace_id);
    } else if (result.workspace_type === "statistics") {
      showView("progress");
      await loadProgress(result.statistics ? null : undefined, result.statistics);
    }
  } catch (error) {
    appendLocalMessage("assistant", error.message || "发送失败");
  }
}

async function openReviewWorkspace(reviewSessionId) {
  state.reviewSessionId = reviewSessionId;
  const review = await api(`/api/reviews/${reviewSessionId}`);
  renderReviewQuestions(review.questions || [], review.answers || []);
  if (review.status === "submitted") {
    els.reviewResult.textContent = JSON.stringify(
      {
        status: review.status,
        total_score: review.total_score,
        answers: review.answers,
      },
      null,
      2
    );
  } else {
    els.reviewResult.textContent = "当前复习会话可作答，提交后会锁定。";
  }
  showView("review");
}

async function createReviewSession() {
  if (!state.knowledgeBaseId) {
    alert("请先选择知识库");
    return;
  }
  const payload = {
    knowledge_base_id: state.knowledgeBaseId,
    file_ids: selectedFileIds(els.reviewFileScope),
    choice_count: Number(els.reviewChoiceCount.value || 0),
    judgment_count: Number(els.reviewJudgmentCount.value || 0),
    short_answer_count: Number(els.reviewShortCount.value || 0),
  };
  const result = await api("/api/reviews", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  await openReviewWorkspace(result.review_session_id);
}

async function saveReviewDraft() {
  if (!state.reviewSessionId) {
    alert("请先生成或打开复习会话");
    return;
  }
  await api(`/api/reviews/${state.reviewSessionId}/draft`, {
    method: "PATCH",
    body: JSON.stringify({ answers: collectReviewAnswers() }),
  });
  els.reviewResult.textContent = "草稿已保存。";
}

async function submitReview() {
  if (!state.reviewSessionId) {
    alert("请先生成或打开复习会话");
    return;
  }
  await saveReviewDraft();
  const result = await api(`/api/reviews/${state.reviewSessionId}/submit`, {
    method: "POST",
  });
  els.reviewResult.textContent = JSON.stringify(result, null, 2);
}

async function openPlanWorkspace(planId) {
  state.planId = planId;
  const plan = await api(`/api/plans/${planId}`);
  els.planContent.value = plan.content || "";
  els.planStatus.textContent = `已加载计划：${plan.title || plan.id}`;
  showView("plan");
}

async function generatePlan() {
  if (!state.knowledgeBaseId) {
    alert("请先选择知识库");
    return;
  }
  const daily = els.planDailyMinutes.value;
  const payload = {
    knowledge_base_id: state.knowledgeBaseId,
    file_ids: selectedFileIds(els.planFileScope),
    goal: els.planGoal.value.trim(),
    deadline: els.planDeadline.value.trim(),
    daily_minutes: daily === "" ? null : Number(daily),
  };
  const result = await api("/api/plans", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  if (result.status === "needs_input") {
    els.planStatus.textContent = `请补充：${(result.missing_fields || []).join("、")}`;
    return;
  }
  state.planId = result.plan_id;
  els.planContent.value = result.content || "";
  els.planStatus.textContent = `计划已生成：${result.plan_id}`;
  showView("plan");
}

async function savePlan() {
  if (!state.planId) {
    alert("请先生成计划");
    return;
  }
  const content = els.planContent.value.trim();
  if (!content) {
    alert("计划内容不能为空");
    return;
  }
  const plan = await api(`/api/plans/${state.planId}`, {
    method: "PATCH",
    body: JSON.stringify({ content }),
  });
  els.planStatus.textContent = `计划已保存：${plan.id}`;
}

async function loadProgress(forcedStats) {
  if (forcedStats) {
    els.progressMetrics.textContent = JSON.stringify(forcedStats, null, 2);
    showView("progress");
    return;
  }
  const scope = els.progressScope.value;
  const query = scope ? `?knowledge_base_id=${encodeURIComponent(scope)}` : "";
  const metrics = await api(`/api/progress${query}`);
  els.progressMetrics.textContent = JSON.stringify(metrics, null, 2);
}

function bindEvents() {
  document.querySelectorAll(".nav-btn").forEach((button) => {
    button.addEventListener("click", async () => {
      showView(button.dataset.view);
      if (button.dataset.view === "progress") {
        await loadProgress();
      }
      if (button.dataset.view === "knowledge" || button.dataset.view === "review" || button.dataset.view === "plan") {
        await refreshFiles();
      }
    });
  });
  els.knowledgeBaseSelect.addEventListener("change", async (event) => {
    await switchKnowledgeBase(event.target.value);
  });
  els.progressScope.addEventListener("change", () => loadProgress());
  els.sendChat.addEventListener("click", () => sendChat());
  els.chatInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendChat();
    }
  });
  els.createKnowledgeBase.addEventListener("click", () => createKnowledgeBase());
  els.renameKnowledgeBase.addEventListener("click", () => renameKnowledgeBase());
  els.deleteKnowledgeBase.addEventListener("click", () => deleteKnowledgeBase());
  els.uploadFiles.addEventListener("click", () => uploadFiles(els.fileInput.files));
  els.clearFiles.addEventListener("click", async () => {
    if (!state.knowledgeBaseId) return;
    if (!confirm("确认清空当前知识库文件？")) return;
    await api(`/api/knowledge-bases/${state.knowledgeBaseId}/files`, { method: "DELETE" });
    await refreshFiles();
  });
  els.createReview.addEventListener("click", () => createReviewSession());
  els.saveReviewDraft.addEventListener("click", () => saveReviewDraft());
  els.submitReview.addEventListener("click", () => submitReview());
  els.generatePlan.addEventListener("click", () => generatePlan());
  els.savePlan.addEventListener("click", () => savePlan());
}

async function init() {
  bindEvents();
  await loadKnowledgeBases();
  await switchKnowledgeBase("");
  showView("chat");
}

init().catch((error) => {
  console.error(error);
  alert(error.message || "初始化失败");
});
