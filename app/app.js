const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const icon = (name) => `<i data-lucide="${name}"></i>`;
const sourceName = (key) =>
  ({
    apple_watch: "Apple Watch",
    apple_health: "Apple 健康",
    iphone: "iPhone",
    manual_context: "个人记录",
    local_import: "本地导入",
    local_media: "本地素材",
    demo_watch: "示例手表",
    demo_journal: "示例日记",
    calendar: "日历",
    audio_analysis: "录音记录",
    iphone_audio: "录音转写",
  })[key] || key;
const metrics = {
  steps: {
    label: "步数",
    unit: "步",
    color: "#32745a",
    icon: "footprints",
    digits: 0,
  },
  sleep: {
    label: "睡眠时长",
    unit: "小时",
    color: "#9985b3",
    icon: "moon",
    digits: 1,
  },
  heart: {
    label: "心率中位数",
    unit: "bpm",
    color: "#c6755d",
    icon: "heart",
    digits: 0,
  },
  focus: {
    label: "专注记录",
    unit: "分钟",
    color: "#598cac",
    icon: "focus",
    digits: 0,
  },
  energy: {
    label: "活动能量",
    unit: "kcal",
    color: "#b89649",
    icon: "flame",
    digits: 0,
  },
  mood: {
    label: "状态自评",
    unit: "/ 5",
    color: "#699455",
    icon: "smile",
    digits: 0,
  },
};
const moodNames = ["很低落", "有点疲惫", "平稳", "不错", "很好"];
const moodIcons = ["frown", "annoyed", "meh", "smile", "laugh"];
const state = {
  dataset: localStorage.getItem("ai-watch-dataset") || "",
  view: "daily",
  date: "",
  overview: null,
  day: null,
  intraday: "heart",
  timeline: "episodes",
  trendMetric: "steps",
  range: 14,
  mood: null,
  queue: [],
  uploading: false,
  request: 0,
  dayChart: null,
  trendChart: null,
};
let toastTimer;

function icons() {
  lucide.createIcons();
}
function localToday() {
  return new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Shanghai" });
}
function dayDate(day) {
  return new Date(day + "T12:00:00+08:00");
}
function shift(day, offset) {
  const d = dayDate(day);
  d.setUTCDate(d.getUTCDate() + offset);
  return d.toISOString().slice(0, 10);
}
function dateLabel(
  day,
  options = { month: "long", day: "numeric", weekday: "long" },
) {
  return dayDate(day).toLocaleDateString("zh-CN", {
    ...options,
    timeZone: "Asia/Shanghai",
  });
}
function fmt(value, key) {
  return value == null
    ? "—"
    : Number(value).toLocaleString("zh-CN", {
        maximumFractionDigits: metrics[key]?.digits ?? 1,
      });
}
function toast(message) {
  $("#toast").textContent = message;
  $("#toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => ($("#toast").hidden = true), 3500);
}
function error(message) {
  $("#loadError").textContent = message;
  $("#loadError").hidden = !message;
}
async function api(path, data) {
  const response = await fetch(
    path,
    data
      ? {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(data),
        }
      : {},
  );
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "请求失败");
  return result;
}
function route(view) {
  location.hash = view;
}
function currentView() {
  const v = location.hash.slice(1);
  return ["daily", "trends", "imports"].includes(v) ? v : "daily";
}
function closeSidebar() {
  $("#sidebar").classList.remove("open");
  $("#sidebarShade").classList.remove("open");
}

async function reload({ date, chooseLatest = false } = {}) {
  const token = ++state.request;
  $("#loadingBar").hidden = false;
  error("");
  try {
    let dataset = state.dataset;
    let overview = await api(`/api/overview?dataset=${dataset || "personal"}`);
    if (!dataset) {
      dataset = overview.days.length ? "personal" : "demo";
      if (dataset === "demo")
        overview = await api("/api/overview?dataset=demo");
    }
    if (token !== state.request) return;
    state.dataset = dataset;
    state.overview = overview;
    localStorage.setItem("ai-watch-dataset", dataset);
    state.date =
      date ||
      (chooseLatest ? "" : state.date) ||
      overview.days.at(-1)?.date ||
      localToday();
    const report = await api(`/api/day?dataset=${dataset}&date=${state.date}`);
    if (token !== state.request) return;
    state.day = report;
    state.mood = report.checkin.mood ?? report.metrics.mood;
    render();
    if (overview.migrationWarnings?.length)
      error(
        "部分旧记录未迁移，原文件已保留。" +
          overview.migrationWarnings.slice(0, 3).join("；"),
      );
  } catch (exc) {
    if (token === state.request) error("未能读取记录：" + exc.message);
  } finally {
    if (token === state.request) $("#loadingBar").hidden = true;
  }
}

