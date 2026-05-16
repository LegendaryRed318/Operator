#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::{AppHandle, Manager};
use tauri::menu::{MenuBuilder, MenuItemBuilder};
use tauri::tray::TrayIconBuilder;
use tauri_plugin_autostart::MacosLauncher;
use tauri_plugin_notification::NotificationExt;

#[tauri::command]
fn show_notification(app: AppHandle, title: String, body: String) -> Result<(), String> {
  app.notification()
    .builder()
    .title(title)
    .body(body)
    .show()
    .map_err(|e| e.to_string())
}

fn main() {
  tauri::Builder::default()
    .plugin(tauri_plugin_notification::init())
    .plugin(tauri_plugin_autostart::init(MacosLauncher::LaunchAgent, Some(vec!["--hidden"])))
    .setup(|app| {
      let show = MenuItemBuilder::with_id("show", "Show / Hide").build(app)?;
      let quit = MenuItemBuilder::with_id("quit", "Quit Operator").build(app)?;

      let tray_menu = MenuBuilder::new(app)
        .item(&show)
        .separator()
        .item(&quit)
        .build()?;

      let _tray = TrayIconBuilder::with_id("main")
        .tooltip("Operator")
        .menu(&tray_menu)
        .on_menu_event(|app, event| match event.id().as_ref() {
          "show" => {
            if let Some(window) = app.get_webview_window("main") {
              if window.is_visible().unwrap_or(false) {
                let _ = window.hide();
              } else {
                let _ = window.show();
                let _ = window.set_focus();
              }
            }
          }
          "quit" => {
            app.exit(0);
          }
          _ => {}
        })
        .build(app)?;

      Ok(())
    })
    .invoke_handler(tauri::generate_handler![show_notification])
    .run(tauri::generate_context!())
    .expect("error while running Operator");
}
