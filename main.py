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
    parser.add_argument(
        "--raw",
        action="store_true",
        help="Composite all raw PNGs regardless of metadata",
    )

    parser.add_argument("--template", type=str, default="assets/cardface.svg")

    # Sizing
    parser.add_argument(
        "--size",
        type=str,
        default="0,0",
        help="Elastic canvas size W,H (0=unconstrained)",
    )
    parser.add_argument(
        "--fix-size", type=str, default=None, help="Fixed canvas size W,H"
    )

    parser.add_argument("--pad-edge", type=str, default="0")
    parser.add_argument("--pad-internal", type=str, default="8%")

    parser.add_argument("--contain", action="store_true")
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--nudge", type=str, default="0,0", help="Art nudge as X,Y")

    parser.add_argument("--no-shadow", action="store_false", dest="add_shadow")
    parser.add_argument("--shadow-radius", type=str, default="2")
    parser.add_argument("--shadow-offset-x", type=str, default="1")
    parser.add_argument("--shadow-offset-y", type=str, default="1")
    parser.add_argument("--shadow-opacity", type=int, default=150)
    parser.add_argument(
        "--mask-method",
        type=str,
        choices=["alpha", "alpha2", "luma"],
        default="alpha",
        help="Mask generation method: alpha (default), alpha2 (threshold), luma (weighted)",
    )
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
    w_el, h_el = (int(x) for x in args.size.split(","))
    fixed = args.fix_size is not None
    w_fix, h_fix = (int(x) for x in args.fix_size.split(",")) if fixed else (None, None)

    run(
        generate=args.generate,
        composite=args.composite,
        deck=args.deck,
        cards=args.card,
        force=args.force,
        raw=args.raw,
        template=str(template_path),
        size=(w_el, h_el),
        fix_size=(w_fix, h_fix),
        fixed=fixed,
        pad_edge=args.pad_edge,
        pad_internal=args.pad_internal,
        contain=args.contain,
        scale=args.scale,
        nudge=args.nudge,
        add_shadow=args.add_shadow,
        shadow_radius=args.shadow_radius,
        shadow_offset_x=args.shadow_offset_x,
        shadow_offset_y=args.shadow_offset_y,
        shadow_opacity=args.shadow_opacity,
        # shadow_color=args.shadow_color,
    )


if __name__ == "__main__":
    main()
