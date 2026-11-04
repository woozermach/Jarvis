/* J.A.R.V.I.S. HUD */
"use strict";
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const S = {
  state: "boot", detail: "", lvlIn: 0, lvlOut: 0, wake: 0, thr: 0.45,
  settings: null, store: { timers: [], tasks: [], notes: [], memory: [] },
  msgs: new Map(), mic: true, booted: false, ws: null, wsOk: false,
};

const STATE_TEXT = {
  boot: ["ЗАГРУЗКА", "Инициализация систем…"],
  idle: ["ОЖИДАНИЕ", "Скажите «Эй, Джарвис» · Ctrl+Alt+J · или нажмите на ядро"],
  connecting: ["ПОДКЛЮЧЕНИЕ", "Связь с нейросетью…"],
  listening: ["СЛУШАЮ", "Говорите — я слушаю"],
  thinking: ["ДУМАЮ", ""],
  speaking: ["ГОВОРЮ", "Скажите «Эй, Джарвис», чтобы перебить"],
  error: ["ОШИБКА", ""],
  nokey: ["НУЖЕН КЛЮЧ", "Откройте настройки ⚙ и вставьте ключ Gemini"],
  offline: ["НЕТ СВЯЗИ", "Переподключаюсь к ядру…"],
};
const TOOL_NAMES = {
  open_app: "запуск", close_app: "закрытие", switch_window: "окно", window_action: "окна", list_windows: "окна",
  press_keys: "клавиши", type_text: "ввод текста", clipboard: "буфер", open_website: "сайт", web_search: "поиск",
  search_internet: "поиск в интернете", youtube: "YouTube", media_control: "медиа", volume: "громкость",
  brightness: "яркость", take_screenshot: "скриншот", look_at_screen: "смотрю на экран", find_file: "поиск файла",
  get_weather: "погода", exchange_rate: "курс валют", system_status: "диагностика", set_timer: "таймер",
  set_reminder: "напоминание", list_timers: "таймеры", cancel_timer: "таймеры", tasks: "задачи", notes: "заметки",
  memory: "память", display: "вывод", calculate: "вычисление", now: "время", power: "питание",
  empty_recycle_bin: "корзина", set_preference: "настройки", end_conversation: "завершение",
  close_display: "закрываю окно", hud_window: "окно Джарвиса", click_on_screen: "клик", scroll: "прокрутка",
  routine_save: "создаю режим", routine_run: "режим", routine_list: "режимы", routine_delete: "режимы",
  quiet_mode: "тихий режим", watch_screen: "вижу экран", game_clip: "клип", discord: "Discord",
  send_screen_photo: "фото экрана", wait: "пауза",
};
const STEP_TPL = {
  open_app: { name: "" }, close_app: { name: "" }, open_website: { site: "" }, youtube: { query: "", mode: "play" },
  volume: { action: "set", level: 40 }, brightness: { level: 70 }, media_control: { action: "play_pause" },
  quiet_mode: { minutes: 60 }, wait: { seconds: 2 }, window_action: { action: "show_desktop" }, press_keys: { keys: "" },
  type_text: { text: "" }, set_timer: { seconds: 1500, label: "" }, discord: { action: "mute" }, switch_window: { title: "" },
  get_weather: {}, tasks: { action: "list" }, search_internet: { query: "" }, game_clip: {}, system_status: {},
};

/* ───────────── WebSocket ───────────── */
function connect() {
  const ws = new WebSocket(`ws://${location.host}/ws`);
  S.ws = ws;
  ws.onopen = () => { S.wsOk = true; };
  ws.onclose = () => {
    S.wsOk = false;
    setState("offline");
    setTimeout(connect, 1500);
  };
  ws.onmessage = (e) => {
    let m; try { m = JSON.parse(e.data); } catch { return; }
    handle(m);
  };
}
function send(obj) { if (S.ws && S.ws.readyState === 1) S.ws.send(JSON.stringify(obj)); }

function handle(m) {
  switch (m.t) {
    case "snapshot":
      applySettings(m.settings); renderStore(m.store); if (m.weather) renderWeather(m.weather);
      $("#chat").innerHTML = ""; S.msgs.clear();
      (m.history || []).slice(-12).forEach((h) => addMsg(h.r === "user" ? "user" : "jarvis", h.t, null, true, true));
      setState(m.state, m.detail);
      boot(m.boot < 4);
      break;
    case "state": setState(m.state, m.detail); break;
    case "lvl": S.lvlIn = m.i; S.lvlOut = m.o; S.wake = m.w; meters(); break;
    case "msg": addMsg(m.role, m.text, m.id, m.final); break;
    case "tool": toolChip(m.name, m.args); break;
    case "toast": toast(m.text); break;
    case "card": showCard(m.title, m.content, m.autoclose); break;
    case "close": closeOverlays(m.what); break;
    case "stats": renderStats(m.data); break;
    case "weather": renderWeather(m.data); break;
    case "store": renderStore(m.data); break;
    case "settings": applySettings(m.data); break;
    case "mic": S.mic = m.on; $("#micBtn").classList.toggle("off", !m.on); break;
    case "watch": $("#fWatch").classList.toggle("hidden", !m.on); break;
    case "update": renderUpdate(m.data); break;
    case "update_progress": toast("⬆ " + m.text); $("#updState").textContent = m.text; break;
    case "alert": showAlert(m.title, m.text); break;
    case "shutdown": shutdownBanner(m.seconds, m.action); break;
    case "capture": document.body.style.visibility = m.hide ? "hidden" : ""; break;
    case "find_app":
      if (m.q) $("#appTestRes").textContent = m.found ? `→ откроется «${m.found}» (уверенность ${Math.round(m.score * 100)}%)` : "→ не найдено. Добавьте программу в таблицу выше.";
      break;
    case "selftest": {
      const o = $("#dOut");
      if (m.start) o.textContent = "";
      o.textContent += m.line + "\n"; o.scrollTop = 1e9; break;
    }
  }
}

/* ───────────── состояние ───────────── */
function setState(st, detail) {
  S.state = st; S.detail = detail || "";
  document.body.dataset.state = st;
  const [t, hint] = STATE_TEXT[st] || [st.toUpperCase(), ""];
  $("#stateText").textContent = t;
  let h = hint;
  if (st === "thinking" && detail) h = "⚙ " + detail.split(", ").map((n) => TOOL_NAMES[n] || n).join(" · ");
  if (st === "error") h = detail || "Что-то пошло не так";
  $("#stateHint").textContent = h;
  $("#chipText").textContent = { idle: "ОНЛАЙН", listening: "АКТИВЕН", speaking: "АКТИВЕН", thinking: "РАБОТАЮ", connecting: "СВЯЗЬ",
    error: "ОШИБКА", nokey: "НЕТ КЛЮЧА", offline: "НЕТ СВЯЗИ", boot: "ЗАГРУЗКА" }[st] || st;
}

