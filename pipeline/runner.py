"""
runner.py — orchestrates generation and/or compositing pipeline stages.

Stages are now independent and CLI-selectable:

    python main.py --generate                          # generate raw art only
    python main.py --composite                         # composite all /raw images
    python main.py --generate --composite              # full pipeline (generate then composite)

    # Deck filtering
    python main.py --generate --decks thoth claymation
    python main.py --composite --decks thoth

    # Card filtering
    python main.py --generate --cards "The Fool" "The Magus"
    python main.py --composite --suit wands
    python main.py --composite --arcana major
    python main.py --composite --deck thoth --cards "The Fool"

    # Force regeneration/recomposite
    python main.py --generate --force
    python main.py --composite --force

    # Guardrail override
    python main.py --generate --guardrail off

Default behaviour (no flags): --generate only.
"""

import json
import logging
import pathlib
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

from tqdm import tqdm

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from prompts.builder import build_prompt
from pipeline.generator import generate_card_image, get_quota_tracker
from pipeline.compositor import composite_batch
from pipeline.manifest import save_manifest
from pipeline.quota import QuotaTracker, QuotaExceededError, QuotaUserDeclined
from config.settings import MODEL, DAILY_LIMIT, API_CALL_DELAY as _API_CALL_DELAY

logger = logging.getLogger(__name__)

CARDS_JSON = ROOT / "config" / "cards.json"
DECKS_JSON = ROOT / "config" / "decks.json"
SVG_FRAME  = ROOT / "assets" / "cardface.svg"

API_CALL_DELAY = _API_CALL_DELAY


# ── data structures ───────────────────────────────────────────────────────

@dataclass
class CardResult:
    deck_id:   str
    card_name: str
    success:   bool
    skipped:   bool = False
    error:     Optional[str] = None


@dataclass
class RunSummary:
    results: list = field(default_factory=list)

    @property
    def total(self):     return len(self.results)
    @property
    def succeeded(self): return sum(1 for r in self.results if r.success)
    @property
    def skipped(self):   return sum(1 for r in self.results if r.skipped)
    @property
    def failed(self):    return sum(1 for r in self.results if not r.success and not r.skipped)

    def print_report(self):
        print(f"\n{'═' * 52}")
        print("PIPELINE RUN SUMMARY")
        print(f"{'═' * 52}")
        print(f"  Total          : {self.total}")
        print(f"  ✓ Generated    : {self.succeeded}")
        print(f"  ↷ Skipped      : {self.skipped}")
        print(f"  ✗ Failed       : {self.failed}")
        if self.failed:
            print("\n  Failed cards:")
            for r in self.results:
                if not r.success and not r.skipped:
                    print(f"    [{r.deck_id}] {r.card_name} — {r.error or 'unknown'}")
        print(f"{'═' * 52}")


# ── card iteration ────────────────────────────────────────────────────────

def iter_cards(cards: dict):
    yield from cards["major_arcana"]
    for suit_cards in cards["minor_arcana"].values():
        yield from suit_cards


def card_filename(card: dict) -> str:
    return card["name"].lower().replace(" ", "_").replace("/", "-") + ".png"


# ── generation stage ──────────────────────────────────────────────────────

def run_generate(
    deck_ids:   Optional[list] = None,
    card_names: Optional[list] = None,
    force:      bool = False,
    guardrail:  Optional[str] = None,
    deck_type:  str = "tarot",
) -> RunSummary:
    """
    Generation stage — calls Gemini API, saves raw PNGs with iTXt metadata.
    """
    cards_data = json.loads(CARDS_JSON.read_text())
    decks_data = json.loads(DECKS_JSON.read_text())

    all_cards = list(iter_cards(cards_data))
    all_decks = decks_data["decks"]

    if deck_ids:
        all_decks = [d for d in all_decks if d["id"] in deck_ids]
    if card_names:
        card_names_lower = [n.lower() for n in card_names]
        all_cards = [c for c in all_cards if c["name"].lower() in card_names_lower]

    total_jobs = len(all_decks) * len(all_cards)
    summary    = RunSummary()

    # Quota setup
    tracker = get_quota_tracker()
    if guardrail:
        tracker.guardrail_mode = guardrail
    tracker.sync_with_server()
    tracker.print_status()

    print(f"\n── GENERATE ── {len(all_decks)} deck(s) × {len(all_cards)} card(s) = {total_jobs} images")
    print(f"   Model       : {MODEL}")
    print(f"   Daily limit : {tracker.daily_limit}  (config/settings.py)")
    print(f"   Used today  : {tracker.effective_count}\n")

    # Preflight quota check
    try:
        tracker.preflight(total_jobs)
    except (QuotaExceededError, QuotaUserDeclined) as e:
        print(f"\n  Halted at preflight: {e}")
        return summary

    for deck in all_decks:
        raw_dir = ROOT / deck["output_dir"] / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n── Deck: {deck['name']} ──")
        with tqdm(total=len(all_cards), unit="card", desc=deck["id"]) as pbar:
            for card in all_cards:
                filename = card_filename(card)
                raw_path = raw_dir / filename

                if raw_path.exists() and not force:
                    summary.results.append(CardResult(
                        deck_id=deck["id"], card_name=card["name"],
                        success=True, skipped=True
                    ))
                    pbar.update(1)
                    continue

                try:
                    prompt = build_prompt(card, deck)
                    ok = generate_card_image(
                        prompt, raw_path, card, deck,
                        deck_type=deck_type,
                    )
                    summary.results.append(CardResult(
                        deck_id=deck["id"], card_name=card["name"],
                        success=ok,
                        error=None if ok else "generation failed"
                    ))
                    if ok:
                        time.sleep(API_CALL_DELAY)

                except (QuotaExceededError, QuotaUserDeclined) as e:
                    print(f"\n\n  Pipeline halted: {e}\n")
                    summary.print_report()
                    return summary

                pbar.update(1)
                pbar.set_postfix({
                    "ok": summary.succeeded,
                    "skip": summary.skipped,
                    "fail": summary.failed,
                })

        # Save manifest after each deck
        manifest_path = save_manifest(raw_dir)
        logger.info(f"Manifest saved: {manifest_path}")

    summary.print_report()
    return summary


