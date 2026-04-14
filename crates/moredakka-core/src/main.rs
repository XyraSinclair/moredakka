mod config;
mod context;
mod doctor;
mod util;

use anyhow::Result;
use clap::{Parser, Subcommand, ValueEnum};
use serde_json::json;

#[derive(Parser)]
#[command(name = "moredakka-core")]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    Doctor {
        #[arg(long, value_enum, default_value = "markdown")]
        format: OutputFormat,
    },
    Pack {
        #[arg(long, default_value = "main")]
        base_ref: String,
        #[arg(long)]
        objective: Option<String>,
        #[arg(long, default_value_t = 24_000)]
        char_budget: usize,
        #[arg(long, value_enum, default_value = "plan")]
        mode: PackMode,
    },
}

#[derive(Copy, Clone, Eq, PartialEq, ValueEnum)]
enum OutputFormat {
    Markdown,
    Json,
}

#[derive(Copy, Clone, Debug, Eq, PartialEq, ValueEnum)]
enum PackMode {
    Plan,
    Review,
    Patch,
    Loop,
    Here,
}

fn main() {
    if let Err(err) = run() {
        eprintln!("error: {err}");
        std::process::exit(1);
    }
}

fn run() -> Result<()> {
    let cli = Cli::parse();
    let cwd = std::env::current_dir()?;
    match cli.command {
        Command::Doctor { format } => {
            let report = doctor::run_doctor(&cwd)?;
            match format {
                OutputFormat::Markdown => print!("{}", doctor::render_markdown(&report)),
                OutputFormat::Json => println!("{}", serde_json::to_string_pretty(&report)?),
            }
            if !report.ok {
                std::process::exit(1);
            }
        }
        Command::Pack {
            base_ref,
            objective,
            char_budget,
            mode,
        } => {
            let (cfg, _) = config::load_config(&cwd, None)?;
            let packet = context::build_context_packet(
                &cwd,
                &format!("{:?}", mode).to_lowercase(),
                objective.as_deref(),
                &base_ref,
                char_budget,
                &cfg,
            )?;
            println!(
                "{}",
                serde_json::to_string_pretty(
                    &json!({"context_packet": packet, "synthesis": {}, "rounds": [], "providers": []})
                )?
            );
        }
    }
    Ok(())
}
