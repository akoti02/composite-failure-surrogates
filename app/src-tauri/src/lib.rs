use serde_json::Value;
use std::io::{BufRead, BufReader, BufWriter, Write};
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::{Arc, Mutex};
use tauri::State;

struct Sidecar(Arc<Mutex<Option<SidecarProc>>>);

struct SidecarProc {
    child: Child,
    writer: BufWriter<ChildStdin>,
    reader: BufReader<ChildStdout>,
}

impl Drop for SidecarProc {
    fn drop(&mut self) {
        if let Err(e) = self.child.kill() {
            eprintln!("Warning: failed to kill sidecar: {}", e);
        }
        let _ = self.child.wait();
    }
}

fn spawn_sidecar() -> Result<SidecarProc, String> {
    let sidecar_dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .ok_or("Cannot find project root")?
        .join("sidecar");

    let mut cmd = if cfg!(debug_assertions) {
        // On macOS/Linux, "python" may not exist — try "python3" first
        let python_cmd = if cfg!(target_os = "windows") { "python" } else { "python3" };
        let mut c = Command::new(python_cmd);
        c.arg(sidecar_dir.join("server.py"));
        c
    } else {
        let exe_dir = std::env::current_exe()
            .map_err(|e| format!("Cannot find exe path: {}", e))?
            .parent()
            .ok_or("Cannot find exe directory")?
            .to_path_buf();
        Command::new(exe_dir.join(if cfg!(target_os = "windows") { "rp3-sidecar.exe" } else { "rp3-sidecar" }))
    };

    // Redirect stderr to a log file instead of discarding it entirely.
    // Direct pipe to parent would deadlock on Windows if buffer fills, so
    // we write to ~/.rp3/sidecar_stderr.log for post-mortem debugging.
    let home = std::env::var("USERPROFILE")
        .or_else(|_| std::env::var("HOME"))
        .unwrap_or_else(|_| ".".to_string());
    let log_dir = std::path::PathBuf::from(home).join(".rp3");
    let _ = std::fs::create_dir_all(&log_dir);
    let stderr_target = std::fs::File::create(log_dir.join("sidecar_stderr.log"))
        .map(Stdio::from)
        .unwrap_or_else(|_| Stdio::null());

    cmd.stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(stderr_target)
        .env("PYTHONUNBUFFERED", "1"); // Prevent stdout buffering deadlock

    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x08000000); // CREATE_NO_WINDOW
    }

    let mut child = cmd.spawn()
        .map_err(|e| format!("Failed to spawn sidecar: {}", e))?;
    let stdin = child.stdin.take()
        .ok_or("Failed to capture sidecar stdin")?;
    let stdout = child.stdout.take()
        .ok_or("Failed to capture sidecar stdout")?;

    Ok(SidecarProc {
        child,
        writer: BufWriter::new(stdin),
        reader: BufReader::new(stdout),
    })
}

fn send_command(proc: &mut SidecarProc, cmd: &Value) -> Result<Value, String> {
    // Check if sidecar is still alive
    if let Some(status) = proc.child.try_wait().unwrap_or(None) {
        return Err(format!("Sidecar exited with status: {}", status));
    }

    let line = serde_json::to_string(cmd).map_err(|e| e.to_string())?;
    proc.writer
        .write_all(format!("{}\n", line).as_bytes())
        .map_err(|e| format!("Sidecar write failed (process may have crashed): {}", e))?;
    proc.writer
        .flush()
        .map_err(|e| format!("Sidecar flush failed: {}", e))?;

    let mut response = String::new();
    let bytes = proc
        .reader
        .read_line(&mut response)
        .map_err(|e| format!("Sidecar read failed (process may have crashed): {}", e))?;

    if bytes == 0 {
        return Err("Sidecar closed unexpectedly (no response)".to_string());
    }

    serde_json::from_str(&response)
        .map_err(|e| {
            let preview = if response.len() > 200 {
                format!("{}...", &response[..200])
            } else {
                response.trim().to_string()
            };
            format!("Parse error: {} (raw: {})", e, preview)
        })
}

/// Ensure the sidecar is running, respawning if needed. Returns a mutable ref to the proc.
fn ensure_sidecar(guard: &mut Option<SidecarProc>) -> Result<&mut SidecarProc, String> {
    // Check if existing sidecar is alive
    let needs_respawn = match guard.as_mut() {
        None => true,
        Some(proc) => proc.child.try_wait().unwrap_or(None).is_some(),
    };

    if needs_respawn {
        eprintln!("Sidecar not running, attempting respawn...");
        *guard = Some(spawn_sidecar()?);
    }

    guard.as_mut().ok_or_else(|| "Sidecar not available".to_string())
}

#[tauri::command]
async fn load_models(sidecar: State<'_, Sidecar>) -> Result<Value, String> {
    let sidecar = sidecar.0.clone();
    tokio::task::spawn_blocking(move || {
        let mut guard = sidecar.lock().map_err(|e| e.to_string())?;
        let proc = ensure_sidecar(&mut guard)?;
        let cmd = serde_json::json!({"cmd": "load_models"});
        send_command(proc, &cmd)
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn predict(params: Value, sidecar: State<'_, Sidecar>) -> Result<Value, String> {
    let sidecar = sidecar.0.clone();

    let prediction = tokio::task::spawn_blocking(move || {
        let mut guard = sidecar.lock().map_err(|e| e.to_string())?;
        let proc = ensure_sidecar(&mut guard)?;
        let cmd = serde_json::json!({"cmd": "predict", "params": params});
        send_command(proc, &cmd)
    });

    // 45-second timeout prevents frozen UI if sidecar hangs
    match tokio::time::timeout(std::time::Duration::from_secs(45), prediction).await {
        Ok(Ok(result)) => result,
        Ok(Err(e)) => Err(format!("Prediction task failed: {}", e)),
        Err(_) => Err("Prediction timed out after 45 seconds".to_string()),
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let proc = match spawn_sidecar() {
        Ok(p) => Some(p),
        Err(e) => {
            eprintln!("WARNING: Sidecar failed to start: {}", e);
            None
        }
    };

    tauri::Builder::default()
        .manage(Sidecar(Arc::new(Mutex::new(proc))))
        .invoke_handler(tauri::generate_handler![load_models, predict])
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
