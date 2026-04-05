from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

import matplotlib.pyplot as plt


@dataclass(frozen=True)
class PreviewPackConfig:
    charts_dir: Path = Path("outputs/charts")
    output_image: Path = Path("outputs/charts/00_executive_preview_pack.png")
    output_manifest: Path = Path("outputs/charts/00_executive_preview_pack.md")


CHART_SELECTION: List[Tuple[str, str]] = [
    ("01_gmv_vs_risk_adjusted_gmv_trend.png", "Growth Quality Gap"),
    ("07_top_sellers_by_governance_priority.png", "Governance Concentration"),
    ("14_scenario_comparison_chart.png", "Scenario Trade-offs"),
    ("16_risk_leakage_waterfall.png", "Leakage Bridge"),
    ("17_order_risk_backtesting_thresholds.png", "Policy Backtesting"),
    ("18_scenario_monte_carlo_ranges.png", "Uncertainty Ranges"),
]


def _render_preview_pack(cfg: PreviewPackConfig) -> Tuple[List[str], List[str]]:
    included: List[str] = []
    missing: List[str] = []

    fig, axes = plt.subplots(2, 3, figsize=(20, 12))
    axes_flat = axes.flatten()

    for ax, (fname, title) in zip(axes_flat, CHART_SELECTION):
        path = cfg.charts_dir / fname
        if path.exists():
            img = plt.imread(path)
            ax.imshow(img)
            ax.set_title(title, fontsize=12, weight="bold")
            included.append(fname)
        else:
            ax.text(0.5, 0.5, f"Missing\n{fname}", ha="center", va="center", fontsize=11)
            ax.set_title(f"{title} (Missing)", fontsize=12, color="#b42318")
            missing.append(fname)
        ax.axis("off")

    fig.suptitle("Marketplace Command Center: Executive Preview Pack", fontsize=18, weight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    cfg.output_image.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(cfg.output_image, dpi=180, bbox_inches="tight")
    plt.close(fig)

    return included, missing


def _write_manifest(cfg: PreviewPackConfig, included: List[str], missing: List[str]) -> None:
    lines: List[str] = []
    lines.append("# Executive Preview Pack Manifest")
    lines.append("")
    lines.append(f"- Output image: `{cfg.output_image}`")
    lines.append(f"- Included charts: `{len(included)}`")
    lines.append(f"- Missing charts: `{len(missing)}`")
    lines.append("")
    lines.append("## Included")
    if included:
        for f in included:
            lines.append(f"- `{f}`")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Missing")
    if missing:
        for f in missing:
            lines.append(f"- `{f}`")
    else:
        lines.append("- none")
    lines.append("")

    cfg.output_manifest.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build executive preview chart pack artifact.")
    parser.add_argument("--charts-dir", type=Path, default=Path("outputs/charts"))
    parser.add_argument("--output-image", type=Path, default=Path("outputs/charts/00_executive_preview_pack.png"))
    parser.add_argument("--output-manifest", type=Path, default=Path("outputs/charts/00_executive_preview_pack.md"))
    args = parser.parse_args()

    cfg = PreviewPackConfig(
        charts_dir=args.charts_dir,
        output_image=args.output_image,
        output_manifest=args.output_manifest,
    )

    included, missing = _render_preview_pack(cfg)
    _write_manifest(cfg, included, missing)

    print(f"Executive preview image written: {cfg.output_image}")
    print(f"Executive preview manifest written: {cfg.output_manifest}")
    print(f"Included={len(included)} Missing={len(missing)}")


if __name__ == "__main__":
    main()
