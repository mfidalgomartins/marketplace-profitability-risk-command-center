from __future__ import annotations

import argparse
from pathlib import Path


def _build_index_html(target_filename: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Marketplace Command Center</title>
  <meta http-equiv="refresh" content="0; url={target_filename}">
  <style>
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      font-family: "IBM Plex Sans", "Segoe UI", Arial, sans-serif;
      background: #f4f7fc;
      color: #0f172a;
      padding: 20px;
    }}
    .card {{
      max-width: 620px;
      width: 100%;
      background: #ffffff;
      border: 1px solid #d8e1ee;
      border-radius: 14px;
      padding: 20px;
      box-shadow: 0 10px 28px rgba(15, 23, 42, 0.08);
    }}
    h1 {{ margin: 0 0 8px 0; font-size: 24px; }}
    p {{ margin: 0 0 14px 0; color: #46546e; }}
    a {{
      color: #0b5ed7;
      font-weight: 600;
      text-decoration: none;
    }}
    a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>Marketplace Command Center</h1>
    <p>Redirecting to the live executive dashboard.</p>
    <a href="{target_filename}">Open dashboard</a>
  </div>
</body>
</html>
"""


def publish_pages_entry(source_html: Path, destination_html: Path, index_html: Path) -> Path:
    if not source_html.exists():
        raise FileNotFoundError(f"Dashboard source not found: {source_html}")

    destination_html.parent.mkdir(parents=True, exist_ok=True)
    destination_html.write_text(source_html.read_text(encoding="utf-8"), encoding="utf-8")
    index_html.parent.mkdir(parents=True, exist_ok=True)
    index_html.write_text(_build_index_html(destination_html.name), encoding="utf-8")
    return destination_html


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Publish the governed dashboard to a GitHub Pages entrypoint."
    )
    parser.add_argument(
        "--source-html",
        type=Path,
        default=Path("outputs/dashboard/executive-marketplace-command-center.html"),
    )
    parser.add_argument(
        "--destination-html",
        type=Path,
        default=Path(".pages/executive-marketplace-command-center.html"),
    )
    parser.add_argument("--index-html", type=Path, default=Path(".pages/index.html"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out = publish_pages_entry(args.source_html, args.destination_html, args.index_html)
    print(f"GitHub Pages dashboard published: {out} (index: {args.index_html})")


if __name__ == "__main__":
    main()
