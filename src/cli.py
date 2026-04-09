"""
CLI entry point for parse-schdoc.

Usage:
    parse-schdoc <file.SchDoc>                  # JSON to stdout
    parse-schdoc <file.SchDoc> -o out.json      # JSON to file
    parse-schdoc <file.SchDoc> --markdown        # Markdown to stdout
    parse-schdoc <file.SchDoc> --markdown -o out.md
    parse-schdoc --batch <directory>             # All SchDoc files in dir
"""

import argparse
import json
import sys
from pathlib import Path

from src.parser import parse_schdoc
from src.markdown import to_markdown


def _process_file(file_path: Path, output_format: str, output_path: Path | None):
    """Parse a single SchDoc file and output results."""
    try:
        data = parse_schdoc(file_path)
    except Exception as e:
        print(f"ERROR parsing {file_path.name}: {e}", file=sys.stderr)
        return False

    if output_format == "markdown":
        result = to_markdown(data)
    else:
        result = json.dumps(data, indent=2, ensure_ascii=False)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(result, encoding="utf-8")
        print(f"  -> {output_path}")
    else:
        print(result)

    return True


def main():
    parser = argparse.ArgumentParser(
        prog="parse-schdoc",
        description="Parse Altium .SchDoc files into structured JSON or Markdown.",
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="Path to a .SchDoc file",
    )
    parser.add_argument(
        "-o", "--output",
        help="Output file path (default: stdout)",
    )
    parser.add_argument(
        "--markdown", "--md",
        action="store_true",
        help="Output as Markdown instead of JSON",
    )
    parser.add_argument(
        "--batch",
        metavar="DIR",
        help="Process all .SchDoc files in a directory",
    )

    args = parser.parse_args()

    if args.batch:
        batch_dir = Path(args.batch)
        if not batch_dir.is_dir():
            print(f"Error: {batch_dir} is not a directory", file=sys.stderr)
            sys.exit(1)

        files = sorted(batch_dir.glob("*.SchDoc"))
        if not files:
            print(f"No .SchDoc files found in {batch_dir}", file=sys.stderr)
            sys.exit(1)

        ext = ".md" if args.markdown else ".json"
        out_dir = Path(args.output) if args.output else batch_dir / "parsed"
        out_dir.mkdir(parents=True, exist_ok=True)

        fmt = "markdown" if args.markdown else "json"
        ok = 0
        fail = 0
        print(f"Processing {len(files)} SchDoc files...")
        for f in files:
            out_file = out_dir / (f.stem + ext)
            print(f"  {f.name}", end="")
            if _process_file(f, fmt, out_file):
                ok += 1
            else:
                fail += 1
        print(f"\nDone: {ok} succeeded, {fail} failed")
        sys.exit(1 if fail > 0 else 0)

    elif args.input:
        file_path = Path(args.input)
        if not file_path.exists():
            print(f"Error: {file_path} not found", file=sys.stderr)
            sys.exit(1)

        fmt = "markdown" if args.markdown else "json"
        out_path = Path(args.output) if args.output else None
        success = _process_file(file_path, fmt, out_path)
        sys.exit(0 if success else 1)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
