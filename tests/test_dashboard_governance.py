from pathlib import Path

from src.dashboard.build_executive_dashboard import DashboardConfig, _build_payload, _dashboard_html


ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_payload_includes_governed_kpis_and_official_path() -> None:
    cfg = DashboardConfig(
        raw_dir=ROOT / "data" / "raw",
        processed_dir=ROOT / "data" / "processed",
        reports_dir=ROOT / "reports",
        output_file=ROOT / "outputs" / "dashboard" / "executive-marketplace-command-center.html",
        max_orders=2000,
        sample_seed=42,
    )
    payload = _build_payload(cfg)

    assert payload["meta"]["official_dashboard_output"] == "outputs/dashboard/executive-marketplace-command-center.html"
    assert str(payload["meta"]["official_kpi_source"]).endswith("reports/executive_kpi_snapshot.csv")
    assert payload["meta"]["is_sampled"] is True
    assert payload["meta"]["orders"] <= 2000

    official = payload["official_kpis"]
    required_metrics = {
        "gmv",
        "net_value",
        "take_rate",
        "subsidy_share",
        "realized_contribution_margin_proxy",
        "refund_rate",
        "dispute_rate",
        "risk_adjusted_value",
        "critical_sellers",
    }
    assert required_metrics.issubset(official.keys())


def test_dashboard_html_includes_print_mode_and_controls() -> None:
    html = _dashboard_html(data_json="{}", plotly_js="")

    assert '@media print' in html
    assert 'id="printDashboard"' in html
    assert 'window.print()' in html
    assert 'id="applyFilters"' in html
    assert 'id="resetFilters"' in html
    assert 'id="themeToggle"' in html