function render() {
  state.view = currentView();
  const titles = {
    daily: "每日复盘",
    trends: "个人时间线",
    imports: "数据中心",
  };
  const eyebrows = {
    daily: "YOUR DAY, IN PERSPECTIVE",
    trends: "A LIFE, OVER TIME",
    imports: "EVERY RECORD HAS A PLACE",
  };
  $("#breadcrumb").textContent = titles[state.view];
  $("#pageTitle").textContent = titles[state.view];
  $("#pageEyebrow").textContent = eyebrows[state.view];
  $("#pageSubtitle").textContent =
    state.view === "imports"
      ? "记录汇集于此，经历串联成日常。"
      : dateLabel(state.date, {
          year: "numeric",
          month: "long",
          day: "numeric",
          weekday: "long",
        });
  $("#selectedDate").value = state.date;
  $("#dateControls").hidden = state.view === "imports";
  $("#demoBanner").hidden = state.dataset !== "demo";
  $("#datasetSelect").value = state.dataset;
  $$(".nav-item").forEach((b) => {
    b.classList.toggle("active", b.dataset.view === state.view);
    b.setAttribute(
      "aria-current",
      b.dataset.view === state.view ? "page" : "false",
    );
  });
  for (const view of ["daily", "trends", "imports"])
    $(`#${view}View`).hidden = view !== state.view;
  renderProfile();
  $("#footerStats").textContent =
    `${state.overview.days.length} 天 · ${state.overview.eventCount.toLocaleString()} 条记录`;
  if (state.view === "daily") renderDaily();
  if (state.view === "trends") renderTrends();
  if (state.view === "imports") {
    renderQueue();
    loadImports();
  }
  icons();
}

function renderProfile() {
  const p = state.overview.profile,
    days = state.overview.days;
  $("#profilePanel").innerHTML =
    `<div class="profile-top"><div class="avatar" aria-hidden="true">${esc([...p.name][0] || "我")}</div><button id="editProfile" class="icon-button" aria-label="编辑个人档案" title="编辑个人档案">${icon("pencil-line")}</button></div>
    <h2>${esc(p.name)}</h2><div class="role">${esc(p.role || "个人生活档案")}</div>${p.city ? `<div class="location">${icon("map-pin")}${esc(p.city)}</div>` : ""}
    <p class="bio">${esc(p.bio || "关于我的故事，正在慢慢积累。")}</p>
    <div class="profile-stats"><div class="profile-stat"><strong>${days.length}</strong><span>有记录的日子</span></div><div class="profile-stat"><strong>${Object.keys(state.overview.sources).length}</strong><span>数据来源</span></div></div>
    <div class="profile-goal"><h3>${icon("sprout")}近期关注</h3><p>${esc(p.goal || "还没有设定近期关注。")}</p></div>
    <div class="profile-targets"><span>${icon("footprints")}每日 ${fmt(p.stepGoal, "steps")} 步</span><span>${icon("moon")}睡眠 ${fmt(p.sleepGoal, "sleep")} 小时</span></div>`;
  $("#editProfile").onclick = () => {
    const form = $("#profileForm");
    $(".form-error", form).textContent = "";
    for (const name of [
      "name",
      "role",
      "city",
      "bio",
      "goal",
      "stepGoal",
      "sleepGoal",
    ])
      form.elements[name].value = p[name] ?? "";
    $("#profileDialog").showModal();
  };
}

