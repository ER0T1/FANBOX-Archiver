use std::{
    env, fs,
    net::{TcpListener, TcpStream},
    path::{Path, PathBuf},
    sync::Mutex,
    thread,
    time::{Duration, Instant},
};

use serde::{Deserialize, Serialize};
use tauri::{
    AppHandle, Manager, RunEvent, Url,
    menu::{MenuBuilder, SubmenuBuilder},
};
use tauri_plugin_shell::{
    ShellExt,
    process::{CommandChild, CommandEvent},
};

const STATE_FILE: &str = "desktop-state.json";
const DEFAULT_CONFIG_FILE: &str = "config.yaml";
const IMPORTED_CONFIG_FILE: &str = "imported-config.yaml";
const CHANGE_ARCHIVE_MENU_ID: &str = "change-archive";

struct DesktopState {
    directory: PathBuf,
    onboarding_url: Url,
    process: Mutex<Option<CommandChild>>,
}

#[derive(Debug, Deserialize, Serialize)]
struct SavedDesktopState {
    config_path: PathBuf,
}

#[derive(Debug, Serialize)]
struct DesktopLaunch {
    config_path: String,
}

fn reserve_port() -> Result<u16, Box<dyn std::error::Error>> {
    let listener = TcpListener::bind(("127.0.0.1", 0))?;
    let port = listener.local_addr()?.port();
    drop(listener);
    Ok(port)
}

fn desktop_state_directory(app: &tauri::App) -> Result<PathBuf, Box<dyn std::error::Error>> {
    let directory = env::var_os("FANBOX_ARCHIVER_DESKTOP_STATE_DIR")
        .map(PathBuf::from)
        .map(Ok)
        .unwrap_or_else(|| app.path().app_config_dir())?;
    fs::create_dir_all(&directory)?;
    Ok(directory)
}

fn find_saved_config(directory: &Path) -> Option<PathBuf> {
    let state = fs::read_to_string(directory.join(STATE_FILE)).ok()?;
    let saved: SavedDesktopState = serde_json::from_str(&state).ok()?;
    saved.config_path.is_file().then_some(saved.config_path)
}

fn automatic_config(directory: &Path) -> Result<Option<PathBuf>, Box<dyn std::error::Error>> {
    if let Some(path) = env::var_os("FANBOX_ARCHIVER_CONFIG") {
        let path = PathBuf::from(path);
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        if !path.exists() {
            fs::write(&path, "{}\n")?;
        }
        return Ok(Some(path));
    }
    Ok(find_saved_config(directory))
}

fn remember_config(directory: &Path, config_path: &Path) -> Result<(), String> {
    let state = SavedDesktopState {
        config_path: config_path.to_path_buf(),
    };
    let json = serde_json::to_string_pretty(&state).map_err(|error| error.to_string())?;
    fs::write(directory.join(STATE_FILE), format!("{json}\n")).map_err(|error| error.to_string())
}

fn clear_saved_config(directory: &Path) -> Result<(), String> {
    let state_file = directory.join(STATE_FILE);
    if state_file.exists() {
        fs::remove_file(state_file).map_err(|error| error.to_string())?;
    }
    Ok(())
}

fn show_launch_error(window: &tauri::WebviewWindow, message: &str) {
    let message = serde_json::to_string(message)
        .unwrap_or_else(|_| "\"本機伺服器未在 20 秒內回應，請查看應用程式日誌。\"".to_owned());
    let _ = window.show();
    let _ = window.eval(format!(
        "document.body.className='desktop-bootstrap';document.body.innerHTML='<main class=\"desktop-onboarding desktop-error\"><section class=\"desktop-intro\"><p class=\"eyebrow\">STARTUP RECOVERY</p><h1>本機伺服器無法啟動</h1><p>設定檔可能已移動、內容無效，或封存位置目前無法存取。</p></section><p id=\"launch-error\" class=\"desktop-status error\"></p><div class=\"desktop-error-actions\"><button id=\"retry-selection\" type=\"button\" class=\"primary\">重新選擇封存</button><small>既有設定檔、資料庫與投稿不會被刪除。</small></div></main>';document.getElementById('launch-error').textContent={message};document.getElementById('retry-selection').addEventListener('click',async function(){{this.disabled=true;this.textContent='正在返回選擇頁…';try{{await window.__TAURI__.core.invoke('reset_desktop_selection')}}catch(error){{this.disabled=false;this.textContent='重新選擇封存';document.getElementById('launch-error').textContent=String(error)}}}});"
    ));
}

