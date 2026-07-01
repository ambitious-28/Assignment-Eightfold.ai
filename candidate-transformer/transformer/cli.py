import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="transformer",
        description="Multi-Source Candidate Data Transformer",
    )
    parser.add_argument(
        "--inputs",
        metavar="DIR",
        required=False,
        help="Directory containing candidate input files (csv/json/resumes/notes).",
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        default=None,
        help="Path to a projection config JSON file (optional; defaults to full schema).",
    )
    parser.add_argument(
        "--out",
        metavar="PATH",
        default=None,
        help="Output file path (optional; defaults to stdout).",
    )
    parser.add_argument(
        "--include-broken",
        action="store_true",
        default=False,
        help="Also feed samples/broken/ to demonstrate graceful degradation.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Print warnings to stderr.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.inputs is None:
        parser.print_help()
        sys.exit(0)

    from pathlib import Path
    import json
    from transformer.pipeline import run_pipeline
    from transformer.project.config import load_config

    inputs_dir = Path(args.inputs)
    config = load_config(args.config) if args.config else None

    warnings: list[str] = []
    results = run_pipeline(
        inputs_dir,
        config=config,
        include_broken=args.include_broken,
        warnings_out=warnings,
    )

    if args.verbose and warnings:
        for w in warnings:
            print(w, file=sys.stderr)

    payload = json.dumps(results, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
    else:
        sys.stdout.buffer.write((payload + "\n").encode("utf-8"))


if __name__ == "__main__":
    main()
