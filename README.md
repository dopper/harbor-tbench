# Harbor + Custom Agents

Lean Harbor + Terminal-Bench setup with a small `custom_agents/` folder (pi-mono and Factory Droid examples). Run from repo root so `custom_agents` is on `PYTHONPATH`.

## Prerequisites
- Docker running
- Python 3.12 preferred (Makefile falls back to 3.11/3.10)
- `make` available

## Quick install
```bash
make install          # creates .venv and installs harbor
source .venv/bin/activate
export OPENAI_API_KEY=...
export ANTHROPIC_API_KEY=...
```

## Run pi-mono agent
```bash
harbor run \
  -d terminal-bench@2.0 \
  --agent-import-path custom_agents:PiMonoAgent \
  --model openai/gpt-5.1-codex \
  --job-name pi-codex \
  --n-concurrent 2
```
Notes: installs the `pi` CLI via `install_pi_mono.sh.j2`; uses `OPENAI_API_KEY`/`ANTHROPIC_API_KEY`; outputs to `/logs/agent/pi_output.log`.

## Run Factory Droid agent
Prereq: run `droid` once on the host so `~/.factory/auth.json` exists, or set `FACTORY_AUTH_TOKEN`.
```bash
export FACTORY_AUTH_TOKEN=...   # optional fallback
harbor run \
  -d terminal-bench@2.0 \
  --agent-import-path custom_agents:FactoryDroidAgent \
  --agent-kwarg droid_model="gpt-5-codex" \
  --n-concurrent 2 \
  --job-name droid-codex
```
Notes: installs the Factory Droid CLI via `install_factory_droid.sh.j2`, uploads `~/.factory/{auth,settings,config}.json` if present, and runs `droid exec` with auto-approval; logs to `/logs/agent/droid_output.log`.

## Add another agent
Create `custom_agents/<new_agent>.py` (optionally with `install_<new_agent>.sh.j2`), then run Harbor with `--agent-import-path custom_agents:<ClassName>` and any `--agent-kwarg key=value`.

## Secret scan
`make secrets-scan` (Docker) → `gitleaks-report.json` in repo root.
