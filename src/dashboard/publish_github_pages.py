from __future__ import annotations

import argparse
from pathlib import Path


def publish_pages_entry(source_html: Path, destination_html: Path) -> Path:
    if not source_html.exists():
        raise FileNotFoundError(f"Dashboard source not found: {source_html}")

    destination_html.parent.mkdir(parents=True, exist_ok=True)
    destination_html.write_text(source_html.read_text(encoding="utf-8"), encoding="utf-8")
    return destination_html


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Publish the governed dashboard to a GitHub Pages entrypoint."
    )
    parser.add_argument(
        "--source-html",
        type=Path,
        default=Path("outputs/dashboard/marketplace_command_center_dashboard.html"),
    )
    parser.add_argument("--destination-html", type=Path, default=Path("docs/index.html"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out = publish_pages_entry(args.source_html, args.destination_html)
    print(f"GitHub Pages entry published: {out}")


if __name__ == "__main__":
    main()
