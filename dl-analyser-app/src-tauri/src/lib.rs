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

// NEW: Command to trigger the ML analysis
#[tauri::command]
fn run_analysis(username: String) -> Result<serde_json::Value, String> {
    println!("Rust requesting ML analysis for user: {}", username);
    
    let python_path = PathBuf::from("../../.venv/Scripts/python.exe");
    let script_path = PathBuf::from("../../src/analyser.py");
    // Hardcoded JSON path for now until we wire up the Java parser
    let json_path = PathBuf::from("../../replay_parser/output/parsed_match.json");

    let output = Command::new(python_path)
        .arg(script_path)
        .arg("analyze")
        .arg(json_path)
        .arg(&username)
        .output()
        .map_err(|e| format!("Failed to execute Python ML model: {}", e))?;

    if !output.status.success() {
        let err = String::from_utf8_lossy(&output.stderr);
        return Err(format!("Python ML script failed: {}", err));
    }

    let json_str = String::from_utf8_lossy(&output.stdout);
    
    // Parse the output directly into a generic JSON Value to send to React
    let report: serde_json::Value = serde_json::from_str(&json_str)
        .map_err(|e| format!("Failed to parse report JSON: {}\nOutput was: {}", e, json_str))?;

    Ok(report)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        // Make sure to register the new run_analysis command here!
        .invoke_handler(tauri::generate_handler![parse_replay_players, run_analysis])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}