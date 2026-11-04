/* Sayro — интерфейс. Протокол с ядром: WebSocket /ws (см. core/assistant.py handle_ui / broadcast). */
"use strict";
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/* Английские строки, которые создаёт скрипт (HTML-строки берутся из разметки). Ключи → ui/i18n/<lang>.json */
const STR = {
  "state.boot": "Loading", "state.boot_h": "Starting up…",
  "state.idle": "Ready", "state.idle_h": "Say “Hey {name}”, press {hotkey}, or click the orb",
  "state.connecting": "Connecting", "state.connecting_h": "Reaching the AI…",
  "state.listening": "Listening", "state.listening_h": "Go ahead — I'm listening",
  "state.thinking": "Thinking", "state.thinking_h": "",
  "state.speaking": "Speaking", "state.speaking_h": "Say “Hey {name}” to interrupt",
  "state.error": "Something went wrong", "state.nokey": "Connect your AI", "state.nokey_h": "Open the setup assistant to add a Gemini key",
  "state.offline": "Reconnecting", "state.offline_h": "Waiting for the core…",
  "chip.idle": "Ready · say “Hey {name}”", "chip.listening": "Listening", "chip.speaking": "Speaking", "chip.thinking": "Working",
  "chip.connecting": "Connecting", "chip.error": "Error", "chip.nokey": "No AI key", "chip.offline": "Offline", "chip.boot": "Loading",
  "empty.timers": "Say “set a timer for 10 minutes”", "empty.tasks": "Say “add a task: buy groceries”",
  "empty.memory": "Nothing yet. Say “remember that I have classes on Tuesdays”", "empty.notes": "No notes. Say “take a note…”",
  "empty.routines": "No routines yet. Say “create a study routine: close Steam, open Teams, quiet mode for 2 hours”",
  "timer.timer": "Timer", "timer.reminder": "Reminder", "timer.alarm": "Alarm",
  "sys.on_ac": "AC", "copied": "Copied", "card.copy": "Copy",
  "sd.restart": "Restarting the computer in {s} s", "sd.shutdown": "Shutting down the computer in {s} s",
  "settings.dirty": "Unsaved changes", "hk.info": "Click the field and press a shortcut (e.g. Ctrl+Alt+J).",
  "hk.busy": "⚠ This shortcut is taken by another app — choose another.", "hk.need_mod": "Use at least one of Ctrl, Alt, Shift or Win.",
  "hk.rec": "press a shortcut…", "hs.headset": "— now: headset {name}, you can interrupt", "hs.speakers": "— now: speakers, interrupt with “Hey {brand}”",
  "default_device": "Windows default", "auto": "Auto", "key.saved": "Saved key {k}", "key.none": "No key yet — Sayro cannot talk.",
  "apps.found": "→ opens “{app}” ({p}% sure)", "apps.notfound": "→ not found. Add the app in the table above.",
  "apps.name_ph": "name (as you say it)", "apps.path_ph": "C:\\path\\to\\app.exe or https://site",
  "rt.run": "Run", "rt.del_q": "Delete this routine?", "rt.need": "A name and at least one step are needed",
  "quiet.on": "on until {t}", "quiet.off": "off",
  "tg.off": "The bot is off.", "tg.connecting": "Connecting to Telegram…",
  "tg.pair": "Bot @{bot} is online. Open t.me/{bot} and send this code:", "tg.ok": "✅ Bot @{bot} is linked to your phone. Message it — Sayro will answer.",
  "tg.unlink_q": "Unlink the phone? The bot stops answering until you send a new code.",
  "pro.active": "Pro is active", "pro.trial": "Pro trial — {d} days left", "pro.free": "Free version",
  "pro.until": " · until {d}", "pro.by_gumroad": " · subscription", "pro.by_key": " · personal key", "pro.lic": "License: {n}",
  "pro.free_sub": "The essentials are free forever. Pro adds what's on the right.", "pro.trial_sub": "All Pro features are unlocked during the trial.",
  "pro.key_saved": "Key saved.", "pro.checking": "Checking…", "pro.del_q": "Remove the key? Sayro will become the free version.",
  "up.version": "Version {v}", "up.available": "— {v} available ({d})", "up.latest": "— up to date (checked at {t})", "up.checking": "— checking…",
  "up.whats_new": "What's new in {v}:", "up.confirm": "Update Sayro to version {v}?\n\nIt restarts for about half a minute. Settings and memory are kept.",
  "up.updating": "Updating…",
  "mem.clear_q": "Sayro will forget every fact about you. Continue?", "quit_q": "Quit Sayro completely (it will stop listening)?",
  "info.voice": "Voice model:", "info.text": "Vision/search:", "info.wake": "Wake word:", "info.mic": "Microphone:", "info.spk": "Speakers:",
  "info.apps": "Apps / files:", "info.autostart": "Start with Windows:", "info.err": "Error:", "info.addr": "Interface:",
  "info.none_mic": "NOT FOUND", "info.on": "on", "info.off": "off",
  "onb.how_pro": "1. Open “Activate AI Pro credits” and join the Google Developer Program with your AI Pro account.|2. Link the monthly credits to a Cloud billing account.|3. Open Google AI Studio, press “Create API key” in that project and paste it below.",
  "onb.how_key": "1. Open Google AI Studio and sign in with Google.|2. Press “Create API key”.|3. Copy it and paste it below. In the EU, enable billing on the project.",
  "onb.checking": "Checking the key…", "onb.key_ok": "✓ Key works", "onb.key_bad": "This key did not work: {e}", "onb.need_key": "Paste a key to continue",
  "onb.finish": "Start", "gaming.min": "{m} min", "gaming.h": "{h} h {m} min",
  "persona.butler": "Butler — polite, dry British wit", "persona.friend": "Friend — casual, funny", "persona.pro": "Professional — only the essentials",
  "persona.tutor": "Tutor — step by step, guiding questions", "persona.custom": "Custom — only my instructions",
  "lang.auto": "Same as I speak",
  "tg_group.apps": "Apps and windows", "tg_group.keyboard": "Keyboard and typing", "tg_group.mouse": "Mouse clicks on screen",
  "tg_group.vision": "Vision (screenshots, seeing the screen)", "tg_group.internet": "Internet and YouTube", "tg_group.media": "Sound, brightness, music",
  "tg_group.files": "File search", "tg_group.info": "Weather, currency, system", "tg_group.time": "Timers and reminders",
  "tg_group.organizer": "Tasks, notes, memory", "tg_group.power": "Power and recycle bin", "tg_group.routines": "Routines and quiet mode",
  "tg_group.gaming": "Games: clips and Discord", "tg_group.update": "Self-update",
  "btn.mic": "Microphone", "btn.settings": "Settings", "btn.stop": "Stop", "btn.send": "Send", "btn.close": "Close",
  "orb.click": "Click to talk", "flag.watch_off": "Sayro sees your screen — click to stop", "flag.quiet_off": "Quiet mode — click to turn off",
  "flag.game_hint": "The GPU is busy — looks like a game",
  "wx.0": "clear", "wx.1": "mostly clear", "wx.2": "partly cloudy", "wx.3": "overcast", "wx.45": "fog", "wx.48": "rime fog",
  "wx.51": "light drizzle", "wx.53": "drizzle", "wx.55": "heavy drizzle", "wx.56": "freezing drizzle", "wx.57": "freezing drizzle",
  "wx.61": "light rain", "wx.63": "rain", "wx.65": "heavy rain", "wx.66": "freezing rain", "wx.67": "freezing rain",
  "wx.71": "light snow", "wx.73": "snow", "wx.75": "heavy snow", "wx.77": "snow grains", "wx.80": "light showers", "wx.81": "showers",
  "wx.82": "heavy showers", "wx.85": "snow showers", "wx.86": "heavy snow showers", "wx.95": "thunderstorm", "wx.96": "thunderstorm with hail",
  "wx.99": "severe thunderstorm with hail",
  "voice.Charon": "deep, calm", "voice.Orus": "confident, firm", "voice.Fenrir": "energetic", "voice.Iapetus": "clear, even",
  "voice.Algenib": "slightly husky", "voice.Rasalgethi": "informative", "voice.Puck": "upbeat", "voice.Kore": "female, firm",
  "voice.Aoede": "female, light", "voice.Leda": "female, young",
};
const TOOL_KEYS = ["open_app", "close_app", "switch_window", "window_action", "list_windows", "press_keys", "type_text", "clipboard",
  "open_website", "web_search", "search_internet", "youtube", "media_control", "volume", "brightness", "take_screenshot", "look_at_screen",
  "find_file", "get_weather", "exchange_rate", "system_status", "set_timer", "set_reminder", "list_timers", "cancel_timer", "tasks", "notes",
  "memory", "display", "calculate", "now", "power", "empty_recycle_bin", "set_preference", "end_conversation", "close_display", "hud_window",
  "click_on_screen", "scroll", "routine_save", "routine_run", "routine_list", "routine_delete", "quiet_mode", "watch_screen", "game_clip",
  "discord", "send_screen_photo", "wait", "jarvis_update"];
