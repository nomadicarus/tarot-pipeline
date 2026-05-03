"""
manifest.py — raw image metadata via PNG iTXt and on-demand manifest generation.

iTXt fields stored in every raw PNG:
    card_name    — e.g. "The Fool"
    card_number  — e.g. "0" (major) or "Ace" (minor)
    arcana       — "major" | "minor"
    suit         — suit name or "" for major arcana
    deck_type    — "tarot" | "poker" | etc. (future expansion)
    deck_id      — "thoth" | "claymation" | "lego_explosive"
    prompt_hash  — first 8 chars of sha256 of prompt used
    generated_at — ISO8601 timestamp in PT

Primary source of truth: the PNG files themselves.
Manifest JSON is generated on demand from scanning /raw — not a live index.

Usage:
    from pipeline.manifest import write_metadata, read_metadata, build_manifest, filter_raw

    # After generating a raw image:
    write_metadata(path, card, deck, prompt)

    # Read metadata back from a single file:
    meta = read_metadata(path)

    # Scan entire /raw folder and return manifest dict:
    manifest = build_manifest(raw_dir)

    # Filter raw files by field values:
    files = filter_raw(raw_dir, suit="wands", deck_id="thoth")
"""

import hashlib
import json
import pathlib
import struct
import zlib
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")

# ── iTXt field names ───────────────────────────────────────────────────────

FIELDS = [
    "card_name",
    "card_number",
    "arcana",
    "suit",
    "deck_type",
    "deck_id",
    "prompt_hash",
    "generated_at",
]


# ── prompt hash ────────────────────────────────────────────────────────────


def prompt_hash(prompt: str) -> str:
    """Return first 8 chars of sha256 of the prompt."""
    return hashlib.sha256(prompt.encode()).hexdigest()[:8]


