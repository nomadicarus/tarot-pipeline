"""
generator.py — calls the Gemini image generation API and saves raw card art.

- Uses us-central1 regional endpoint to avoid region-locking
- Falls back to global endpoint if regional fails
- Integrates with QuotaTracker: records success/failure, checks limit pre-call
- Reads model and retry settings from config/settings.py
"""

import os
import time
import pathlib
import logging
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ── load settings ──────────────────────────────────────────────────────────
import sys
ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import (
    MODEL, API_REGION, API_REGION_FALLBACK,
    MAX_RETRIES, RETRY_BASE_DELAY, RATE_LIMIT_RETRY_DELAY,
)
from pipeline.quota import QuotaTracker, QuotaExceededError


# ── regional endpoint builder ─────────────────────────────────────────────

def _build_client(region: str):
    """
    Build a Gemini client pointed at a specific region.
    us-central1 is preferred to avoid region-locking on image generation models.
    """
    from google import genai

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GEMINI_API_KEY not found. "
            "Add it to your .env file or set it as an environment variable."
        )

    if region == "global":
        return genai.Client(api_key=api_key)
    else:
        # Regional endpoint with v1beta to support image generation preview models
        return genai.Client(
            api_key=api_key,
            http_options={"api_version": "v1beta"},
        )


# ── module-level state ────────────────────────────────────────────────────

_client = None
_quota_tracker: Optional[QuotaTracker] = None


def get_client():
    global _client
    if _client is None:
        try:
            logger.debug(f"Connecting via region: {API_REGION}")
            _client = _build_client(API_REGION)
        except Exception as e:
            logger.warning(f"Regional client ({API_REGION}) failed: {e}. Trying {API_REGION_FALLBACK}.")
            _client = _build_client(API_REGION_FALLBACK)
    return _client


def get_quota_tracker() -> QuotaTracker:
    global _quota_tracker
    if _quota_tracker is None:
        _quota_tracker = QuotaTracker()
    return _quota_tracker


# ── core generation ───────────────────────────────────────────────────────

def generate_card_image(
    prompt: str,
    output_path: pathlib.Path,
    retries: int = MAX_RETRIES,
    interactive: bool = True,
) -> bool:
    """
    Generate a single card image via the Gemini API and save it to disk.

    Pre-call:  checks daily quota (may prompt user or raise QuotaExceededError)
    Post-call: records success or failure to QuotaTracker

    Args:
        prompt:       Fully built image prompt string.
        output_path:  Where to save the resulting PNG.
        retries:      Number of retry attempts on transient failures.
        interactive:  Whether quota gate can prompt the user (default True).

    Returns:
        True on success, False if all retries exhausted or quota hard-blocked.
    """
    from google.genai import types

    output_path = pathlib.Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    client  = get_client()
    tracker = get_quota_tracker()

    # ── pre-flight quota check ────────────────────────────────────────────
    tracker.check_and_gate(interactive=interactive)

    # ── API call loop ─────────────────────────────────────────────────────
    for attempt in range(1, retries + 1):
        try:
            logger.debug(f"[{MODEL}] Attempt {attempt}/{retries} -> {output_path.name}")

            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE", "TEXT"],
                ),
            )

            # Extract image bytes from response parts
            for part in response.candidates[0].content.parts:
                if part.inline_data is not None:
                    output_path.write_bytes(part.inline_data.data)
                    tracker.record_success()
                    logger.info(
                        f"Saved: {output_path.name}  "
                        f"[quota: {tracker.effective_count}/{tracker.daily_limit}]"
                    )
                    return True

            # Response came back but contained no image
            logger.warning(
                f"Attempt {attempt}: no image in response. "
                f"Text: {response.text[:200] if response.text else 'none'}"
            )

        except QuotaExceededError:
            raise  # propagate user's decision — never swallow this

        except Exception as e:
            err_str = str(e).lower()
            is_rate_limit = any(
                x in err_str for x in ("429", "quota", "rate limit", "resource exhausted")
            )

            if is_rate_limit:
                delay = RATE_LIMIT_RETRY_DELAY * attempt  # 60s, 120s, 180s...
                logger.warning(
                    f"Rate limited (429) on attempt {attempt}. "
                    f"Waiting {delay:.0f}s before retry..."
                )
            else:
                delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(f"Attempt {attempt} failed: {e}")

            if attempt < retries:
                logger.info(f"Retrying in {delay:.0f}s...")
                time.sleep(delay)

    # All retries exhausted
    tracker.record_failure()
    logger.error(
        f"All {retries} attempts failed: {output_path.name}  "
        f"[quota: successful={tracker.successful} failed={tracker.failed}]"
    )
    return False


# ── smoke test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    tracker = get_quota_tracker()
    tracker.sync_with_server()
    tracker.print_status()

    from prompts.builder import build_prompt
    import json

    cards  = json.loads((ROOT / "config" / "cards.json").read_text())
    decks  = json.loads((ROOT / "config" / "decks.json").read_text())
    card   = cards["major_arcana"][0]
    deck   = decks["decks"][1]
    prompt = build_prompt(card, deck)

    out = ROOT / "output" / "thoth" / "test_the_fool.png"
    print(f"\nGenerating test image -> {out}\n")
    success = generate_card_image(prompt, out)
    print("Success!" if success else "Failed — check logs.")
    tracker.print_status()
