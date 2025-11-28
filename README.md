# Harbor + Custom Agents

This repo keeps Harbor, the Terminal-Bench harness, and a slim `custom_agents/` folder for local agents. The current example is **pi-mono**, but the layout is ready for more.

## Layout
- `custom_agents/` — importable agent modules.
  - `pi_mono_agent.py` — `PiMonoAgent` (`BaseInstalledAgent`) that installs and runs the `pi` CLI.
  - `install_pi_mono.sh.j2` — install template (Node 20+, `@mariozechner/pi-coding-agent`, optional `pi-bundle.tgz`).

## Prerequisites
- Docker Desktop/Engine running (Harbor executes tests inside containers).
- Python 3.12 preferred (Makefile falls back to 3.11/3.10 if 3.12 missing).
- `make` available (for the `make install` helper).

## Run Terminal-Bench with the custom pi-mono agent
Run from repo root so `custom_agents` is on `PYTHONPATH`.
```bash
# install Harbor once (make sets up .venv and installs harbor)
make install
source .venv/bin/activate  # optional: put harbor on PATH

# set provider API key(s), e.g.
export OPENAI_API_KEY=...
export ANTHROPIC_API_KEY=

# launch harbor terminal bench with pi-mono
harbor run \
  -d terminal-bench@2.0 \
  --agent-import-path custom_agents:PiMonoAgent \
  --model openai/gpt-5.1-codex \
  --job-name pi-codex \
  --n-concurrent 2
```
What this agent does:
- During setup, Harbor renders `install_pi_mono.sh.j2` to install Node (if needed) and the `pi` CLI; if `custom_agents/pi-bundle.tgz` exists, it restores from that bundle to skip npm.
- At runtime, it forwards provider/model flags to `pi`, passes through common API keys, streams output to `/logs/agent/pi_output.log`, and (JSON mode) saves `/logs/agent/results.json`.

## Add another custom agent
1) Create `custom_agents/<new_agent>.py` with a `BaseInstalledAgent` (or `BaseAgent`) subclass.
2) If it needs install steps, add `install_<new_agent>.sh.j2` and reference it via `_install_agent_template_path`.
3) Run Harbor with `--agent-import-path custom_agents.<new_agent>:ClassName` and any `--agent-kwarg key=value`.

## Secret scanning
- One-off scan (Docker required): `make secrets-scan`  
  Generates `gitleaks-report.json` in repo root.

Tips:
- Keep `custom_agents/` importable (run from repo root or set `PYTHONPATH=$(pwd)`).
- Drop a prebuilt `pi-bundle.tgz` into `custom_agents/` to accelerate pi installs.
- OpenAI models can flag Terminal-Bench “weapons” scenarios; if you hit safety refusals, add a safety identifier per OpenAI guidance (e.g., include your org’s identifier string in the prompt/request headers as described at https://help.openai.com/en/articles/5428082-how-to-incorporate-a-safety-identifier).
- If `pip install harbor` backtracks on `daytona`/`obstore`, ensure the venv uses Python 3.12 (wheels may not yet exist for 3.14).
