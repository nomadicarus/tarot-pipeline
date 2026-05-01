"""
runner.py — orchestrates the full pipeline across all decks and cards.

Flow per card per deck:
  1. Check if final output already exists → skip (resumable)
  2. Check if raw art already exists → skip generation, go to compositing
  3. Build prompt from card data + deck style config
  4. Generate raw art via Gemini API → save to output/{deck}/raw/
  5. Composite art + card frame → save to output/{deck}/{card_name}.png
  6. Log result (success / failure)

After each run a summary report is printed.
"""

import json
import logging
import pathlib
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

from tqdm import tqdm

# ---------------------------------------------------------------------------
# Bootstrap path so sub-modules resolve correctly when run directly
# ---------------------------------------------------------------------------
ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import API_CALL_DELAY as _API_CALL_DELAY
from config.settings import DAILY_LIMIT, MODEL
from pipeline.compositor import composite_card
from pipeline.generator import generate_card_image, get_quota_tracker
from pipeline.quota import QuotaExceededError
from prompts.builder import build_prompt

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config paths
# ---------------------------------------------------------------------------

CARDS_JSON = ROOT / "config" / "cards.json"
DECKS_JSON = ROOT / "config" / "decks.json"
SVG_FRAME = ROOT / "assets" / "cardface.svg"

# Inter-request delay — read from config/settings.py
# Free tier (~3 RPM): 20s. Paid tier (~10 RPM): 8s.
API_CALL_DELAY = _API_CALL_DELAY


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class CardResult:
    deck_id: str
    card_name: str
    success: bool
    skipped: bool = False
    error: Optional[str] = None


@dataclass
class RunSummary:
    results: list[CardResult] = field(default_factory=list)

    @property
    def total(self):
        return len(self.results)

    @property
    def succeeded(self):
        return sum(1 for r in self.results if r.success)

    @property
    def skipped(self):
        return sum(1 for r in self.results if r.skipped)

    @property
    def failed(self):
        return sum(1 for r in self.results if not r.success and not r.skipped)

    def print_report(self):
        print("\n" + "=" * 60)
        print("PIPELINE RUN SUMMARY")
        print("=" * 60)
        print(f"  Total cards processed : {self.total}")
        print(f"  ✓ Generated + composited: {self.succeeded}")
        print(f"  ↷ Skipped (already done): {self.skipped}")
        print(f"  ✗ Failed               : {self.failed}")
        if self.failed > 0:
            print("\nFailed cards:")
            for r in self.results:
                if not r.success and not r.skipped:
                    print(
                        f"  [{r.deck_id}] {r.card_name} — {r.error or 'unknown error'}"
                    )
        print("=" * 60)


# ---------------------------------------------------------------------------
# Card iteration helper
# ---------------------------------------------------------------------------


def iter_cards(cards: dict):
    """Yield all 78 card dicts in order: major arcana then minor arcana by suit."""
    yield from cards["major_arcana"]
    for suit_cards in cards["minor_arcana"].values():
        yield from suit_cards


def card_filename(card: dict) -> str:
    """Normalise card name to a safe filename."""
    return card["name"].lower().replace(" ", "_").replace("/", "-") + ".png"


# ---------------------------------------------------------------------------
# Single card pipeline
# ---------------------------------------------------------------------------


