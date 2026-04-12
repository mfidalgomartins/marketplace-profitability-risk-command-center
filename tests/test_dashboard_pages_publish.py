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
    index_path = ROOT / "docs" / "index.html"
    assert index_path.exists(), "docs/index.html must exist for GitHub Pages publishing"
    index_html = index_path.read_text(encoding="utf-8")
    named_dashboard = ROOT / "docs" / "executive-marketplace-command-center.html"
    assert named_dashboard.exists(), "Named dashboard publish file must exist in docs/"
    dashboard_html = named_dashboard.read_text(encoding="utf-8")

    assert "executive-marketplace-command-center.html" in index_html
    assert 'id="applyFilters"' in dashboard_html
    assert 'id="resetFilters"' in dashboard_html
    assert 'id="themeToggle"' in dashboard_html
    assert 'id="printDashboard"' in dashboard_html
    assert "const EMBEDDED =" in dashboard_html
    assert "/Users/" not in dashboard_html