function renderDaily() {
  const d = state.day,
    prev = state.overview.days.filter((x) => x.date < state.date).at(-1);
  const known = new Set(state.overview.days.map((x) => x.date));
  $("#dateStrip").innerHTML = Array.from({ length: 7 }, (_, i) =>
    shift(state.date, i - 6),
  )
    .map(
      (day) =>
        `<button class="date-cell ${day === state.date ? "selected" : ""} ${known.has(day) ? "has-data" : ""}" data-date="${day}" aria-label="${day}" aria-pressed="${day === state.date}"><span>${dateLabel(day, { weekday: "short" })}</span><strong>${Number(day.slice(-2))}</strong></button>`,
    )
    .join("");
  $$("#dateStrip button").forEach(
    (b) => (b.onclick = () => reload({ date: b.dataset.date })),
  );
  $("#metricGrid").innerHTML = ["steps", "sleep", "heart", "focus"]
    .map((key) => {
      const m = metrics[key],
        value = d.metrics[key],
        previous = prev?.metrics[key];
      const delta = value != null && previous != null ? value - previous : null;
      return `<article class="metric-card" style="--metric-color:${m.color}"><div class="metric-heading"><span>${m.label}</span>${icon(m.icon)}</div><div class="metric-number">${fmt(value, key)}<small>${m.unit}</small></div><div class="metric-delta" ${delta != null ? `aria-label="较 ${prev.date} ${delta > 0 ? "增加" : delta < 0 ? "减少" : "持平"} ${fmt(Math.abs(delta), key)} ${m.unit}"` : ""}>${delta != null ? `${icon(delta > 0 ? "arrow-up-right" : delta < 0 ? "arrow-down-right" : "minus")}<b>${fmt(Math.abs(delta), key)}</b><span>较 ${prev.date.slice(5).replace("-", "/")}</span>` : "<span>暂无可比较记录</span>"}</div></article>`;
    })
    .join("");
  $("#reviewTitle").textContent = d.title;
  $("#reviewBody").textContent = d.summary;
  $("#sourceTags").innerHTML = Object.entries(d.sources)
    .map(
      ([key, n]) =>
        `<span>${icon(key.includes("watch") ? "watch" : "file-text")}${esc(sourceName(key))} · ${n}</span>`,
    )
    .join("");
  renderDayChart();
  renderEpisodes();
  renderHighlights();
  renderMoods();
  $("#checkinNote").value = d.checkin.note || "";
  $("#checkinStatus").textContent =
    d.checkin.mood != null || d.checkin.note ? "已保存" : "";
}

function baseChart() {
  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 250 },
    interaction: { mode: "nearest", intersect: false },
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: "#2b4032",
        titleFont: { size: 11 },
        bodyFont: { size: 11 },
        padding: 12,
        displayColors: false,
      },
    },
    scales: {
      x: {
        grid: { display: false },
        border: { display: false },
        ticks: { color: "#98a28e", font: { size: 10 }, maxTicksLimit: 8 },
      },
      y: {
        grid: { color: "#eef1e9" },
        border: { display: false },
        ticks: {
          color: "#98a28e",
          font: { size: 10 },
          maxTicksLimit: 5,
          padding: 10,
        },
      },
    },
  };
}
function renderDayChart() {
  if (state.dayChart) state.dayChart.destroy();
  const heart = state.intraday === "heart";
  let points = state.day.heartSeries;
  if (!heart) points = state.day.stepSeries;
  $("#dayChartEmpty").hidden = points.length > 0;
  $("#chartCaption").textContent =
    `${heart ? "心率 · bpm" : "步数 · 步"}${points.length ? `　${points.length} 个样本` : ""}${!heart && state.day.aggregation?.step_count ? ` · ${sourceName(state.day.aggregation.step_count.source)}` : ""}`;
  $("#dayChart").setAttribute(
    "aria-label",
    `${state.date}${heart ? "心率" : "步数"}，${points.length} 个样本；详情见全部记录`,
  );
  const options = baseChart();
  options.scales.x = {
    ...options.scales.x,
    type: "linear",
    min: 0,
    max: 24,
    ticks: {
      ...options.scales.x.ticks,
      stepSize: 4,
      callback: (v) => String(v).padStart(2, "0") + ":00",
    },
  };
  options.plugins.tooltip.callbacks = {
    title: (items) => {
      const hour = items[0].parsed.x;
      return `${String(Math.floor(hour)).padStart(2, "0")}:${String(Math.round((hour % 1) * 60)).padStart(2, "0")}`;
    },
    label: (c) => `${c.parsed.y} ${heart ? "bpm" : "步"}`,
  };
  if (!heart) options.scales.y.beginAtZero = true;
  state.dayChart = new Chart($("#dayChart"), {
    type: heart ? "line" : "bar",
    data: {
      datasets: [
        {
          data: points,
          borderColor: "#387a5c",
          backgroundColor: heart ? "#32745909" : "#93b49a",
          fill: heart,
          borderWidth: 2,
          pointRadius: 3,
          pointHoverRadius: 5,
          pointBackgroundColor: "#fff",
          pointBorderWidth: 2,
          tension: 0.23,
          spanGaps: false,
          maxBarThickness: 30,
        },
      ],
    },
    options,
  });
}