/* ───────────── чат ───────────── */
function addMsg(role, text, id, final, silent) {
  const chat = $("#chat");
  let el = id ? S.msgs.get(id) : null;
  if (!el) {
    el = document.createElement("div");
    el.className = "msg " + role;
    chat.appendChild(el);
    if (id) S.msgs.set(id, el);
    while (chat.children.length > 60) chat.removeChild(chat.firstChild);
  }
  el.textContent = text;
  el.classList.toggle("live", !final);
  if (final && id) S.msgs.delete(id);
  chat.scrollTop = chat.scrollHeight;
}
function toolChip(name, args) {
  const el = document.createElement("div");
  el.className = "tool";
  const a = Object.entries(args || {}).filter(([k]) => k !== "confirmed").map(([k, v]) => String(v).slice(0, 40)).join(", ");
  el.textContent = `⚙ ${TOOL_NAMES[name] || name}${a ? " · " + a : ""}`;
  $("#chat").appendChild(el);
  $("#chat").scrollTop = 1e9;
}

/* ───────────── тосты, карточки, алерты ───────────── */
function toast(text) {
  const el = document.createElement("div");
  el.className = "toast"; el.textContent = text;
  $("#toasts").appendChild(el);
  setTimeout(() => { el.classList.add("out"); setTimeout(() => el.remove(), 500); }, 4200);
}
function md(src) {
  let s = esc(src);
  const blocks = [];
  s = s.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, l, c) => { blocks.push(`<pre><code>${c}</code></pre>`); return `\u0000${blocks.length - 1}\u0000`; });
  s = s.replace(/^### (.*)$/gm, "<h3>$1</h3>").replace(/^## (.*)$/gm, "<h2>$1</h2>").replace(/^# (.*)$/gm, "<h1>$1</h1>");
  s = s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/`([^`]+)`/g, "<code>$1</code>");
  s = s.replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank">$1</a>');
  s = s.replace(/^(?:\s*[-*•] .*(?:\n|$))+/gm, (blk) => "<ul>" + blk.trim().split("\n").map((l) => `<li>${l.replace(/^\s*[-*•] /, "")}</li>`).join("") + "</ul>");
  s = s.replace(/^(?:\s*\d+[.)] .*(?:\n|$))+/gm, (blk) => "<ol>" + blk.trim().split("\n").map((l) => `<li>${l.replace(/^\s*\d+[.)] /, "")}</li>`).join("") + "</ol>");
  s = s.split(/\n{2,}/).map((p) => /^<(h\d|ul|ol|pre)/.test(p.trim()) || p.includes("\u0000") ? p : `<p>${p.replace(/\n/g, "<br>")}</p>`).join("");
  return s.replace(/\u0000(\d+)\u0000/g, (_, i) => blocks[+i]);
}
let cardRaw = "", cardTimer = null;
function showCard(title, content, autoclose) {
  cardRaw = content;
  $("#cardTitle").textContent = title; $("#cardBody").innerHTML = md(content);
  $("#card").classList.remove("hidden");
  clearTimeout(cardTimer);
  if (autoclose > 0) cardTimer = setTimeout(() => closeCard(), autoclose * 1000);
}
function closeCard() {
  clearTimeout(cardTimer);
  if (!$("#card").classList.contains("hidden")) { $("#card").classList.add("hidden"); send({ t: "card_closed" }); }
}
function closeOverlays(what) {
  if (what === "card" || what === "all") closeCard();
  if (what === "alert" || what === "all") $("#alert").classList.add("hidden");
  if (what === "settings" || what === "all") { if (!$("#settings").classList.contains("hidden")) $("#setClose").click(); }
}
$("#cardClose").onclick = () => closeCard();
$("#card").onclick = (e) => { if (e.target.id === "card") closeCard(); };
$("#cardCopy").onclick = () => { navigator.clipboard.writeText(cardRaw).then(() => toast("Скопировано")); };
function showAlert(kind, text) {
  $("#alertKind").textContent = kind.toUpperCase(); $("#alertText").textContent = text;
  $("#alert").classList.remove("hidden");
}
$("#alertOk").onclick = () => $("#alert").classList.add("hidden");
let sdTimer = null;
function shutdownBanner(sec, action) {
  clearInterval(sdTimer);
  if (!sec) { $("#shutdown").classList.add("hidden"); return; }
  let left = sec;
  const word = action === "restart" ? "Перезагрузка" : "Выключение";
  const tick = () => { $("#sdText").textContent = `${word} компьютера через ${left} с`; if (left-- <= 0) clearInterval(sdTimer); };
  tick(); sdTimer = setInterval(tick, 1000);
  $("#shutdown").classList.remove("hidden");
}
$("#sdCancel").onclick = () => { send({ t: "cancel_shutdown" }); shutdownBanner(0); };

/* ───────────── система ───────────── */
function gauge(k, v) {
  const g = document.querySelector(`.gauge[data-k=${k}]`);
  if (!g) return;
  v = Math.max(0, Math.min(100, v ?? 0));
  g.querySelector(".val").style.strokeDashoffset = 251.3 * (1 - v / 100);
  g.querySelector("b").textContent = Math.round(v);
  g.classList.toggle("hot", v >= 75 && v < 92); g.classList.toggle("crit", v >= 92);
}
const fmtRate = (b) => b > 1048576 ? (b / 1048576).toFixed(1) + " МБ/с" : Math.round(b / 1024) + " КБ/с";
function fmtUp(s) { const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60); return (d ? d + "д " : "") + h + "ч " + m + "м"; }
function renderStats(d) {
  const gs = d.gaming_since;
  $("#fGame").classList.toggle("hidden", !gs);
  if (gs) { const mn = Math.floor((Date.now() / 1000 - gs) / 60); $("#fGameT").textContent = mn >= 60 ? `${Math.floor(mn / 60)} ч ${mn % 60} мин` : `${mn} мин`; }
  gauge("cpu", d.cpu); gauge("ram", d.ram); gauge("gpu", d.gpu ? d.gpu.util : 0);
  $("#gpuName").textContent = d.gpu ? d.gpu.name : "";
  $("#gpuTemp").textContent = d.gpu ? Math.round(d.gpu.temp) + " °C" : "—";
  $("#vram").textContent = d.gpu ? (d.gpu.mem_used / 1024).toFixed(1) + " / " + (d.gpu.mem_total / 1024).toFixed(0) + " ГБ" : "—";
  $("#ramAbs").textContent = d.ram_used ? `${d.ram_used} / ${d.ram_total} ГБ` : "—";
  if (d.battery != null) {
    $("#bat").textContent = d.battery + "%" + (d.plugged ? " ⚡" : "");
    $("#batBar").style.width = d.battery + "%";
  } else $("#bat").textContent = "сеть";
  $("#disk").textContent = d.disk_free != null ? d.disk_free + " ГБ" : "—";
  $("#net").textContent = d.down != null ? `${fmtRate(d.down)} / ${fmtRate(d.up)}` : "—";
  $("#uptime").textContent = d.uptime ? fmtUp(d.uptime) : "—";
}
function meters() {
  $("#inBar").style.width = Math.min(100, S.lvlIn * 160) + "%";
  $("#outBar").style.width = Math.min(100, S.lvlOut * 140) + "%";
  $("#wakeBar").style.width = Math.min(100, S.wake * 100) + "%";
  if (!$("#settings").classList.contains("hidden")) {
    $("#setInBar").style.width = Math.min(100, S.lvlIn * 160) + "%";
    $("#setWakeBar").style.width = Math.min(100, S.wake * 100) + "%";
  }
}

/* ───────────── погода ───────────── */
const ICONS = {
  sun: '<circle cx="32" cy="32" r="11"/><path d="M32 8v6M32 50v6M8 32h6M50 32h6M15 15l4 4M45 45l4 4M15 49l4-4M45 19l4-4"/>',
  "cloud-sun": '<circle cx="24" cy="24" r="8"/><path d="M24 8v4M10 24H6M13 13l3 3M35 13l-3 3"/><path d="M22 48h24a9 9 0 0 0 0-18 13 13 0 0 0-24 4 7 7 0 0 0 0 14z"/>',
  cloud: '<path d="M18 46h28a10 10 0 0 0 0-20 14 14 0 0 0-27 4 8 8 0 0 0-1 16z"/>',
  rain: '<path d="M18 38h28a10 10 0 0 0 0-20 14 14 0 0 0-27 4 8 8 0 0 0-1 16z"/><path d="M22 44l-3 8M32 44l-3 8M42 44l-3 8"/>',
  snow: '<path d="M18 36h28a10 10 0 0 0 0-20 14 14 0 0 0-27 4 8 8 0 0 0-1 16z"/><path d="M22 44v8M18 48h8M36 44v8M32 48h8"/>',
  storm: '<path d="M18 36h28a10 10 0 0 0 0-20 14 14 0 0 0-27 4 8 8 0 0 0-1 16z"/><path d="M33 38l-6 10h8l-5 9"/>',
  fog: '<path d="M12 26h40M8 34h44M14 42h36M20 50h24"/>',
};
const ico = (k) => `<svg viewBox="0 0 64 64">${ICONS[k] || ICONS.cloud}</svg>`;
const DOW = ["ВС", "ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ"];
const sgn = (t) => (t > 0 ? "+" : "") + t + "°";
function renderWeather(w) {
  if (!w || !w.now) return;
  $("#wxCity").textContent = w.city;
  $("#wxIco").innerHTML = ico(w.now.icon);
  $("#wxTemp").textContent = sgn(w.now.temp);
  $("#wxDesc").textContent = w.now.desc;
  $("#wxFeels").textContent = sgn(w.now.feels);
  $("#wxWind").textContent = `${w.now.wind} м/с · ${w.now.humidity ?? "—"}%`;
  $("#wxSun").textContent = `${w.sunrise} · ${w.sunset}`;
  $("#wxDays").innerHTML = (w.days || []).slice(1, 4).map((d) => {
    const dd = new Date(d.date + "T12:00");
    return `<div class="wx-day"><small>${DOW[dd.getDay()]}</small>${ico(d.icon)}<b>${sgn(d.max)}</b> <i>${sgn(d.min)}</i></div>`;
  }).join("");
}

/* ───────────── таймеры и задачи ───────────── */
function renderStore(st) {
  if (!st) return;
  S.store = st;
  renderTimers();
  const tasks = st.tasks || [];
  $("#taskCount").textContent = tasks.length ? `${tasks.filter((t) => !t.done).length} из ${tasks.length}` : "";
  $("#tasks").innerHTML = tasks.length ? tasks.map((t) => `<div class="task ${t.done ? "done" : ""}" data-id="${t.id}">
     <input type="checkbox" ${t.done ? "checked" : ""}><span>${esc(t.text)}</span><button class="x" title="Удалить">✕</button></div>`).join("")
    : '<div class="empty">Скажите: «добавь задачу купить продукты»</div>';
  const mem = st.memory || [];
  $("#memList").innerHTML = mem.length ? mem.map((m) => `<div class="mem" data-id="${m.id}"><input value="${esc(m.fact)}"><button class="x">✕</button></div>`).join("")
    : '<div class="empty">Пока пусто. Скажите: «запомни, что у меня пары по вторникам»</div>';
  renderRoutines(st.routines || []);
  renderQuiet(st.quiet_until || 0);
  const notes = (st.notes || []).slice().reverse();
  $("#noteList").innerHTML = notes.length ? notes.slice(0, 50).map((n) => `<div class="mem" data-id="${n.id}"><span>${esc(n.text)}</span><small>${new Date(n.created * 1000).toLocaleDateString("ru")}</small><button class="x">✕</button></div>`).join("")
    : '<div class="empty">Заметок нет. Скажите: «запиши заметку…»</div>';
}
function stepText(x) {
  const vals = Object.values(x.args || {}).filter((v) => v !== "" && v !== null && v !== false).join(", ");
  return (TOOL_NAMES[x.tool] || x.tool) + (vals ? ": " + vals : "");
}
function renderRoutines(rs) {
  $("#routineList").innerHTML = rs.length ? rs.map((r) => `<div class="rt" data-id="${r.id}"><div class="rt-body"><b>${esc(r.name)}</b>
     ${r.description ? `<small>${esc(r.description)}</small>` : ""}<ol>${r.steps.map((x) => `<li>${esc(stepText(x))}</li>`).join("")}</ol></div>
     <div class="hrow"><button class="btn" data-act="run">▶ запустить</button><button class="btn danger" data-act="del">✕</button></div></div>`).join("")
    : '<div class="empty">Режимов пока нет. Скажите: «создай режим учёбы: закрой стим, открой тимс, тихий режим на 2 часа»</div>';
}
$("#routineList").onclick = (e) => {
  const b = e.target.closest("button"), row = e.target.closest(".rt"); if (!b || !row) return;
  if (b.dataset.act === "run") send({ t: "routine_run", id: row.dataset.id });
  if (b.dataset.act === "del" && confirm("Удалить режим?")) send({ t: "routine_delete", id: row.dataset.id });
};
function renderQuiet(until) {
  const on = until > Date.now() / 1000;
  const hm = on ? new Date(until * 1000).toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit" }) : "";
  $("#fQuiet").classList.toggle("hidden", !on); $("#fQuietT").textContent = on ? "ДО " + hm : "";
  $("#quietInfo").textContent = on ? `включён до ${hm}` : "выключен";
}
setInterval(() => renderQuiet(S.store.quiet_until || 0), 30000);
$("#fQuiet").onclick = () => send({ t: "quiet", on: false });
$("#fWatch").onclick = () => send({ t: "watch", on: false });
$("#watchOn").onclick = () => { send({ t: "watch", on: true }); $("#setClose").click(); };
document.querySelectorAll("[data-quiet]").forEach((b) => b.onclick = () => { const m = +b.dataset.quiet; send(m ? { t: "quiet", on: true, minutes: m } : { t: "quiet", on: false }); });
// ручной конструктор режима
$("#rtTool").innerHTML = Object.keys(STEP_TPL).map((k) => `<option value="${k}">${esc(TOOL_NAMES[k] || k)} (${k})</option>`).join("");
$("#rtAddStep").onclick = () => {
  const k = $("#rtTool").value;
  $("#rtSteps").insertAdjacentHTML("beforeend", `<div class="rt-step" data-tool="${k}"><b>${esc(TOOL_NAMES[k] || k)}</b><input value='${esc(JSON.stringify(STEP_TPL[k]))}'><button class="x">✕</button></div>`);
};
$("#rtSteps").onclick = (e) => { if (e.target.classList.contains("x")) e.target.closest(".rt-step").remove(); };
$("#rtSave").onclick = () => {
  const steps = [...document.querySelectorAll(".rt-step")].map((r) => ({ tool: r.dataset.tool, args_json: r.querySelector("input").value }));
  const name = $("#rtName").value.trim();
  if (!name || !steps.length) { toast("Нужно название и хотя бы один шаг"); return; }
  send({ t: "routine_save", data: { name, description: $("#rtDesc").value.trim(), steps } });
  $("#rtName").value = ""; $("#rtDesc").value = ""; $("#rtSteps").innerHTML = "";
};
$("#tasks").onclick = (e) => {
  const row = e.target.closest(".task"); if (!row) return;
  if (e.target.classList.contains("x")) send({ t: "task_delete", id: row.dataset.id });
  else if (e.target.tagName === "INPUT") send({ t: "task_toggle", id: row.dataset.id });
};
$("#memList").onclick = (e) => { const row = e.target.closest(".mem"); if (row && e.target.classList.contains("x")) send({ t: "memory_delete", id: row.dataset.id }); };
let stLines = [];
$("#taskForm").onsubmit = (e) => { e.preventDefault(); const v = $("#taskText").value.trim(); if (v) send({ t: "task_add", text: v }); $("#taskText").value = ""; };
function fmtLeft(s) {
  s = Math.max(0, Math.round(s));
  const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60;
  return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(x).padStart(2, "0");
}
function renderTimers() {
  const ts = (S.store.timers || []).slice().sort((a, b) => a.due - b.due);
  $("#timerCount").textContent = ts.length ? ts.length : "";
  const now = Date.now() / 1000;
  $("#timers").innerHTML = ts.length ? ts.map((t) => {
    const left = t.due - now;
    const label = t.label || { timer: "Таймер", reminder: "Напоминание", alarm: "Будильник" }[t.kind];
    const big = left > 86400 ? new Date(t.due * 1000).toLocaleDateString("ru", { day: "numeric", month: "short" }) :
      left > 3 * 3600 ? new Date(t.due * 1000).toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit" }) : fmtLeft(left);
    return `<div class="timer ${left < 60 ? "soon" : ""}" data-id="${t.id}"><span>${t.kind === "alarm" ? "⏰ " : t.kind === "reminder" ? "🔔 " : "⏱ "}${esc(label)}</span><b>${big}</b><button class="x">✕</button></div>`;
  }).join("") : '<div class="empty">Скажите: «поставь таймер на 10 минут»</div>';
}
$("#timers").onclick = (e) => { const row = e.target.closest(".timer"); if (row && e.target.classList.contains("x")) send({ t: "timer_cancel", id: row.dataset.id }); };
setInterval(renderTimers, 1000);

/* ───────────── часы ───────────── */
function clock() {
  const d = new Date();
  $("#clock").textContent = d.toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  $("#date").textContent = d.toLocaleDateString("ru", { weekday: "long", day: "numeric", month: "long" });
}
setInterval(clock, 1000); clock();

/* ───────────── настройки ───────────── */
const ACCENTS = ["#4fe3ff", "#5b8cff", "#a78bfa", "#ff5fa2", "#ff5468", "#ffb648", "#4ff0a6", "#e8f1f5"];
const TAB_TITLES = { main: "Основное", voice: "Голос и характер", wake: "Активация", sound: "Звук", tools: "Возможности",
  apps: "Программы", memory: "Память", ai: "ИИ и ключ", diag: "Диагностика", routines: "Режимы",
  proactive: "Проактивность", games: "Игры и экран", phone: "Телефон (Telegram)" };
const RANGES = ["wake_threshold", "wake_verify_threshold", "idle_timeout", "vad_silence_ms", "mic_gain", "card_autoclose",
  "proactive_gpu_temp", "proactive_battery", "proactive_disk_gb", "proactive_game_hours", "watch_interval", "watch_idle_timeout"];
const TOGGLES = ["open_window_on_start", "autostart", "autostart_window", "sounds", "show_system_panel", "show_weather_panel",
  "headphones", "headphones_auto", "confirm_dangerous", "proactive", "proactive_voice", "proactive_night", "morning_briefing",
  "telegram_enabled", "telegram_notify", "update_auto_check"];
const F = {}; // текущие значения формы
let formDirty = false;
function hexA(h, a) { const n = parseInt(h.slice(1), 16); return `rgba(${n >> 16 & 255},${n >> 8 & 255},${n & 255},${a})`; }
function lighten(h, k) { const n = parseInt(h.slice(1), 16); const c = [n >> 16 & 255, n >> 8 & 255, n & 255].map((v) => Math.round(v + (255 - v) * k)); return "#" + c.map((v) => v.toString(16).padStart(2, "0")).join(""); }
function applyAccent(h) {
  if (!/^#[0-9a-f]{6}$/i.test(h || "")) return;
  const r = document.documentElement.style;
  r.setProperty("--c", h); r.setProperty("--c2", lighten(h, 0.5)); r.setProperty("--cdim", hexA(h, 0.45));
  r.setProperty("--line", hexA(h, 0.16)); r.setProperty("--line2", hexA(h, 0.34));
  const n = parseInt(h.slice(1), 16); PAL.idle = [n >> 16 & 255, n >> 8 & 255, n & 255]; PAL.boot = PAL.idle;
  PAL.listening = PAL.idle.map((v) => v + (255 - v) * 0.25); PAL.speaking = PAL.idle.map((v) => v + (255 - v) * 0.45); PAL.connecting = PAL.speaking;
}
const prettyKey = (c) => (c || "").split("+").map((k) => k.length === 1 ? k.toUpperCase() : k[0].toUpperCase() + k.slice(1)).join("+");
function applySettings(st) {
  if (!st) return;
  S.settings = st;
  const c = st.config;
  S.thr = c.wake_threshold;
  applyAccent(c.accent);
  document.body.classList.toggle("no-sys", c.show_system_panel === false);
  document.body.classList.toggle("no-wx", c.show_weather_panel === false);
  $("#wakeThr").style.left = (c.wake_threshold * 100) + "%"; $("#setWakeThr").style.left = (c.wake_threshold * 100) + "%";
  $("#modelName").textContent = st.live_model || "—";
  $("#voiceName").textContent = c.voice;
  $("#hotkey").textContent = prettyKey(c.hotkey);
  $("#wakeEng").textContent = { openwakeword: "локально", google: "через распознавание", off: "выкл" }[st.wake.engine] || "";
  if (!$("#settings").classList.contains("hidden") && formDirty) { renderInfo(st); return; } // не затираем правки
  fillForm(st);
}
function fillForm(st) {
  const c = st.config;
  Object.assign(F, JSON.parse(JSON.stringify(c)));
  for (const k of ["user_name", "city", "custom_instructions", "reply_language", "wake_engine", "clip_method", "discord_mute_key", "discord_deafen_key"]) { const el = $("#s_" + k); if (el) el.value = c[k] ?? ""; }
  for (const k of TOGGLES) $("#s_" + k).checked = !!c[k];
  for (const k of RANGES) { $("#s_" + k).value = c[k] ?? 0; $("#v_" + k).textContent = c[k] || ({ card_autoclose: "выкл", proactive_game_hours: "выкл" }[k] ?? c[k]); }
  renderUpdate(st.update || {});
  $("#tgTokInfo").textContent = c.has_tg_token ? `Сохранён токен ${c.telegram_token}` : "Токен не задан.";
  renderTg(st.telegram || {});
  $("#fTg").classList.toggle("hidden", !(st.telegram && st.telegram.ok && st.telegram.bound));
  $("#fWatch").classList.toggle("hidden", !st.watch);
  $("#s_hotkey").value = prettyKey(c.hotkey);
  $("#hsInfo").textContent = st.speaker.headset ? `— сейчас гарнитура: ${st.speaker.name}, перебивать можно` : "— сейчас динамики, перебить можно словами «Эй, Джарвис»";
  $("#hkInfo").textContent = st.hotkey_ok === false ? "⚠ Это сочетание занято другой программой — выберите другое." : "Кликните в поле и нажмите нужное сочетание (например Ctrl+Alt+J).";
  $("#s_voice").innerHTML = Object.entries(st.voices).map(([k, v]) => `<option value="${k}" ${k === c.voice ? "selected" : ""}>${esc(v)}</option>`).join("");
  $("#personaCards").innerHTML = Object.entries(st.personas).map(([k, v]) => { const [t, d] = v.split(" — "); return `<button data-v="${k}" class="${k === c.persona ? "on" : ""}"><b>${esc(t)}</b>${esc(d || "")}</button>`; }).join("");
  document.querySelectorAll("#seg_reply_length button").forEach((b) => b.classList.toggle("on", b.dataset.v === c.reply_length));
  $("#swatches").innerHTML = ACCENTS.map((h) => `<button data-v="${h}" style="background:${h};color:${h}" class="${h === c.accent ? "on" : ""}"></button>`).join("");
  const dev = (list, cur) => `<option value="">По умолчанию Windows</option>` + list.map((d) => `<option value="${d.id}" ${d.id === cur ? "selected" : ""}>${esc(d.name)}</option>`).join("");
  $("#s_mic_device").innerHTML = dev(st.devices.inputs, c.mic_device); $("#s_speaker_device").innerHTML = dev(st.devices.outputs, c.speaker_device);
  const off = new Set(c.tools_disabled || []);
  $("#toolToggles").innerHTML = Object.entries(st.tool_groups).map(([k, v]) => `<label class="tgl"><input type="checkbox" data-g="${k}" ${off.has(k) ? "" : "checked"}><i></i><span>${esc(v)}</span></label>`).join("");
  renderApps(c.apps || {});
  $("#appsCount").textContent = st.apps_indexed;
  $("#sKeyInfo").textContent = c.has_key ? `Сохранён ключ ${c.gemini_api_key}` : "Ключ не задан — Джарвис не сможет говорить.";
  const mopt = (list, cur) => `<option value="">Авто</option>` + (list || []).map((m) => `<option ${m === cur ? "selected" : ""}>${m}</option>`).join("");
  $("#s_live_model").innerHTML = mopt(st.live_models, c.live_model); $("#s_text_model").innerHTML = mopt(st.all_text_models, c.text_model);
  renderInfo(st);
  setDirty(false);
}
function renderInfo(st) {
  $("#sInfo").textContent = [
    `Голосовая модель: ${st.live_model || "—"}`,
    `Зрение/поиск:     ${(st.text_models || [])[0] || "—"}`,
    `Активация:        ${st.wake.status || st.wake.engine}`,
    `Микрофон:         ${st.mic.ok ? st.mic.name : "НЕ НАЙДЕН"}`,
    `Динамики:         ${st.speaker.ok ? st.speaker.name : "НЕ НАЙДЕНЫ"}`,
    `Программ / файлов: ${st.apps_indexed} / ${st.files_indexed}`,
    `Автозапуск:       ${st.autostart_real ? "включён" : "выключен"}`,
    st.live_error ? `Ошибка:           ${st.live_error}` : "",
    `Адрес интерфейса: http://127.0.0.1:${st.port}`,
  ].filter(Boolean).join("\n");
}
function renderApps(apps) {
  const rows = Object.entries(apps);
  $("#appsTable").innerHTML = (rows.length ? rows : [["", ""]]).map(([k, v]) => `<div class="apps-row"><input class="an" value="${esc(k)}" placeholder="название (как говорите)">
    <input class="ap" value="${esc(v)}" placeholder="C:\\путь\\к\\программе.exe или https://сайт"><button class="x">✕</button></div>`).join("");
}
function collectApps() {
  const o = {};
  document.querySelectorAll(".apps-row").forEach((r) => { const k = r.querySelector(".an").value.trim(), v = r.querySelector(".ap").value.trim(); if (k && v) o[k] = v; });
  return o;
}
function setDirty(d) { formDirty = d; $("#setDirty").textContent = d ? "есть несохранённые изменения" : ""; }
$("#settings").addEventListener("input", () => setDirty(true));
$("#settings").addEventListener("change", () => setDirty(true));
document.querySelectorAll(".set-nav button").forEach((b) => b.onclick = () => {
  document.querySelectorAll(".set-nav button").forEach((x) => x.classList.toggle("on", x === b));
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("on", t.dataset.tab === b.dataset.tab));
  $("#setTitle").textContent = TAB_TITLES[b.dataset.tab];
});
function renderTg(t) {
  let h;
  if (!t.on) h = '<span class="mut">Бот выключен.</span>';
  else if (t.error) h = `⚠ ${esc(t.error)}`;
  else if (!t.ok) h = "Подключаюсь к Telegram…";
  else if (!t.bound) h = `Бот <b>@${esc(t.bot)}</b> на связи. Откройте <a href="https://t.me/${esc(t.bot)}" target="_blank">t.me/${esc(t.bot)}</a> и отправьте код:<br><span class="code">${esc(t.code)}</span>`;
  else h = `✅ Бот <b>@${esc(t.bot)}</b> привязан к вашему телефону. Пишите ему — Джарвис ответит.`;
  $("#tgStatus").innerHTML = h;
}
function renderUpdate(u) {
  if (!u || !u.current) return;
  S.update = u;
  $("#ver").textContent = "v" + u.current;
  $("#fUpd").classList.toggle("hidden", !u.available); $("#fUpdV").textContent = u.latest || "";
  $("#updInstall").classList.toggle("hidden", !u.available);
  $("#updTitle").textContent = `Версия ${u.current}`;
  const when = u.checked ? new Date(u.checked * 1000).toLocaleTimeString("ru", { hour: "2-digit", minute: "2-digit" }) : "";
  $("#updState").textContent = u.available ? `— доступна ${u.latest} (${u.published || ""})` : u.error ? `— ${u.error}` : u.checked ? `— последняя (проверено в ${when})` : "";
  $("#updNotes").innerHTML = u.available && u.notes ? `<b>Что нового в ${esc(u.latest)}:</b>` + md(u.notes) : "";
}
function installUpdate() {
  const u = S.update || {};
  if (!u.available) return;
  if (!confirm(`Обновить Джарвиса до версии ${u.latest}?\n\nОн перезапустится примерно на полминуты. Настройки и память сохранятся.`)) return;
  send({ t: "update_install" });
  $("#fUpd").textContent = "⬆ ОБНОВЛЯЮСЬ…";
}
$("#fUpd").onclick = installUpdate;
$("#updInstall").onclick = installUpdate;
$("#updCheck").onclick = () => { $("#updState").textContent = "— проверяю…"; send({ t: "update_check" }); };
$("#tgTest").onclick = () => send({ t: "tg_test" });
$("#tgUnlink").onclick = () => { if (confirm("Отвязать телефон? Бот перестанет отвечать, пока не отправите новый код.")) send({ t: "tg_unlink" }); };
for (const k of RANGES)
  $("#s_" + k).addEventListener("input", (e) => { $("#v_" + k).textContent = e.target.value; if (k === "wake_threshold") $("#setWakeThr").style.left = e.target.value * 100 + "%"; });
