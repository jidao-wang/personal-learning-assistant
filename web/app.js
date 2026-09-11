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
  chatKbLabel: document.getElementById("chat-kb-label"),
  reviewKbLabel: document.getElementById("review-kb-label"),
  planKbLabel: document.getElementById("plan-kb-label"),
  progressScope: document.getElementById("progress-scope"),
  progressMetrics: document.getElementById("progress-metrics"),
  dependencyBanner: document.getElementById("dependency-banner"),
  dependencyBannerText: document.getElementById("dependency-banner-text"),
  dismissDependencyBanner: document.getElementById("dismiss-dependency-banner"),
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

function setStatus(node, text) {
  if (!node) return;
  const value = (text || "").trim();
  if (!value) {
    node.hidden = true;
    node.textContent = "";
    return;
  }
  node.hidden = false;
  node.textContent = value;
}


async function withBusyButton(button, busyText, statusNode, statusText, work) {
  if (!button) return work();
  const original = button.textContent;
  button.disabled = true;
  button.textContent = busyText;
  if (statusNode) setStatus(statusNode, statusText);
  try {
    return await work();
  } catch (error) {
    const message = (error && error.message) || "操作失败";
    if (statusNode) setStatus(statusNode, message);
    alert(message);
    return null;
  } finally {
    button.disabled = false;
    button.textContent = original;
  }
}

function showDependencyBanner(warnings) {
  if (!els.dependencyBanner || !els.dependencyBannerText) return;
  const list = Array.isArray(warnings) ? warnings.filter(Boolean) : [];
  if (!list.length) {
    els.dependencyBanner.hidden = true;
    els.dependencyBannerText.textContent = "";
    return;
  }
  if (window.sessionStorage.getItem("learningAssistant.dismissDependencyBanner") === list.join("|")) {
    els.dependencyBanner.hidden = true;
    return;
  }
  els.dependencyBanner.dataset.warnings = list.join("|");
  els.dependencyBannerText.textContent =
    "模型相关功能暂不可用：" + list.join("；") + "。知识库管理仍可使用。";
  els.dependencyBanner.hidden = false;
}

async function loadDependencyStatus() {
  try {
    const health = await api("/api/health");
    showDependencyBanner(health.warnings || []);
    return health;
  } catch (error) {
    // Older servers may only expose /health
    try {
      const health = await api("/health");
      showDependencyBanner(health.warnings || []);
      return health;
    } catch (_ignored) {
      return null;
    }
  }
}

function selectedFileIds(container) {
  return Array.from(container.querySelectorAll('input[type="checkbox"]:checked')).map(
    (input) => input.value
  );
}

function emptyState(text, actionLabel, onClick) {
  const wrap = document.createElement("div");
  wrap.className = "empty-state";
  wrap.textContent = text;
  if (actionLabel && onClick) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "secondary";
    button.textContent = actionLabel;
    button.addEventListener("click", onClick);
    wrap.appendChild(document.createElement("br"));
    wrap.appendChild(button);
  }
  return wrap;
}

function renderMessages(messages) {
  els.chatMessages.innerHTML = "";
  if (!messages.length) {
    els.chatMessages.appendChild(
      emptyState("还没有消息。先选择知识库，或直接开始普通聊天。")
    );
    return;
  }
  messages.forEach((message) => appendMessageNode(message));
  els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
}

function appendMessageNode(message) {
  if (els.chatMessages.querySelector(".empty-state")) {
    els.chatMessages.innerHTML = "";
  }
  const node = document.createElement("div");
  node.className = `message ${message.role || "assistant"}`;
  const meta = document.createElement("div");
  meta.className = "meta";
  meta.textContent = `${message.role || "assistant"} · ${message.task_type || "chat"}`;
  node.appendChild(meta);
  const body = document.createElement("div");
  body.textContent = message.content || message.answer || "";
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
  els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
}

function appendLocalMessage(role, content, extra = {}) {
  appendMessageNode({
    role,
    content,
    task_type: extra.task_type || "chat",
    citations: extra.citations || [],
    workspace_type: extra.workspace_type || "",
    workspace_id: extra.workspace_id || "",
  });
}