function renderEpisodes() {
  const query = $("#eventSearch").value.trim().toLowerCase();
  let rows =
    state.timeline === "episodes" ? state.day.episodes : state.day.events;
  rows = rows.filter((r) =>
    `${r.summary} ${r.modality} ${r.source} ${r.raw.value ?? r.raw.bpm ?? ""}`
      .toLowerCase()
      .includes(query),
  );
  $("#episodeCount").textContent = rows.length;
  $("#episodeList").innerHTML = rows.length
    ? rows
        .slice(0, 250)
        .map((row) => {
          const image =
            row.media_type === "image"
              ? `/api/media/${encodeURIComponent(row.media_id)}`
              : row.image === "/assets/park.jpg"
                ? row.image
                : "";
          return `<article class="episode-row"><span class="episode-time">${esc(row.time || row.timestamp.slice(11, 16))}</span><span class="episode-node"></span><button class="episode-button" data-event="${row.id}"><div class="episode-info"><div class="episode-label">${esc(row.label || row.modality)}${row.kind === "plan" ? " · 计划" : ""}</div><h3>${esc(row.summary || `${row.modality} · ${row.raw.bpm ?? row.raw.value ?? "记录"}`)}</h3><div class="episode-meta"><span>${esc(sourceName(row.source))}</span>${row.location ? `<span>${esc(row.location)}</span>` : ""}${row.endTime ? `<span>至 ${esc(row.endTime)}</span>` : ""}${row.media_type ? `<span>${{ audio: "录音", video: "视频", image: "照片" }[row.media_type]} ${icon("paperclip")}</span>` : ""}</div></div>${image ? `<img class="episode-thumb" src="${image}" alt="${esc(row.summary)}" loading="lazy">` : ""}</button></article>`;
        })
        .join("") +
      (rows.length > 250
        ? '<p class="small-muted">显示前 250 条。可搜索更多记录，或导出当天数据。</p>'
        : "")
    : `<div class="empty-state">${icon("notebook-pen")}${query ? "没有匹配的记录" : "这一天还没有生活片段"}</div>`;
  $$("#episodeList [data-event]").forEach(
    (b) => (b.onclick = () => showEvidence([b.dataset.event])),
  );
  icons();
}
function showEvidence(ids) {
  const rows = state.day.events.filter((e) => ids.includes(e.id));
  $("#evidenceBody").innerHTML =
    rows
      .map((row) => {
        let media = "";
        const url =
          row.media_id && /^[a-f0-9]{32}$/.test(row.media_id)
            ? `/api/media/${row.media_id}`
            : "";
        if (url) {
          if (row.media_type === "audio")
            media = `<audio controls preload="metadata" src="${url}"></audio>`;
          if (row.media_type === "video")
            media = `<video class="evidence-media" controls preload="metadata" src="${url}"></video>`;
          if (row.media_type === "image")
            media = `<img class="evidence-media" src="${url}" alt="${esc(row.summary)}">`;
        } else if (
          state.dataset === "demo" &&
          row.raw.image === "/assets/park.jpg"
        )
          media =
            '<img class="evidence-media" src="/assets/park.jpg" alt="示例散步场景">';
        return `<div class="evidence-content"><h3 class="evidence-title">${esc(row.summary || row.modality)}</h3><div class="evidence-meta">${esc(row.timestamp.replace("T", " "))}<br>${esc(sourceName(row.source))} · ${esc(row.modality)}</div>${media}<pre>${esc(JSON.stringify(row.raw, null, 2))}</pre></div>`;
      })
      .join("<hr>") || '<div class="empty-state">暂无关联证据</div>';
  $("#evidenceDialog").showModal();
}

