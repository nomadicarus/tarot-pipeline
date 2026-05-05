import argparse
import logging
import pathlib
import sys

from pipeline.runner import run

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")


def main():
    parser = argparse.ArgumentParser(description="Deck Generator & Compositor")

    parser.add_argument("--generate", action="store_true")
    parser.add_argument("--composite", action="store_true")

    parser.add_argument("--deck", type=str)
    parser.add_argument("--card", nargs="*")

    parser.add_argument("--force", action="store_true")
    parser.add_argument("--force-raw", action="store_true")
    parser.add_argument("--preview", action="store_true")

    parser.add_argument("--template", type=str, default="assets/cardface.svg")

    # Elastic
    parser.add_argument("--width", type=int, default=734)
    parser.add_argument("--height", type=int, default=1024)

    # Fixed
    parser.add_argument("--width-f", type=int)
    parser.add_argument("--height-f", type=int)

    parser.add_argument("--pad-edge", type=str, default="0")
    parser.add_argument("--pad-internal", type=str, default="48")

    parser.add_argument("--f-crop", action="store_true")
    parser.add_argument("--art-scale", type=float, default=1.0)

    parser.add_argument("--art-nudge-x", type=str, default="0")
    parser.add_argument("--art-nudge-y", type=str, default="0")

    parser.add_argument("--no-shadow", action="store_false", dest="add_shadow")
    parser.add_argument("--shadow-radius", type=str, default="3.8")
    parser.add_argument("--shadow-offset-x", type=str, default="1.5")
    parser.add_argument("--shadow-offset-y", type=str, default="1.5")
    parser.add_argument("--shadow-opacity", type=int, default=150)
    # parser.add_argument("--shadow-color", type=[], default="")
    parser.set_defaults(add_shadow=True)

    args = parser.parse_args()

    if not args.generate and not args.composite:
        parser.error("Specify --generate or --composite")

    template_path = pathlib.Path(args.template)
    if not template_path.exists():
        print(f"Template not found: {template_path}")
        sys.exit(1)

    # Normalize sizing contract
    fixed = args.width_f and args.height_f

    run(
        generate=args.generate,
        composite=args.composite,
        deck=args.deck,
        cards=args.card,
        force=args.force,
        force_raw=args.force_raw,
        template=str(template_path),
        width=args.width,
        height=args.height,
        width_f=args.width_f,
        height_f=args.height_f,
        fixed=fixed,
        pad_edge=args.pad_edge,
        pad_internal=args.pad_internal,
        f_crop=args.f_crop,
        art_scale=args.art_scale,
        art_nudge=(args.art_nudge_x, args.art_nudge_y),
        add_shadow=args.add_shadow,
        shadow_radius=args.shadow_radius,
        shadow_offset_x=args.shadow_offset_x,
        shadow_offset_y=args.shadow_offset_y,
        shadow_opacity=args.shadow_opacity,
        # shadow_color=args.shadow_color,
    )


if __name__ == "__main__":
    main()
