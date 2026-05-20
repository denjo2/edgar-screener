"""
Central configuration. Edit values here — nothing else needs changing.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# SEC API
# ---------------------------------------------------------------------------

# SEC requires a real name + contact email in User-Agent.
SEC_USER_AGENT = "Dennis Joseph denjo2@gmail.com"
SEC_HEADERS = {"User-Agent": SEC_USER_AGENT}

# SEC rate limit is 10 req/sec. 0.15 s between calls keeps us well under.
SEC_RATE_DELAY_SECONDS = 0.5

SEC_API_TIMEOUT_DEFAULT = 30  # seconds
SEC_API_TIMEOUT_FILING = 60   # 10-K HTML can be large

# ---------------------------------------------------------------------------
# Claude models
# ---------------------------------------------------------------------------

STAGE_1_MODEL = "claude-sonnet-4-6"   # fast batch screener
STAGE_2_MODEL = "claude-opus-4-7"     # thorough deep-dive analyst

STAGE_1_MAX_TOKENS = 8_192
STAGE_2_MAX_TOKENS = 16_000

# 10-Ks can exceed 1 M context, but cost matters.
# ~400 K chars ≈ 100 K tokens — enough to cover most 10-Ks without burning budget.
FILING_TEXT_MAX_CHARS = 400_000

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).parent
PROMPTS_DIR = ROOT_DIR / "prompts"
