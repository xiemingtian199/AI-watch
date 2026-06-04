const statusBadge = document.getElementById("statusBadge");
const statusMessage = document.getElementById("statusMessage");
const resultStats = document.getElementById("resultStats");

function localIso(value) {
  if (!value) return value;
  const date = new Date(value);
  const offset = -date.getTimezoneOffset();
  const sign = offset >= 0 ? "+" : "-";
  const hours = String(Math.floor(Math.abs(offset) / 60)).padStart(2, "0");
  const minutes = String(Math.abs(offset) % 60).padStart(2, "0");
  return `${value}:00${sign}${hours}:${minutes}`;
}

function setStatus(kind, message, result) {
  statusBadge.textContent = kind;
  statusBadge.dataset.kind = kind;
  statusMessage.textContent = message;
  resultStats.innerHTML = "";
  if (!result?.summary) return;
  const rows = [
    ["日期", result.date],
    ["事件数量", result.summary.eventCount],
    ["数据来源", Object.keys(result.summary.sources).join("、")],
    ["数据类型", Object.keys(result.summary.modalities).join("、")],
    ["复盘卡片", result.cards.length],
  ];
  for (const [label, value] of rows) {
    const dt = document.createElement("dt");
    const dd = document.createElement("dd");
    dt.textContent = label;
    dd.textContent = value;
    resultStats.append(dt, dd);
  }
}

async function post(path, payload) {
  setStatus("处理中", "正在本机处理数据，请保持页面打开。");
  const response = await fetch(path, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok || !data.ok) {
    throw new Error(data.error || "处理失败");
  }
  setStatus("已完成", data.message, data.result);
  return data;
}

function wireForm(id, endpoint, transform) {
  document.getElementById(id).addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.currentTarget.querySelector("button[type=submit]");
    const payload = Object.fromEntries(new FormData(event.currentTarget));
    button.disabled = true;
    button.textContent = "处理中...";
    try {
      await post(endpoint, transform ? transform(payload) : payload);
    } catch (error) {
      setStatus("失败", error.message);
    } finally {
      button.disabled = false;
      button.textContent = button.dataset.label;
    }
  });
}

document.querySelectorAll("button[type=submit]").forEach((button) => {
  button.dataset.label = button.textContent;
});

wireForm("healthForm", "/api/import-health");
wireForm("audioForm", "/api/import-audio", (data) => ({
  ...data,
  start: localIso(data.start),
  transcribe: data.transcribe === "on",
}));
wireForm("contextForm", "/api/add-context", (data) => ({...data, timestamp: localIso(data.timestamp)}));
wireForm("generateForm", "/api/generate");

fetch("/api/status")
  .then((response) => response.json())
  .then((data) => {
    document.getElementById("privacyText").textContent = data.privacy;
  })
  .catch(() => setStatus("离线", "本地服务未响应，请使用 start-local-app 启动。"));

const now = new Date();
const localDate = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString();
document.querySelectorAll('input[type="date"]').forEach((input) => {
  input.value = localDate.slice(0, 10);
});
document.querySelectorAll('input[type="datetime-local"]').forEach((input) => {
  input.value = localDate.slice(0, 16);
});
