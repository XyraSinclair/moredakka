use std::collections::HashMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

pub fn truncate_middle(text: &str, max_chars: usize) -> String {
    if max_chars == 0 {
        return String::new();
    }
    if text.chars().count() <= max_chars {
        return text.to_string();
    }
    if max_chars < 16 {
        return text.chars().take(max_chars).collect();
    }
    let marker = "\n…\n";
    let head = max_chars / 2;
    let tail = max_chars.saturating_sub(head + marker.chars().count());
    let start: String = text.chars().take(head).collect();
    let end: String = text
        .chars()
        .rev()
        .take(tail)
        .collect::<String>()
        .chars()
        .rev()
        .collect();
    format!("{start}{marker}{end}")
}

pub fn find_upward(start: &Path, filename: &str) -> Option<PathBuf> {
    let mut current = Some(start.to_path_buf());
    while let Some(dir) = current {
        let candidate = dir.join(filename);
        if candidate.exists() {
            return Some(candidate);
        }
        current = dir.parent().map(|p| p.to_path_buf());
    }
    None
}

pub fn load_local_env(start: &Path) -> HashMap<String, String> {
    let mut merged: HashMap<String, String> = std::env::vars().collect();
    let Some(path) = find_upward(start, ".env") else {
        return merged;
    };
    if let Ok(content) = fs::read_to_string(path) {
        for raw_line in content.lines() {
            let line = raw_line.trim();
            if line.is_empty() || line.starts_with('#') || !line.contains('=') {
                continue;
            }
            let mut parts = line.splitn(2, '=');
            let key = parts.next().unwrap_or("").trim();
            let mut value = parts.next().unwrap_or("").trim().to_string();
            if key.is_empty() || merged.contains_key(key) {
                continue;
            }
            if value.len() >= 2 {
                let first = value.chars().next().unwrap();
                let last = value.chars().last().unwrap();
                if (first == '"' || first == '\'') && first == last {
                    value = value[1..value.len() - 1].to_string();
                }
            }
            merged.insert(key.to_string(), value);
        }
    }
    merged
}

pub fn run_command(cwd: &Path, program: &str, args: &[&str]) -> Option<String> {
    let output = Command::new(program)
        .current_dir(cwd)
        .args(args)
        .output()
        .ok()?;
    if !output.status.success() {
        return None;
    }
    Some(
        String::from_utf8_lossy(&output.stdout)
            .trim_end()
            .to_string(),
    )
}

pub fn safe_read_text(path: &Path, max_chars: usize) -> Option<String> {
    let data = fs::read(path).ok()?;
    if data.iter().take(4096).any(|b| *b == 0) {
        return None;
    }
    let text = String::from_utf8_lossy(&data).to_string();
    Some(truncate_middle(&text, max_chars))
}
