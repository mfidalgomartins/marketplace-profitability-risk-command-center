from __future__ import annotations

import argparse
from pathlib import Path


def _build_index_html(target_filename: str) -> str:
    # Reuse the dashboard's typography, color tokens, and motion preferences.
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Marketplace Command Center</title>
  <meta http-equiv="refresh" content="0; url={target_filename}">
  <style>
    :root {{
      --bg: #f5f5f7;
      --panel: #ffffff;
      --ink: #0a1628;
      --muted: #5c6b80;
      --eyebrow: #8593a5;
      --line: #e6e9ef;
      --accent: #5b54e0;
      --accent-ink: #4a43c9;
      --shadow: 0 1px 2px rgba(10, 22, 40, 0.05), 0 8px 24px rgba(10, 22, 40, 0.045);
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #0a0c10;
        --panel: #12151c;
        --ink: #edf0f5;
        --muted: #98a3b3;
        --eyebrow: #6b7686;
        --line: #222732;
        --accent: #8e88ff;
        --accent-ink: #aaa4ff;
        --shadow: 0 1px 2px rgba(0, 0, 0, 0.45), 0 8px 24px rgba(0, 0, 0, 0.35);
      }}
    }}
    * {{ box-sizing: border-box; }}
    @media (prefers-reduced-motion: reduce) {{
      * {{ transition-duration: 0.01ms !important; animation-duration: 0.01ms !important; }}
    }}
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display", "Helvetica Neue", "Geist", "Segoe UI", Arial, sans-serif;
      background: var(--bg);
      color: var(--ink);
      padding: 24px;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
      text-rendering: optimizeLegibility;
    }}
    .card {{
      max-width: 640px;
      width: 100%;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 32px;
      box-shadow: var(--shadow);
    }}
    .eyebrow {{
      margin-bottom: 14px;
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 1.4px;
      text-transform: uppercase;
      color: var(--eyebrow);
    }}
    h1 {{
      margin: 0 0 12px 0;
      font-size: 28px;
      line-height: 1.15;
      letter-spacing: -0.5px;
      font-weight: 600;
    }}
    p {{ margin: 0 0 20px 0; color: var(--muted); font-size: 15px; line-height: 1.55; }}
    a {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 11px 18px;
      border-radius: 980px;
      background: var(--accent);
      color: #ffffff;
      font-weight: 600;
      text-decoration: none;
      transition: background 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    }}
    a:hover {{ background: var(--accent-ink); }}
  </style>
</head>
<body>
  <div class="card">
    <div class="eyebrow">Live Dashboard</div>
    <h1>Marketplace Profitability, Fraud &amp; Seller Quality Command Center</h1>
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
    parser = argparse.ArgumentParser(description="Publish the governed dashboard to a GitHub Pages entrypoint.")
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
