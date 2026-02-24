"""
Example config — copy to config.py or just use env vars.
All values can be overridden via environment variables.
"""
import os

CDP_ENDPOINT = os.getenv("CDP_ENDPOINT", "http://127.0.0.1:18800")
PLAYER_NAME = os.getenv("POKER_PLAYER_NAME", "Clawhi")
MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

if not API_KEY:
    raise RuntimeError("ANTHROPIC_API_KEY env var is required. Set it in .env or export it.")