function currentKnowledgeBaseName() {
  if (!state.knowledgeBaseId) return "未选择";
  const found = state.knowledgeBases.find((item) => item.id === state.knowledgeBaseId);
  return found ? found.name : "未选择";
}

function renderKnowledgeBaseLabels() {
  const label = "当前知识库：" + currentKnowledgeBaseName();
  [els.chatKbLabel, els.reviewKbLabel, els.planKbLabel].forEach((node) => {
    if (node) node.textContent = label;
  });
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
  renderKnowledgeBaseLabels();
  els.progressScope.innerHTML =
    '<option value="">全部知识库</option>' +
    state.knowledgeBases
      .map(
        (item) =>
          `<option value="${item.id}" ${
            item.id === state.knowledgeBaseId ? "selected" : ""
          }>${item.name}</option>`
      )
      .join("");

  els.knowledgeBaseList.innerHTML = "";
  if (!state.knowledgeBases.length) {
    els.knowledgeBaseList.appendChild(
      emptyState("还没有知识库。请填写名称并选择 txt/md 文件后创建。")
    );
    return;
  }
  state.knowledgeBases.forEach((item) => {
    const node = document.createElement("div");
    node.className = `kb-item ${item.id === state.knowledgeBaseId ? "active" : ""}`;
    node.innerHTML = `<strong>${item.name}</strong><div class="meta">${item.id}</div>`;
    node.addEventListener("click", () => switchKnowledgeBase(item.id));
    els.knowledgeBaseList.appendChild(node);
  });
}

function renderScopeBox(host, options = {}) {
  const selectable = Boolean(options.selectable);
  const allowUploadJump = Boolean(options.allowUploadJump);
  host.innerHTML = "";
  if (!state.knowledgeBaseId) {
    host.appendChild(
      emptyState(
        "请先在左侧「当前知识库」中选择。若还没有库，请到「知识库」页创建并上传。",
        "去知识库",
        () => showView("knowledge"),
      ),
    );
    return;
  }
  if (!state.files.length) {
    host.appendChild(
      emptyState(
        "当前知识库没有文件。上传 txt/md 后才能按资料出题或制定计划。",
        allowUploadJump ? "去知识库上传" : null,
        allowUploadJump ? () => showView("knowledge") : null
      )
    );
    return;
  }
  state.files.forEach((file) => {
    const node = document.createElement("div");
    node.className = "file-item";

    const main = document.createElement("div");
    main.className = "file-item-main";

    const name = document.createElement("div");
    name.className = "file-name";
    const fullName = file.original_name || file.filename || file.id;
    name.textContent = fullName;
    name.title = fullName;

    const status = document.createElement("div");
    const statusClass = file.status === "ready" ? "status-ok" : "status-failed";
    status.className = statusClass;
    status.textContent = `${file.status || "ready"}${
      file.error_message ? ` · ${file.error_message}` : ""
    }`;

    main.appendChild(name);
    main.appendChild(status);
    node.appendChild(main);

    if (selectable) {
      const label = document.createElement("label");
      label.className = "file-scope-check";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = file.id;
      checkbox.checked = true;
      label.appendChild(checkbox);
      label.appendChild(document.createTextNode("纳入范围"));
      node.appendChild(label);
    } else {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "danger";
      button.textContent = "删除";
      button.addEventListener("click", async () => {
        await api(
          `/api/knowledge-bases/${state.knowledgeBaseId}/files/${file.id}`,
          { method: "DELETE" }
        );
        await refreshFiles();
      });
      node.appendChild(button);
    }
    host.appendChild(node);
  });
}) {
  const selectable = Boolean(options.selectable);
  const allowUploadJump = Boolean(options.allowUploadJump);
  host.innerHTML = "";
  if (!state.knowledgeBaseId) {
    host.appendChild(
      emptyState(
        "请先在左侧「当前知识库」中选择。若还没有库，请到「知识库」页创建并上传。",
        "去知识库",
        () => showView("knowledge"),
      ),
    );
    return;
  }
  if (!state.files.length) {
    host.appendChild(
      emptyState(
        "当前知识库没有文件。上传 txt/md 后才能按资料出题或制定计划。",
        allowUploadJump ? "去知识库上传" : null,
        allowUploadJump ? () => showView("knowledge") : null
      )
    );
    return;
  }
  state.files.forEach((file) => {
    const node = document.createElement("div");
    node.className = "file-item";
    const statusClass = file.status === "ready" ? "status-ok" : "status-failed";
    node.innerHTML = `
      <div><strong>${file.original_name || file.filename || file.id}</strong></div>
      <div class="${statusClass}">${file.status || "ready"}${
      file.error_message ? ` · ${file.error_message}` : ""
    }</div>`;
    if (selectable) {
      const label = document.createElement("label");
      label.innerHTML = `<input type="checkbox" value="${file.id}" /> 纳入范围`;
      node.appendChild(label);
    } else {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "danger";
      button.textContent = "删除";
      button.addEventListener("click", async () => {
        await api(
          `/api/knowledge-bases/${state.knowledgeBaseId}/files/${file.id}`,
          { method: "DELETE" }
        );
        await refreshFiles();
      });
      node.appendChild(button);
    }
    host.appendChild(node);
  });
}

