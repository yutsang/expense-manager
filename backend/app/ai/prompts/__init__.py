from __future__ import annotations

from pathlib import Path

SYSTEM_PROMPT_VERSION = "v1"
SYSTEM_PROMPT = (Path(__file__).parent / "system_prompt.md").read_text()