$("#personaCards").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; F.persona = b.dataset.v; document.querySelectorAll("#personaCards button").forEach((x) => x.classList.toggle("on", x === b)); setDirty(true); };
$("#seg_reply_length").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; F.reply_length = b.dataset.v; document.querySelectorAll("#seg_reply_length button").forEach((x) => x.classList.toggle("on", x === b)); setDirty(true); };
$("#swatches").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; F.accent = b.dataset.v; applyAccent(F.accent); document.querySelectorAll("#swatches button").forEach((x) => x.classList.toggle("on", x === b)); setDirty(true); };
$("#appAdd").onclick = () => { const o = collectApps(); renderApps(o); $("#appsTable").insertAdjacentHTML("beforeend", `<div class="apps-row"><input class="an" placeholder="название"><input class="ap" placeholder="путь или сайт"><button class="x">✕</button></div>`); };
$("#appsTable").onclick = (e) => { if (e.target.classList.contains("x")) { e.target.closest(".apps-row").remove(); setDirty(true); } };
$("#appTestBtn").onclick = () => send({ t: "find_app", q: $("#appTest").value });
// горячая клавиша — запись сочетания
const hk = $("#s_hotkey");
hk.onfocus = () => { hk.classList.add("rec"); hk.value = "нажмите сочетание…"; };
hk.onblur = () => { hk.classList.remove("rec"); hk.value = prettyKey(F.hotkey); };
hk.onkeydown = (e) => {
  e.preventDefault();
  const k = e.key.toLowerCase();
  if (["control", "alt", "shift", "meta"].includes(k)) return;
  const mods = [e.ctrlKey && "ctrl", e.altKey && "alt", e.shiftKey && "shift", e.metaKey && "win"].filter(Boolean);
  let key = e.code.startsWith("Key") ? e.code.slice(3).toLowerCase() : e.code.startsWith("Digit") ? e.code.slice(5) : /^F\d+$/.test(e.code) ? e.code.toLowerCase() : e.code === "Space" ? "space" : null;
  if (!key || !mods.length) { $("#hkInfo").textContent = "Нужен хотя бы один модификатор: Ctrl, Alt, Shift или Win."; return; }
  F.hotkey = [...mods, key].join("+"); hk.value = prettyKey(F.hotkey); hk.blur(); setDirty(true);
};
$("#hkReset").onclick = () => { F.hotkey = "ctrl+alt+j"; hk.value = prettyKey(F.hotkey); setDirty(true); };
// память
$("#memAdd").onclick = () => { const v = $("#memNew").value.trim(); if (v) send({ t: "memory_add", text: v }); $("#memNew").value = ""; };
$("#memNew").onkeydown = (e) => { if (e.key === "Enter") $("#memAdd").click(); };
$("#memList").addEventListener("change", (e) => { const row = e.target.closest(".mem"); if (row && e.target.tagName === "INPUT") send({ t: "memory_edit", id: row.dataset.id, text: e.target.value }); });
$("#noteList").onclick = (e) => { const row = e.target.closest(".mem"); if (row && e.target.classList.contains("x")) send({ t: "notes_delete", id: row.dataset.id }); };
$("#memClear").onclick = () => { if (confirm("Джарвис забудет все факты о вас. Продолжить?")) send({ t: "memory_clear" }); };
$("#histClear").onclick = () => send({ t: "history_clear" });
// диагностика
$("#dQuick").onclick = () => send({ t: "selftest", full: false });
$("#dFull").onclick = () => send({ t: "selftest", full: true });
document.querySelectorAll("[data-open]").forEach((b) => b.onclick = () => send({ t: "open_path", what: b.dataset.open }));
$("#dRestart").onclick = () => send({ t: "restart" });
$("#dQuit").onclick = () => { if (confirm("Выключить Джарвиса полностью (он перестанет слушать)?")) send({ t: "quit" }); };
$("#sSnd").onclick = () => send({ t: "test_sound" });
$("#setBtn").onclick = () => { if (S.settings) fillForm(S.settings); $("#settings").classList.remove("hidden"); };
$("#setClose").onclick = () => { $("#settings").classList.add("hidden"); if (formDirty && S.settings) { applyAccent(S.settings.config.accent); } setDirty(false); };
$("#settings").onclick = (e) => { if (e.target.id === "settings") $("#setClose").click(); };
$("#sTest").onclick = () => { saveSettings(false); setTimeout(() => send({ t: "test_voice" }), 400); };
function saveSettings(close = true) {
  const v = (id) => $(id).value;
  const data = {
    user_name: v("#s_user_name").trim() || "сэр", city: v("#s_city").trim() || "Жилина",
    open_window_on_start: $("#s_open_window_on_start").checked, autostart: $("#s_autostart").checked, autostart_window: $("#s_autostart_window").checked,
    sounds: $("#s_sounds").checked, show_system_panel: $("#s_show_system_panel").checked, show_weather_panel: $("#s_show_weather_panel").checked,
    accent: F.accent, voice: v("#s_voice"), persona: F.persona, reply_length: F.reply_length, reply_language: v("#s_reply_language"),
    custom_instructions: v("#s_custom_instructions"), wake_engine: v("#s_wake_engine"),
    wake_threshold: +v("#s_wake_threshold"), wake_verify_threshold: +v("#s_wake_verify_threshold"), hotkey: F.hotkey,
    idle_timeout: +v("#s_idle_timeout"), vad_silence_ms: +v("#s_vad_silence_ms"), headphones: $("#s_headphones").checked, headphones_auto: $("#s_headphones_auto").checked,
    mic_device: v("#s_mic_device"), speaker_device: v("#s_speaker_device"), mic_gain: +v("#s_mic_gain"),
    tools_disabled: [...document.querySelectorAll("#toolToggles input")].filter((i) => !i.checked).map((i) => i.dataset.g),
    confirm_dangerous: $("#s_confirm_dangerous").checked, apps: collectApps(), card_autoclose: +v("#s_card_autoclose"),
    live_model: v("#s_live_model"), text_model: v("#s_text_model"),
    proactive: $("#s_proactive").checked, proactive_voice: $("#s_proactive_voice").checked, proactive_night: $("#s_proactive_night").checked,
    morning_briefing: $("#s_morning_briefing").checked, proactive_gpu_temp: +v("#s_proactive_gpu_temp"), proactive_battery: +v("#s_proactive_battery"),
    proactive_disk_gb: +v("#s_proactive_disk_gb"), proactive_game_hours: +v("#s_proactive_game_hours"),
    watch_interval: +v("#s_watch_interval"), watch_idle_timeout: +v("#s_watch_idle_timeout"), clip_method: v("#s_clip_method"),
    discord_mute_key: v("#s_discord_mute_key").trim().toLowerCase(), discord_deafen_key: v("#s_discord_deafen_key").trim().toLowerCase(),
    update_auto_check: $("#s_update_auto_check").checked,
    telegram_enabled: $("#s_telegram_enabled").checked, telegram_notify: $("#s_telegram_notify").checked,
  };
  const k = v("#sKey").trim(); if (k) data.gemini_api_key = k;
  const tk = $("#sTgToken").value.trim(); if (tk) { data.telegram_token = tk; $("#sTgToken").value = ""; }
  send({ t: "settings", data });
  $("#sKey").value = "";
  setDirty(false);
  if (close) $("#settings").classList.add("hidden");
}
$("#setSave").onclick = () => saveSettings(true);