function renderFiles() {
  renderScopeBox(els.fileList, { selectable: false });
  renderScopeBox(els.reviewFileScope, { selectable: true, allowUploadJump: true });
  renderScopeBox(els.planFileScope, { selectable: true, allowUploadJump: true });
}

function renderReviewQuestions(questions, answers = []) {
  state.reviewQuestions = questions || [];
  const answerMap = Object.fromEntries(
    (answers || []).map((item) => [item.question_id, item])
  );
  els.reviewForm.innerHTML = "";
  if (!state.reviewQuestions.length) {
    els.reviewForm.appendChild(
      emptyState("还没有题目。设置题型后点击“生成复习题”。")
    );
    return;
  }
  state.reviewQuestions.forEach((question, index) => {
    const draft = answerMap[question.id]?.answer_text || "";
    const card = document.createElement("div");
    card.className = "question-card";
    card.dataset.questionId = question.id;
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
      control = `<textarea name="q-${question.id}" rows="5">${draft}</textarea>`;
    }
    card.innerHTML = `
      <div><strong>第 ${index + 1} 题 · ${question.question_type}</strong></div>
      <div>${question.prompt}</div>
      <div class="stack-list">${control}</div>`;
    els.reviewForm.appendChild(card);
  });
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

function renderProgress(metrics) {
  const data = metrics || {};
  const byType = data.by_question_type || {};
  const weakPoints = data.weak_points || [];
  const cards = [
    ["复习次数", data.review_count ?? 0],
    ["正确率", `${data.accuracy ?? 0}%`],
    ["平均分", data.average_score ?? 0],
    ["错题数", data.wrong_count ?? 0],
  ];
  const typeOrder = [
    ["choice", "选择题"],
    ["judgment", "判断题"],
    ["short_answer", "简答题"],
  ];
  els.progressMetrics.innerHTML = `
    <div class="metric-grid">
      ${cards
        .map(
          ([label, value]) => `
        <div class="metric-card">
          <div class="label">${label}</div>
          <div class="value">${value}</div>
        </div>`
        )
        .join("")}
    </div>
    <div class="panel">
      <h3>薄弱知识点</h3>
      <div class="weak-list">
        ${
          weakPoints.length
            ? weakPoints.map((item) => `<span class="weak-chip">${item}</span>`).join("")
            : '<div class="empty-state">暂无薄弱点，完成复习后会显示在这里。</div>'
        }
      </div>
    </div>
    <div class="type-grid">
      ${typeOrder
        .map(([key, label]) => {
          const item = byType[key] || {};
          return `
            <div class="type-card">
              <div class="label">${label}</div>
              <div class="value">${item.question_count ?? 0} 题</div>
              <div class="meta">正确率 ${item.accuracy ?? 0}% · 平均分 ${
            item.average_score ?? 0
          }</div>
            </div>`;
        })
        .join("")}
    </div>`;
}