function renderHighlights() {
  $("#highlights").innerHTML = state.day.highlights.length
    ? state.day.highlights
        .map((item, index) => {
          const id = `${state.date}:${item.type}`,
            value = state.day.feedback[id];
          return `<article class="insight"><div class="insight-top">${icon(item.type === "heart" ? "activity" : "leaf")}<h3>${esc(item.title)}</h3></div><p>${esc(item.body)}</p><div class="insight-actions"><button data-feedback="accurate" data-id="${id}" class="${value === "accurate" ? "selected" : ""}" title="这条总结准确">${icon("thumbs-up")}准确</button><button data-feedback="wrong" data-id="${id}" class="${value === "wrong" ? "selected" : ""}" title="这条总结不准确">${icon("thumbs-down")}不准确</button><button class="evidence-button" data-highlight="${index}">证据 ${icon("arrow-up-right")}</button></div></article>`;
        })
        .join("")
    : `<div class="empty-state">${icon("leaf")}暂无足够记录生成观察</div>`;
  $$("#highlights [data-feedback]").forEach(
    (b) =>
      (b.onclick = async () => {
        try {
          await api("/api/feedback", {
            dataset: state.dataset,
            id: b.dataset.id,
            value: b.dataset.feedback,
          });
          state.day.feedback[b.dataset.id] = b.dataset.feedback;
          renderHighlights();
          icons();
          toast("反馈已保存");
        } catch (e) {
          toast(e.message);
        }
      }),
  );
  $$("#highlights [data-highlight]").forEach(
    (b) =>
      (b.onclick = () =>
        showEvidence(
          state.day.highlights[Number(b.dataset.highlight)].evidence,
        )),
  );
}
function renderMoods() {
  $("#moodOptions").innerHTML = moodNames
    .map(
      (name, i) =>
        `<button class="mood-button ${state.mood === i + 1 ? "selected" : ""}" data-mood="${i + 1}" aria-label="状态自评：${name}" aria-pressed="${state.mood === i + 1}" title="${name} · ${i + 1}/5">${icon(moodIcons[i])}</button>`,
    )
    .join("");
  $$("#moodOptions button").forEach(
    (b) =>
      (b.onclick = () => {
        state.mood = Number(b.dataset.mood);
        renderMoods();
        icons();
        $("#checkinStatus").textContent = "未保存";
      }),
  );
}

function trendDays() {
  const start = shift(state.date, -state.range + 1);
  return state.overview.days.filter(
    (d) => d.date >= start && d.date <= state.date,
  );
}
function renderTrends() {
  const key = state.trendMetric,
    m = metrics[key];
  $("#trendMetrics").innerHTML = Object.entries(metrics)
    .map(
      ([k, info]) =>
        `<button style="--metric-color:${info.color}" class="${k === key ? "selected" : ""}" data-metric="${k}" aria-pressed="${k === key}"><i></i>${info.label}</button>`,
    )
    .join("");
  $$("#trendMetrics button").forEach(
    (b) =>
      (b.onclick = () => {
        state.trendMetric = b.dataset.metric;
        renderTrends();
        icons();
      }),
  );
  const available = trendDays(),
    byDate = new Map(available.map((d) => [d.date, d]));
  const dates = Array.from({ length: state.range }, (_, i) =>
    shift(state.date, i - state.range + 1),
  );
  const values = dates.map((d) => byDate.get(d)?.metrics[key] ?? null),
    valid = values.filter((v) => v != null);
  $("#trendLabel").textContent = m.label;
  $("#trendValue").innerHTML =
    `${fmt(state.day.metrics[key], key)}<small>${m.unit} · 当天</small>`;
  $("#trendComparison").innerHTML =
    `近 ${state.range} 天平均<br><strong>${fmt(valid.length ? valid.reduce((s, v) => s + v, 0) / valid.length : null, key)}</strong> ${m.unit}`;
  $("#trendLegend").textContent = m.label;
  $(".chart-legend b").style.background = m.color;
  $("#trendChartEmpty").hidden = valid.length > 0;
  $("#trendChart").setAttribute(
    "aria-label",
    `近${state.range}天${m.label}趋势，有${valid.length}天数据；每天的数值与经历列于下方`,
  );
  const options = baseChart();
  if (["steps", "energy", "focus"].includes(key))
    options.scales.y.beginAtZero = true;
  if (key === "mood") {
    options.scales.y.min = 1;
    options.scales.y.max = 5;
    options.scales.y.ticks.stepSize = 1;
  }
  options.plugins.tooltip.callbacks = {
    title: (items) => dates[items[0].dataIndex],
    label: (c) => `${fmt(c.parsed.y, key)} ${m.unit}`,
    afterBody: (items) =>
      byDate
        .get(dates[items[0].dataIndex])
        ?.keywords?.slice(0, 3)
        .join(" · ") || "",
  };
  options.onClick = (_event, active) => {
    if (active.length) {
      const day = dates[active[0].index];
      state.date = day;
      route("daily");
      reload({ date: day });
    }
  };
  if (state.trendChart) state.trendChart.destroy();
  state.trendChart = new Chart($("#trendChart"), {
    type: "line",
    data: {
      labels: dates.map((d) => d.slice(5).replace("-", "/")),
      datasets: [
        {
          data: values,
          borderColor: m.color,
          backgroundColor: m.color + "0b",
          fill: true,
          borderWidth: 2,
          pointRadius: state.range > 30 ? 2 : 4,
          pointBackgroundColor: "#fff",
          pointHoverRadius: 6,
          pointBorderWidth: 2,
          tension: 0.2,
          spanGaps: false,
        },
      ],
    },
    options,
  });
  $("#historyCount").textContent = `${available.length} 个有记录的日子`;
  $("#dayHistory").innerHTML = available.length
    ? [...available]
        .reverse()
        .map(
          (day) =>
            `<button class="history-row" data-date="${day.date}" aria-label="打开 ${day.date} 每日复盘"><div class="history-date">${day.date.slice(5).replace("-", " / ")}<small>${dateLabel(day.date, { weekday: "long" })}</small></div><div><h3>${esc(day.title)}</h3><p>${esc(day.summary)}</p>${day.reflection ? `<p class="history-reflection">${esc(day.reflection)}</p>` : ""}<div class="history-metrics"><span>${m.label} ${fmt(day.metrics[key], key)} ${m.unit}</span><span>${day.eventCount} 条记录</span>${day.metrics.mood != null ? `<span>自评 ${fmt(day.metrics.mood, "mood")} / 5</span>` : ""}</div></div>${icon("arrow-up-right")}</button>`,
        )
        .join("")
    : `<div class="empty-state">${icon("calendar-search")}这个时间范围还没有记录</div>`;
  $$("#dayHistory button").forEach(
    (b) =>
      (b.onclick = () => {
        state.date = b.dataset.date;
        route("daily");
        reload({ date: b.dataset.date });
      }),
  );
  icons();
}