/* ───────────── ввод ───────────── */
$("#form").onsubmit = (e) => {
  e.preventDefault();
  const v = $("#text").value.trim(); if (!v) return;
  send({ t: "text", text: v }); $("#text").value = "";
};
$("#stopBtn").onclick = () => send({ t: "stop" });
$("#micBtn").onclick = () => { S.mic = !S.mic; send({ t: "mic", on: S.mic }); $("#micBtn").classList.toggle("off", !S.mic); };
$("#reactorWrap").onclick = () => send({ t: "activate" });
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { closeCard(); $("#alert").classList.add("hidden"); if (!$("#settings").classList.contains("hidden")) $("#setClose").click(); }
  if (e.key === "/" && document.activeElement.tagName !== "INPUT") { e.preventDefault(); $("#text").focus(); }
});

/* ───────────── загрузка ───────────── */
function boot(play) {
  if (S.booted) return; S.booted = true;
  const el = $("#boot");
  if (!play) { el.classList.add("done"); return; }
  const st = S.settings || {};
  const lines = [
    "J.A.R.V.I.S.  v2.0",
    "› ядро .................. OK",
    `› аудио ................. ${st.mic?.ok ? "OK" : "НЕТ МИКРОФОНА"}`,
    `› активация ............. ${st.wake?.engine === "openwakeword" ? "ЛОКАЛЬНО" : (st.wake?.engine || "—").toUpperCase()}`,
    `› нейросеть ............. ${st.live_model || "…"}`,
    "› все системы в норме.",
  ];
  let i = 0;
  const log = $("#bootLog");
  const tick = setInterval(() => {
    log.textContent += lines[i++] + "\n";
    if (i >= lines.length) { clearInterval(tick); setTimeout(() => el.classList.add("done"), 650); }
  }, 260);
}
setTimeout(() => $("#boot").classList.add("done"), 6000);