function renderReviewResult(result) {
  if (!result) {
    setStatus(els.reviewResult, "");
    return;
  }
  if (typeof result === "string") {
    setStatus(els.reviewResult, result);
    return;
  }
  const answers = result.answers || [];
  const failed = answers.filter((item) => item.status === "grading_failed").length;
  const summary = `总分 ${result.total_score ?? "-"} · 状态 ${result.status || "submitted"} · ${
    answers.length
  } 题${failed ? ` · ${failed} 道简答评分失败` : ""}`;
  setStatus(els.reviewResult, summary);
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
  const files = Array.from(els.fileInput.files || []);
  if (!files.length) {
    alert("创建知识库时必须同时选择至少一个 txt/md 文件");
    return;
  }

  let created = null;
  try {
    created = await api("/api/knowledge-bases", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
    await switchKnowledgeBase(created.id);

    const formData = new FormData();
    files.forEach((file) => formData.append("files", file));
    const results = await api(`/api/knowledge-bases/${created.id}/files`, {
      method: "POST",
      body: formData,
    });
    const readyCount = results.filter((item) => item.status === "ready").length;
    if (!readyCount) {
      const reason = results
        .map((item) => `${item.filename || "文件"}: ${item.error_message || item.status}`)
        .join("\n");
      try {
        await api(`/api/knowledge-bases/${created.id}`, { method: "DELETE" });
      } catch (cleanupError) {
        console.error(cleanupError);
      }
      state.knowledgeBaseId = null;
      state.sessionId = null;
      state.files = [];
      els.knowledgeBaseName.value = "";
      els.fileInput.value = "";
      await loadKnowledgeBases();
      await switchKnowledgeBase("");
      alert(`创建失败：没有成功入库的文件。\n${reason}`);
      return;
    }

    els.knowledgeBaseName.value = "";
    els.fileInput.value = "";
    await loadKnowledgeBases();
    await switchKnowledgeBase(created.id);
    await refreshFiles();
    showView("knowledge");
    if (readyCount < results.length) {
      alert(`知识库已创建，但有 ${results.length - readyCount} 个文件失败。`);
    }
  } catch (error) {
    if (created?.id) {
      try {
        await api(`/api/knowledge-bases/${created.id}`, { method: "DELETE" });
      } catch (cleanupError) {
        console.error(cleanupError);
      }
      state.knowledgeBaseId = null;
      state.sessionId = null;
      state.files = [];
      await loadKnowledgeBases();
      await switchKnowledgeBase("");
    }
    alert(error.message || "创建知识库失败");
  }
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
  try {
    await api(`/api/knowledge-bases/${state.knowledgeBaseId}`, { method: "DELETE" });
    state.knowledgeBaseId = null;
    state.sessionId = null;
    state.files = [];
    await loadKnowledgeBases();
    await switchKnowledgeBase("");
  } catch (error) {
    alert(error.message || "删除知识库失败");
    await loadKnowledgeBases();
    await refreshFiles();
  }
}

async function refreshFiles() {
  if (!state.knowledgeBaseId) {
    state.files = [];
  } else {
    state.files = await api(`/api/knowledge-bases/${state.knowledgeBaseId}/files`);
  }
  renderFiles();
}

async function switchKnowledgeBase(knowledgeBaseId) {
  state.knowledgeBaseId = knowledgeBaseId || null;
  if (state.knowledgeBaseId) {
    window.localStorage.setItem("learningAssistant.knowledgeBaseId", state.knowledgeBaseId);
  } else {
    window.localStorage.removeItem("learningAssistant.knowledgeBaseId");
  }
  const session = await api("/api/chat/sessions", {
    method: "POST",
    body: JSON.stringify({ knowledge_base_id: state.knowledgeBaseId }),
  });
  state.sessionId = session.id;
  renderKnowledgeBases();
  renderMessages([]);
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
  els.fileList.innerHTML = "";
  results.forEach((item) => {
    const node = document.createElement("div");
    node.className = "file-item";
    const statusClass = item.status === "ready" ? "status-ok" : "status-failed";
    node.innerHTML = `
      <div><strong>${item.filename || item.original_name || "未命名文件"}</strong></div>
      <div class="${statusClass}">${item.status}${
      item.error_message ? ` · ${item.error_message}` : ""
    }</div>`;
    els.fileList.appendChild(node);
  });
  await refreshFiles();
}

async function sendChat() {
  const message = els.chatInput.value.trim();
  if (!message) return;
  appendLocalMessage("user", message);
  els.chatInput.value = "";
  autoResizeChatInput();
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
      renderProgress(result.statistics || {});
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
    renderReviewResult(review);
  } else {
    setStatus(els.reviewResult, "当前复习会话可作答，提交后会锁定。");
  }
  showView("review");
}

