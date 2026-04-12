from pathlib import Path

from src.dashboard.publish_github_pages import publish_pages_entry


ROOT = Path(__file__).resolve().parents[1]


def test_publish_pages_entry_copies_dashboard_html(tmp_path: Path) -> None:
    source = tmp_path / "source.html"
    source.write_text("<html><body>dashboard</body></html>", encoding="utf-8")
    destination = tmp_path / "docs" / "executive-marketplace-command-center.html"
    index = tmp_path / "docs" / "index.html"

    out = publish_pages_entry(source, destination, index)

    assert out == destination
    assert destination.exists()
    assert index.exists()
    assert destination.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")
    assert "executive-marketplace-command-center.html" in index.read_text(encoding="utf-8")


def test_docs_index_contains_required_dashboard_controls() -> None:
    named_dashboard = ROOT / "outputs" / "dashboard" / "executive-marketplace-command-center.html"
    assert named_dashboard.exists(), "Final dashboard artifact must exist in outputs/dashboard"
    dashboard_html = named_dashboard.read_text(encoding="utf-8")

    assert 'id="applyFilters"' in dashboard_html
    assert 'id="resetFilters"' in dashboard_html
    assert 'id="themeToggle"' in dashboard_html
    assert 'id="printDashboard"' in dashboard_html
    assert "const EMBEDDED =" in dashboard_html
    assert "/Users/" not in dashboard_html

    duplicate_docs_dashboard = ROOT / "docs" / "executive-marketplace-command-center.html"
    assert not duplicate_docs_dashboard.exists(), "Duplicate dashboard should not be tracked in docs/"
