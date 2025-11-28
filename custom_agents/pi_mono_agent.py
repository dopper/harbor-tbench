"""
Pi-Mono Coding Agent for Harbor.
This agent wraps the pi-coding-agent CLI tool from the pi-mono monorepo.
"""

import json
import shlex
import os
from pathlib import Path
from typing import List, Optional

from harbor.agents.installed.base import BaseInstalledAgent, ExecInput
from harbor.models.agent.context import AgentContext


class PiMonoAgent(BaseInstalledAgent):
    """
    Custom agent that installs and runs the pi-coding-agent CLI.

    The pi-coding-agent is a radically simple coding agent with multi-model support,
    including the ability to switch models mid-session. It provides tools for
    reading, editing, writing files, and executing bash commands.
    """

    def __init__(self, logs_dir: Path, model_name: Optional[str] = None, **kwargs):
        """Initialize with model information."""
        super().__init__(logs_dir, model_name, **kwargs)

        # Parse model configuration
        self.provider = kwargs.get("provider")  # resolved below
        self.pi_model = kwargs.get("pi_model")  # Specific model ID for pi
        self.output_mode = kwargs.get("output_mode", "json")  # json or text
        self.no_session = kwargs.get("no_session", False)  # Ephemeral mode
        self.timeout_seconds = kwargs.get("timeout_seconds", 1800)  # 30 min default

        # Require model_name in provider/model format for clarity (mirrors opencode)
        if not self.provider:
            if not model_name or "/" not in model_name:
                raise ValueError("PiMonoAgent expects model_name like 'provider/model'.")
            provider, model = model_name.split("/", 1)
        else:
            provider = self.provider
            model = model_name.split("/", 1)[1] if model_name and "/" in model_name else (model_name or "")

        # Map Harbor provider names to pi-coding-agent provider names
        provider_map = {
            "anthropic": "anthropic",
            "openai": "openai",
            "google": "google",
            "groq": "groq",
            "cerebras": "cerebras",
            "xai": "xai",
            "openrouter": "openrouter",
        }

        if provider not in provider_map:
            raise ValueError(f"Unknown provider '{provider}' for pi-mono agent.")

        self.provider = provider_map[provider]

        # Map specific model names if not explicitly provided
        if not self.pi_model:
            lower_model = model.lower()
            if "claude" in model.lower():
                if "haiku" in model.lower():
                    self.pi_model = "claude-3-5-haiku-latest"
                elif "opus" in model.lower():
                    self.pi_model = "claude-3-opus-latest"
                elif "sonnet" in model.lower():
                    self.pi_model = "claude-3-5-sonnet-latest"
            elif "gpt" in model.lower():
                if "5.1-codex-mini" in lower_model:
                    self.pi_model = "gpt-5.1-codex-mini"
                elif "5.1-codex" in lower_model:
                    self.pi_model = "gpt-5.1-codex"
                elif "5.1" in lower_model:
                    self.pi_model = "gpt-5.1"
                elif "4o" in lower_model:
                    self.pi_model = "gpt-4o"
                elif "4-turbo" in lower_model or "4turbo" in lower_model:
                    self.pi_model = "gpt-4-turbo"
                elif "o1" in lower_model:
                    self.pi_model = "o1-preview"
                elif "3.5" in lower_model:
                    self.pi_model = "gpt-3.5-turbo"
                else:
                    # Default to gpt-4o for unknown GPT models
                    self.pi_model = "gpt-4o"
                    self.logger.warning(f"Unknown GPT model '{model}', defaulting to gpt-4o")
            elif "gemini" in model.lower():
                self.pi_model = "gemini-2.0-flash-exp"
            else:
                # Fall back to provided model string
                self.pi_model = model

        # Normalize model IDs so `--provider openai` works with either
        # `gpt-5.1-codex` or `openai/gpt-5.1-codex` inputs.
        self.pi_model = self._normalize_model_id(self.provider, self.pi_model)

    @staticmethod
    def _normalize_model_id(provider: str, model: Optional[str]) -> Optional[str]:
        """
        Pi CLI expects model IDs without the provider prefix for built-in providers
        (e.g., `--provider openai --model gpt-5.1-codex`). Harbor configs sometimes
        pass `openai/gpt-5.1-codex`, which Pi interprets as `openai/openai/...`.
        Strip the provider prefix when it matches the selected provider.
        """
        if not model or "/" not in model:
            return model

        prefix, remainder = model.split("/", 1)
        if prefix.lower() == provider.lower():
            return remainder
        return model

    @staticmethod
    def name() -> str:
        """Return the agent name."""
        return "pi-mono"

    def version(self) -> Optional[str]:
        """Return the agent version."""
        return "1.0.0"

    @property
    def _template_variables(self) -> dict[str, str]:
        """Expose provider/model to the install template for defaults."""
        return {
            **super()._template_variables,
            "provider": self.provider,
            "pi_model": self.pi_model,
        }

    @property
    def _install_agent_template_path(self) -> Path:
        """
        Path to the installation script template.
        This template will be rendered and executed during setup.
        """
        return Path(__file__).parent / "install_pi_mono.sh.j2"

    async def setup(self, environment):
        """
        Override setup to optionally upload a prebuilt pi bundle to speed install.
        If pi-bundle.tgz exists alongside this file, it is uploaded to /tmp/pi-bundle.tgz
        and the installer will extract it instead of running npm every time.
        """
        agent_dir = Path(__file__).parent
        bundle = agent_dir / "pi-bundle.tgz"
        if bundle.exists():
            self.logger.debug(f"Found prebuilt pi bundle at {bundle}, uploading for fast install")
            await environment.upload_file(source_path=bundle, target_path="/tmp/pi-bundle.tgz")

        await super().setup(environment)

    def create_run_agent_commands(self, instruction: str) -> List[ExecInput]:
        """
        Create the command(s) to run pi-coding-agent.

        Args:
            instruction: The task instruction to pass to the agent

        Returns:
            List of commands to execute
        """
        # Escape the instruction for shell safety
        escaped_instruction = shlex.quote(instruction)

        # Prepare environment variables based on provider
        env_vars = {}

        # Set API keys based on provider
        api_key_mapping = {
            "anthropic": ("ANTHROPIC_API_KEY", "ANTHROPIC_OAUTH_TOKEN"),
            "openai": ("OPENAI_API_KEY",),
            "google": ("GEMINI_API_KEY",),
            "groq": ("GROQ_API_KEY",),
            "cerebras": ("CEREBRAS_API_KEY",),
            "xai": ("XAI_API_KEY",),
            "openrouter": ("OPENROUTER_API_KEY",),
        }

        # Check for API keys and set them
        if self.provider in api_key_mapping:
            for key_name in api_key_mapping[self.provider]:
                key_value = os.environ.get(key_name)
                if key_value:
                    env_vars[key_name] = key_value
                    break  # Use first available key

        # Always pass through common API keys in case the agent needs them
        for key in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"]:
            if key not in env_vars and key in os.environ:
                env_vars[key] = os.environ[key]

        # Pass through OpenAI context needed for gated models like gpt-5.1-codex
        for key in [
            "OPENAI_USER_EMAIL",
            "OPENAI_ORG",
            "OPENAI_ORG_ID",
            "OPENAI_PROJECT",
            "OPENAI_PROJECT_ID",
            "OPENAI_API_BASE",
        ]:
            if key in os.environ:
                env_vars[key] = os.environ[key]

        commands = []

        # Create working directory
        commands.append(
            ExecInput(
                command="mkdir -p /logs/agent/pi_session",
                env=env_vars if env_vars else None,
                cwd="/workspace",
            )
        )

        # Build the pi command
        pi_command_parts = ["pi"]

        # Add provider and model if specified
        if self.provider:
            pi_command_parts.extend(["--provider", self.provider])

        if self.pi_model:
            pi_command_parts.extend(["--model", self.pi_model])

        # Add output mode
        pi_command_parts.extend(["--mode", self.output_mode])

        # Add session control
        if self.no_session:
            pi_command_parts.append("--no-session")

        # Add the instruction as the message
        pi_command_parts.append(escaped_instruction)

        # Join command parts and add output redirection
        main_command = (
            f"cd /workspace && "
            f"timeout {self.timeout_seconds} "
            f"{' '.join(pi_command_parts)} "
            f"2>&1 | tee /logs/agent/pi_output.log"
        )

        commands.append(
            ExecInput(
                command=main_command,
                env=env_vars if env_vars else None,
                timeout_sec=self.timeout_seconds + 60,  # Add buffer
                cwd="/workspace",
            )
        )

        # If using JSON mode, try to extract the structured output
        if self.output_mode == "json":
            commands.append(
                ExecInput(
                    command=(
                        "if [ -f /logs/agent/pi_output.log ]; then "
                        "  echo '=== Extracting JSON results ===' && "
                        "  python3 -c \"import json, sys; "
                        "lines = open('/logs/agent/pi_output.log').readlines(); "
                        "json_lines = [l for l in lines if l.strip().startswith('{')]; "
                        "if json_lines: "
                        "  data = json.loads(json_lines[-1]); "
                        "  json.dump(data, open('/logs/agent/results.json', 'w'), indent=2); "
                        "  print('Results saved to results.json')"
                        "\" 2>/dev/null || echo 'Could not parse JSON output'; "
                        "fi"
                    ),
                    env=env_vars if env_vars else None,
                    cwd="/workspace",
                )
            )

        # Check final state
        commands.append(
            ExecInput(
                command=(
                    "echo '=== Pi-Mono Session Complete ===' && "
                    "ls -la /workspace && "
                    "git status 2>/dev/null || true"
                ),
                env=env_vars if env_vars else None,
                cwd="/workspace",
            )
        )

        return commands

    def populate_context_post_run(self, context: AgentContext) -> None:
        """
        Parse pi-coding-agent's output and populate the context with metrics.

        Args:
            context: The context to populate with metrics
        """
        self.logger.info("Parsing results from pi-coding-agent")

        # Look for the output log
        # First try the direct path where we save it
        output_file = self.logs_dir / "pi_output.log"
        # Fallback to command directory if not found
        if not output_file.exists():
            output_file = self.logs_dir / "command-1" / "pi_output.log"

        if not output_file.exists():
            self.logger.warning("Pi-coding-agent output file not found")
            context.metadata = {
                "error": "No output file found",
                "provider": self.provider,
                "model": self.pi_model or "default",
            }
            return

        # Parse the JSON streaming log to extract actual API usage
        try:
            total_input_tokens = 0
            total_output_tokens = 0
            total_cache_read_tokens = 0
            total_cache_write_tokens = 0
            total_cost = 0.0

            with open(output_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or not line.startswith('{'):
                        continue

                    try:
                        event = json.loads(line)

                        # Look for message_end events from assistant with usage data
                        if (event.get("type") == "message_end" and
                            "message" in event and
                            event["message"].get("role") == "assistant" and
                            "usage" in event["message"]):

                            usage = event["message"]["usage"]

                            # Accumulate token counts
                            total_input_tokens += usage.get("input", 0)
                            total_output_tokens += usage.get("output", 0)
                            total_cache_read_tokens += usage.get("cacheRead", 0)
                            total_cache_write_tokens += usage.get("cacheWrite", 0)

                            # Accumulate cost if available
                            if "cost" in usage:
                                if isinstance(usage["cost"], dict):
                                    total_cost += usage["cost"].get("total", 0)
                                else:
                                    total_cost += usage["cost"]

                    except json.JSONDecodeError:
                        continue  # Skip malformed JSON lines

            # Set context with actual API usage
            context.n_input_tokens = total_input_tokens
            context.n_output_tokens = total_output_tokens
            context.n_cache_tokens = total_cache_read_tokens
            context.cost_usd = total_cost

            # Check if we got any data
            if total_input_tokens == 0 and total_output_tokens == 0:
                self.logger.warning("No usage data found in streaming log, using fallback estimation")
                # Fallback: count actual output in the log
                with open(output_file, 'r') as f:
                    lines = f.readlines()

                # Try to estimate from actual model output (not the JSON overhead)
                # Count characters in assistant message content only
                actual_content_chars = 0
                for line in lines:
                    if '"role":"assistant"' in line and '"content"' in line:
                        try:
                            event = json.loads(line.strip())
                            if "message" in event and "content" in event["message"]:
                                content = str(event["message"]["content"])
                                actual_content_chars += len(content)
                        except:
                            pass

                # Much more conservative estimate
                context.n_input_tokens = 500  # Rough estimate for typical instruction
                context.n_output_tokens = max(actual_content_chars // 4, 100)

                # Estimate cost
                cost_per_1k_out = {
                    "anthropic": 0.015,  # Sonnet output
                    "openai": 0.002,     # GPT-4o output
                    "google": 0.001,
                    "groq": 0.0,
                }.get(self.provider, 0.002)

                cost_per_1k_in = cost_per_1k_out / 5  # Input typically 5x cheaper

                context.cost_usd = (
                    (context.n_input_tokens / 1000) * cost_per_1k_in +
                    (context.n_output_tokens / 1000) * cost_per_1k_out
                )

            # Look for error indicators
            with open(output_file, 'r') as f:
                first_lines = [next(f, '') for _ in range(20)]
            has_errors = any("error" in line.lower() or "failed" in line.lower()
                            for line in first_lines)

            context.metadata = {
                "provider": self.provider,
                "model": self.pi_model or "default",
                "output_mode": self.output_mode,
                "success": not has_errors and total_output_tokens > 0,
                "session_saved": not self.no_session,
                "actual_api_usage": total_input_tokens > 0 or total_output_tokens > 0,
            }

            self.logger.info(
                f"Actual API usage: {context.n_input_tokens} input, "
                f"{context.n_output_tokens} output, "
                f"{context.n_cache_tokens} cache read tokens, "
                f"${context.cost_usd:.4f} cost"
            )

        except Exception as e:
            self.logger.error(f"Failed to parse pi-coding-agent output: {e}")
            context.metadata = {
                "error": str(e),
                "provider": self.provider,
                "model": self.pi_model or "default",
            }
