# Harbor + Custom Agents

This repo keeps Harbor, the Terminal-Bench harness, and a slim `custom_agents/` folder for local agents. The current example is **pi-mono**, but the layout is ready for more.

## Layout
- `custom_agents/` — importable agent modules.
  - `pi_mono_agent.py` — `PiMonoAgent` (`BaseInstalledAgent`) that installs and runs the `pi` CLI.
  - `install_pi_mono.sh.j2` — install template (Node 20+, `@mariozechner/pi-coding-agent`, optional `pi-bundle.tgz`).
- `pi-mono/` — upstream pi-mono checkout (dev + bundling).
- `harbor/` — vendored Harbor source/docs for offline reference.

## Run Terminal-Bench with built-in agents
- Prereqs: Docker running; Harbor installed (`uv tool install harbor` or `pip install harbor`).
- Quick sanity check (oracle):  
  `harbor run -d terminal-bench@2.0 -a oracle` citeturn4view0
- Example with a prebuilt agent (Claude Code on Daytona):  
  ```
  export DAYTONA_API_KEY=...
  export ANTHROPIC_API_KEY=...
  harbor run \
    -d terminal-bench@2.0 \
    -m anthropic/claude-haiku-4-5 \
    -a claude-code \
    --env daytona \
    -n 32
  ``` citeturn4view0
- To see the full list of bundled agents (Terminus-2, Claude Code, Codex CLI, Gemini CLI, OpenHands, Mini-SWE-Agent, etc.), run `harbor run --help`. citeturn3view0

## Run Terminal-Bench with the custom pi-mono agent
Run from repo root so `custom_agents` is on `PYTHONPATH`.
```bash
# install Harbor once
uv tool install harbor  # or pip install harbor

# set provider API key(s), e.g.
export OPENAI_API_KEY=...

# launch a small task with pi-mono
harbor run \
  --dataset hello-world@head \
  --agent-import-path custom_agents.pi_mono_agent:PiMonoAgent \
  --model openai/gpt-4o \
  --agent-kwarg output_mode=json
```
What this agent does:
- During setup, Harbor renders `install_pi_mono.sh.j2` to install Node (if needed) and the `pi` CLI; if `custom_agents/pi-bundle.tgz` exists, it restores from that bundle to skip npm.  
- At runtime, it forwards provider/model flags to `pi`, passes through common API keys, streams output to `/logs/agent/pi_output.log`, and (JSON mode) saves `/logs/agent/results.json`.

## Add another custom agent
1) Create `custom_agents/<new_agent>.py` with a `BaseInstalledAgent` (or `BaseAgent`) subclass.  
2) If it needs install steps, add `install_<new_agent>.sh.j2` and reference it via `_install_agent_template_path`.  
3) Run Harbor with `--agent-import-path custom_agents.<new_agent>:ClassName` and any `--agent-kwarg key=value`. citeturn3view0

Tips:
- Keep `custom_agents/` importable (run from repo root or set `PYTHONPATH=$(pwd)`).
- Drop a prebuilt `pi-bundle.tgz` into `custom_agents/` to accelerate pi installs.
- OpenAI models can flag Terminal-Bench “weapons” scenarios; if you hit safety refusals, add a safety identifier per OpenAI guidance (e.g., include your org’s identifier string in the prompt/request headers as described at https://help.openai.com/en/articles/5428082-how-to-incorporate-a-safety-identifier).
