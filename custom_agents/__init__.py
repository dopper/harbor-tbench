"""
Make PiMonoAgent importable via the shorthand path `custom_agents:PiMonoAgent`.

Harbor's `--agent-import-path` expects the module portion to export the agent
class directly. Without this file, `custom_agents` is just a namespace package
and `harbor run --agent-import-path custom_agents:PiMonoAgent` fails with
`ImportError: cannot import name 'PiMonoAgent'`.
"""

from .pi_mono_agent import PiMonoAgent

__all__ = ["PiMonoAgent"]
