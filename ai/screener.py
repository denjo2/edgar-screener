"""
Stage 1: Batch screening via Claude Sonnet.

Sends a list of Financials dicts to the model and parses the JSON verdict
array back into a list of ScreeningResult dicts.

The system prompt is loaded from prompts/stage1_screen.md at import time and
cached for the process lifetime. The cache_control block tells Claude to
cache the prompt across API calls — since the prompt is static and large,
this saves cost and latency when screening many batches in one session.

To change the screening logic or output format, edit prompts/stage1_screen.md.
Do not hardcode criteria in this file.
"""

import json

import anthropic

from config import PROMPTS_DIR, STAGE_1_MAX_TOKENS, STAGE_1_MODEL
from models import Financials, ScreeningResult

# Load once at import time so repeated calls don't re-read disk.
_SYSTEM_PROMPT: str = (PROMPTS_DIR / "stage1_screen.md").read_text(encoding="utf-8")


def screen_batch(companies: list[Financials]) -> list[ScreeningResult]:
    """
    Screen a list of companies and return one ScreeningResult per company.

    Raises json.JSONDecodeError if the model returns malformed JSON —
    the caller (pipeline.py) should handle this and decide whether to retry.
    """
    client = anthropic.Anthropic()

    payload = json.dumps(
        [c.to_dict() for c in companies],
        indent=2,
        default=str,
    )

    response = client.messages.create(
        model=STAGE_1_MODEL,
        max_tokens=STAGE_1_MAX_TOKENS,
        system=[
            {
                "type": "text",
                "text": _SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": (
                    "Analyze the following microcap companies. All financials are "
                    "from SEC EDGAR XBRL (US-GAAP). TTM values are pre-computed; "
                    "balance sheet items are point-in-time. Dollar values are USD.\n\n"
                    f"{payload}\n\n"
                    "Return the JSON verdict array."
                ),
            }
        ],
    )

    raw = response.content[0].text
    return json.loads(raw)
