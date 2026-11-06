//! Oswin.exe — оболочка приложения (Rust): одна копия на пользователя, ядро (pythonw jarvis.py) — дочерний
//! процесс, окно интерфейса — WebView2. Протокол с ядром описан в core/host.py.
//!
//! Коды выхода ядра: 0 — пользователь вышел (или ставится обновление: update_helper сам запустит Oswin.exe заново),
//! 3 — «перезапусти меня», остальное — сбой (перезапуск, но не больше 3 раз за 2 минуты).
#![windows_subsystem = "windows"]

use std::env;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::os::windows::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use tao::dpi::{LogicalSize, PhysicalPosition, PhysicalSize};
use tao::event::{Event, WindowEvent};
use tao::event_loop::{ControlFlow, EventLoopBuilder, EventLoopProxy};
use tao::platform::windows::{IconExtWindows, WindowBuilderExtWindows};
use tao::window::{Icon, Theme, Window, WindowBuilder};
use wry::{WebContext, WebView, WebViewBuilder};

const NO_WINDOW: u32 = 0x0800_0000;
const RESTART_CODE: i32 = 3;
const TITLE: &str = "Oswin"; // brand.WINDOW_TITLE — по нему ядро узнаёт своё окно
const APP_ID: &str = "oswin.assistant"; // AppUserModelID ярлыков установщика

#[derive(Debug, Clone)]
enum Ev {
    Show,
    Quit,
}

fn base() -> PathBuf {
    env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(Path::to_path_buf))
        .unwrap_or_else(|| PathBuf::from("."))
}

fn log(msg: &str) {
    let d = base().join("data");
    let _ = fs::create_dir_all(&d);
    let t = SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0);
    if let Ok(mut f) = OpenOptions::new().create(true).append(true).open(d.join("host.log")) {
        let _ = writeln!(f, "{t} {msg}");
    }
}

fn wide(s: &str) -> Vec<u16> {
    s.encode_utf16().chain(std::iter::once(0)).collect()
}

fn message_box(text: &str) {
    use windows_sys::Win32::UI::WindowsAndMessaging::{MessageBoxW, MB_ICONERROR, MB_OK};
    let (t, c) = (wide(text), wide(TITLE));
    unsafe {
        MessageBoxW(std::ptr::null_mut(), t.as_ptr(), c.as_ptr(), MB_OK | MB_ICONERROR);
    }
}

/// true — мы первая копия. Мьютекс живёт до конца процесса.
fn single_instance() -> bool {
    use windows_sys::Win32::Foundation::{GetLastError, ERROR_ALREADY_EXISTS};
    use windows_sys::Win32::System::Threading::CreateMutexW;
    let name = wide("Local\\OswinHost");
    unsafe {
        let h = CreateMutexW(std::ptr::null(), 0, name.as_ptr());
        !(h.is_null() || GetLastError() == ERROR_ALREADY_EXISTS)
    }
}

fn host_info() -> Option<(u16, String)> {
    let raw = fs::read_to_string(base().join("data").join("host.json")).ok()?;
    let v: serde_json::Value = serde_json::from_str(&raw).ok()?;
    Some((v["port"].as_u64()? as u16, v["token"].as_str()?.to_string()))
}

/// Вторая копия: попросить работающую показать окно.
fn forward_show() {
    for _ in 0..40 {
        if let Some((port, _)) = host_info() {
            let ok = ureq::post(&format!("http://127.0.0.1:{port}/show"))
                .timeout(Duration::from_secs(2))
                .call()
                .is_ok();
            if ok {
                return;
            }
        }
        thread::sleep(Duration::from_millis(250));
    }
}

fn token() -> String {
    let n = SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_nanos()).unwrap_or(0);
    format!("{:x}{:x}", n, std::process::id())
}

fn python() -> Option<PathBuf> {
    let s = base().join(".venv").join("Scripts");
    ["pythonw.exe", "python.exe"].iter().map(|n| s.join(n)).find(|p| p.exists())
}

/// Запускает ядро и следит за ним.
fn supervise(proxy: EventLoopProxy<Ev>, token: String, mut args: Vec<String>) {
    let Some(py) = python() else {
        log("нет .venv\\Scripts\\pythonw.exe");
        message_box("Oswin is damaged: Python runtime not found. Please reinstall Oswin.");
        let _ = proxy.send_event(Ev::Quit);
        return;
    };
    let mut crashes: Vec<Instant> = Vec::new();
    loop {
        let _ = fs::remove_file(base().join("data").join("host.json"));
        let child = Command::new(&py)
            .arg(base().join("jarvis.py"))
            .args(&args)
            .current_dir(base())
            .env("OSWIN_HOST_TOKEN", &token)
            .creation_flags(NO_WINDOW)
            .spawn();
        let mut child = match child {
            Ok(c) => c,
            Err(e) => {
                log(&format!("не запустилось ядро: {e}"));
                message_box("Oswin could not start. Please reinstall Oswin.");
                let _ = proxy.send_event(Ev::Quit);
                return;
            }
        };
        log(&format!("ядро запущено, pid {}", child.id()));
        let code = child.wait().ok().and_then(|s| s.code()).unwrap_or(-1);
        log(&format!("ядро завершилось, код {code}"));
        args.retain(|a| a != "--autostart" && a != "--no-window"); // после перезапуска — как обычный запуск
        match code {
            0 => {
                let _ = proxy.send_event(Ev::Quit);
                return;
            }
            RESTART_CODE => continue,
            _ => {
                let now = Instant::now();
                crashes.retain(|t| now.duration_since(*t) < Duration::from_secs(120));
                crashes.push(now);
                if crashes.len() >= 3 {
                    message_box("Oswin stopped unexpectedly several times. Details: data\\jarvis.log in the Oswin folder.");
                    let _ = proxy.send_event(Ev::Quit);
                    return;
                }
                thread::sleep(Duration::from_secs(2));
            }
        }
    }
}

