use serde::{Deserialize, Serialize};
use std::process::Command;
use std::path::PathBuf;

#[derive(Serialize, Deserialize)]
pub struct Player {
    username: String,
    team: u8,
}

#[tauri::command]
fn parse_replay_players(file_path: String) -> Result<Vec<Player>, String> {
    println!("Rust received request to analyze file: {}", file_path);

    let python_path = PathBuf::from("../../.venv/Scripts/python.exe");
    let script_path = PathBuf::from("../../src/analyser.py");

    let output = Command::new(python_path)
        .arg(script_path)
        .arg("get_players")
        .arg(&file_path)
        .output()
        .map_err(|e| format!("Failed to execute Python: {}", e))?;

    if !output.status.success() {
        let err = String::from_utf8_lossy(&output.stderr);
        return Err(format!("Python script failed: {}", err));
    }

    let json_str = String::from_utf8_lossy(&output.stdout);
    let players: Vec<Player> = serde_json::from_str(&json_str)
        .map_err(|e| format!("Failed to parse Python JSON: {}\nOutput was: {}", e, json_str))?;

    Ok(players)
}

#[tauri::command]
async fn run_analysis(username: String, file_path: String) -> Result<serde_json::Value, String> {
    let python_path = PathBuf::from("../../.venv/Scripts/python.exe");
    let script_path = PathBuf::from("../../src/analyser.py");

    let output = Command::new(python_path)
        .arg(script_path)
        .arg("analyze")
        .arg(&file_path)
        .arg(&username)
        .output()
        .map_err(|e| format!("Failed to execute Python: {}", e))?;

    if !output.status.success() {
        let err_msg = String::from_utf8_lossy(&output.stderr);
        return Err(format!("Python analysis failed: {}", err_msg));
    }

    let json_str = String::from_utf8_lossy(&output.stdout);
    let data: serde_json::Value = serde_json::from_str(&json_str)
        .map_err(|e| format!("Failed to parse Python JSON: {} \nOutput was: {}", e, json_str))?;

    Ok(data)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![parse_replay_players, run_analysis])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}