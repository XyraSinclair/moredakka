use crate::config::{load_config, AppConfig};
use crate::util::{load_local_env, run_command};
use serde::Serialize;
use std::collections::HashSet;
use std::fs;
use std::path::Path;

#[derive(Clone, Debug, Serialize)]
pub struct DoctorCheck {
    pub name: String,
    pub status: String,
    pub summary: String,
    pub detail: String,
    pub fix: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct DoctorReport {
    pub ok: bool,
    pub cwd: String,
    pub config_path: Option<String>,
    pub checks: Vec<DoctorCheck>,
}

fn check_python() -> DoctorCheck {
    let probe = [
        "/opt/homebrew/bin/python3.12",
        "/opt/homebrew/bin/python3.11",
        "/usr/local/bin/python3.12",
        "/usr/local/bin/python3.11",
        "python3.12",
        "python3.11",
        "python3",
    ]
        .into_iter()
        .find_map(|bin| {
            run_command(
                Path::new("."),
                bin,
                &["-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"],
            )
            .map(|version| (bin.to_string(), version))
        });
    match probe {
        Some((bin, version)) => {
            let parts: Vec<u32> = version.split('.').filter_map(|p| p.parse().ok()).collect();
            if parts.len() >= 2 && (parts[0], parts[1]) >= (3, 11) {
                DoctorCheck {
                    name: "python".into(),
                    status: "pass".into(),
                    summary: "Python version is supported.".into(),
                    detail: format!("{bin} {version}"),
                    fix: String::new(),
                }
            } else {
                DoctorCheck {
                    name: "python".into(),
                    status: "fail".into(),
                    summary: "Python 3.11+ is required.".into(),
                    detail: format!("{bin} {version}"),
                    fix: "Use bin/moredakka or a Python 3.11+ interpreter.".into(),
                }
            }
        }
        None => DoctorCheck {
            name: "python".into(),
            status: "warn".into(),
            summary: "Python version could not be checked.".into(),
            detail: String::new(),
            fix: String::new(),
        },
    }
}

fn check_git(cwd: &Path) -> DoctorCheck {
    match run_command(cwd, "git", &["--version"]) {
        Some(version) => DoctorCheck {
            name: "git".into(),
            status: "pass".into(),
            summary: "git is available.".into(),
            detail: version,
            fix: String::new(),
        },
        None => DoctorCheck {
            name: "git".into(),
            status: "fail".into(),
            summary: "git is not available on PATH.".into(),
            detail: String::new(),
            fix: "Install git and ensure it is on PATH.".into(),
        },
    }
}

fn repo_checks(cwd: &Path, base_ref: &str, git_ok: bool) -> (DoctorCheck, DoctorCheck) {
    if !git_ok {
        return (
            DoctorCheck {
                name: "repo".into(),
                status: "warn".into(),
                summary: "Repository checks skipped because git is unavailable.".into(),
                detail: String::new(),
                fix: String::new(),
            },
            DoctorCheck {
                name: "base_ref".into(),
                status: "warn".into(),
                summary: "Base ref check skipped because git is unavailable.".into(),
                detail: String::new(),
                fix: String::new(),
            },
        );
    }
    let repo_root = run_command(cwd, "git", &["rev-parse", "--show-toplevel"]);
    let Some(repo_root) = repo_root else {
        return (
            DoctorCheck {
                name: "repo".into(),
                status: "warn".into(),
                summary: "Current directory is not inside a git repo.".into(),
                detail: String::new(),
                fix: "Run moredakka inside a git repo for review-oriented workflows.".into(),
            },
            DoctorCheck {
                name: "base_ref".into(),
                status: "warn".into(),
                summary: "Base ref not checked outside a git repo.".into(),
                detail: String::new(),
                fix: String::new(),
            },
        );
    };
    if run_command(cwd, "git", &["rev-parse", "--verify", base_ref]).is_none() {
        return (
            DoctorCheck {
                name: "repo".into(),
                status: "pass".into(),
                summary: "Current directory is inside a git repo.".into(),
                detail: repo_root,
                fix: String::new(),
            },
            DoctorCheck {
                name: "base_ref".into(),
                status: "fail".into(),
                summary: "Configured base ref does not resolve locally.".into(),
                detail: base_ref.into(),
                fix: "Fetch the ref, set defaults.base_ref, or pass --base-ref explicitly.".into(),
            },
        );
    }
    (
        DoctorCheck {
            name: "repo".into(),
            status: "pass".into(),
            summary: "Current directory is inside a git repo.".into(),
            detail: repo_root,
            fix: String::new(),
        },
        DoctorCheck {
            name: "base_ref".into(),
            status: "pass".into(),
            summary: "Base ref resolves locally.".into(),
            detail: base_ref.into(),
            fix: String::new(),
        },
    )
}

fn cache_check(cwd: &Path, cache_dir: &str) -> DoctorCheck {
    let resolved = if Path::new(cache_dir).is_absolute() {
        Path::new(cache_dir).to_path_buf()
    } else {
        cwd.join(cache_dir)
    };
    match fs::create_dir_all(&resolved).and_then(|_| {
        let probe = resolved.join(".doctor-write-test");
        fs::write(&probe, "ok\n")?;
        fs::remove_file(&probe)
    }) {
        Ok(_) => DoctorCheck {
            name: "cache_dir".into(),
            status: "pass".into(),
            summary: "Cache directory is writable.".into(),
            detail: resolved.display().to_string(),
            fix: String::new(),
        },
        Err(err) => DoctorCheck {
            name: "cache_dir".into(),
            status: "fail".into(),
            summary: "Cache directory is not writable.".into(),
            detail: err.to_string(),
            fix: "Set defaults.cache_dir to a writable path.".into(),
        },
    }
}

fn provider_checks(
    config: &AppConfig,
    env: &std::collections::HashMap<String, String>,
) -> Vec<DoctorCheck> {
    let active: HashSet<String> = config.roles.values().map(|r| r.provider.clone()).collect();
    config
        .providers
        .values()
        .map(|provider| {
            let missing_env = env
                .get(&provider.api_key_env)
                .map(|v| v.is_empty())
                .unwrap_or(true);
            if !missing_env {
                DoctorCheck {
                    name: format!("provider:{}", provider.name),
                    status: "pass".into(),
                    summary: format!("{} is ready.", provider.name),
                    detail: format!("kind={} env={}", provider.kind, provider.api_key_env),
                    fix: String::new(),
                }
            } else {
                DoctorCheck {
                    name: format!("provider:{}", provider.name),
                    status: if active.contains(&provider.name) {
                        "fail".into()
                    } else {
                        "warn".into()
                    },
                    summary: format!("{} is not fully ready.", provider.name),
                    detail: format!("missing env {}", provider.api_key_env),
                    fix: format!("export {}", provider.api_key_env),
                }
            }
        })
        .collect()
}

fn roster_diversity(config: &AppConfig) -> DoctorCheck {
    let models: HashSet<String> = config
        .roles
        .values()
        .filter_map(|r| config.providers.get(&r.provider).map(|p| p.model.clone()))
        .collect();
    if models.len() >= 2 {
        DoctorCheck {
            name: "roster_diversity".into(),
            status: "pass".into(),
            summary: "Active role roster uses multiple model families.".into(),
            detail: models.into_iter().collect::<Vec<_>>().join(", "),
            fix: String::new(),
        }
    } else {
        DoctorCheck {
            name: "roster_diversity".into(),
            status: "warn".into(),
            summary: "Active role roster collapses to one model.".into(),
            detail: models.into_iter().next().unwrap_or_default(),
            fix: "Map at least one critical role to a contrast model or provider.".into(),
        }
    }
}

pub fn run_doctor(cwd: &Path) -> anyhow::Result<DoctorReport> {
    let env = load_local_env(cwd);
    let (config, config_path) = load_config(cwd, None)?;
    let mut checks = Vec::new();
    checks.push(check_python());
    let git = check_git(cwd);
    let git_ok = git.status == "pass";
    checks.push(git);
    checks.push(DoctorCheck {
        name: "config".into(),
        status: "pass".into(),
        summary: "Configuration loaded.".into(),
        detail: config_path
            .as_ref()
            .map(|p| p.display().to_string())
            .unwrap_or_else(|| "using built-in defaults".into()),
        fix: String::new(),
    });
    let (repo, base_ref) = repo_checks(cwd, &config.defaults.base_ref, git_ok);
    checks.push(repo);
    checks.push(base_ref);
    checks.push(cache_check(cwd, &config.defaults.cache_dir));
    checks.extend(provider_checks(&config, &env));
    checks.push(roster_diversity(&config));
    let ok = checks.iter().all(|c| c.status != "fail");
    Ok(DoctorReport {
        ok,
        cwd: cwd.display().to_string(),
        config_path: config_path.map(|p| p.display().to_string()),
        checks,
    })
}

pub fn render_markdown(report: &DoctorReport) -> String {
    let mut lines = vec![
        "# moredakka doctor".to_string(),
        String::new(),
        format!("overall: {}", if report.ok { "PASS" } else { "FAIL" }),
        format!("cwd: {}", report.cwd),
        format!(
            "config: {}",
            report
                .config_path
                .clone()
                .unwrap_or_else(|| "built-in defaults".into())
        ),
        String::new(),
        "## checks".to_string(),
    ];
    for check in &report.checks {
        lines.push(format!(
            "- [{}] {}: {}",
            check.status, check.name, check.summary
        ));
        if !check.detail.is_empty() {
            lines.push(format!("  detail: {}", check.detail));
        }
        if !check.fix.is_empty() {
            lines.push(format!("  fix: {}", check.fix));
        }
    }
    format!("{}\n", lines.join("\n"))
}