function isMedia(file) {
  return /\.(m4a|mp3|wav|ogg|flac|aac|mp4|mov|jpe?g|png|webp)$/i.test(
    file.name,
  );
}
function fileSize(size) {
  return size >= 1048576
    ? (size / 1048576).toFixed(1) + " MB"
    : (size / 1024).toFixed(1) + " KB";
}
function queueFiles(files) {
  for (const file of files) {
    if (
      state.queue.some(
        (q) =>
          q.file.name === file.name &&
          q.file.size === file.size &&
          q.status !== "failed",
      )
    )
      continue;
    const match = file.name.match(
      /(\d{4}-\d{2}-\d{2})[ _T](\d{2})[-_:](\d{2})/,
    );
    state.queue.push({
      id: crypto.randomUUID(),
      file,
      status: "waiting",
      progress: 0,
      message: "等待同步",
      start: match ? `${match[1]}T${match[2]}:${match[3]}` : "",
      summary: "",
    });
  }
  $("#fileInput").value = "";
  renderQueue();
}
function renderQueue() {
  $("#uploadQueue").innerHTML = state.queue
    .map(
      (q) =>
        `<div class="queue-row"><div class="queue-top"><div class="file-icon">${icon(isMedia(q.file) ? "file-image" : "file-text")}</div><div class="file-details"><div class="file-name">${esc(q.file.name)}</div><small>${fileSize(q.file.size)}</small></div><span class="queue-status ${q.status}">${esc(q.message)}</span><button class="icon-button" data-remove="${q.id}" aria-label="移除 ${esc(q.file.name)}" title="移除文件" ${state.uploading ? "disabled" : ""}>${icon("x")}</button></div>${isMedia(q.file) ? `<div class="queue-inputs"><label>录制 / 拍摄开始时间<input type="datetime-local" data-start="${q.id}" value="${esc(q.start)}" ${state.uploading || q.status === "success" ? "disabled" : ""}></label><label>场景备注（可选）<input data-summary="${q.id}" value="${esc(q.summary)}" maxlength="4000" ${state.uploading || q.status === "success" ? "disabled" : ""}></label></div>` : ""}<div class="queue-progress"><span style="width:${q.progress}%"></span></div></div>`,
    )
    .join("");
  $("#queueFooter").hidden = !state.queue.length;
  $("#queueSummary").textContent =
    `${state.queue.filter((q) => q.status === "success").length} / ${state.queue.length} 个文件已同步`;
  const pending = state.queue.filter((q) => q.status !== "success");
  $("#startUpload").disabled = state.uploading || !pending.length;
  $("#startUpload").innerHTML =
    icon(state.uploading ? "loader-circle" : "folder-sync") +
    (state.uploading
      ? "正在同步…"
      : pending.some((q) => q.status === "failed")
        ? "重试未完成文件"
        : "同步记录");
  $$("#uploadQueue [data-remove]").forEach(
    (b) =>
      (b.onclick = () => {
        state.queue = state.queue.filter((q) => q.id !== b.dataset.remove);
        renderQueue();
      }),
  );
  $$("#uploadQueue [data-start]").forEach(
    (i) =>
      (i.oninput = () => {
        state.queue.find((q) => q.id === i.dataset.start).start = i.value;
      }),
  );
  $$("#uploadQueue [data-summary]").forEach(
    (i) =>
      (i.oninput = () => {
        state.queue.find((q) => q.id === i.dataset.summary).summary = i.value;
      }),
  );
  icons();
}
function sendFile(q) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/upload");
    xhr.setRequestHeader("X-Filename", encodeURIComponent(q.file.name));
    if (q.start)
      xhr.setRequestHeader(
        "X-Start",
        encodeURIComponent(q.start + ":00+08:00"),
      );
    if (q.summary)
      xhr.setRequestHeader("X-Summary", encodeURIComponent(q.summary));
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) {
        q.progress = Math.round((e.loaded / e.total) * 100);
        q.message =
          q.progress === 100 ? "解析与同步中…" : `上传中 ${q.progress}%`;
        renderQueue();
      }
    };
    xhr.onload = () => {
      try {
        const data = JSON.parse(xhr.responseText);
        if (xhr.status >= 400) reject(new Error(data.error || "上传失败"));
        else resolve(data);
      } catch {
        reject(new Error("服务未返回有效响应"));
      }
    };
    xhr.onerror = () => reject(new Error("连接中断，可重试此文件"));
    xhr.send(q.file);
  });
}
async function startUpload() {
  state.uploading = true;
  renderQueue();
  let latest = "";
  let added = 0;
  for (const q of state.queue.filter((q) => q.status !== "success")) {
    try {
      if (isMedia(q.file) && !q.start)
        throw new Error("请填写这段素材的开始时间");
      q.status = "uploading";
      q.message = "上传中…";
      renderQueue();
      const result = await sendFile(q);
      q.status = "success";
      q.progress = 100;
      q.message = result.duplicate
        ? "已存在，未重复导入"
        : `已同步 ${result.added} 条`;
      latest = [latest, ...result.dates].sort().at(-1);
      added += result.added;
    } catch (exc) {
      q.status = "failed";
      q.message = exc.message;
    }
    renderQueue();
  }
  state.uploading = false;
  if (latest) {
    state.dataset = "personal";
    await reload({ date: latest });
  }
  renderQueue();
  await loadImports();
  toast(added ? `已同步 ${added} 条记录` : "同步处理完成");
}
async function loadImports() {
  try {
    const { imports } = await api("/api/imports");
    $("#importHistory").innerHTML = imports.length
      ? `<div class="table-wrap"><table><thead><tr><th>文件</th><th>类型</th><th>新增记录</th><th>记录日期</th><th>同步时间</th></tr></thead><tbody>${imports
          .map((r) => {
            const dates = JSON.parse(r.dates);
            return `<tr><td>${esc(r.name)}<br><small>${fileSize(r.size)}</small></td><td>${{ health: "Apple 健康", records: "结构化记录", audio: "录音", video: "视频", image: "照片" }[r.kind] || r.kind}</td><td>${r.count}</td><td><button class="table-date" data-import-date="${dates[0]}">${dates[0]}${dates.length > 1 ? ` 等 ${dates.length} 天` : ""}</button></td><td>${esc(r.created.slice(5, 16).replace("T", " "))}</td></tr>`;
          })
          .join("")}</tbody></table></div>`
      : `<div class="empty-state">${icon("folder-open")}还没有个人文件的同步记录</div>`;
    $$("[data-import-date]").forEach(
      (b) =>
        (b.onclick = () => {
          state.dataset = "personal";
          state.date = b.dataset.importDate;
          route("daily");
          reload({ date: b.dataset.importDate });
        }),
    );
    icons();
  } catch (exc) {
    $("#importHistory").textContent = exc.message;
  }
}