# ── composite stage ───────────────────────────────────────────────────────

def run_composite(
    deck_ids:   Optional[list] = None,
    card_names: Optional[list] = None,
    arcana:     Optional[str]  = None,
    suit:       Optional[str]  = None,
    deck_type:  Optional[str]  = None,
    force:      bool = False,
) -> None:
    """
    Compositing stage — reads raw PNGs by iTXt metadata, composites with frame.
    Fully independent of generation — can be run at any time on existing /raw files.
    """
    decks_data = json.loads(DECKS_JSON.read_text())
    all_decks  = decks_data["decks"]

    if deck_ids:
        all_decks = [d for d in all_decks if d["id"] in deck_ids]

    total_ok = total_skip = total_fail = 0

    for deck in all_decks:
        raw_dir    = ROOT / deck["output_dir"] / "raw"
        output_dir = ROOT / deck["output_dir"]

        if not raw_dir.exists():
            logger.warning(f"No /raw folder found for deck '{deck['id']}' — skipping.")
            continue

        print(f"\n── Compositing: {deck['name']} ──")
        ok, skip, fail = composite_batch(
            raw_dir    = raw_dir,
            output_dir = output_dir,
            svg_path   = SVG_FRAME,
            deck_id    = deck["id"] if not deck_ids else None,
            deck_type  = deck_type,
            arcana     = arcana,
            suit       = suit,
            card_names = card_names,
            force      = force,
        )
        total_ok   += ok
        total_skip += skip
        total_fail += fail
        print(f"   ✓ {ok} composited  ↷ {skip} skipped  ✗ {fail} failed")

    print(f"\n{'═' * 40}")
    print(f"COMPOSITE SUMMARY: ✓ {total_ok}  ↷ {total_skip}  ✗ {total_fail}")
    print(f"{'═' * 40}")


# ── CLI ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Tarot pipeline — generate and/or composite")

    # Stage flags
    parser.add_argument("--generate",  action="store_true", help="Run generation stage")
    parser.add_argument("--composite", action="store_true", help="Run compositing stage")

    # Shared filters
    parser.add_argument("--decks", nargs="*",
        choices=["lego_explosive", "thoth", "claymation"],
        help="Deck(s) to process (default: all)")
    parser.add_argument("--cards", nargs="*",
        help="Card name(s) to process e.g. 'The Fool' 'The Magus'")
    parser.add_argument("--force", action="store_true",
        help="Re-generate/re-composite even if output exists")

    # Composite-specific filters
    parser.add_argument("--suit",   default=None,
        choices=["wands", "cups", "swords", "disks"],
        help="Filter composite by suit (minor arcana only)")
    parser.add_argument("--arcana", default=None,
        choices=["major", "minor"],
        help="Filter composite by arcana")
    parser.add_argument("--deck-type", default="tarot",
        help="Deck type for metadata (default: tarot)")

    # Generation options
    parser.add_argument("--guardrail", default=None,
        choices=["preflight", "realtime", "off"],
        help="Override guardrail mode for this run")

    # Logging
    parser.add_argument("--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Default: generate only if no stage flag given
    if not args.generate and not args.composite:
        args.generate = True

    if args.generate:
        run_generate(
            deck_ids   = args.decks,
            card_names = args.cards,
            force      = args.force,
            guardrail  = args.guardrail,
            deck_type  = args.deck_type,
        )

    if args.composite:
        run_composite(
            deck_ids   = args.decks,
            card_names = args.cards,
            arcana     = args.arcana,
            suit       = args.suit,
            deck_type  = args.deck_type,
            force      = args.force,
        )
