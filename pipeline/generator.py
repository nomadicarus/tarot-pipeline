"""
generator.py — Gemini API image generation stage only.

Responsibilities:
  - Build prompt from card + deck config
  - Call Gemini API, save raw PNG to output/{deck}/raw/
  - Write iTXt metadata into each raw PNG (card_name, suit, deck_id etc.)
  - Track quota via QuotaTracker
  - No compositing — that is handled separately by compositor.py

CLI:
    python pipeline/generator.py --deck thoth
    python pipeline/generator.py --deck thoth --cards "The Fool" "The Magus"
    python pipeline/generator.py --deck all
    (normally invoked via main.py --generate)
"""

import os
import time
import pathlib
import logging
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)

import sys
ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import (
    MODEL, API_REGION, API_REGION_FALLBACK,
    MAX_RETRIES, RETRY_BASE_DELAY, RATE_LIMIT_RETRY_DELAY,
)
from pipeline.quota import QuotaTracker, QuotaExceededError
from pipeline.manifest import write_metadata

# ── client ────────────────────────────────────────────────────────────────

_client = None
_quota_tracker: Optional[QuotaTracker] = None


def _build_client(region: str):
    from google import genai
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY not found in environment or .env file.")
    if region == "global":
        return genai.Client(api_key=api_key)
    return genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})


def get_client():
    global _client
    if _client is None:
        try:
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
    prompt:      str,
    output_path: pathlib.Path,
    card:        dict,
    deck:        dict,
    deck_type:   str = "tarot",
    retries:     int = MAX_RETRIES,
) -> bool:
    """
    Generate a single card image and save raw PNG with iTXt metadata.

    Args:
        prompt:      Fully built prompt string.
        output_path: Path to save the raw PNG.
        card:        Card dict from cards.json (used for metadata).
        deck:        Deck dict from decks.json (used for metadata).
        deck_type:   Card deck type for metadata (default "tarot").
        retries:     Number of retry attempts.

    Returns:
        True on success, False on failure.
    """
    from google.genai import types

    output_path = pathlib.Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    client  = get_client()
    tracker = get_quota_tracker()

    # Pre-flight quota gate
    tracker.check_and_gate()

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

            for part in response.candidates[0].content.parts:
                if part.inline_data is not None:
                    output_path.write_bytes(part.inline_data.data)

                    # Write iTXt metadata into the raw PNG
                    write_metadata(output_path, card, deck, prompt, deck_type=deck_type)

                    tracker.record_success()
                    logger.info(
                        f"Saved: {output_path.name}  "
                        f"[quota: {tracker.effective_count}/{tracker.daily_limit}]"
                    )
                    return True

            logger.warning(f"Attempt {attempt}: no image in response.")

        except QuotaExceededError:
            raise

        except Exception as e:
            err_str = str(e).lower()
            is_rate_limit = any(
                x in err_str for x in ("429", "quota", "rate limit", "resource exhausted")
            )
            if is_rate_limit:
                delay = RATE_LIMIT_RETRY_DELAY * attempt
                logger.warning(f"Rate limited (429) attempt {attempt}. Waiting {delay:.0f}s...")
            else:
                delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(f"Attempt {attempt} failed: {e}")

            if attempt < retries:
                logger.info(f"Retrying in {delay:.0f}s...")
                time.sleep(delay)

    tracker.record_failure()
    logger.error(f"All {retries} attempts failed: {output_path.name}")
    return False