/// Долгий опрос команд ядра (GET /host/next).
fn poll_commands(proxy: EventLoopProxy<Ev>, token: String, port: Arc<Mutex<Option<u16>>>) {
    let agent = ureq::AgentBuilder::new().timeout(Duration::from_secs(35)).build();
    loop {
        match host_info() {
            Some((p, t)) if t == token => {
                *port.lock().unwrap() = Some(p);
                let r = agent.get(&format!("http://127.0.0.1:{p}/host/next")).query("token", &token).call();
                match r.ok().and_then(|r| r.into_string().ok()) {
                    Some(body) => {
                        if body.contains("\"show\"") && proxy.send_event(Ev::Show).is_err() {
                            return;
                        }
                    }
                    None => thread::sleep(Duration::from_millis(400)),
                }
            }
            _ => thread::sleep(Duration::from_millis(200)),
        }
    }
}

fn set_app_id() {
    use windows_sys::Win32::UI::Shell::SetCurrentProcessExplicitAppUserModelID;
    let id = wide(APP_ID);
    unsafe {
        SetCurrentProcessExplicitAppUserModelID(id.as_ptr());
    }
}

fn main() {
    let args: Vec<String> = env::args().skip(1).collect();
    if !single_instance() {
        forward_show();
        return;
    }
    set_app_id();
    log(&format!("Oswin.exe {} запущен {:?}", env!("CARGO_PKG_VERSION"), args));

    let event_loop = EventLoopBuilder::<Ev>::with_user_event().build();
    let proxy = event_loop.create_proxy();
    let token = token();
    let port: Arc<Mutex<Option<u16>>> = Arc::new(Mutex::new(None));
    {
        let (p, t) = (proxy.clone(), token.clone());
        thread::spawn(move || supervise(p, t, args));
    }
    {
        let (p, t, pt) = (proxy.clone(), token.clone(), port.clone());
        thread::spawn(move || poll_commands(p, t, pt));
    }

    let mut ctx = WebContext::new(Some(base().join("data").join("webview")));
    let mut ui: Option<(WebView, Window)> = None; // сначала WebView, потом окно (порядок удаления)

    event_loop.run(move |event, target, control_flow| {
        *control_flow = ControlFlow::Wait;
        match event {
            Event::UserEvent(Ev::Show) => {
                if let Some((_, w)) = &ui {
                    w.set_visible(true);
                    w.set_minimized(false);
                    w.set_focus();
                    return;
                }
                let Some(p) = *port.lock().unwrap() else { return };
                let icon = Icon::from_resource(1, None).ok();
                let mut b = WindowBuilder::new()
                    .with_title(TITLE)
                    .with_min_inner_size(LogicalSize::new(860.0, 560.0))
                    .with_window_icon(icon.clone())
                    .with_taskbar_icon(icon)
                    .with_theme(None::<Theme>);
                let mut pos = None;
                if let Some(m) = target.primary_monitor() {
                    let ms = m.size();
                    let (w, h) = ((ms.width as f64 * 0.72) as u32, (ms.height as f64 * 0.78) as u32);
                    b = b.with_inner_size(PhysicalSize::new(w, h));
                    let mp = m.position();
                    pos = Some(PhysicalPosition::new(
                        mp.x + (ms.width as i32 - w as i32) / 2,
                        mp.y + (ms.height as i32 - h as i32) / 2 - 20,
                    ));
                } else {
                    b = b.with_inner_size(LogicalSize::new(1280.0, 820.0));
                }
                let window = match b.build(target) {
                    Ok(w) => w,
                    Err(e) => {
                        log(&format!("окно: {e}"));
                        return;
                    }
                };
                if let Some(p) = pos {
                    window.set_outer_position(p);
                }
                let dark = window.theme() == Theme::Dark;
                let bg = if dark { (22, 22, 24, 255) } else { (245, 245, 247, 255) };
                let wv = WebViewBuilder::new_with_web_context(&mut ctx)
                    .with_url(format!("http://127.0.0.1:{p}/"))
                    .with_background_color(bg)
                    .build(&window);
                match wv {
                    Ok(wv) => {
                        window.set_focus();
                        ui = Some((wv, window));
                        log("окно открыто");
                    }
                    Err(e) => {
                        log(&format!("WebView2: {e}"));
                        message_box("Oswin needs Microsoft Edge WebView2 Runtime. Install it from microsoft.com/edge/webview2 and start Oswin again.");
                    }
                }
            }
            Event::UserEvent(Ev::Quit) => {
                ui = None;
                *control_flow = ControlFlow::Exit;
            }
            Event::WindowEvent { event: WindowEvent::CloseRequested, .. } => {
                ui = None; // закрыли окно — ядро продолжает слушать в фоне (значок в трее)
                log("окно закрыто");
            }
            _ => {}
        }
    });
}