Object.assign(STR, {
  "tool.open_app": "opening", "tool.close_app": "closing", "tool.switch_window": "window", "tool.window_action": "windows", "tool.list_windows": "windows",
  "tool.press_keys": "keys", "tool.type_text": "typing", "tool.clipboard": "clipboard", "tool.open_website": "website", "tool.web_search": "search",
  "tool.search_internet": "searching the web", "tool.youtube": "YouTube", "tool.media_control": "media", "tool.volume": "volume",
  "tool.brightness": "brightness", "tool.take_screenshot": "screenshot", "tool.look_at_screen": "looking at the screen", "tool.find_file": "finding a file",
  "tool.get_weather": "weather", "tool.exchange_rate": "exchange rate", "tool.system_status": "system", "tool.set_timer": "timer",
  "tool.set_reminder": "reminder", "tool.list_timers": "timers", "tool.cancel_timer": "timers", "tool.tasks": "tasks", "tool.notes": "notes",
  "tool.memory": "memory", "tool.display": "showing", "tool.calculate": "calculating", "tool.now": "time", "tool.power": "power",
  "tool.empty_recycle_bin": "recycle bin", "tool.set_preference": "settings", "tool.end_conversation": "ending", "tool.close_display": "closing the card",
  "tool.hud_window": "window", "tool.click_on_screen": "click", "tool.scroll": "scroll", "tool.routine_save": "creating a routine",
  "tool.routine_run": "routine", "tool.routine_list": "routines", "tool.routine_delete": "routines", "tool.quiet_mode": "quiet mode",
  "tool.watch_screen": "seeing the screen", "tool.game_clip": "clip", "tool.discord": "Discord", "tool.send_screen_photo": "screen photo",
  "tool.wait": "pause", "tool.jarvis_update": "update",
});
const toolName = (n) => T("tool." + n);
const STEP_TPL = {
  open_app: { name: "" }, close_app: { name: "" }, open_website: { site: "" }, youtube: { query: "", mode: "play" },
  volume: { action: "set", level: 40 }, brightness: { level: 70 }, media_control: { action: "play_pause" },
  quiet_mode: { minutes: 60 }, wait: { seconds: 2 }, window_action: { action: "show_desktop" }, press_keys: { keys: "" },
  type_text: { text: "" }, set_timer: { seconds: 1500, label: "" }, discord: { action: "mute" }, switch_window: { title: "" },
  get_weather: {}, tasks: { action: "list" }, search_internet: { query: "" }, game_clip: {}, system_status: {},
};
const ACCENTS = ["#0A84FF", "#5E5CE6", "#BF5AF2", "#FF375F", "#FF453A", "#FF9F0A", "#30D158", "#64D2FF"];

const S = { state: "boot", detail: "", lvlIn: 0, lvlOut: 0, wake: 0, settings: null, store: { timers: [], tasks: [], notes: [], memory: [], routines: [] },
  msgs: new Map(), mic: true, booted: false, ws: null, wsOk: false, brand: "Sayro", pro: false, update: null, onbShown: false };

/* ───────────── WebSocket ───────────── */
function connect() {
  const ws = new WebSocket(`ws://${location.host}/ws`);
  S.ws = ws;
  ws.onopen = () => { S.wsOk = true; };
  ws.onclose = () => { S.wsOk = false; setState("offline"); setTimeout(connect, 1500); };
  ws.onmessage = (e) => { let m; try { m = JSON.parse(e.data); } catch { return; } handle(m); };
}
function send(obj) { if (S.ws && S.ws.readyState === 1) S.ws.send(JSON.stringify(obj)); }

