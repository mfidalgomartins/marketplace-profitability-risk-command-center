from pathlib import Path

from src.dashboard.publish_github_pages import publish_pages_entry


ROOT = Path(__file__).resolve().parents[1]


def test_publish_pages_entry_copies_dashboard_html(tmp_path: Path) -> None:
    source = tmp_path / "source.html"
    source.write_text("<html><body>dashboard</body></html>", encoding="utf-8")
    destination = tmp_path / "docs" / "index.html"

    out = publish_pages_entry(source, destination)

    assert out == destination
    assert destination.exists()
    assert destination.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")


def test_docs_index_contains_required_dashboard_controls() -> None:
    index_path = ROOT / "docs" / "index.html"
    assert index_path.exists(), "docs/index.html must exist for GitHub Pages publishing"
    html = index_path.read_text(encoding="utf-8")

    assert 'id="applyFilters"' in html
    assert 'id="resetFilters"' in html
    assert 'id="themeToggle"' in html
    assert 'id="printDashboard"' in html
    assert "const EMBEDDED =" in html
    assert "/Users/" not in html
