import argparse
import logging
import pathlib
import sys

from pipeline.runner import run

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")


def main():
    parser = argparse.ArgumentParser(description="Deck Generator & Compositor")

    # Modes
    parser.add_argument("--generate", action="store_true", help="Run image generation")
    parser.add_argument("--composite", action="store_true", help="Run compositing")

    # Filtering
    parser.add_argument("--deck", type=str, help="Deck ID (e.g., thoth)")
    parser.add_argument("--card", nargs="*", help="Specific card names to process")

    # Config & Metadata
    parser.add_argument("--force", action="store_true", help="Overwrite existing files")
    parser.add_argument(
        "--no-metadata", action="store_true", help="Skip writing iTXt metadata"
    )
    parser.add_argument("--mapping", type=str, help="Path to metadata mapping JSON")
    parser.add_argument(
        "--force-raw",
        action="store_true",
        help="Bypass filtering; process all raw files",
    )
    parser.add_argument(
        "--preview", action="store_true", help="Show what would be processed"
    )

    # Sizing & Template
    parser.add_argument(
        "--template", type=str, default="assets/cardface.svg", help="SVG template path"
    )
    parser.add_argument("--width", type=int, default=734, help="Target output width")
    parser.add_argument("--height", type=int, default=1024, help="Target output height")
    parser.add_argument(
        "--pad-edge", type=int, default=13, help="Gutter width in pixels"
    )
    parser.add_argument(
        "--pad-internal", type=int, default=30, help="Internal art margin"
    )

    # Shadow Controls
    parser.add_argument(
        "--no-shadow",
        action="store_false",
        dest="add_shadow",
        help="Disable drop shadow",
    )
    parser.add_argument(
        "--shadow-radius", type=int, default=5, help="Blur radius of the shadow"
    )
    parser.add_argument(
        "--shadow-offset-x", type=int, default=3, help="Horizontal shadow offset"
    )
    parser.add_argument(
        "--shadow-offset-y", type=int, default=3, help="Vertical shadow offset"
    )
    parser.set_defaults(add_shadow=True)

    args = parser.parse_args()

    # Default behavior: if no mode selected, default to generate
    if not args.generate and not args.composite:
        args.generate = True

    template_path = pathlib.Path(args.template)
    if not template_path.exists():
        print(f"Error: Template {args.template} not found.")
        sys.exit(1)

    run(
        generate=args.generate,
        composite=args.composite,
        deck=args.deck,
        cards=args.card if args.card else None,
        force=args.force,
        no_metadata=args.no_metadata,
        mapping_path=args.mapping,
        force_raw=args.force_raw,
        preview=args.preview,
        template=str(template_path),
        width=args.width,
        height=args.height,
        pad_edge=args.pad_edge,
        pad_internal=args.pad_internal,
        # New Shadow Args
        add_shadow=args.add_shadow,
        shadow_radius=args.shadow_radius,
        shadow_offset_x=args.shadow_offset_x,
        shadow_offset_y=args.shadow_offset_y,
    )


if __name__ == "__main__":
    main()