function handle(m) {
  switch (m.t) {
    case "snapshot":
      // ядро обновилось, а страница старая — перезагрузиться, чтобы взять новый интерфейс
      if (S.version && m.version && m.version !== S.version) { location.reload(); return; }
      S.version = m.version;
      applySettings(m.settings); renderStore(m.store); if (m.weather) renderWeather(m.weather);
      $("#chat").innerHTML = ""; S.msgs.clear();
      (m.history || []).slice(-12).forEach((h) => addMsg(h.r === "user" ? "user" : "jarvis", h.t, null, true));
      setState(m.state, m.detail); boot(); maybeOnboarding();
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
    case "key_check": onKeyCheck(m); break;
    case "find_app":
      if (m.q) $("#appTestRes").textContent = m.found ? T("apps.found", { app: m.found, p: Math.round(m.score * 100) }) : T("apps.notfound");
      break;
    case "selftest": { const o = $("#dOut"); if (m.start) o.textContent = ""; o.textContent += m.line + "\n"; o.scrollTop = 1e9; break; }
  }
}

/* ───────────── язык и тема ───────────── */
function onLangApplied() {
  setState(S.state, S.detail);
  if (S.settings) { renderInfo(S.settings); renderLicense(S.settings.license || {}); renderUpdate(S.update || S.settings.update || {}); renderTg(S.settings.telegram || {}); }
  renderStore(S.store);
  if (lastWx) renderWeather(lastWx);
  const tab = document.querySelector(".set-nav button.on"); if (tab) $("#setTitle").textContent = tab.textContent.replace(" · Pro", "");
}
let themePref = "dark";
function applyTheme(pref) {
  themePref = pref || "dark";
  const dark = themePref === "system" ? matchMedia("(prefers-color-scheme: dark)").matches : themePref !== "light";
  document.body.dataset.theme = dark ? "dark" : "light";
}
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => applyTheme(themePref));
function applyAccent(h) {
  if (!/^#[0-9a-f]{6}$/i.test(h || "")) return;
  document.documentElement.style.setProperty("--accent", h);
}

/* ───────────── состояние ───────────── */
function setState(st, detail) {
  S.state = st; S.detail = detail || "";
  document.body.dataset.state = st;
  const v = { name: S.brand, hotkey: prettyKey(S.settings?.config?.hotkey || "ctrl+alt+j") };
  $("#stateText").textContent = T("state." + st, v);
  let h = STR["state." + st + "_h"] !== undefined || I18N.en["state." + st + "_h"] ? T("state." + st + "_h", v) : "";
  if (st === "thinking" && detail) h = detail.split(", ").map(toolName).join(" · ");
  if (st === "error") h = detail || "";
  $("#stateHint").textContent = h;
  $("#chipText").textContent = T("chip." + st, v);
}

/* ───────────── чат ───────────── */
function addMsg(role, text, id, final) {
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
  const a = Object.entries(args || {}).filter(([k]) => k !== "confirmed").map(([, v]) => String(v).slice(0, 40)).join(", ");
  el.textContent = toolName(name) + (a ? " · " + a : "");
  $("#chat").appendChild(el); $("#chat").scrollTop = 1e9;
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
$("#cardCopy").onclick = () => { navigator.clipboard.writeText(cardRaw).then(() => toast(T("copied"))); };
function showAlert(kind, text) { $("#alertKind").textContent = kind; $("#alertText").textContent = text; $("#alert").classList.remove("hidden"); }
$("#alertOk").onclick = () => $("#alert").classList.add("hidden");
let sdTimer = null;
function shutdownBanner(sec, action) {
  clearInterval(sdTimer);
  if (!sec) { $("#shutdown").classList.add("hidden"); return; }
  let left = sec;
  const tick = () => { $("#sdText").textContent = T(action === "restart" ? "sd.restart" : "sd.shutdown", { s: left }); if (left-- <= 0) clearInterval(sdTimer); };
  tick(); sdTimer = setInterval(tick, 1000);
  $("#shutdown").classList.remove("hidden");
}
$("#sdCancel").onclick = () => { send({ t: "cancel_shutdown" }); shutdownBanner(0); };

/* ───────────── система ───────────── */
function setVal(id, v, hot, crit) {
  const el = $(id); el.textContent = v;
  el.classList.toggle("hot", !!hot && !crit); el.classList.toggle("crit", !!crit);
}
function renderStats(d) {
  const gs = d.gaming_since;
  $("#fGame").classList.toggle("hidden", !gs);
  if (gs) { const mn = Math.floor((Date.now() / 1000 - gs) / 60); $("#fGameT").textContent = mn >= 60 ? T("gaming.h", { h: Math.floor(mn / 60), m: mn % 60 }) : T("gaming.min", { m: mn }); }
  setVal("#cpuV", d.cpu != null ? Math.round(d.cpu) + "%" : "—", d.cpu > 75, d.cpu > 92);
  setVal("#gpuV", d.gpu ? Math.round(d.gpu.temp) + "°" : "—", d.gpu && d.gpu.temp > 80, d.gpu && d.gpu.temp > 88);
  setVal("#ramV", d.ram != null ? Math.round(d.ram) + "%" : "—", d.ram > 80, d.ram > 92);
  setVal("#batV", d.battery != null ? d.battery + "%" + (d.plugged ? "⚡" : "") : T("sys.on_ac"), d.battery != null && !d.plugged && d.battery < 25, d.battery != null && !d.plugged && d.battery < 10);
  $("#gpuV").title = d.gpu ? `${d.gpu.name} · ${Math.round(d.gpu.util)}%` : "";
}
const orb = $("#orb");
let orbS = 1;
function meters() {
  $("#inBar").style.width = Math.min(100, S.lvlIn * 160) + "%";
  $("#outBar").style.width = Math.min(100, S.lvlOut * 140) + "%";
  const lvl = S.state === "speaking" ? S.lvlOut * 1.2 : S.state === "listening" ? S.lvlIn * 1.6 : 0;
  const target = 1 + Math.min(0.22, lvl * 0.5);
  orbS += (target - orbS) * 0.45;
  orb.style.setProperty("--s", orbS.toFixed(3));
  orb.style.setProperty("--g", Math.min(0.5, lvl).toFixed(2));
  orb.style.setProperty("--glow", Math.round(Math.min(60, lvl * 120)) + "px");
  if (!$("#settings").classList.contains("hidden")) {
    $("#setInBar").style.width = Math.min(100, S.lvlIn * 160) + "%";
    $("#setWakeBar").style.width = Math.min(100, S.wake * 100) + "%";
  }
  if (!$("#onb").classList.contains("hidden")) $("#onbMic").style.width = Math.min(100, S.lvlIn * 160) + "%";
}

/* ───────────── погода ───────────── */
const ICONS = {
  sun: '<circle cx="32" cy="32" r="11"/><path d="M32 8v6M32 50v6M8 32h6M50 32h6M15 15l4 4M45 45l4 4M15 49l4-4M45 19l4-4"/>',
  "cloud-sun": '<circle cx="24" cy="24" r="8"/><path d="M24 8v4M10 24H6M13 13l3 3M35 13l-3 3"/><path d="M22 48h24a9 9 0 0 0 0-18 13 13 0 0 0-24 4 7 7 0 0 0 0 14z"/>',
  cloud: '<path d="M18 46h28a10 10 0 0 0 0-20 14 14 0 0 0-27 4 8 8 0 0 0-1 16z"/>',
  rain: '<path d="M18 38h28a10 10 0 0 0 0-20 14 14 0 0 0-27 4 8 8 0 0 0-1 16z"/><path d="M22 44l-3 8M32 44l-3 8M42 44l-3 8"/>',
  snow: '<path d="M18 36h28a10 10 0 0 0 0-20 14 14 0 0 0-27 4 8 8 0 0 0-1 16z"/><path d="M22 44v8M18 48h8M36 44v8M32 48h8"/>',
  storm: '<path d="M18 36h28a10 10 0 0 0 0-20 14 14 0 0 0-27 4 8 8 0 0 0-1 16z"/><path d="M33 38l-6 10h8l-5 9"/>',
  fog: '<path d="M12 26h40M8 34h48M14 42h36"/>',
};
const ico = (k) => `<svg viewBox="0 0 64 64">${ICONS[k] || ICONS.cloud}</svg>`;
let lastWx = null;
function renderWeather(w) {
  if (!w || !w.now) return;
  lastWx = w;
  const sgn = (v) => (v > 0 ? "+" : "") + v + "°";
  $("#wxIco").innerHTML = ico(w.now.icon);
  $("#wxTemp").textContent = sgn(w.now.temp);
  const desc = w.now.code != null && T("wx." + w.now.code) !== "wx." + w.now.code ? T("wx." + w.now.code) : w.now.desc;
  $("#wxDesc").textContent = `${w.city} · ${desc}`;
  const fmt = new Intl.DateTimeFormat(I18N.lang, { weekday: "short" });
  $("#wxDays").innerHTML = (w.days || []).slice(0, 4).map((d) => {
    const dd = new Date(d.date + "T12:00");
    return `<div class="wx-day"><small>${esc(fmt.format(dd))}</small>${ico(d.icon)}<b>${sgn(d.max)}</b><i>${sgn(d.min)}</i></div>`;
  }).join("");
}

/* ───────────── таймеры, задачи, память, режимы ───────────── */
function renderStore(st) {
  if (!st) return;
  S.store = st;
  renderTimers();
  const tasks = st.tasks || [];
  $("#taskCount").textContent = tasks.length ? `${tasks.filter((t) => !t.done).length} / ${tasks.length}` : "";
  $("#tasks").innerHTML = tasks.length ? tasks.map((t) => `<label class="task ${t.done ? "done" : ""}" data-id="${t.id}">
     <input type="checkbox" ${t.done ? "checked" : ""}><span>${esc(t.text)}</span><button class="x" type="button" aria-label="✕">✕</button></label>`).join("")
    : `<div class="empty">${esc(T("empty.tasks"))}</div>`;
  const mem = st.memory || [];
  $("#memList").innerHTML = mem.length ? mem.map((m) => `<div class="mem" data-id="${m.id}"><input value="${esc(m.fact)}" aria-label="fact"><button class="x" aria-label="✕">✕</button></div>`).join("")
    : `<div class="empty">${esc(T("empty.memory"))}</div>`;
  const notes = (st.notes || []).slice().reverse();
  $("#noteList").innerHTML = notes.length ? notes.slice(0, 50).map((n) => `<div class="mem" data-id="${n.id}"><span>${esc(n.text)}</span><small>${new Date(n.created * 1000).toLocaleDateString(I18N.lang)}</small><button class="x" aria-label="✕">✕</button></div>`).join("")
    : `<div class="empty">${esc(T("empty.notes"))}</div>`;
  renderRoutines(st.routines || []);
  renderQuiet(st.quiet_until || 0);
}
$("#tasks").onclick = (e) => {
  const row = e.target.closest(".task"); if (!row) return;
  if (e.target.classList.contains("x")) { e.preventDefault(); send({ t: "task_delete", id: row.dataset.id }); }
  else if (e.target.tagName === "INPUT") send({ t: "task_toggle", id: row.dataset.id });
};
$("#taskForm").onsubmit = (e) => { e.preventDefault(); const v = $("#taskText").value.trim(); if (v) send({ t: "task_add", text: v }); $("#taskText").value = ""; };
$("#memList").onclick = (e) => { const row = e.target.closest(".mem"); if (row && e.target.classList.contains("x")) send({ t: "memory_delete", id: row.dataset.id }); };
$("#memList").addEventListener("change", (e) => { const row = e.target.closest(".mem"); if (row && e.target.tagName === "INPUT") send({ t: "memory_edit", id: row.dataset.id, text: e.target.value }); });
$("#noteList").onclick = (e) => { const row = e.target.closest(".mem"); if (row && e.target.classList.contains("x")) send({ t: "notes_delete", id: row.dataset.id }); };
$("#memAdd").onclick = () => { const v = $("#memNew").value.trim(); if (v) send({ t: "memory_add", text: v }); $("#memNew").value = ""; };
$("#memNew").onkeydown = (e) => { if (e.key === "Enter") $("#memAdd").click(); };
$("#memClear").onclick = () => { if (confirm(T("mem.clear_q"))) send({ t: "memory_clear" }); };
$("#histClear").onclick = () => send({ t: "history_clear" });

function fmtLeft(s) {
  s = Math.max(0, Math.round(s));
  const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60;
  return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(x).padStart(2, "0");
}
function renderTimers() {
  const ts = (S.store.timers || []).slice().sort((a, b) => a.due - b.due);
  $("#timerCount").textContent = ts.length || "";
  const now = Date.now() / 1000;
  $("#timers").innerHTML = ts.length ? ts.map((t) => {
    const left = t.due - now;
    const label = t.label || T("timer." + t.kind);
    const big = left > 86400 ? new Date(t.due * 1000).toLocaleDateString(I18N.lang, { day: "numeric", month: "short" }) :
      left > 3 * 3600 ? new Date(t.due * 1000).toLocaleTimeString(I18N.lang, { hour: "2-digit", minute: "2-digit" }) : fmtLeft(left);
    return `<div class="timer ${left < 60 ? "soon" : ""}" data-id="${t.id}"><span>${esc(label)}</span><b>${big}</b><button class="x" aria-label="✕">✕</button></div>`;
  }).join("") : `<div class="empty">${esc(T("empty.timers"))}</div>`;
}
$("#timers").onclick = (e) => { const row = e.target.closest(".timer"); if (row && e.target.classList.contains("x")) send({ t: "timer_cancel", id: row.dataset.id }); };
setInterval(renderTimers, 1000);

function stepText(x) {
  const vals = Object.values(x.args || {}).filter((v) => v !== "" && v !== null && v !== false).join(", ");
  return toolName(x.tool) + (vals ? ": " + vals : "");
}
function renderRoutines(rs) {
  $("#routineList").innerHTML = rs.length ? rs.map((r) => `<div class="rt" data-id="${r.id}"><div class="rt-body"><b>${esc(r.name)}</b>
     ${r.description ? `<small>${esc(r.description)}</small>` : ""}<ol>${r.steps.map((x) => `<li>${esc(stepText(x))}</li>`).join("")}</ol></div>
     <div class="hrow"><button class="btn" data-act="run">▶ ${esc(T("rt.run"))}</button><button class="round sm" data-act="del" aria-label="✕">✕</button></div></div>`).join("")
    : `<div class="empty">${esc(T("empty.routines"))}</div>`;
}
$("#routineList").onclick = (e) => {
  const b = e.target.closest("button"), row = e.target.closest(".rt"); if (!b || !row) return;
  if (b.dataset.act === "run") send({ t: "routine_run", id: row.dataset.id });
  if (b.dataset.act === "del" && confirm(T("rt.del_q"))) send({ t: "routine_delete", id: row.dataset.id });
};
function renderQuiet(until) {
  const on = until > Date.now() / 1000;
  const hm = on ? new Date(until * 1000).toLocaleTimeString(I18N.lang, { hour: "2-digit", minute: "2-digit" }) : "";
  $("#fQuiet").classList.toggle("hidden", !on); $("#fQuietT").textContent = hm;
  $("#quietInfo").textContent = on ? T("quiet.on", { t: hm }) : T("quiet.off");
}
setInterval(() => renderQuiet(S.store.quiet_until || 0), 30000);
$("#fQuiet").onclick = () => send({ t: "quiet", on: false });
$("#fWatch").onclick = () => send({ t: "watch", on: false });
$("#watchOn").onclick = () => { send({ t: "watch", on: true }); $("#setClose").click(); };
document.querySelectorAll("[data-quiet]").forEach((b) => b.onclick = () => { const m = +b.dataset.quiet; send(m ? { t: "quiet", on: true, minutes: m } : { t: "quiet", on: false }); });
function fillRtTools() { $("#rtTool").innerHTML = Object.keys(STEP_TPL).map((k) => `<option value="${k}">${esc(toolName(k))} (${k})</option>`).join(""); }
$("#rtAddStep").onclick = () => {
  const k = $("#rtTool").value;
  $("#rtSteps").insertAdjacentHTML("beforeend", `<div class="rt-step" data-tool="${k}"><b>${esc(toolName(k))}</b><input value='${esc(JSON.stringify(STEP_TPL[k]))}'><button class="x" aria-label="✕">✕</button></div>`);
};
$("#rtSteps").onclick = (e) => { if (e.target.classList.contains("x")) e.target.closest(".rt-step").remove(); };
$("#rtSave").onclick = () => {
  const steps = [...document.querySelectorAll(".rt-step")].map((r) => ({ tool: r.dataset.tool, args_json: r.querySelector("input").value }));
  const name = $("#rtName").value.trim();
  if (!name || !steps.length) { toast(T("rt.need")); return; }
  send({ t: "routine_save", data: { name, description: $("#rtDesc").value.trim(), steps } });
  $("#rtName").value = ""; $("#rtDesc").value = ""; $("#rtSteps").innerHTML = "";
};

/* ───────────── настройки ───────────── */
const F = {};
let formDirty = false;
const RANGES = ["wake_threshold", "wake_verify_threshold", "idle_timeout", "vad_silence_ms", "mic_gain", "card_autoclose",
  "proactive_gpu_temp", "proactive_battery", "proactive_disk_gb", "proactive_game_hours", "watch_interval", "watch_idle_timeout"];
const TOGGLES = ["open_window_on_start", "autostart", "autostart_window", "sounds", "show_system_panel", "show_weather_panel",
  "headphones", "headphones_auto", "confirm_dangerous", "proactive", "proactive_voice", "proactive_night", "morning_briefing",
  "telegram_enabled", "telegram_notify", "update_auto_check"];
const prettyKey = (c) => (c || "").split("+").map((k) => k.length === 1 ? k.toUpperCase() : k[0].toUpperCase() + k.slice(1)).join("+");
function langOptions(sel, cur, withAuto) {
  sel.innerHTML = (withAuto ? `<option value="auto">${esc(T("lang.auto"))}</option>` : "") +
    Object.entries(LANGS).map(([k, v]) => `<option value="${k}" ${k === cur ? "selected" : ""}>${v}</option>`).join("");
  if (withAuto && cur === "auto") sel.value = "auto";
}
function applySettings(st) {
  if (!st) return;
  S.settings = st;
  const c = st.config;
  S.brand = st.brand || "Sayro";
  $("#brandName").textContent = S.brand;  // заголовок окна не трогаем: по нему ядро находит окно
  applyAccent(c.accent); applyTheme(c.theme);
  document.body.classList.toggle("no-sys", c.show_system_panel === false);
  document.body.classList.toggle("no-wx", c.show_weather_panel === false);
  $("#setWakeThr").style.left = (c.wake_threshold * 100) + "%";
  if (I18N.lang !== (c.ui_language || "en")) loadLang(c.ui_language || "en");
  renderLicense(st.license || {});
  if (st.update) renderUpdate(st.update);
  $("#fTg").classList.toggle("hidden", !(st.telegram && st.telegram.ok && st.telegram.bound));
  $("#fWatch").classList.toggle("hidden", !st.watch);
  setState(S.state, S.detail);
  if (!$("#settings").classList.contains("hidden") && formDirty) { renderInfo(st); return; }
  fillForm(st);
}
function fillForm(st) {
  const c = st.config;
  Object.assign(F, JSON.parse(JSON.stringify(c)));
  for (const k of ["user_name", "city", "custom_instructions", "wake_engine", "wake_word", "clip_method", "discord_mute_key", "discord_deafen_key"]) { const el = $("#s_" + k); if (el) el.value = c[k] ?? ""; }
  for (const k of TOGGLES) $("#s_" + k).checked = !!c[k];
  for (const k of RANGES) { $("#s_" + k).value = c[k] ?? 0; $("#v_" + k).textContent = c[k] || (["card_autoclose", "proactive_game_hours"].includes(k) ? "—" : c[k]); }
  langOptions($("#s_ui_language"), c.ui_language || "en", false);
  langOptions($("#s_reply_language"), c.reply_language || "auto", true);
  document.querySelectorAll("#seg_theme button").forEach((b) => b.classList.toggle("on", b.dataset.v === (c.theme || "dark")));
  $("#s_hotkey").value = prettyKey(c.hotkey);
  $("#hsInfo").textContent = st.speaker.headset ? T("hs.headset", { name: st.speaker.name }) : T("hs.speakers", { brand: S.brand });
  $("#hkInfo").textContent = st.hotkey_ok === false ? T("hk.busy") : T("hk.info");
  $("#s_voice").innerHTML = Object.entries(st.voices).map(([k, v]) => `<option value="${k}" ${k === c.voice ? "selected" : ""}>${esc(k)} — ${esc(T("voice." + k))}</option>`).join("");
  $("#personaCards").innerHTML = Object.keys(st.personas).map((k) => { const [t, d] = T("persona." + k).split(" — "); return `<button data-v="${k}" class="${k === c.persona ? "on" : ""} ${k === "tutor" ? "lockable" : ""}"><b>${esc(t)}</b>${esc(d || "")}</button>`; }).join("");
  document.querySelectorAll("#seg_reply_length button").forEach((b) => b.classList.toggle("on", b.dataset.v === c.reply_length));
  $("#swatches").innerHTML = ACCENTS.map((h) => `<button data-v="${h}" style="background:${h};color:${h}" class="${h.toLowerCase() === (c.accent || "").toLowerCase() ? "on" : ""}" aria-label="${h}"></button>`).join("");
  const dev = (list, cur) => `<option value="">${esc(T("default_device"))}</option>` + list.map((d) => `<option value="${d.id}" ${d.id === cur ? "selected" : ""}>${esc(d.name)}</option>`).join("");
  $("#s_mic_device").innerHTML = dev(st.devices.inputs, c.mic_device); $("#s_speaker_device").innerHTML = dev(st.devices.outputs, c.speaker_device);
  $("#onbMicDev").innerHTML = $("#s_mic_device").innerHTML;
  const off = new Set(c.tools_disabled || []);
  $("#toolToggles").innerHTML = Object.entries(st.tool_groups).map(([k, v]) => `<label class="tgl"><span>${esc(T("tg_group." + k))}</span><input type="checkbox" data-g="${k}" ${off.has(k) ? "" : "checked"}><i></i></label>`).join("");
  renderApps(c.apps || {});
  $("#appsCount").textContent = st.apps_indexed;
  $("#sKeyInfo").textContent = c.has_key ? T("key.saved", { k: c.gemini_api_key }) : T("key.none");
  const mopt = (list, cur) => `<option value="">${esc(T("auto"))}</option>` + (list || []).map((m) => `<option ${m === cur ? "selected" : ""}>${m}</option>`).join("");
  $("#s_live_model").innerHTML = mopt(st.live_models, c.live_model); $("#s_text_model").innerHTML = mopt(st.all_text_models, c.text_model);
  $("#tgTokInfo").textContent = c.has_tg_token ? T("key.saved", { k: c.telegram_token }) : "";
  renderTg(st.telegram || {});
  fillRtTools();
  renderInfo(st);
  setDirty(false);
}
function renderInfo(st) {
  $("#sInfo").textContent = [
    `${T("info.voice")} ${st.live_model || "—"}`,
    `${T("info.text")} ${(st.text_models || [])[0] || "—"}`,
    `${T("info.wake")} ${st.wake.status || st.wake.engine}`,
    `${T("info.mic")} ${st.mic.ok ? st.mic.name : T("info.none_mic")}`,
    `${T("info.spk")} ${st.speaker.ok ? st.speaker.name : T("info.none_mic")}`,
    `${T("info.apps")} ${st.apps_indexed} / ${st.files_indexed}`,
    `${T("info.autostart")} ${st.autostart_real ? T("info.on") : T("info.off")}`,
    st.live_error ? `${T("info.err")} ${st.live_error}` : "",
    `${T("info.addr")} http://127.0.0.1:${st.port}`,
  ].filter(Boolean).join("\n");
}
function renderApps(apps) {
  const rows = Object.entries(apps);
  $("#appsTable").innerHTML = (rows.length ? rows : [["", ""]]).map(([k, v]) => `<div class="apps-row"><input class="an" value="${esc(k)}" placeholder="${esc(T("apps.name_ph"))}">
    <input class="ap" value="${esc(v)}" placeholder="${esc(T("apps.path_ph"))}"><button class="x" aria-label="✕">✕</button></div>`).join("");
}
function collectApps() {
  const o = {};
  document.querySelectorAll(".apps-row").forEach((r) => { const k = r.querySelector(".an").value.trim(), v = r.querySelector(".ap").value.trim(); if (k && v) o[k] = v; });
  return o;
}
function setDirty(d) { formDirty = d; $("#setDirty").textContent = d ? T("settings.dirty") : ""; }
$("#settings").addEventListener("input", () => setDirty(true));
$("#settings").addEventListener("change", () => setDirty(true));
document.querySelectorAll(".set-nav button").forEach((b) => b.onclick = () => openTab(b.dataset.tab));
function openTab(tab) {
  document.querySelectorAll(".set-nav button").forEach((x) => x.classList.toggle("on", x.dataset.tab === tab));
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("on", t.dataset.tab === tab));
  const b = document.querySelector(`.set-nav button[data-tab=${tab}]`);
  $("#setTitle").textContent = b ? b.querySelector("span").textContent : "";
}
for (const k of RANGES) $("#s_" + k).addEventListener("input", (e) => { $("#v_" + k).textContent = e.target.value; if (k === "wake_threshold") $("#setWakeThr").style.left = e.target.value * 100 + "%"; });
$("#personaCards").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; F.persona = b.dataset.v; document.querySelectorAll("#personaCards button").forEach((x) => x.classList.toggle("on", x === b)); setDirty(true); };
$("#seg_reply_length").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; F.reply_length = b.dataset.v; document.querySelectorAll("#seg_reply_length button").forEach((x) => x.classList.toggle("on", x === b)); setDirty(true); };
$("#seg_theme").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; F.theme = b.dataset.v; applyTheme(F.theme); document.querySelectorAll("#seg_theme button").forEach((x) => x.classList.toggle("on", x === b)); setDirty(true); };
$("#s_ui_language").onchange = (e) => { F.ui_language = e.target.value; loadLang(F.ui_language); setDirty(true); };
$("#swatches").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; F.accent = b.dataset.v; applyAccent(F.accent); document.querySelectorAll("#swatches button").forEach((x) => x.classList.toggle("on", x === b)); setDirty(true); };
$("#appAdd").onclick = () => { const o = collectApps(); renderApps(o); $("#appsTable").insertAdjacentHTML("beforeend", `<div class="apps-row"><input class="an" placeholder="${esc(T("apps.name_ph"))}"><input class="ap" placeholder="${esc(T("apps.path_ph"))}"><button class="x" aria-label="✕">✕</button></div>`); };
$("#appsTable").onclick = (e) => { if (e.target.classList.contains("x")) { e.target.closest(".apps-row").remove(); setDirty(true); } };
$("#appTestBtn").onclick = () => send({ t: "find_app", q: $("#appTest").value });
const hk = $("#s_hotkey");
hk.onfocus = () => { hk.classList.add("rec"); hk.value = T("hk.rec"); };
hk.onblur = () => { hk.classList.remove("rec"); hk.value = prettyKey(F.hotkey); };
hk.onkeydown = (e) => {
  e.preventDefault();
  const k = e.key.toLowerCase();
  if (["control", "alt", "shift", "meta"].includes(k)) return;
  const mods = [e.ctrlKey && "ctrl", e.altKey && "alt", e.shiftKey && "shift", e.metaKey && "win"].filter(Boolean);
  const key = e.code.startsWith("Key") ? e.code.slice(3).toLowerCase() : e.code.startsWith("Digit") ? e.code.slice(5) : /^F\d+$/.test(e.code) ? e.code.toLowerCase() : e.code === "Space" ? "space" : null;
  if (!key || !mods.length) { $("#hkInfo").textContent = T("hk.need_mod"); return; }
  F.hotkey = [...mods, key].join("+"); hk.value = prettyKey(F.hotkey); hk.blur(); setDirty(true);
};
$("#hkReset").onclick = () => { F.hotkey = "ctrl+alt+j"; hk.value = prettyKey(F.hotkey); setDirty(true); };
$("#dQuick").onclick = () => send({ t: "selftest", full: false });
$("#dFull").onclick = () => send({ t: "selftest", full: true });
document.querySelectorAll("[data-open]").forEach((b) => b.onclick = () => send({ t: "open_path", what: b.dataset.open }));
$("#dRestart").onclick = () => send({ t: "restart" });
$("#dQuit").onclick = () => { if (confirm(T("quit_q"))) send({ t: "quit" }); };
$("#sSnd").onclick = () => send({ t: "test_sound" });
$("#setBtn").onclick = () => { if (S.settings) fillForm(S.settings); $("#settings").classList.remove("hidden"); };
$("#setClose").onclick = () => {
  $("#settings").classList.add("hidden");
  if (formDirty && S.settings) { const c = S.settings.config; applyAccent(c.accent); applyTheme(c.theme); if (I18N.lang !== c.ui_language) loadLang(c.ui_language); }
  setDirty(false);
};
$("#settings").onclick = (e) => { if (e.target.id === "settings") $("#setClose").click(); };
$("#sTest").onclick = () => { saveSettings(false); setTimeout(() => send({ t: "test_voice" }), 400); };
function saveSettings(close = true) {
  const v = (id) => $(id).value;
  const data = {
    user_name: v("#s_user_name").trim(), city: v("#s_city").trim(), ui_language: v("#s_ui_language"), theme: F.theme,
    open_window_on_start: $("#s_open_window_on_start").checked, autostart: $("#s_autostart").checked, autostart_window: $("#s_autostart_window").checked,
    sounds: $("#s_sounds").checked, show_system_panel: $("#s_show_system_panel").checked, show_weather_panel: $("#s_show_weather_panel").checked,
    accent: F.accent, voice: v("#s_voice"), persona: F.persona, reply_length: F.reply_length, reply_language: v("#s_reply_language"),
    custom_instructions: v("#s_custom_instructions"), wake_engine: v("#s_wake_engine"), wake_word: v("#s_wake_word"),
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

/* ───────────── Telegram ───────────── */
function renderTg(t) {
  let h;
  if (!t.on) h = `<span class="mut">${esc(T("tg.off"))}</span>`;
  else if (t.error) h = "⚠ " + esc(t.error);
  else if (!t.ok) h = esc(T("tg.connecting"));
  else if (!t.bound) h = `${esc(T("tg.pair", { bot: t.bot }))}<span class="code">${esc(t.code)}</span>`;
  else h = esc(T("tg.ok", { bot: t.bot }));
  $("#tgStatus").innerHTML = h;
}
$("#tgTest").onclick = () => send({ t: "tg_test" });
$("#tgUnlink").onclick = () => { if (confirm(T("tg.unlink_q"))) send({ t: "tg_unlink" }); };

/* ───────────── Pro ───────────── */
function renderLicense(l) {
  const pro = !!l.pro;
  S.pro = pro;
  document.body.classList.toggle("free", !pro);
  $("#proBadge").classList.toggle("hidden", !pro);
  $("#proCard").classList.toggle("on", pro);
  const trial = l.kind === "trial";
  $("#proStatus").textContent = !pro ? T("pro.free") : trial ? T("pro.trial", { d: l.trial_days_left }) : T("pro.active");
  const exp = l.expires && !trial ? T("pro.until", { d: new Date(l.expires * 1000).toLocaleDateString(I18N.lang) }) : "";
  $("#proSub").textContent = !pro ? T("pro.free_sub") : trial ? T("pro.trial_sub")
    : (l.name ? T("pro.lic", { n: l.name }) : "") + exp + (l.kind === "gumroad" ? T("pro.by_gumroad") : l.kind === "offline" ? T("pro.by_key") : "");
  $("#proBuy").classList.toggle("hidden", !l.buy_url || (pro && !trial)); if (l.buy_url) $("#proBuy").href = l.buy_url;
  $("#proNoShop").classList.toggle("hidden", !!l.buy_url || (pro && !trial));
  $("#licDel").classList.toggle("hidden", !l.has_key);
  $("#licInfo").textContent = l.error ? "⚠ " + l.error : l.has_key ? T("pro.key_saved") : "";
}
$("#licAct").onclick = () => { const k = $("#licKey").value.trim(); if (!k) return; $("#licInfo").textContent = T("pro.checking"); send({ t: "license_activate", key: k }); $("#licKey").value = ""; };
$("#licDel").onclick = () => { if (confirm(T("pro.del_q"))) send({ t: "license_activate", key: "" }); };

/* ───────────── обновления ───────────── */
function renderUpdate(u) {
  if (!u || !u.current) return;
  S.update = u;
  $("#fUpd").classList.toggle("hidden", !u.available); $("#fUpdV").textContent = u.latest || "";
  $("#updInstall").classList.toggle("hidden", !u.available);
  $("#updTitle").innerHTML = esc(T("up.version", { v: u.current })) + (u.url ? ` <a class="mut" href="${esc(u.url)}" target="_blank">github.com/${esc(u.repo || "")}</a>` : "");
  const when = u.checked ? new Date(u.checked * 1000).toLocaleTimeString(I18N.lang, { hour: "2-digit", minute: "2-digit" }) : "";
  $("#updState").textContent = u.available ? T("up.available", { v: u.latest, d: u.published || "" }) : u.error ? "— " + u.error : u.checked ? T("up.latest", { t: when }) : "";
  $("#updNotes").innerHTML = u.available && u.notes ? `<b>${esc(T("up.whats_new", { v: u.latest }))}</b>` + md(u.notes) : "";
}
function installUpdate() {
  const u = S.update || {};
  if (!u.available || !confirm(T("up.confirm", { v: u.latest }))) return;
  send({ t: "update_install" });
  $("#fUpd").textContent = T("up.updating");
}
$("#fUpd").onclick = installUpdate;
$("#updInstall").onclick = installUpdate;
$("#updCheck").onclick = () => { $("#updState").textContent = T("up.checking"); send({ t: "update_check" }); };

/* ───────────── первый запуск ───────────── */
let onbStep = 0, onbChoice = "pro", onbKeyOk = false;
function maybeOnboarding() {
  const c = S.settings?.config; if (!c || S.onbShown) return;
  if (!c.onboarding_done || !c.has_key) openOnboarding(c.has_key ? 0 : 0);
}
function openOnboarding(step = 0) {
  S.onbShown = true;
  const c = S.settings?.config || {};
  langOptions($("#onbLang"), c.ui_language || I18N.lang || "en", false);
  $("#onbName").value = c.user_name || ""; $("#onbCity").value = c.city || "";
  onbKeyOk = !!c.has_key;
  $("#onb").classList.remove("hidden");
  showOnbStep(step);
}
function showOnbStep(n) {
  onbStep = n;
  document.querySelectorAll(".onb-step").forEach((s) => s.classList.toggle("on", +s.dataset.step === n));
  document.querySelectorAll("#onbBar i").forEach((b, i) => b.classList.toggle("on", i <= n));
  $("#onbBack").style.visibility = n ? "visible" : "hidden";
  $("#onbNext").textContent = n === 3 ? T("onb.finish") : T("btn.continue");
  $("#onbErr").textContent = "";
  if (n === 2) {
    $("#onbHow").innerHTML = T(onbChoice === "pro" ? "onb.how_pro" : "onb.how_key").split("|").map((l) => `<li>${esc(l.replace(/^\d+\.\s*/, ""))}</li>`).join("");
    $("#onbCreditsLink").classList.toggle("hidden", onbChoice !== "pro");
    $("#onbKeyInfo").textContent = S.settings?.config?.has_key ? T("key.saved", { k: S.settings.config.gemini_api_key }) : "";
  }
}
$("#onbLang").onchange = (e) => { loadLang(e.target.value); send({ t: "settings", data: { ui_language: e.target.value }, silent: true }); };
$("#onbChoices").onclick = (e) => { const b = e.target.closest(".choice"); if (!b || b.disabled) return; onbChoice = b.dataset.v; document.querySelectorAll(".choice").forEach((x) => x.classList.toggle("on", x === b)); };
$("#onbBack").onclick = () => showOnbStep(Math.max(0, onbStep - 1));
$("#onbNext").onclick = () => {
  if (onbStep === 2) {
    const k = $("#onbKey").value.trim();
    if (!k && !onbKeyOk) { $("#onbErr").textContent = T("onb.need_key"); return; }
    if (k) { $("#onbErr").textContent = T("onb.checking"); $("#onbNext").disabled = true; send({ t: "key_check", key: k }); return; }
  }
  if (onbStep === 0) send({ t: "settings", data: { user_name: $("#onbName").value.trim(), city: $("#onbCity").value.trim() }, silent: true });
  if (onbStep === 3) {
    send({ t: "settings", data: { onboarding_done: true, mic_device: $("#onbMicDev").value }, silent: true });
    $("#onb").classList.add("hidden");
    return;
  }
  showOnbStep(onbStep + 1);
};
function onKeyCheck(m) {
  $("#onbNext").disabled = false;
  if (m.ok) { onbKeyOk = true; $("#onbKey").value = ""; $("#onbKeyInfo").textContent = T("onb.key_ok"); showOnbStep(3); }
  else $("#onbErr").textContent = T("onb.key_bad", { e: m.error || "" });
}
$("#onbAgain").onclick = () => { $("#settings").classList.add("hidden"); openOnboarding(1); };

/* ───────────── ввод ───────────── */
$("#form").onsubmit = (e) => { e.preventDefault(); const v = $("#text").value.trim(); if (!v) return; send({ t: "text", text: v }); $("#text").value = ""; };
$("#stopBtn").onclick = () => send({ t: "stop" });
$("#micBtn").onclick = () => { S.mic = !S.mic; send({ t: "mic", on: S.mic }); $("#micBtn").classList.toggle("off", !S.mic); };
$("#orbWrap").onclick = () => send({ t: "activate" });
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { closeCard(); $("#alert").classList.add("hidden"); if (!$("#settings").classList.contains("hidden")) $("#setClose").click(); }
  if (e.key === "/" && !["INPUT", "TEXTAREA"].includes(document.activeElement.tagName)) { e.preventDefault(); $("#text").focus(); }
});

/* ───────────── загрузка ───────────── */
function boot() { if (S.booted) return; S.booted = true; setTimeout(() => $("#boot").classList.add("done"), 350); }
setTimeout(() => $("#boot").classList.add("done"), 5000);

loadLang("en").then(connect);
