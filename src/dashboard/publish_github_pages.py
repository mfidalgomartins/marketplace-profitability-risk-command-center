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
    :root {{
      --bg-start: #edf4fb;
      --bg-end: #f7f8fb;
      --panel: rgba(255, 255, 255, 0.94);
      --ink: #0e1726;
      --muted: #56657d;
      --line: #d5deea;
      --brand: #0a5bd3;
      --brand-soft: #e6f0ff;
      --brand-ink: #0d4dad;
      --shadow: 0 18px 40px rgba(12, 23, 39, 0.08);
    }}
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      font-family: "IBM Plex Sans", "Segoe UI", Arial, sans-serif;
      background:
        radial-gradient(circle at top left, rgba(33, 94, 190, 0.08), transparent 34%),
        linear-gradient(170deg, var(--bg-start) 0%, var(--bg-end) 100%);
      color: var(--ink);
      padding: 24px;
    }}
    .card {{
      max-width: 680px;
      width: 100%;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 28px;
      box-shadow: var(--shadow);
    }}
    .eyebrow {{
      display: inline-flex;
      margin-bottom: 10px;
      padding: 6px 10px;
      border-radius: 999px;
      background: var(--brand-soft);
      color: var(--brand-ink);
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.5px;
      text-transform: uppercase;
    }}
    h1 {{ margin: 0 0 10px 0; font-size: 30px; line-height: 1.08; letter-spacing: -0.3px; }}
    p {{ margin: 0 0 16px 0; color: var(--muted); font-size: 15px; line-height: 1.55; }}
    a {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 11px 14px;
      border-radius: 12px;
      background: var(--brand);
      color: #ffffff;
      font-weight: 600;
      text-decoration: none;
    }}
    a:hover {{ filter: brightness(0.98); }}
  </style>
</head>
<body>
  <div class="card">
    <div class="eyebrow">Live Dashboard</div>
    <h1>Marketplace Profitability, Fraud & Seller Quality Command Center</h1>
    <p>Redirecting to the live executive dashboard. If the redirect does not trigger automatically, use the link below.</p>
    <a href="{target_filename}">Open the live dashboard</a>
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