def process_card(
    card: dict,
    deck: dict,
    summary: RunSummary,
    force: bool = False,
) -> bool:
    """
    Run the full generate → composite pipeline for one card in one deck.

    Args:
        card:    Card dict from cards.json
        deck:    Deck dict from decks.json
        summary: RunSummary to append results to
        force:   If True, regenerate even if output already exists

    Returns:
        True if card was successfully processed or skipped, False on failure.
    """
    deck_out_dir = ROOT / deck["output_dir"]
    raw_dir = deck_out_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    filename = card_filename(card)
    raw_path = raw_dir / filename
    final_path = deck_out_dir / filename

    # --- Skip if final output already exists ---
    if final_path.exists() and not force:
        logger.debug(f"Skipping (exists): [{deck['id']}] {card['name']}")
        summary.results.append(
            CardResult(
                deck_id=deck["id"], card_name=card["name"], success=True, skipped=True
            )
        )
        return True

    # --- Step 1: Generate raw art (skip if raw already exists) ---
    if not raw_path.exists() or force:
        prompt = build_prompt(card, deck)
        logger.info(f"Generating: [{deck['id']}] {card['name']}")

        ok = generate_card_image(prompt, raw_path)
        if not ok:
            summary.results.append(
                CardResult(
                    deck_id=deck["id"],
                    card_name=card["name"],
                    success=False,
                    error="API generation failed",
                )
            )
            return False

        # Polite delay between API calls
        time.sleep(API_CALL_DELAY)
    else:
        logger.debug(f"Raw art exists, skipping generation: {raw_path.name}")

    # --- Step 2: Composite art + frame ---
    ok = composite_card(raw_path, SVG_FRAME, final_path)
    if not ok:
        summary.results.append(
            CardResult(
                deck_id=deck["id"],
                card_name=card["name"],
                success=False,
                error="Compositing failed",
            )
        )
        return False

    summary.results.append(
        CardResult(deck_id=deck["id"], card_name=card["name"], success=True)
    )
    return True


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


def run(
    deck_ids: Optional[list[str]] = None,
    card_names: Optional[list[str]] = None,
    force: bool = False,
):
    """
    Run the pipeline.

    Args:
        deck_ids:   List of deck IDs to process (default: all three).
                    e.g. ["thoth"] or ["lego_explosive", "claymation"]
        card_names: Limit to specific card names (default: all 78).
                    e.g. ["The Fool", "The Magus"]
        force:      Regenerate even if output already exists.
    """
    # Load config
    cards_data = json.loads(CARDS_JSON.read_text())
    decks_data = json.loads(DECKS_JSON.read_text())

    all_cards = list(iter_cards(cards_data))
    all_decks = decks_data["decks"]

    # Apply filters
    if deck_ids:
        all_decks = [d for d in all_decks if d["id"] in deck_ids]
    if card_names:
        card_names_lower = [n.lower() for n in card_names]
        all_cards = [c for c in all_cards if c["name"].lower() in card_names_lower]

    total_jobs = len(all_decks) * len(all_cards)
    summary = RunSummary()

    # ── quota sync at startup ──────────────────────────────────────────────
    tracker = get_quota_tracker()
    tracker.sync_with_server()
    tracker.print_status()

    print(
        f"\nTarot Pipeline — {len(all_decks)} deck(s) × {len(all_cards)} card(s) = {total_jobs} images\n"
    )
    print(f"  Model       : {MODEL}")
    print(f"  Daily limit : {tracker.daily_limit}  (change in config/settings.py)")
    print(f"  Used today  : {tracker.effective_count}\n")

    for deck in all_decks:
        print(f"\n── Deck: {deck['name']} ──")
        with tqdm(total=len(all_cards), unit="card", desc=deck["id"]) as pbar:
            for card in all_cards:
                try:
                    process_card(card, deck, summary, force=force)
                except QuotaExceededError as e:
                    print(f"\n\n  Pipeline halted: {e}\n")
                    summary.print_report()
                    return summary
                pbar.update(1)
                pbar.set_postfix(
                    {
                        "ok": summary.succeeded,
                        "skip": summary.skipped,
                        "fail": summary.failed,
                    }
                )

    summary.print_report()
    return summary


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Tarot deck image pipeline")
    parser.add_argument(
        "--decks",
        nargs="*",
        choices=["lego_explosive", "thoth", "claymation"],
        help="Which deck(s) to generate (default: all)",
    )
    parser.add_argument(
        "--cards",
        nargs="*",
        help="Limit to specific card names e.g. 'The Fool' 'The Magus'",
    )
    parser.add_argument(
        "--force", action="store_true", help="Regenerate even if output already exists"
    )
    parser.add_argument(
        "--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"]
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    run(
        deck_ids=args.decks,
        card_names=args.cards,
        force=args.force,
    )
