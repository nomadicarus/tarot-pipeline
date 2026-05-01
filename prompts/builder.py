"""
builder.py — builds final image generation prompts per card per deck.

Prompt structure (adopted from web-interface JSON, per owner instruction):
  1. Rendering engine prefix       — medium/style anchor
  2. Master prompt template        — deck-specific template with card injections
  3. Negative prompt suffix        — what to avoid (appended as instructional text)

Card-specific injections available in templates:
  {card_name}        — e.g. "The Fool"
  {card_number}      — roman numeral (major) or ordinal word (minor)
  {card_description} — full Thoth scene description from cards.json
  {symbols}          — comma-joined list of key symbols
  {colours}          — comma-joined colour palette
  {technical_suffix} — quality/resolution suffix from deck config

Temperature note (from web2api notes):
  Keep API temperature at 0.7-0.8 for creative geometric backgrounds.
  Set in the API call, not here.

Gemini 2.5 compatibility note:
  Gemini 3 applies a quality style block automatically. For 2.5, the
  technical_suffix in each deck config replicates this behaviour.
"""

import pathlib
import sys

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


# ── roman numeral helper ───────────────────────────────────────────────────

_ROMAN = [
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
    (100,  "C"), (90,  "XC"), (50,  "L"), (40,  "XL"),
    (10,   "X"), (9,   "IX"), (5,   "V"), (4,   "IV"), (1, "I"),
]

def to_roman(n: int) -> str:
    if n == 0:
        return "0"   # The Fool
    result = ""
    for value, numeral in _ROMAN:
        while n >= value:
            result += numeral
            n -= value
    return result


_MINOR_ORDINALS = {
    1: "Ace", 2: "Two", 3: "Three", 4: "Four", 5: "Five",
    6: "Six", 7: "Seven", 8: "Eight", 9: "Nine", 10: "Ten",
    11: "Princess", 12: "Prince", 13: "Queen", 14: "Knight",
}

def card_number_str(card: dict) -> str:
    """Return a human-readable card number for prompt injection."""
    if card["arcana"] == "major":
        return to_roman(card["number"])
    return _MINOR_ORDINALS.get(card["number"], str(card["number"]))


# ── negative prompt formatter ─────────────────────────────────────────────

def format_negative(negative_prompts: list) -> str:
    """
    Format the negative prompts list as an instructional suffix.
    Gemini has no native negative prompt parameter so we inject
    it as natural language at the end of the prompt.
    """
    if not negative_prompts:
        return ""
    items = ", ".join(negative_prompts)
    return f"Avoid: {items}."


# ── main prompt builder ───────────────────────────────────────────────────

def build_prompt(card: dict, deck: dict) -> str:
    """
    Build a final image generation prompt for a given card and deck.

    Args:
        card: A card dict from cards.json
        deck: A deck dict from decks.json

    Returns:
        A fully rendered prompt string ready to send to the Gemini API.
    """
    # ── card field extraction ─────────────────────────────────────────────
    card_name        = card["name"]
    card_number      = card_number_str(card)
    card_description = card.get("thoth_description", "")
    symbols          = ", ".join(card.get("symbols", []))
    colours          = ", ".join(card.get("colours", []))
    technical_suffix = deck.get("technical_suffix", "")

    # ── template rendering ────────────────────────────────────────────────
    template = deck["master_prompt_template"]

    rendered = template.format(
        card_name=card_name,
        card_number=card_number,
        card_description=card_description,
        symbols=symbols,
        colours=colours,
        technical_suffix=technical_suffix,
    )

    # ── assemble final prompt ─────────────────────────────────────────────
    parts = [
        deck.get("rendering_engine_prefix", "").strip(),
        rendered.strip(),
        format_negative(deck.get("negative_prompts", [])),
    ]

    return "\n\n".join(p for p in parts if p)


# ── smoke test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    cards = json.loads((ROOT / "config" / "cards.json").read_text())
    decks = json.loads((ROOT / "config" / "decks.json").read_text())

    # Test The Fool across all three decks
    card = cards["major_arcana"][0]
    print(f"Card: {card['name']}\n{'=' * 60}\n")

    for deck in decks["decks"]:
        prompt = build_prompt(card, deck)
        print(f"-- {deck['name']} --")
        print(prompt)
        print(f"\n({len(prompt)} chars)\n{'─' * 60}\n")

    # Also test a minor arcana card
    card2 = cards["minor_arcana"]["wands"][0]  # Ace of Wands
    print(f"\nCard: {card2['name']}\n{'=' * 60}\n")
    deck = decks["decks"][1]  # Thoth
    prompt2 = build_prompt(card2, deck)
    print(prompt2)
    print(f"\n({len(prompt2)} chars)")
