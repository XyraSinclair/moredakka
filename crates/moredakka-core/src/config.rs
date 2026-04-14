use anyhow::{anyhow, Result};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ProviderConfig {
    pub name: String,
    pub kind: String,
    pub model: String,
    pub api_key_env: String,
    pub reasoning_effort: Option<String>,
    pub base_url: Option<String>,
    pub app_url: Option<String>,
    pub app_name: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct RoleConfig {
    pub name: String,
    pub provider: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct DefaultsConfig {
    pub mode: String,
    pub max_rounds: usize,
    pub base_ref: String,
    pub char_budget: usize,
    pub cache_dir: String,
    pub novelty_threshold: f64,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct AppConfig {
    pub defaults: DefaultsConfig,
    pub providers: BTreeMap<String, ProviderConfig>,
    pub roles: BTreeMap<String, RoleConfig>,
}

#[derive(Deserialize)]
struct TomlConfig {
    defaults: Option<TomlDefaults>,
    providers: Option<BTreeMap<String, TomlProvider>>,
    roles: Option<BTreeMap<String, TomlRole>>,
}

#[derive(Deserialize)]
struct TomlDefaults {
    mode: Option<String>,
    max_rounds: Option<usize>,
    base_ref: Option<String>,
    char_budget: Option<usize>,
    cache_dir: Option<String>,
    novelty_threshold: Option<f64>,
}

#[derive(Deserialize)]
struct TomlProvider {
    kind: Option<String>,
    model: Option<String>,
    api_key_env: Option<String>,
    reasoning_effort: Option<String>,
    base_url: Option<String>,
    app_url: Option<String>,
    app_name: Option<String>,
}

#[derive(Deserialize)]
struct TomlRole {
    provider: Option<String>,
}

pub fn default_config() -> AppConfig {
    let providers = BTreeMap::from([
        (
            "openrouter_planner".to_string(),
            ProviderConfig {
                name: "openrouter_planner".into(),
                kind: "openrouter".into(),
                model: "anthropic/claude-opus-4.6".into(),
                api_key_env: "OPENROUTER_API_KEY".into(),
                reasoning_effort: None,
                base_url: Some("https://openrouter.ai/api/v1".into()),
                app_url: None,
                app_name: Some("moredakka".into()),
            },
        ),
        (
            "openrouter_implementer".to_string(),
            ProviderConfig {
                name: "openrouter_implementer".into(),
                kind: "openrouter".into(),
                model: "openai/gpt-5.4".into(),
                api_key_env: "OPENROUTER_API_KEY".into(),
                reasoning_effort: Some("medium".into()),
                base_url: Some("https://openrouter.ai/api/v1".into()),
                app_url: None,
                app_name: Some("moredakka".into()),
            },
        ),
        (
            "openrouter_breaker".to_string(),
            ProviderConfig {
                name: "openrouter_breaker".into(),
                kind: "openrouter".into(),
                model: "google/gemini-3.1-pro-preview".into(),
                api_key_env: "OPENROUTER_API_KEY".into(),
                reasoning_effort: None,
                base_url: Some("https://openrouter.ai/api/v1".into()),
                app_url: None,
                app_name: Some("moredakka".into()),
            },
        ),
        (
            "openrouter_minimalist".to_string(),
            ProviderConfig {
                name: "openrouter_minimalist".into(),
                kind: "openrouter".into(),
                model: "openai/gpt-5.4-mini".into(),
                api_key_env: "OPENROUTER_API_KEY".into(),
                reasoning_effort: Some("medium".into()),
                base_url: Some("https://openrouter.ai/api/v1".into()),
                app_url: None,
                app_name: Some("moredakka".into()),
            },
        ),
        (
            "openrouter_synthesizer".to_string(),
            ProviderConfig {
                name: "openrouter_synthesizer".into(),
                kind: "openrouter".into(),
                model: "openai/gpt-5.4".into(),
                api_key_env: "OPENROUTER_API_KEY".into(),
                reasoning_effort: Some("medium".into()),
                base_url: Some("https://openrouter.ai/api/v1".into()),
                app_url: None,
                app_name: Some("moredakka".into()),
            },
        ),
    ]);
    let roles = BTreeMap::from([
        (
            "planner".into(),
            RoleConfig {
                name: "planner".into(),
                provider: "openrouter_planner".into(),
            },
        ),
        (
            "implementer".into(),
            RoleConfig {
                name: "implementer".into(),
                provider: "openrouter_implementer".into(),
            },
        ),
        (
            "breaker".into(),
            RoleConfig {
                name: "breaker".into(),
                provider: "openrouter_breaker".into(),
            },
        ),
        (
            "minimalist".into(),
            RoleConfig {
                name: "minimalist".into(),
                provider: "openrouter_minimalist".into(),
            },
        ),
        (
            "synthesizer".into(),
            RoleConfig {
                name: "synthesizer".into(),
                provider: "openrouter_synthesizer".into(),
            },
        ),
    ]);
    AppConfig {
        defaults: DefaultsConfig {
            mode: "plan".into(),
            max_rounds: 2,
            base_ref: "main".into(),
            char_budget: 24_000,
            cache_dir: ".moredakka/cache".into(),
            novelty_threshold: 0.15,
        },
        providers,
        roles,
    }
}

pub fn find_config_path(explicit: Option<&Path>, cwd: &Path) -> Option<PathBuf> {
    if let Some(path) = explicit {
        return path.exists().then(|| path.to_path_buf());
    }
    let mut current = Some(cwd.to_path_buf());
    while let Some(dir) = current {
        let candidate = dir.join("moredakka.toml");
        if candidate.exists() {
            return Some(candidate);
        }
        current = dir.parent().map(|p| p.to_path_buf());
    }
    None
}

pub fn load_config(cwd: &Path, explicit: Option<&Path>) -> Result<(AppConfig, Option<PathBuf>)> {
    let mut cfg = default_config();
    let path = find_config_path(explicit, cwd);
    let Some(found) = path.clone() else {
        return Ok((cfg, None));
    };
    let raw: TomlConfig = toml::from_str(&fs::read_to_string(&found)?)?;
    if let Some(defaults) = raw.defaults {
        if let Some(v) = defaults.mode {
            cfg.defaults.mode = v;
        }
        if let Some(v) = defaults.max_rounds {
            cfg.defaults.max_rounds = v;
        }
        if let Some(v) = defaults.base_ref {
            cfg.defaults.base_ref = v;
        }
        if let Some(v) = defaults.char_budget {
            cfg.defaults.char_budget = v;
        }
        if let Some(v) = defaults.cache_dir {
            cfg.defaults.cache_dir = v;
        }
        if let Some(v) = defaults.novelty_threshold {
            cfg.defaults.novelty_threshold = v;
        }
    }
    if let Some(providers) = raw.providers {
        for (name, provider_raw) in providers {
            let entry = cfg.providers.entry(name.clone()).or_insert(ProviderConfig {
                name: name.clone(),
                kind: "openrouter".into(),
                model: String::new(),
                api_key_env: String::new(),
                reasoning_effort: None,
                base_url: None,
                app_url: None,
                app_name: None,
            });
            if let Some(v) = provider_raw.kind {
                entry.kind = v;
            }
            if let Some(v) = provider_raw.model {
                entry.model = v;
            }
            if let Some(v) = provider_raw.api_key_env {
                entry.api_key_env = v;
            }
            if let Some(v) = provider_raw.reasoning_effort {
                entry.reasoning_effort = Some(v);
            }
            if let Some(v) = provider_raw.base_url {
                entry.base_url = Some(v);
            }
            if let Some(v) = provider_raw.app_url {
                entry.app_url = Some(v);
            }
            if let Some(v) = provider_raw.app_name {
                entry.app_name = Some(v);
            }
        }
    }
    if let Some(roles) = raw.roles {
        for (name, role_raw) in roles {
            let entry = cfg.roles.entry(name.clone()).or_insert(RoleConfig {
                name: name.clone(),
                provider: String::new(),
            });
            if let Some(v) = role_raw.provider {
                entry.provider = v;
            }
        }
    }
    validate_config(&cfg)?;
    Ok((cfg, path))
}

pub fn validate_config(cfg: &AppConfig) -> Result<()> {
    if cfg.defaults.base_ref.trim().is_empty() {
        return Err(anyhow!("defaults.base_ref must not be empty"));
    }
    if cfg.defaults.cache_dir.trim().is_empty() {
        return Err(anyhow!("defaults.cache_dir must not be empty"));
    }
    for (name, provider) in &cfg.providers {
        if provider.model.trim().is_empty() || provider.api_key_env.trim().is_empty() {
            return Err(anyhow!(
                "provider {name} must include non-empty model and api_key_env"
            ));
        }
        if let Some(effort) = &provider.reasoning_effort {
            if !["low", "medium", "high"].contains(&effort.as_str()) {
                return Err(anyhow!(
                    "provider {name} has unsupported reasoning_effort {effort}"
                ));
            }
        }
    }
    Ok(())
}