async function createReviewSession() {
  if (!state.knowledgeBaseId) {
    alert("请先选择知识库");
    return;
  }
  await withBusyButton(
    els.createReview,
    "生成中…",
    els.reviewResult,
    "正在根据资料生成…",
    async () => {
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
      setStatus(els.reviewResult, "复习题已生成，可在作答区作答。");
    },
  );
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
  setStatus(els.reviewResult, "草稿已保存。");
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
  renderReviewResult(result);
}

async function openPlanWorkspace(planId) {
  state.planId = planId;
  const plan = await api(`/api/plans/${planId}`);
  els.planContent.value = plan.content || "";
  setStatus(els.planStatus, `已加载计划：${plan.title || plan.id}`);
  showView("plan");
}

async function generatePlan() {
  if (!state.knowledgeBaseId) {
    alert("请先选择知识库");
    return;
  }
  await withBusyButton(
    els.generatePlan,
    "生成中…",
    els.planStatus,
    "正在根据资料生成…",
    async () => {
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
        setStatus(els.planStatus, `请补充：${(result.missing_fields || []).join("、")}`);
        return;
      }
      state.planId = result.plan_id;
      els.planContent.value = result.content || "";
      setStatus(els.planStatus, `计划已生成：${result.plan_id}`);
      showView("plan");
    },
  );
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
  setStatus(els.planStatus, `计划已保存：${plan.id}`);
}

async function loadProgress(forcedStats) {
  if (forcedStats) {
    renderProgress(forcedStats);
    showView("progress");
    return;
  }
  const scope = els.progressScope.value;
  const query = scope ? `?knowledge_base_id=${encodeURIComponent(scope)}` : "";
  const metrics = await api(`/api/progress${query}`);
  renderProgress(metrics);
}

function autoResizeChatInput() {
  const input = els.chatInput;
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 160)}px`;
}

function bindEvents() {
  document.querySelectorAll(".nav-btn").forEach((button) => {
    button.addEventListener("click", async () => {
      showView(button.dataset.view);
      if (button.dataset.view === "progress") {
        await loadProgress();
      }
      if (
        button.dataset.view === "knowledge" ||
        button.dataset.view === "review" ||
        button.dataset.view === "plan"
      ) {
        await refreshFiles();
      }
    });
  });
  els.knowledgeBaseSelect.addEventListener("change", async (event) => {
    await switchKnowledgeBase(event.target.value);
  });
  els.progressScope.addEventListener("change", () => loadProgress());
  els.sendChat.addEventListener("click", () => sendChat());
  els.chatInput.addEventListener("input", autoResizeChatInput);
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
  if (els.dismissDependencyBanner) {
    els.dismissDependencyBanner.addEventListener("click", () => {
      if (!els.dependencyBanner || !els.dependencyBannerText) return;
      window.sessionStorage.setItem(
        "learningAssistant.dismissDependencyBanner",
        (els.dependencyBannerText.textContent || "").replace(/^模型相关功能暂不可用：/, "").replace(/。知识库管理仍可使用。$/, ""),
      );
      // Store raw warnings joined if we kept them on dataset
      const raw = els.dependencyBanner.dataset.warnings || "";
      window.sessionStorage.setItem("learningAssistant.dismissDependencyBanner", raw);
      els.dependencyBanner.hidden = true;
    });
  }
}

async function init() {
  bindEvents();
  setStatus(els.planStatus, "");
  setStatus(els.reviewResult, "");
  await loadKnowledgeBases();
  const preferredId = window.localStorage.getItem("learningAssistant.knowledgeBaseId") || "";
  const availableIds = new Set(state.knowledgeBases.map((item) => item.id));
  const initialId = availableIds.has(preferredId)
    ? preferredId
    : (state.knowledgeBases[0] && state.knowledgeBases[0].id) || "";
  await switchKnowledgeBase(initialId);
  await loadDependencyStatus();
  renderProgress({
    review_count: 0,
    accuracy: 0,
    average_score: 0,
    wrong_count: 0,
    weak_points: [],
    by_question_type: {},
  });
  autoResizeChatInput();
  showView("chat");
}

init().catch((error) => {
  console.error(error);
  alert(error.message || "初始化失败");
});
