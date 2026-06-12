from pathlib import Path

from src.dashboard.build_executive_dashboard import DashboardConfig, _build_payload, _dashboard_html, _json_safe


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
        "expected_margin_after_risk",
        "refund_rate",
        "dispute_rate",
        "chargeback_rate",
        "risk_adjusted_value",
        "top10_seller_gmv_share",
        "critical_sellers",
    }
    assert required_metrics.issubset(official.keys())

    assert payload["validation"]["publish_blocked"] is False
    assert payload["validation"]["critical_issues"] == 0
    assert payload["validation"]["release_state"] == "decision-support only"
    assert payload["validation"]["committee_grade_ready"] is False
    assert payload["recommended_policy"][0]["recommended_threshold"] == 60


def test_dashboard_html_includes_print_mode_and_controls() -> None:
    html = _dashboard_html(data_json="{}", plotly_js="")

    assert '@media print' in html
    assert 'id="printDashboard"' in html
    assert 'window.print()' in html
    assert 'id="applyFilters"' in html
    assert 'id="resetFilters"' in html
    assert 'id="themeToggle"' in html
    assert 'class="sort-button"' in html
    assert 'aria-pressed="true"' in html
    assert 'role="dialog"' in html
    assert 'aria-modal="true"' in html
    assert 'aria-live="polite"' in html
    assert 'scope="col"' in html
    assert "event.key === 'Tab' && drawerOpen" in html


def test_dashboard_payload_serializes_without_nonstandard_nan_tokens() -> None:
    import json
    import math

    cleaned = _json_safe({"ok": 1, "bad": math.nan, "nested": [{"v": float("inf")}]})
    encoded = json.dumps(cleaned, allow_nan=False)

    assert '"bad": null' in encoded
    assert '"v": null' in encoded
