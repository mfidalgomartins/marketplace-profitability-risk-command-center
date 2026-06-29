from pathlib import Path

import pytest
from src.dashboard import publish_github_pages
from src.dashboard.publish_github_pages import (
    _build_index_html,
    publish_pages_entry,
)

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


def test_publish_pages_entry_raises_when_source_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        publish_pages_entry(
            source_html=tmp_path / "missing.html",
            destination_html=tmp_path / "out.html",
            index_html=tmp_path / "index.html",
        )


def test_index_html_redirects_and_links_to_target() -> None:
    html = _build_index_html("executive-marketplace-command-center.html")
    assert "0; url=executive-marketplace-command-center.html" in html
    assert 'href="executive-marketplace-command-center.html"' in html
    assert "<title>" in html


def test_index_html_matches_apple_design_language() -> None:
    # The landing page must stay consistent with the dashboard's design system:
    # system/SF type, Apple-grey canvas, indigo accent, pill control — and must
    # NOT reintroduce the banned "AI smell" (gradients, glass, eyebrow pills, serif).
    html = _build_index_html("d.html")
    assert "-apple-system" in html
    assert "#f5f5f7" in html
    assert "prefers-color-scheme: dark" in html
    assert "border-radius: 980px" in html  # pill button
    assert "prefers-reduced-motion: reduce" in html  # honors Reduce Motion
    assert "linear-gradient" not in html
    assert "radial-gradient" not in html
    assert "backdrop-filter" not in html  # no glass on the card
    # No serif display font (sans-serif in the stack is fine).
    for serif_font in ("Iowan", "Palatino", "Georgia", "Times"):
        assert serif_font not in html


def test_main_publishes_via_cli(tmp_path: Path, monkeypatch, capsys) -> None:
    source = tmp_path / "source.html"
    source.write_text("<html><body>dashboard</body></html>", encoding="utf-8")
    destination = tmp_path / "docs" / "executive-marketplace-command-center.html"
    index = tmp_path / "docs" / "index.html"
    monkeypatch.setattr(
        "sys.argv",
        [
            "publish_github_pages.py",
            "--source-html",
            str(source),
            "--destination-html",
            str(destination),
            "--index-html",
            str(index),
        ],
    )

    publish_github_pages.main()

    assert destination.exists()
    assert index.exists()
    assert "published" in capsys.readouterr().out.lower()
