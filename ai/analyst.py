"""
Stage 2: Deep-dive analysis via Claude Opus.

Takes the raw 10-K text for one company and returns a structured markdown
memo covering business overview, moat, management, financial quality, risks,
variant view, and a final analyst verdict.

Two cache_control blocks are used:
  1. System prompt — static across all deep-dives in a session; cached once.
  2. Filing text   — cached per-filing. If the caller re-runs the deep-dive
                     on the same 10-K (e.g. prompt iteration), the filing body
                     is served from cache on the second call.

To change the memo structure or analysis instructions, edit
prompts/stage2_deepdive.md. Do not hardcode instructions in this file.
"""

import anthropic

from config import (
    FILING_TEXT_MAX_CHARS,
    PROMPTS_DIR,
    STAGE_2_MAX_TOKENS,
    STAGE_2_MODEL,
)

_SYSTEM_PROMPT: str = (PROMPTS_DIR / "stage2_deepdive.md").read_text(encoding="utf-8")


def deep_dive(company_name: str, ticker: str, filing_text: str) -> str:
    """
    Run a full deep-dive on a single company's 10-K and return the memo as
    a markdown string.

    filing_text is truncated to FILING_TEXT_MAX_CHARS before sending.
    The truncation point is noted in the text so the model knows the filing
    was cut off.
    """
    client = anthropic.Anthropic()

    if len(filing_text) > FILING_TEXT_MAX_CHARS:
        filing_text = filing_text[:FILING_TEXT_MAX_CHARS] + "\n\n[FILING TRUNCATED]"

    response = client.messages.create(
        model=STAGE_2_MODEL,
        max_tokens=STAGE_2_MAX_TOKENS,
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
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"Perform a deep-dive analysis on "
                            f"{company_name} ({ticker}).\n\n"
                            "Below is the company's most recent 10-K filing:"
                        ),
                    },
                    {
                        "type": "text",
                        "text": filing_text,
                        "cache_control": {"type": "ephemeral"},
                    },
                ],
            }
        ],
    )

    return response.content[0].text
