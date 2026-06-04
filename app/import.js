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
wireForm("contextForm", "/api/add-context", (data) => ({...data, timestamp: localIso(data.timestamp)}));
wireForm("generateForm", "/api/generate");

const audioRows = document.getElementById("audioRows");
const audioTemplate = document.getElementById("audioRowTemplate");
const audioDropzone = document.getElementById("audioDropzone");
const audioFilePicker = document.getElementById("audioFilePicker");

function refreshAudioIndexes() {
  audioRows.querySelectorAll(".audio-row").forEach((row, index) => {
    row.querySelector(".audio-index").textContent = index + 1;
    row.querySelector(".remove-audio").disabled = audioRows.children.length === 1;
  });
}

function addAudioRow(values = {}) {
  const row = audioTemplate.content.firstElementChild.cloneNode(true);
  for (const [field, value] of Object.entries(values)) {
    const input = row.querySelector(`[data-field="${field}"]`);
    if (input) input.value = value;
  }
  row.querySelector(".remove-audio").addEventListener("click", () => {
    row.remove();
    refreshAudioIndexes();
  });
  audioRows.appendChild(row);
  refreshAudioIndexes();
}

document.getElementById("addAudioRow").addEventListener("click", () => addAudioRow());

function startToLocalInput(value) {
  return value ? value.slice(0, 16) : "";
}

async function uploadAudioFile(file) {
  setStatus("上传中", `正在复制 ${file.name} 到本机私有目录...`);
  const response = await fetch("/api/upload-audio", {
    method: "POST",
    headers: {"X-Filename": encodeURIComponent(file.name)},
    body: file,
  });
  const result = await response.json();
  if (!response.ok || !result.ok) {
    throw new Error(result.error || `无法读取 ${file.name}`);
  }
  const emptyRow = [...audioRows.querySelectorAll(".audio-row")].find((row) => {
    return !row.querySelector('[data-field="path"]').value.trim();
  });
  const values = {
    path: result.path,
    start: startToLocalInput(result.start),
    summary: "",
  };
  if (emptyRow) {
    for (const [field, value] of Object.entries(values)) {
      emptyRow.querySelector(`[data-field="${field}"]`).value = value;
    }
  } else {
    addAudioRow(values);
  }
  refreshAudioIndexes();
  return result;
}

async function handleAudioFiles(files) {
  const selected = [...files].filter((file) => file.size > 0);
  if (!selected.length) return;
  try {
    const results = [];
    for (const file of selected) {
      results.push(await uploadAudioFile(file));
    }
    setStatus("已选择", `已添加 ${results.length} 段录音，请补充场景摘要后批量导入。`);
  } catch (error) {
    setStatus("失败", error.message);
  }
}

audioDropzone.addEventListener("click", () => audioFilePicker.click());
audioDropzone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    audioFilePicker.click();
  }
});
audioFilePicker.addEventListener("change", () => {
  handleAudioFiles(audioFilePicker.files);
  audioFilePicker.value = "";
});
for (const eventName of ["dragenter", "dragover"]) {
  audioDropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    audioDropzone.classList.add("dragging");
  });
}
for (const eventName of ["dragleave", "drop"]) {
  audioDropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    audioDropzone.classList.remove("dragging");
  });
}
audioDropzone.addEventListener("drop", (event) => handleAudioFiles(event.dataTransfer.files));

document.getElementById("audioBatchForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector('button[type="submit"]');
  const items = [...audioRows.querySelectorAll(".audio-row")].map((row) => {
    const start = row.querySelector('[data-field="start"]').value;
    return {
      path: row.querySelector('[data-field="path"]').value.trim(),
      start: start ? localIso(start) : "",
      summary: row.querySelector('[data-field="summary"]').value.trim(),
    };
  }).filter((item) => item.path);
  button.disabled = true;
  button.textContent = "批量处理中...";
  try {
    await post("/api/import-audios", {items});
  } catch (error) {
    setStatus("失败", error.message);
  } finally {
    button.disabled = false;
    button.textContent = button.dataset.label;
  }
});

addAudioRow();

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
document.querySelector('#contextForm input[type="datetime-local"]').value = localDate.slice(0, 16);
