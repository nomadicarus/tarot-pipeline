"""
pipeline/generator.py — Gemini API image generation.

Public API:
    generate_card_image(prompt, output_path, card, deck, deck_type, retries)
        Generate a single card image, write iTXt metadata, track quota.

    generate_batch(cards, deck, output_root, force, no_metadata)
        Batch wrapper — iterates cards, calls generate_card_image per card.

Quota gating, retry logic and cost tracking are handled internally.
All settings are read from config/settings.py.
"""

import logging
import os
import pathlib
import time
from typing import List, Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

import sys

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import (
    API_CALL_DELAY,
    API_REGION,
    API_REGION_FALLBACK,
    MAX_RETRIES,
    MODEL,
    RATE_LIMIT_RETRY_DELAY,
    RETRY_BASE_DELAY,
)
from pipeline.manifest import write_metadata
from pipeline.quota import QuotaExceededError, QuotaTracker, QuotaUserDeclined

# ── client ────────────────────────────────────────────────────────────────

_client = None
_tracker = None


def _build_client(region: str):
    from google import genai

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY not found. Add it to your .env file.")
    if region == "global":
        return genai.Client(api_key=api_key)
    return genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})


def get_client():
    global _client
    if _client is None:
        try:
            logger.debug(f"Connecting via region: {API_REGION}")
            _client = _build_client(API_REGION)
        except Exception as e:
            logger.warning(
                f"Regional client ({API_REGION}) failed: {e}. "
                f"Trying {API_REGION_FALLBACK}."
            )
            _client = _build_client(API_REGION_FALLBACK)
    return _client


def get_tracker(guardrail: Optional[str] = None) -> QuotaTracker:
    global _tracker
    if _tracker is None:
        _tracker = QuotaTracker(guardrail_mode=guardrail)
    return _tracker


# ── single image generation ───────────────────────────────────────────────


def generate_card_image(
    prompt: str,
    output_path: pathlib.Path,
    card: dict,
    deck: dict,
    deck_type: str = "tarot",
    retries: int = MAX_RETRIES,
    no_metadata: bool = False,
) -> bool:
    """
    Generate a single card image via the Gemini API.

    Writes iTXt metadata into the PNG after generation unless no_metadata=True.
    Tracks quota via QuotaTracker (check_and_gate before, record after).

    Args:
        prompt:      Fully built prompt string.
        output_path: Where to save the raw PNG.
        card:        Card dict from cards.json (used for metadata).
        deck:        Deck dict from decks.json (used for metadata).
        deck_type:   Deck type for metadata (default "tarot").
        retries:     Number of retry attempts on failure.
        no_metadata: If True, skip writing iTXt metadata.

    Returns:
        True on success, False on failure.

    Raises:
        QuotaExceededError / QuotaUserDeclined: propagated from quota gate.
    """
    from google.genai import types

    output_path = pathlib.Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    client = get_client()
    tracker = get_tracker()

    # Pre-call quota gate
    tracker.check_and_gate()

    for attempt in range(1, retries + 1):
        try:
            logger.debug(f"[{MODEL}] Attempt {attempt}/{retries} → {output_path.name}")

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

                    if not no_metadata:
                        write_metadata(
                            output_path,
                            card,
                            deck,
                            prompt,
                            deck_type=deck_type,
                        )

                    tracker.record_success()
                    logger.info(
                        f"Saved: {output_path.name}  "
                        f"[quota: {tracker.effective_count}/{tracker.daily_limit}]  "
                        f"[est. cost: ${tracker.estimated_cost:.2f}]"
                    )
                    return True

            logger.warning(f"Attempt {attempt}: no image data in response.")

        except (QuotaExceededError, QuotaUserDeclined):
            raise  # never swallow quota decisions

        except Exception as e:
            err = str(e).lower()
            is_rate = any(
                x in err for x in ("429", "quota", "rate limit", "resource exhausted")
            )
            if is_rate:
                delay = RATE_LIMIT_RETRY_DELAY * attempt
                logger.warning(
                    f"Rate limited (429) attempt {attempt}. Waiting {delay:.0f}s..."
                )
            else:
                delay = RETRY_BASE_DELAY * (2 ** (attempt - 1))
                logger.warning(f"Attempt {attempt} failed: {e}")

            if attempt < retries:
                logger.info(f"Retrying in {delay:.0f}s...")
                time.sleep(delay)

    tracker.record_failure()
    logger.error(f"All {retries} attempts failed: {output_path.name}")
    return False