# ── low-level PNG iTXt read/write ──────────────────────────────────────────
# We implement iTXt directly rather than relying on Pillow's info dict,
# which doesn't always round-trip custom iTXt chunks reliably.

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _make_itxt_chunk(keyword: str, text: str) -> bytes:
    """Build a raw PNG iTXt chunk."""
    # iTXt structure: keyword \x00 \x00 \x00 "" \x00 text (UTF-8, uncompressed)
    keyword_bytes = keyword.encode("latin-1")
    text_bytes = text.encode("utf-8")
    data = keyword_bytes + b"\x00\x00\x00\x00\x00" + text_bytes
    crc = zlib.crc32(b"iTXt" + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + b"iTXt" + data + struct.pack(">I", crc)


def _parse_itxt_chunk(data: bytes) -> Optional[tuple]:
    """Parse an iTXt chunk's data bytes. Returns (keyword, text) or None."""
    try:
        null_pos = data.index(b"\x00")
        keyword = data[:null_pos].decode("latin-1")
        # Skip: null, compression_flag, compression_method, language_tag null, translated_keyword null
        rest = data[null_pos + 1 :]
        # compression_flag
        comp_flag = rest[0]
        rest = rest[2:]  # skip compression_flag + compression_method
        # find end of language tag (null terminated)
        lang_end = rest.index(b"\x00")
        rest = rest[lang_end + 1 :]
        # find end of translated keyword (null terminated)
        tkey_end = rest.index(b"\x00")
        text_bytes = rest[tkey_end + 1 :]
        if comp_flag == 1:
            text_bytes = zlib.decompress(text_bytes)
        return keyword, text_bytes.decode("utf-8")
    except Exception:
        return None


def write_metadata(
    png_path: pathlib.Path,
    card: dict,
    deck: dict,
    prompt: str,
    deck_type: str = "tarot",
) -> None:
    """
    Write card metadata as iTXt chunks into an existing PNG file.

    Inserts chunks after the PNG signature + IHDR chunk so they are
    near the top of the file and readable without decoding image data.

    Args:
        png_path:  Path to the raw PNG to annotate.
        card:      Card dict from cards.json.
        deck:      Deck dict from decks.json.
        prompt:    The prompt string used to generate this image.
        deck_type: Card deck type (default "tarot").
    """
    png_path = pathlib.Path(png_path)
    raw = png_path.read_bytes()

    if not raw.startswith(PNG_SIGNATURE):
        raise ValueError(f"Not a valid PNG: {png_path}")

    # Build metadata dict
    meta = {
        "card_name": card["name"],
        "card_number": str(card["number"]),
        "arcana": card.get("arcana", ""),
        "suit": card.get("suit", ""),
        "deck_type": deck_type,
        "deck_id": deck["id"],
        "prompt_hash": prompt_hash(prompt),
        "generated_at": datetime.now(tz=PT).isoformat(),
    }

    # Build iTXt chunks
    itxt_chunks = b"".join(_make_itxt_chunk(k, v) for k, v in meta.items())

    # Find insertion point: after signature (8) + IHDR chunk (4+4+13+4 = 25)
    insert_pos = 8 + 25  # after PNG sig + IHDR
    new_png = raw[:insert_pos] + itxt_chunks + raw[insert_pos:]
    png_path.write_bytes(new_png)


def read_metadata(png_path: pathlib.Path) -> dict:
    """
    Read iTXt metadata from a PNG file.

    Returns a dict of all iTXt fields found. Returns empty dict if none found
    or file is not a valid PNG.
    """
    png_path = pathlib.Path(png_path)
    try:
        raw = png_path.read_bytes()
        if not raw.startswith(PNG_SIGNATURE):
            return {}

        meta = {}
        pos = 8  # skip signature

        while pos < len(raw) - 12:
            length = struct.unpack(">I", raw[pos : pos + 4])[0]
            chunk_type = raw[pos + 4 : pos + 8]
            chunk_data = raw[pos + 8 : pos + 8 + length]

            if chunk_type == b"iTXt":
                result = _parse_itxt_chunk(chunk_data)
                if result:
                    keyword, text = result
                    if keyword in FIELDS:
                        meta[keyword] = text
            elif chunk_type == b"IEND":
                break

            pos += 12 + length

        return meta

    except Exception:
        return {}


# ── manifest builder ───────────────────────────────────────────────────────


def build_manifest(raw_dir: pathlib.Path) -> dict:
    """
    Scan a /raw directory and build a manifest from PNG iTXt metadata.

    Returns:
        {
            "generated_at": "...",
            "total": 42,
            "cards": [
                { "file": "the_fool.png", "card_name": "The Fool", ... },
                ...
            ]
        }
    """
    raw_dir = pathlib.Path(raw_dir)
    cards = []

    for png in sorted(raw_dir.glob("*.png")):
        meta = read_metadata(png)
        if meta:
            meta["file"] = png.name
            cards.append(meta)
        else:
            # No iTXt metadata — include file with unknown fields
            cards.append(
                {
                    "file": png.name,
                    "card_name": "unknown",
                    "card_number": "unknown",
                    "arcana": "unknown",
                    "suit": "unknown",
                    "deck_type": "unknown",
                    "deck_id": "unknown",
                    "prompt_hash": "unknown",
                    "generated_at": "unknown",
                }
            )

    return {
        "generated_at": datetime.now(tz=PT).isoformat(),
        "total": len(cards),
        "cards": cards,
    }


def save_manifest(raw_dir: pathlib.Path) -> pathlib.Path:
    """
    Build and save manifest.json into raw_dir.
    Returns path to the saved manifest file.
    """
    raw_dir = pathlib.Path(raw_dir)
    manifest = build_manifest(raw_dir)
    out_path = raw_dir / "manifest.json"
    out_path.write_text(json.dumps(manifest, indent=2))
    return out_path


# ── filter helper ──────────────────────────────────────────────────────────


def filter_raw(
    raw_dir: pathlib.Path,
    card_name: Optional[str] = None,
    card_number: Optional[str] = None,
    arcana: Optional[str] = None,
    suit: Optional[str] = None,
    deck_type: Optional[str] = None,
    deck_id: Optional[str] = None,
    card_names: Optional[list] = None,
) -> list:
    """
    Filter PNG files in raw_dir by metadata field values.

    All filters are AND conditions. String comparisons are case-insensitive.
    card_names accepts a list for multi-card selection.

    Args:
        raw_dir:     Path to the /raw folder to scan.
        card_name:   Exact card name match e.g. "The Fool"
        card_number: Card number string e.g. "0" or "Ace"
        arcana:      "major" or "minor"
        suit:        "wands" | "cups" | "swords" | "disks"
        deck_type:   "tarot" | "poker" etc.
        deck_id:     "thoth" | "claymation" | "lego_explosive"
        card_names:  List of card names for multi-select

    Returns:
        List of pathlib.Path objects matching all filters.
    """
    raw_dir = pathlib.Path(raw_dir)
    results = []

    # Normalise card_names list
    names_filter = None
    if card_names:
        names_filter = [n.lower() for n in card_names]
    elif card_name:
        names_filter = [card_name.lower()]

    for png in sorted(raw_dir.glob("*.png")):
        meta = read_metadata(png)
        if not meta:
            continue

        # Apply filters
        if names_filter:
            if meta.get("card_name", "").lower() not in names_filter:
                continue
        if card_number and meta.get("card_number", "").lower() != card_number.lower():
            continue
        if arcana and meta.get("arcana", "").lower() != arcana.lower():
            continue
        if suit and meta.get("suit", "").lower() != suit.lower():
            continue
        if deck_type and meta.get("deck_type", "").lower() != deck_type.lower():
            continue
        if deck_id and meta.get("deck_id", "").lower() != deck_id.lower():
            continue

        results.append(png)

    return results


# ── CLI ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Manifest tools for raw card images")
    sub = parser.add_subparsers(dest="command")

    # manifest build
    p_build = sub.add_parser("build", help="Scan /raw dir and save manifest.json")
    p_build.add_argument("raw_dir", help="Path to /raw directory")

    # manifest show
    p_show = sub.add_parser("show", help="Print metadata for a single PNG")
    p_show.add_argument("png", help="Path to PNG file")

    # manifest filter
    p_filter = sub.add_parser("filter", help="List PNGs matching filter criteria")
    p_filter.add_argument("raw_dir")
    p_filter.add_argument("--deck-id", default=None)
    p_filter.add_argument("--deck-type", default=None)
    p_filter.add_argument("--suit", default=None)
    p_filter.add_argument("--arcana", default=None)
    p_filter.add_argument("--card-name", default=None)
    p_filter.add_argument("--card-number", default=None)

    args = parser.parse_args()

    if args.command == "build":
        out = save_manifest(pathlib.Path(args.raw_dir))
        manifest = json.loads(out.read_text())
        print(f"Manifest saved: {out}  ({manifest['total']} cards)")

    elif args.command == "show":
        meta = read_metadata(pathlib.Path(args.png))
        if meta:
            for k, v in meta.items():
                print(f"  {k:<16}: {v}")
        else:
            print("No iTXt metadata found.")

    elif args.command == "filter":
        matches = filter_raw(
            pathlib.Path(args.raw_dir),
            card_name=args.card_name,
            card_number=args.card_number,
            arcana=args.arcana,
            suit=args.suit,
            deck_type=args.deck_type,
            deck_id=args.deck_id,
        )
        print(f"{len(matches)} match(es):")
        for p in matches:
            print(f"  {p}")

    else:
        parser.print_help()
