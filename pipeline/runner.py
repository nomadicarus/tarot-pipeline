import json
import logging
import pathlib
import sys

logger = logging.getLogger(__name__)

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

CARDS_JSON = ROOT / "config" / "cards.json"
DECKS_JSON = ROOT / "config" / "decks.json"


def _load_decks(deck_id: str = None) -> list:
    decks = json.loads(DECKS_JSON.read_text())["decks"]
    if deck_id:
        decks = [d for d in decks if d["id"] == deck_id]
    return decks


def _load_cards(card_names: list = None) -> list:
    data = json.loads(CARDS_JSON.read_text())
    cards = list(data["major_arcana"])
    for suit_cards in data["minor_arcana"].values():
        cards.extend(suit_cards)
    if card_names:
        names_lower = [n.lower() for n in card_names]
        cards = [c for c in cards if c["name"].lower() in names_lower]
    return cards


def run(
    generate: bool = False,
    composite: bool = False,
    deck: str = None,
    cards: list = None,
    force: bool = False,
    no_metadata: bool = False,
    mapping_path=None,
    force_raw=False,
    preview: bool = False,
    width: int = 734,
    height: int = 1024,
    template: str = "assets/cardface.svg",
    pad_edge: int = None,
    **kwargs,
):
    decks = _load_decks(deck)
    all_cards = _load_cards(cards)

    if generate:
        from pipeline.generator import generate_batch

        for d in decks:
            generate_batch(
                cards=all_cards,
                deck=d,
                output_root=str(ROOT / "output"),
                force=force,
                no_metadata=no_metadata,
            )

    if composite:
        from pipeline.compositor import composite_batch

        for d in decks:
            raw_dir = ROOT / "output" / d["id"] / "raw"
            output_dir = ROOT / "output" / d["id"]
            if not raw_dir.exists():
                continue

            print(f"\n── Compositing: {d['name']} ──")
            s, k, f = composite_batch(
                raw_dir=raw_dir,
                output_dir=output_dir,
                svg_path=template,
                deck_id=d["id"],
                card_names=cards,
                force=force,
                mapping_path=mapping_path,
                force_raw=force_raw,
                preview=preview,
                target_size=(width, height),
                pad_edge=pad_edge,
                add_shadow=kwargs.get("add_shadow", True),
            )
            print(f"   ✓ {s} composited  ↷ {k} skipped  ✗ {f} failed")
