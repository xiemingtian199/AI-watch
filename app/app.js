const state = {
  data: null,
  filter: "all",
  feedback: JSON.parse(localStorage.getItem("ai-watch-feedback") || "{}"),
};

const feedbackLabels = {
  accurate: "准确",
  wrong: "不准确",
  mute: "别再提",
  watch: "继续观察",
};

async function loadData() {
  const response = await fetch("data/cards.json", { cache: "no-store" });
  if (!response.ok) {
    throw new Error("无法载入复盘数据，请先运行生成脚本。");
  }
  state.data = await response.json();
  render();
}

function saveFeedback() {
  localStorage.setItem("ai-watch-feedback", JSON.stringify(state.feedback, null, 2));
  document.getElementById("feedbackCount").textContent = Object.keys(state.feedback).length;
}

function renderMetrics() {
  const { summary, cards, date, generatedAt, mode } = state.data;
  document.getElementById("runMeta").textContent = `${date} 生成，${mode}，${new Date(generatedAt).toLocaleString("zh-CN")}`;
  document.getElementById("eventCount").textContent = summary.eventCount;
  document.getElementById("sourceCount").textContent = Object.keys(summary.sources).length;
  document.getElementById("cardCount").textContent = cards.length;
  document.getElementById("modeBadge").textContent = mode;
  saveFeedback();
}

function renderCards() {
  const root = document.getElementById("cards");
  const template = document.getElementById("cardTemplate");
  root.innerHTML = "";

  const cards = state.data.cards.filter((card) => {
    return state.filter === "all" || card.type === state.filter;
  });

  if (!cards.length) {
    root.innerHTML = '<div class="empty">这个筛选下还没有卡片。</div>';
    return;
  }

  for (const card of cards) {
    const node = template.content.firstElementChild.cloneNode(true);
    node.dataset.type = card.type;
    node.querySelector(".type").textContent = card.typeLabel || card.type;
    node.querySelector(".confidence").textContent = `置信度 ${Math.round((card.confidence || 0) * 100)}%`;
    node.querySelector("h3").textContent = card.title;
    node.querySelector(".time").textContent = card.timeRange;
    node.querySelector(".body").textContent = card.body;
    node.querySelector(".suggestion").textContent = card.suggestion;

    const evidence = node.querySelector(".evidence");
    for (const item of card.evidence || []) {
      const li = document.createElement("li");
      li.textContent = `${item.time} · ${item.source}/${item.modality}: ${item.summary}`;
      evidence.appendChild(li);
    }

    const selected = state.feedback[card.id];
    node.querySelectorAll(".feedback button").forEach((button) => {
      if (button.dataset.feedback === selected) {
        button.classList.add("selected");
      }
      button.addEventListener("click", () => {
        state.feedback[card.id] = button.dataset.feedback;
        saveFeedback();
        renderCards();
      });
    });

    root.appendChild(node);
  }
}

function renderTimeline() {
  const root = document.getElementById("timeline");
  root.innerHTML = "";
  for (const event of state.data.timeline) {
    const item = document.createElement("div");
    item.className = "timeline-item";
    const activity = event.context?.activity || "unknown";
    item.innerHTML = `
      <div class="timeline-time">${event.time}</div>
      <div>
        <div class="timeline-title">${escapeHtml(event.summary)}</div>
        <div class="timeline-meta">${escapeHtml(event.source)} · ${escapeHtml(event.modality)} · ${escapeHtml(activity)}</div>
      </div>
    `;
    root.appendChild(item);
  }
}

function render() {
  renderMetrics();
  renderCards();
  renderTimeline();
}

function escapeHtml(value) {
  return String(value || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

document.querySelectorAll(".filter").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".filter").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    state.filter = button.dataset.type;
    renderCards();
  });
});

document.getElementById("exportFeedback").addEventListener("click", async () => {
  const payload = JSON.stringify(state.feedback, null, 2);
  try {
    await navigator.clipboard.writeText(payload);
    document.getElementById("exportFeedback").textContent = "已复制反馈";
    setTimeout(() => {
      document.getElementById("exportFeedback").textContent = "导出反馈";
    }, 1400);
  } catch {
    alert(payload);
  }
});

document.getElementById("clearFeedback").addEventListener("click", () => {
  state.feedback = {};
  saveFeedback();
  renderCards();
});

loadData().catch((error) => {
  document.getElementById("cards").innerHTML = `<div class="error">${escapeHtml(error.message)}</div>`;
});