fn launch_sidecar(app: &AppHandle, config: &Path) -> Result<DesktopLaunch, String> {
    let state = app.state::<DesktopState>();
    let mut process = state.process.lock().map_err(|error| error.to_string())?;
    if process.is_some() {
        return Err("本機伺服器已經在執行。".to_owned());
    }

    let port = reserve_port().map_err(|error| error.to_string())?;
    let config = config.to_path_buf();
    let arguments = vec![
        "serve".to_owned(),
        "--no-open".to_owned(),
        "--port".to_owned(),
        port.to_string(),
        "--config".to_owned(),
        config.to_string_lossy().into_owned(),
    ];
    let (mut events, child) = app
        .shell()
        .sidecar("fanbox-archiver-sidecar")
        .map_err(|error| error.to_string())?
        .args(arguments)
        .spawn()
        .map_err(|error| error.to_string())?;
    tauri::async_runtime::spawn(async move {
        while let Some(event) = events.recv().await {
            match event {
                CommandEvent::Stdout(line) => {
                    log::info!("sidecar: {}", String::from_utf8_lossy(&line).trim());
                }
                CommandEvent::Stderr(line) => {
                    let message = String::from_utf8_lossy(&line);
                    let message = message.trim();
                    if message.contains("ERROR") || message.contains("CRITICAL") {
                        log::error!("sidecar: {message}");
                    } else {
                        log::info!("sidecar: {message}");
                    }
                }
                CommandEvent::Error(error) => log::error!("sidecar: {error}"),
                CommandEvent::Terminated(payload) => {
                    log::info!("sidecar terminated with code {:?}", payload.code);
                }
                _ => {}
            }
        }
    });
    *process = Some(child);
    drop(process);

    let window = app
        .get_webview_window("main")
        .ok_or_else(|| "找不到主視窗".to_owned())?;
    let url = format!("http://127.0.0.1:{port}/");
    thread::spawn(move || {
        let deadline = Instant::now() + Duration::from_secs(20);
        while Instant::now() < deadline {
            if TcpStream::connect(("127.0.0.1", port)).is_ok() {
                if let Ok(parsed) = url.parse() {
                    let _ = window.navigate(parsed);
                    let _ = window.show();
                }
                return;
            }
            thread::sleep(Duration::from_millis(100));
        }
        show_launch_error(&window, "本機伺服器未在 20 秒內回應，請查看應用程式日誌。");
    });

    Ok(DesktopLaunch {
        config_path: config.to_string_lossy().into_owned(),
    })
}

fn save_and_launch(app: &AppHandle, config: &Path) -> Result<DesktopLaunch, String> {
    let state = app.state::<DesktopState>();
    remember_config(&state.directory, config)?;
    drop(state);
    launch_sidecar(app, config)
}

#[tauri::command]
fn choose_existing_config(app: AppHandle) -> Result<Option<DesktopLaunch>, String> {
    let Some(path) = rfd::FileDialog::new()
        .add_filter("YAML 設定檔", &["yaml", "yml"])
        .pick_file()
    else {
        return Ok(None);
    };
    if !path.is_file() {
        return Err("選擇的設定檔不存在。".to_owned());
    }
    save_and_launch(&app, &path).map(Some)
}

#[tauri::command]
fn choose_archive_folder(app: AppHandle) -> Result<Option<DesktopLaunch>, String> {
    let Some(folder) = rfd::FileDialog::new().pick_folder() else {
        return Ok(None);
    };
    let state = app.state::<DesktopState>();
    let config_path = state.directory.join(IMPORTED_CONFIG_FILE);
    let config = serde_json::json!({
        "storage": {
            "output_dir": folder,
            "database": folder.join("backup.db"),
        }
    });
    let contents = serde_json::to_string_pretty(&config).map_err(|error| error.to_string())?;
    fs::write(&config_path, format!("{contents}\n")).map_err(|error| error.to_string())?;
    drop(state);
    save_and_launch(&app, &config_path).map(Some)
}

