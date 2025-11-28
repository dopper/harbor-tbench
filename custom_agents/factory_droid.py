"""
Factory Droid custom agent for Harbor.
This agent wraps the Factory AI Droid CLI tool.

IMPORTANT: Factory Droid requires browser authentication on first run,
which is not possible in containerized environments. This agent automatically
uploads essential configuration files (auth.json, settings.json, config.json)
from ~/.factory/ on the host to the container, allowing Factory Droid to work
seamlessly.

Prerequisites:
- Run 'droid' on your host machine first to authenticate
- Ensure ~/.factory/auth.json exists with valid tokens
"""

import json
import os
import shlex
from pathlib import Path
from typing import List, Optional

from harbor.agents.installed.base import BaseInstalledAgent, ExecInput
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext


class FactoryDroidAgent(BaseInstalledAgent):
    """
    Custom agent that installs and runs Factory AI's Droid CLI.

    This agent automatically handles Factory Droid's authentication by:
    1. Uploading essential config files (auth.json, settings.json, config.json)
       from ~/.factory/ on host to container
    2. Using your existing auth tokens for seamless operation

    To use actual Factory Droid:
    - Run 'droid' on your host machine first to authenticate
    - Ensure ~/.factory/auth.json exists with valid tokens
    - The agent will automatically upload these files during setup

    Optional: Set FACTORY_AUTH_TOKEN environment variable for additional auth methods
    """

    def __init__(self, logs_dir: Path, model_name: Optional[str] = None, **kwargs):
        """Initialize with model information."""
        super().__init__(logs_dir, model_name, **kwargs)

        self.auth_token = os.environ.get("FACTORY_AUTH_TOKEN")

        # Model ID mapping: short name -> Factory model ID
        self._model_id_map = {
            "sonnet": "claude-sonnet-4-20250514",
            "opus": "claude-opus-4-1-20250805",
            "haiku": "claude-sonnet-4-20250514",  # Fallback to sonnet (no haiku in Factory)
            "gpt-5": "gpt-5-codex",
            "gpt-5-codex": "gpt-5-codex",
            "gpt-5-high": "gpt-5-codex-high",
        }

        # Extract model preference from kwargs or model_name
        short_model = kwargs.get("droid_model", "sonnet")  # Default to Sonnet
        if model_name and "/" in model_name:
            provider, model = model_name.split("/", 1)
            if provider == "anthropic":
                if "haiku" in model.lower():
                    short_model = "haiku"
                elif "opus" in model.lower():
                    short_model = "opus"
                elif "sonnet" in model.lower():
                    short_model = "sonnet"
            elif provider == "openai":
                if "gpt-5" in model.lower():
                    short_model = "gpt-5"

        # Map to actual Factory model ID
        self.droid_model = self._model_id_map.get(short_model, short_model)

        self.reasoning_effort = kwargs.get("reasoning_effort", "medium")
        self.timeout_seconds = kwargs.get("timeout_seconds", 1800)  # 30 min default
        # Track the last instruction so post-run metrics can use it
        self._last_instruction: Optional[str] = None

    @staticmethod
    def name() -> str:
        """Return the agent name."""
        return "factory-droid"

    def version(self) -> Optional[str]:
        """Return the agent version."""
        return "1.0.0"

    @property
    def _install_agent_template_path(self) -> Path:
        """
        Path to the installation script template.
        This template will be rendered and executed during setup.
        """
        return Path(__file__).parent / "install_factory_droid.sh.j2"

    async def setup(self, environment: BaseEnvironment) -> None:
        """
        Override setup to upload Factory Droid configuration files.

        This allows the Factory Droid agent to work in containerized environments
        by copying essential auth and config files from the host machine.

        Uploads:
        - auth.json: Authentication tokens
        - config.json: Factory configuration
        - settings.json: User preferences
        """
        # Run standard installation
        await super().setup(environment)

        # Upload essential Factory files if they exist on host
        factory_dir = Path.home() / ".factory"
        if not factory_dir.exists():
            self.logger.warning(
                "No .factory directory found on host at ~/.factory. "
                "Factory Droid will require manual authentication (not possible in containers)."
            )
            self.logger.info(
                "To fix: Run 'droid' on your host machine first to authenticate"
            )
            return

        # Files to upload (in order of importance)
        essential_files = ["auth.json", "settings.json", "config.json"]
        uploaded_count = 0

        for filename in essential_files:
            source_file = factory_dir / filename
            if source_file.exists():
                self.logger.info(f"Uploading {filename}...")
                try:
                    target_path = f"/root/.factory/{filename}"

                    # If uploading config.json, inject runtime API keys so custom models resolve
                    if filename == "config.json":
                        patched_path = source_file
                        try:
                            with open(source_file, "r", encoding="utf-8") as f:
                                config_data = f.read()

                            openai_key = os.environ.get("OPENAI_API_KEY")
                            ollama_key = os.environ.get("OLLAMA_API_KEY")

                            if openai_key:
                                config_data = config_data.replace(
                                    "${OPENAI_API_KEY}", openai_key
                                )
                            if ollama_key:
                                config_data = config_data.replace(
                                    "${OLLAMA_API_KEY}", ollama_key
                                )

                            tmp_path = Path("/tmp/factory_config_patched.json")
                            tmp_path.write_text(config_data, encoding="utf-8")
                            patched_path = tmp_path
                        except Exception as e:
                            self.logger.warning(
                                f"  WARNING: Failed to patch config.json with env keys: {e}"
                            )
                            patched_path = source_file

                        await environment.upload_file(
                            source_path=patched_path, target_path=target_path
                        )
                    else:
                        await environment.upload_file(
                            source_path=source_file, target_path=target_path
                        )
                    uploaded_count += 1
                    self.logger.info(f"  ✓ {filename} uploaded")
                except Exception as e:
                    self.logger.error(f"  ✗ Failed to upload {filename}: {e}")
            else:
                self.logger.warning(f"  ⊘ {filename} not found (skipping)")

        if uploaded_count > 0:
            self.logger.info(
                f"✓ Uploaded {uploaded_count}/{len(essential_files)} Factory configuration files"
            )
            if "auth.json" in [
                f for f in essential_files if (factory_dir / f).exists()
            ]:
                self.logger.info(
                    "  Factory Droid should now work with authenticated session"
                )
        else:
            self.logger.warning(
                "No Factory configuration files found. "
                "Factory Droid may require manual authentication."
            )

    def create_run_agent_commands(self, instruction: str) -> List[ExecInput]:
        """
        Create the command(s) to run Factory Droid.

        Args:
            instruction: The task instruction to pass to droid

        Returns:
            List of commands to execute
        """
        # Remember the instruction for later metric estimation
        self._last_instruction = instruction

        # Escape the instruction for shell safety
        escaped_instruction = shlex.quote(instruction)

        # Prepare environment variables
        env_vars = {}

        # Set Factory API key if available
        factory_key = os.environ.get("FACTORY_API_KEY")
        if factory_key:
            env_vars["FACTORY_API_KEY"] = factory_key

        # Also check for Anthropic/OpenAI keys since Factory might use them
        anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
        if anthropic_key:
            env_vars["ANTHROPIC_API_KEY"] = anthropic_key

        openai_key = os.environ.get("OPENAI_API_KEY")
        if openai_key:
            env_vars["OPENAI_API_KEY"] = openai_key

        # Add auth token if available
        if self.auth_token:
            env_vars["FACTORY_AUTH_TOKEN"] = self.auth_token

        commands = []

        # Create a working directory for the session
        commands.append(
            ExecInput(
                command="mkdir -p /logs/agent/droid_session",
                env=env_vars if env_vars else None,
                cwd="/workspace",
            )
        )

        # Attempt to run real Factory Droid
        # First check if authentication might work
        commands.append(
            ExecInput(
                command=(
                    "echo 'Checking Factory Droid authentication...' && "
                    "if [ -f ~/.factory/auth.json ]; then "
                    "  echo 'Auth file found'; "
                    "else "
                    "  echo 'WARNING: No auth file found. Factory Droid may fail.'; "
                    "  echo 'To authenticate: run droid on host machine first, or set FACTORY_AUTH_TOKEN'; "
                    "fi"
                ),
                env=env_vars if env_vars else None,
                cwd="/workspace",
            )
        )

        # Build droid exec command with proper flags
        # Use droid exec for headless/non-interactive execution
        droid_cmd_parts = ["droid", "exec"]

        # Add model flag
        droid_cmd_parts.extend(["-m", self.droid_model])

        # Add reasoning effort flag if specified
        if self.reasoning_effort and self.reasoning_effort != "off":
            droid_cmd_parts.extend(["-r", self.reasoning_effort])

        # Add auto-approval flag to grant permissions automatically
        # Match the auto level to reasoning effort, default to 'high' for non-interactive execution
        auto_level = (
            self.reasoning_effort
            if self.reasoning_effort and self.reasoning_effort != "off"
            else "high"
        )
        droid_cmd_parts.extend(["--auto", auto_level])

        # Add the instruction (properly escaped)
        droid_cmd_parts.append(escaped_instruction)

        # Join command and add timeout + logging
        droid_command = " ".join(droid_cmd_parts)
        main_command = (
            f"timeout {self.timeout_seconds} "
            f"{droid_command} "
            f"2>&1 | tee /logs/agent/droid_output.log || "
            f"echo 'Factory Droid failed - likely due to authentication requirements'"
        )

        commands.append(
            ExecInput(
                command=main_command,
                env=env_vars if env_vars else None,
                timeout_sec=self.timeout_seconds + 60,
                cwd="/workspace",
            )
        )

        # Try to extract any generated files or results
        commands.append(
            ExecInput(
                command=(
                    "echo '=== Factory Droid Session Complete ===' && "
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
        Parse Factory Droid's output and populate the context with metrics.

        Args:
            context: The context to populate with metrics
        """
        self.logger.info("Parsing results from Factory Droid")

        # Look for the output log
        output_file = (
            self.logs_dir / "command-2" / "droid_output.log"
        )  # command-2 is the main droid command

        if output_file.exists():
            try:
                with open(output_file, "r") as f:
                    output_content = f.read()

                # Try to extract metrics from the output
                # Factory Droid doesn't provide structured metrics, so we estimate
                lines = output_content.split("\n")

                # Count approximate tokens based on output size
                # This is a rough estimation since Factory doesn't expose token counts
                char_count = len(output_content)
                estimated_tokens = (
                    char_count // 4
                )  # Rough approximation: 4 chars per token

                # Split tokens between input and output
                if self._last_instruction:
                    approx_input_tokens = max(len(self._last_instruction) // 4, 1)
                else:
                    approx_input_tokens = None

                context.n_input_tokens = approx_input_tokens
                context.n_output_tokens = estimated_tokens if estimated_tokens > 0 else None

                # Estimate cost based on model (these are rough estimates)
                cost_per_1k_tokens = {
                    "sonnet": 0.003,
                    "opus": 0.015,
                    "haiku": 0.0008,
                    "GPT-5": 0.01,
                    "droid-core": 0.002,
                }

                rate = cost_per_1k_tokens.get(self.droid_model, 0.003)
                total_tokens = (context.n_input_tokens or 0) + (context.n_output_tokens or 0)
                context.cost_usd = (total_tokens / 1000) * rate if total_tokens else None

                # Check if the session completed successfully
                success = "Factory Droid Session Complete" in output_content

                # Extract any error messages
                error_lines = [
                    line
                    for line in lines
                    if "error" in line.lower() or "failed" in line.lower()
                ]

                context.metadata = {
                    "droid_model": self.droid_model,
                    "reasoning_effort": self.reasoning_effort,
                    "success": success,
                    "output_lines": len(lines),
                    "errors": error_lines[:5]
                    if error_lines
                    else None,  # First 5 error lines
                }

                cost_display = (
                    f"${context.cost_usd:.4f}" if context.cost_usd is not None else "n/a"
                )
                self.logger.info(
                    f"Metrics extracted: {context.n_input_tokens} input tokens, "
                    f"{context.n_output_tokens} output tokens, {cost_display} cost"
                )

            except Exception as e:
                self.logger.error(f"Failed to parse Factory Droid output: {e}")
                context.metadata = {"error": str(e), "droid_model": self.droid_model}
        else:
            self.logger.warning("Factory Droid output file not found")

            # Check if there are any command outputs
            for i in range(5):
                cmd_output = self.logs_dir / f"command-{i}" / "stdout.txt"
                if cmd_output.exists():
                    with open(cmd_output, "r") as f:
                        content = f.read()
                        if content:
                            context.metadata = {
                                "error": "No main output file",
                                "command_output_sample": content[:500],
                                "droid_model": self.droid_model,
                            }
                            break
