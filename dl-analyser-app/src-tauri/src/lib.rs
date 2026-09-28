use serde::{Deserialize, Serialize};
use tauri_plugin_shell::ShellExt;

#[derive(Serialize, Deserialize)]
pub struct Player {
    username: String,
    team: u8,
}

#[tauri::command]
async fn parse_replay_players(app: tauri::AppHandle, file_path: String) -> Result<Vec<Player>, String> {
    println!("Rust received request to parse file via sidecar: {}", file_path);

    // Call the bundled sidecar binary named "analyser"
    let output = app.shell().sidecar("analyser")
        .map_err(|e| format!("Failed to create sidecar reference: {}", e))?
        .args(["get_players", &file_path])
        .output()
        .await
        .map_err(|e| format!("Failed to execute analyser sidecar: {}", e))?;

    if !output.status.success() {
        let err = String::from_utf8_lossy(&output.stderr);
        return Err(format!("Analyser sidecar failed: {}", err));
    }

    let json_str = String::from_utf8_lossy(&output.stdout);
    let players: Vec<Player> = serde_json::from_str(&json_str)
        .map_err(|e| format!("Failed to parse sidecar JSON: {}\nOutput was: {}", e, json_str))?;

    Ok(players)
}

#[tauri::command]
async fn run_analysis(app: tauri::AppHandle, username: String, file_path: String) -> Result<serde_json::Value, String> {
    let output = app.shell().sidecar("analyser")
        .map_err(|e| format!("Failed to create sidecar reference: {}", e))?
        .args(["analyze", &file_path, &username])
        .output()
        .await
        .map_err(|e| format!("Failed to execute analyser sidecar: {}", e))?;

    if !output.status.success() {
        let err_msg = String::from_utf8_lossy(&output.stderr);
        return Err(format!("Analysis sidecar failed: {}", err_msg));
    }

    let json_str = String::from_utf8_lossy(&output.stdout);
    let data: serde_json::Value = serde_json::from_str(&json_str)
        .map_err(|e| format!("Failed to parse analysis JSON: {} \nOutput was: {}", e, json_str))?;

    Ok(data)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init()) // Initialise the shell plugin for sidecars
        .invoke_handler(tauri::generate_handler![parse_replay_players, run_analysis])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}