#[tauri::command]
fn use_default_config(app: AppHandle) -> Result<Option<DesktopLaunch>, String> {
    let state = app.state::<DesktopState>();
    let config_path = state.directory.join(DEFAULT_CONFIG_FILE);
    if !config_path.exists() {
        fs::write(&config_path, "{}\n").map_err(|error| error.to_string())?;
    }
    drop(state);
    save_and_launch(&app, &config_path).map(Some)
}

#[tauri::command]
fn reset_desktop_selection(app: AppHandle) -> Result<(), String> {
    show_archive_selection(&app)
}

fn stop_sidecar(app: &AppHandle) {
    if let Some(state) = app.try_state::<DesktopState>() {
        if let Ok(mut process) = state.process.lock() {
            if let Some(child) = process.take() {
                let _ = child.kill();
            }
        }
    }
}

fn show_archive_selection(app: &AppHandle) -> Result<(), String> {
    stop_sidecar(app);
    let state = app.state::<DesktopState>();
    clear_saved_config(&state.directory)?;
    let onboarding_url = state.onboarding_url.clone();
    drop(state);

    let window = app
        .get_webview_window("main")
        .ok_or_else(|| "找不到主視窗".to_owned())?;
    window
        .navigate(onboarding_url)
        .map_err(|error| error.to_string())?;
    window.show().map_err(|error| error.to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let application = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .menu(|app| {
            let archive_menu = SubmenuBuilder::new(app, "封存")
                .text(CHANGE_ARCHIVE_MENU_ID, "變更封存位置…")
                .build()?;
            MenuBuilder::new(app).item(&archive_menu).build()
        })
        .on_menu_event(|app, event| {
            if event.id() == CHANGE_ARCHIVE_MENU_ID {
                if let Err(error) = show_archive_selection(app) {
                    log::error!("無法顯示封存選擇頁：{error}");
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            choose_existing_config,
            choose_archive_folder,
            use_default_config,
            reset_desktop_selection
        ])
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            let window = app.get_webview_window("main").ok_or("找不到主視窗")?;
            let onboarding_url = window.url()?;
            let directory = desktop_state_directory(app)?;
            let config = automatic_config(&directory)?;
            app.manage(DesktopState {
                directory,
                onboarding_url,
                process: Mutex::new(None),
            });

            if let Some(config) = config {
                launch_sidecar(app.handle(), &config)?;
            } else {
                window.show()?;
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building Tauri application");

    application.run(|app, event| {
        if matches!(event, RunEvent::Exit | RunEvent::ExitRequested { .. }) {
            stop_sidecar(app);
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn saved_config_requires_an_existing_file() {
        let directory =
            std::env::temp_dir().join(format!("fanbox-desktop-state-{}", std::process::id()));
        let _ = fs::remove_dir_all(&directory);
        fs::create_dir_all(&directory).unwrap();
        let config = directory.join("chosen.yaml");
        remember_config(&directory, &config).unwrap();
        assert_eq!(find_saved_config(&directory), None);
        fs::write(&config, "{}\n").unwrap();
        assert_eq!(find_saved_config(&directory), Some(config));
        fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn clearing_selection_preserves_configs_and_archive_data() {
        let directory =
            std::env::temp_dir().join(format!("fanbox-desktop-reset-{}", std::process::id()));
        let _ = fs::remove_dir_all(&directory);
        fs::create_dir_all(&directory).unwrap();
        let config = directory.join(DEFAULT_CONFIG_FILE);
        let imported_config = directory.join(IMPORTED_CONFIG_FILE);
        let database = directory.join("backup.db");
        fs::write(&config, "{}\n").unwrap();
        fs::write(&imported_config, "{}\n").unwrap();
        fs::write(&database, "archive-data").unwrap();
        remember_config(&directory, &config).unwrap();

        clear_saved_config(&directory).unwrap();

        assert!(!directory.join(STATE_FILE).exists());
        assert_eq!(find_saved_config(&directory), None);
        assert!(config.is_file());
        assert!(imported_config.is_file());
        assert_eq!(fs::read_to_string(database).unwrap(), "archive-data");
        fs::remove_dir_all(directory).unwrap();
    }
}