# ── batch generation ──────────────────────────────────────────────────────


def generate_batch(
    cards: List[dict],
    deck: dict,
    output_root: str = "output",
    force: bool = False,
    no_metadata: bool = False,
    guardrail: Optional[str] = None,
    deck_type: str = "tarot",
) -> dict:
    """
    Generate images for a list of cards in a single deck.

    Runs preflight quota check before starting.
    Skips cards that already have a raw PNG unless force=True.
    Applies API_CALL_DELAY between successful generations.

    Args:
        cards:       List of card dicts from cards.json.
        deck:        Deck dict from decks.json.
        output_root: Root output directory (default "output").
        force:       Re-generate even if raw PNG already exists.
        no_metadata: Skip writing iTXt metadata into PNGs.
        guardrail:   Override guardrail mode for this run.
        deck_type:   Deck type written to image metadata.

    Returns:
        {"succeeded": int, "skipped": int, "failed": int}
    """
    from tqdm import tqdm

    from prompts.builder import build_prompt

    tracker = get_tracker(guardrail)
    tracker.sync_with_server()
    tracker.print_status()

    deck_id = deck["id"]
    raw_dir = pathlib.Path(output_root) / deck_id / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    # Count jobs that actually need generation
    pending = [
        c
        for c in cards
        if force
        or not (raw_dir / f"{c['name'].lower().replace(' ', '_')}.png").exists()
    ]

    print(
        f"\n── Generating: {deck['name']} ──\n"
        f"   Total cards : {len(cards)}\n"
        f"   To generate : {len(pending)}\n"
        f"   Model       : {MODEL}\n"
        f"   Est. cost   : ${len(pending) * tracker.cost_per_image:.2f}\n"
    )

    # Preflight check against pending jobs only
    try:
        tracker.preflight(len(pending))
    except (QuotaExceededError, QuotaUserDeclined) as e:
        print(f"\n  Halted at preflight: {e}")
        return {"succeeded": 0, "skipped": len(cards) - len(pending), "failed": 0}

    succeeded = skipped = failed = 0

    with tqdm(total=len(cards), unit="card", desc=deck_id) as pbar:
        for card in cards:
            safe_name = card["name"].lower().replace(" ", "_").replace("/", "-")
            output_path = raw_dir / f"{safe_name}.png"

            if output_path.exists() and not force:
                skipped += 1
                pbar.update(1)
                continue

            try:
                prompt = build_prompt(card, deck)
                ok = generate_card_image(
                    prompt=prompt,
                    output_path=output_path,
                    card=card,
                    deck=deck,
                    deck_type=deck_type,
                    no_metadata=no_metadata,
                )
                if ok:
                    succeeded += 1
                    time.sleep(API_CALL_DELAY)
                else:
                    failed += 1

            except (QuotaExceededError, QuotaUserDeclined) as e:
                print(f"\n  Pipeline halted: {e}\n")
                pbar.close()
                break

            pbar.update(1)
            pbar.set_postfix(
                {
                    "quota": f"{tracker.effective_count}/{tracker.daily_limit}",
                    "cost": f"${tracker.estimated_cost:.2f}",
                    "ok": succeeded,
                    "fail": failed,
                }
            )

    print(f"\n── Generation complete: ✓ {succeeded}  ↷ {skipped}  ✗ {failed} ──")
    return {"succeeded": succeeded, "skipped": skipped, "failed": failed}