/* ───────────── реактор ───────────── */
const cv = $("#reactor"), ctx = cv.getContext("2d");
const PAL = {
  idle: [79, 227, 255], listening: [110, 240, 255], speaking: [150, 245, 255], thinking: [255, 182, 72],
  connecting: [160, 235, 255], error: [255, 84, 104], nokey: [255, 182, 72], offline: [90, 110, 125], boot: [79, 227, 255],
};
let col = [79, 227, 255], energy = 0, spin = 0, tPrev = performance.now();
const bars = new Float32Array(120);
const parts = Array.from({ length: 46 }, () => ({ a: Math.random() * 6.283, r: 0.55 + Math.random() * 0.4, s: (Math.random() * 0.4 + 0.1) * (Math.random() < 0.5 ? -1 : 1), z: Math.random() }));
function resize() {
  const r = cv.getBoundingClientRect(), d = window.devicePixelRatio || 1;
  cv.width = Math.round(r.width * d); cv.height = Math.round(r.height * d);
}
addEventListener("resize", resize);
new ResizeObserver(resize).observe(cv);
const rgba = (c, a) => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${a})`;
function frame(now) {
  requestAnimationFrame(frame);
  const dt = Math.min(0.05, (now - tPrev) / 1000); tPrev = now;
  { const r = cv.getBoundingClientRect(), d = window.devicePixelRatio || 1; if (Math.abs(cv.width - r.width * d) > 2 || Math.abs(cv.height - r.height * d) > 2) resize(); }
  const W = cv.width, H = cv.height, cx = W / 2, cy = H / 2, R = Math.min(W, H) / 2 * 0.92;
  const st = S.state;
  const tgt = PAL[st] || PAL.idle;
  for (let i = 0; i < 3; i++) col[i] += (tgt[i] - col[i]) * Math.min(1, dt * 4);
  const lvl = st === "speaking" ? S.lvlOut : (st === "listening" ? S.lvlIn * 1.4 : 0);
  const target = { idle: 0.12, listening: 0.35 + lvl, speaking: 0.45 + lvl, thinking: 0.55, connecting: 0.45, error: 0.3, nokey: 0.1, offline: 0.05, boot: 0.2 }[st] ?? 0.2;
  energy += (Math.min(1.2, target) - energy) * Math.min(1, dt * 6);
  const speed = { thinking: 2.6, connecting: 1.8, speaking: 0.9, listening: 0.7 }[st] ?? 0.25;
  spin += dt * speed;
  const t = now / 1000;
  ctx.clearRect(0, 0, W, H);
  ctx.save(); ctx.translate(cx, cy);

  // фон-свечение
  let g = ctx.createRadialGradient(0, 0, R * 0.1, 0, 0, R);
  g.addColorStop(0, rgba(col, 0.20 + energy * 0.25)); g.addColorStop(0.45, rgba(col, 0.05 + energy * 0.06)); g.addColorStop(1, rgba(col, 0));
  ctx.fillStyle = g; ctx.beginPath(); ctx.arc(0, 0, R, 0, 6.283); ctx.fill();

  ctx.lineCap = "round";
  // внешняя шкала
  for (let i = 0; i < 120; i++) {
    const a = i / 120 * 6.283 + spin * 0.15;
    const major = i % 10 === 0;
    const r1 = R * 0.95, r2 = R * (major ? 0.9 : 0.925);
    ctx.strokeStyle = rgba(col, major ? 0.7 : 0.22); ctx.lineWidth = major ? 2.2 : 1.2;
    ctx.beginPath(); ctx.moveTo(Math.cos(a) * r1, Math.sin(a) * r1); ctx.lineTo(Math.cos(a) * r2, Math.sin(a) * r2); ctx.stroke();
  }
  // дуги
  const arcs = [[0.84, 3, 0.9, 1], [0.79, 6, 0.35, -1.4], [0.72, 2, 0.6, 0.7]];
  arcs.forEach(([rr, w, alpha, dir], k) => {
    ctx.lineWidth = w * (W / 900 + 0.5); ctx.strokeStyle = rgba(col, alpha);
    const n = k === 1 ? 5 : 3;
    for (let j = 0; j < n; j++) {
      const s = spin * dir + j / n * 6.283 + k;
      ctx.beginPath(); ctx.arc(0, 0, R * rr, s, s + (k === 1 ? 0.55 : 1.15) + Math.sin(t * 0.7 + j) * 0.12); ctx.stroke();
    }
  });
  // аудио-лучи
  const base = R * 0.6;
  for (let i = 0; i < bars.length; i++) {
    const n = Math.sin(i * 0.37 + t * 5.1) * 0.5 + Math.sin(i * 0.11 - t * 3.3) * 0.5;
    const v = Math.max(0.02, (st === "speaking" || st === "listening") ? lvl * (0.55 + 0.45 * n) + 0.03 : 0.03 + energy * 0.08 * (n + 1));
    bars[i] += (v - bars[i]) * Math.min(1, dt * 14);
    const a = i / bars.length * 6.283 - 1.5708;
    const L = R * 0.18 * Math.min(1.4, bars[i] * 1.6);
    ctx.strokeStyle = rgba(col, 0.35 + Math.min(0.6, bars[i]));
    ctx.lineWidth = Math.max(1.5, W / 420);
    ctx.beginPath(); ctx.moveTo(Math.cos(a) * base, Math.sin(a) * base); ctx.lineTo(Math.cos(a) * (base + L), Math.sin(a) * (base + L)); ctx.stroke();
  }
  // сегментное кольцо
  const segs = 36;
  for (let i = 0; i < segs; i++) {
    const a0 = i / segs * 6.283 - spin * 0.5, a1 = a0 + 6.283 / segs * 0.7;
    const wave = 0.25 + 0.75 * Math.max(0, Math.sin(i / segs * 6.283 * 2 - t * 3));
    ctx.strokeStyle = rgba(col, 0.15 + wave * (0.25 + energy * 0.5)); ctx.lineWidth = R * 0.035;
    ctx.beginPath(); ctx.arc(0, 0, R * 0.53, a0, a1); ctx.stroke();
  }
  // частицы
  parts.forEach((p) => {
    p.a += p.s * dt * (0.4 + energy * 2);
    const rr = R * p.r, x = Math.cos(p.a) * rr, y = Math.sin(p.a) * rr * (0.92 + p.z * 0.08);
    ctx.fillStyle = rgba(col, 0.25 + p.z * 0.5);
    ctx.beginPath(); ctx.arc(x, y, (1 + p.z * 1.6) * (W / 700 + 0.4), 0, 6.283); ctx.fill();
  });
  // ядро
  const pulse = st === "idle" ? Math.sin(t * 1.8) * 0.04 : 0;
  const cr = R * (0.3 + energy * 0.1 + pulse);
  g = ctx.createRadialGradient(0, 0, 0, 0, 0, cr * 1.5);
  g.addColorStop(0, "rgba(255,255,255,.95)"); g.addColorStop(0.18, rgba(col.map((v) => v + (255 - v) * 0.6), 0.95));
  g.addColorStop(0.5, rgba(col, 0.55)); g.addColorStop(1, rgba(col, 0));
  ctx.fillStyle = g; ctx.beginPath(); ctx.arc(0, 0, cr * 1.5, 0, 6.283); ctx.fill();
  ctx.strokeStyle = rgba(col, 0.9); ctx.lineWidth = Math.max(2, W / 300);
  ctx.beginPath(); ctx.arc(0, 0, cr * 0.98, 0, 6.283); ctx.stroke();
  // шестигранник в ядре
  ctx.rotate(-spin * 0.3);
  ctx.strokeStyle = rgba([255, 255, 255], 0.28 + energy * 0.25); ctx.lineWidth = Math.max(1.2, W / 600);
  for (const sc of [0.62, 0.42]) {
    ctx.beginPath();
    for (let k = 0; k < 6; k++) { const a = k / 6 * 6.283; const x = Math.cos(a) * cr * sc, y = Math.sin(a) * cr * sc; k ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }
    ctx.closePath(); ctx.stroke(); ctx.rotate(0.5236);
  }
  ctx.restore();
}
requestAnimationFrame(frame);
setState("boot");
connect();