$$("[data-view]").forEach(
  (b) =>
    (b.onclick = () => {
      closeSidebar();
      route(b.dataset.view);
    }),
);
window.addEventListener("hashchange", () => {
  if (state.day) render();
});
$("#datasetSelect").onchange = (e) => {
  state.dataset = e.target.value;
  closeSidebar();
  reload({ chooseLatest: true });
};
$("#usePersonal").onclick = () => {
  state.dataset = "personal";
  reload({ chooseLatest: true });
};
$("#uploadButton").onclick = () => {
  route("imports");
  if (state.day) render();
};
$("#menuButton").onclick = () => {
  $("#sidebar").classList.toggle("open");
  $("#sidebarShade").classList.toggle("open");
};
$("#sidebarShade").onclick = closeSidebar;
$("#selectedDate").onchange = (e) => {
  if (e.target.value) reload({ date: e.target.value });
};
$("#previousDay").onclick = () => reload({ date: shift(state.date, -1) });
$("#nextDay").onclick = () => reload({ date: shift(state.date, 1) });
$("#todayButton").onclick = () => reload({ date: localToday() });
$("#refreshDay").onclick = async () => {
  await reload();
  toast("总结已更新");
};
$("#exportDay").onclick = () => {
  const a = document.createElement("a");
  a.href = `/api/export?dataset=${state.dataset}&date=${state.date}`;
  a.download = `ai-watch-${state.dataset}-${state.date}.json`;
  a.click();
};
$$("#intradayMode button").forEach(
  (b) =>
    (b.onclick = () => {
      state.intraday = b.dataset.mode;
      $$("#intradayMode button").forEach((x) =>
        x.classList.toggle("selected", x === b),
      );
      renderDayChart();
    }),
);
$$("#timelineMode button").forEach(
  (b) =>
    (b.onclick = () => {
      state.timeline = b.dataset.mode;
      $$("#timelineMode button").forEach((x) =>
        x.classList.toggle("selected", x === b),
      );
      renderEpisodes();
    }),
);
$("#eventSearch").oninput = renderEpisodes;
$("#checkinNote").oninput = () => ($("#checkinStatus").textContent = "未保存");
$("#saveCheckin").onclick = async () => {
  const button = $("#saveCheckin");
  button.disabled = true;
  try {
    await api("/api/checkin", {
      dataset: state.dataset,
      date: state.date,
      mood: state.mood,
      note: $("#checkinNote").value,
    });
    await reload();
    toast("今天的感受已保存");
  } catch (e) {
    toast(e.message);
  } finally {
    button.disabled = false;
  }
};
$("#trendRange").onchange = (e) => {
  state.range = Number(e.target.value);
  renderTrends();
};
$$("[data-close]").forEach(
  (b) => (b.onclick = () => document.getElementById(b.dataset.close).close()),
);
$("#evidenceDialog").addEventListener("close", () => {
  $$("#evidenceDialog audio, #evidenceDialog video").forEach((m) => m.pause());
});
$("#profileForm").onsubmit = async (e) => {
  e.preventDefault();
  const form = e.target,
    button = $("[type=submit]", form);
  button.disabled = true;
  try {
    await api("/api/profile", {
      dataset: state.dataset,
      ...Object.fromEntries(new FormData(form)),
    });
    $("#profileDialog").close();
    await reload();
    toast("档案已保存");
  } catch (exc) {
    $(".form-error", form).textContent = exc.message;
  } finally {
    button.disabled = false;
  }
};
$("#addNote").onclick = () => {
  const f = $("#noteForm");
  f.reset();
  f.elements.start.value = state.date + "T09:00";
  $(".form-error", f).textContent = "";
  $("#noteDialog").showModal();
};
$("#noteForm").onsubmit = async (e) => {
  e.preventDefault();
  const form = e.target,
    data = Object.fromEntries(new FormData(form)),
    button = $("[type=submit]", form);
  button.disabled = true;
  try {
    const row = await api("/api/note", {
      dataset: state.dataset,
      text: data.text,
      activity: data.activity,
      location: data.location,
      timestamp: data.start + ":00+08:00",
      end_timestamp: data.end ? data.end + ":00+08:00" : null,
    });
    $("#noteDialog").close();
    await reload({ date: row.timestamp.slice(0, 10) });
    toast("经历已加入时间线");
  } catch (exc) {
    $(".form-error", form).textContent = exc.message;
  } finally {
    button.disabled = false;
  }
};
$("#chooseFiles").onclick = () => $("#fileInput").click();
$("#fileInput").onchange = (e) => queueFiles(e.target.files);
$("#startUpload").onclick = startUpload;
$("#refreshImports").onclick = loadImports;
for (const event of ["dragenter", "dragover"])
  $("#dropzone").addEventListener(event, (e) => {
    e.preventDefault();
    $("#dropzone").classList.add("dragover");
  });
$("#dropzone").addEventListener("dragleave", (e) => {
  if (!$("#dropzone").contains(e.relatedTarget))
    $("#dropzone").classList.remove("dragover");
});
$("#dropzone").addEventListener("drop", (e) => {
  e.preventDefault();
  $("#dropzone").classList.remove("dragover");
  queueFiles(e.dataTransfer.files);
});
document.addEventListener("dragover", (e) => e.preventDefault());
document.addEventListener("drop", (e) => e.preventDefault());
Chart.defaults.font.family = '"Segoe UI", "Microsoft YaHei", sans-serif';
Chart.defaults.color = "#8e9c84";
icons();
reload();
