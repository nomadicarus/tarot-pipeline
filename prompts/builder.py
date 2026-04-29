"""
Prompt builder — merges deck style config with per-card Thoth symbolism data
to produce a final image generation prompt for each card × deck combination.
"""

from jinja2 import Template

# ---------------------------------------------------------------------------
# Base prompt template (shared across all decks)
# Card-specific fields are injected at render time.
# ---------------------------------------------------------------------------

CARD_PROMPT_TEMPLATE = Template("""
{{ style_prefix }}.

Tarot card: {{ card.name }}
{% if card.arcana == "major" -%}
Major Arcana, card number {{ card.number }}.
Hebrew letter: {{ card.hebrew_letter }}.
Astrological attribution: {{ card.astrological }}.
Thoth title: {{ card.thoth_title }}.
{% else -%}
Minor Arcana — {{ card.suit }}, {{ card.name }}.
Elemental attribution: {{ card.element }}.
{% if card.astrological is defined -%}
Astrological decan: {{ card.astrological }}.
{% endif -%}
Thoth title: {{ card.thoth_title }}.
{% endif -%}

Scene description: {{ card.thoth_description }}

Key symbols to include: {{ card.symbols | join(", ") }}.
Colour palette: {{ card.colours | join(", ") }}.

{{ style_suffix }}.

Portrait orientation, tarot card proportions (approximately 2:3 ratio).
No card borders, no text, no titles, no numbers — artwork only.
""".strip())


def build_prompt(card: dict, deck: dict) -> str:
    """
    Build a final image generation prompt for a given card and deck config.

    Args:
        card:  A card dict from cards.json
        deck:  A deck dict from decks.json

    Returns:
        A fully rendered prompt string ready to send to the Gemini API.
    """
    return CARD_PROMPT_TEMPLATE.render(
        card=card,
        style_prefix=deck["style_prefix"],
        style_suffix=deck["style_suffix"],
    ).strip()


if __name__ == "__main__":
    # Quick smoke test
    import json, pathlib

    root = pathlib.Path(__file__).parent.parent
    cards = json.loads((root / "config" / "cards.json").read_text())
    decks = json.loads((root / "config" / "decks.json").read_text())

    card = cards["major_arcana"][0]   # The Fool
    deck = decks["decks"][0]          # Lego Explosive Media

    prompt = build_prompt(card, deck)
    print("=== SAMPLE PROMPT ===")
    print(prompt)
    print(f"\n({len(prompt)} characters)")
