# pipeline/generator.py (refactored for filesystem orchestration)

import logging
import pathlib
from typing import List

logger = logging.getLogger(__name__)

from pipeline.generator import generate_card_image
from prompts.builder import build_prompt


def generate_batch(cards: List[dict], deck: dict, output_root: str = "output"):
    """Batch wrapper for generation stage."""

    deck_id = deck["id"]

    for card in cards:
        try:
            prompt = build_prompt(card, deck)

            output_path = (
                pathlib.Path(output_root) / deck_id / "raw" / f"{card['name']}.png"
            )

            generate_card_image(
                prompt=prompt,
                output_path=output_path,
                card=card,
                deck=deck,
            )

        except Exception as e:
            logger.error(f"Generation failed for {card.get('name')}: {e}")
