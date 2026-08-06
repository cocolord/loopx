#!/usr/bin/env python3
"""Validate the monorepo-owned LoopX Developer Book publication contract."""

from __future__ import annotations

import argparse
from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[1]
BOOK = REPO_ROOT / "docs" / "book"
MKDOCS = REPO_ROOT / "mkdocs.yaml"
MKDOCS_ZH = REPO_ROOT / "mkdocs.book.zh.yaml"
MKDOCS_EN = REPO_ROOT / "mkdocs.book.en.yaml"
BRAND_STYLES = REPO_ROOT / "docs" / "stylesheets" / "loopx.css"
HOMEPAGE = REPO_ROOT / "apps" / "presentation" / "site" / "index.html"
HOMEPAGE_SCRIPT = REPO_ROOT / "apps" / "presentation" / "site" / "home.js"

CHAPTERS = (
    "00-reading-guide",
    "01-from-session-to-loop",
    "02-session-goal-loopx",
    "state-substrate",
    "work-graph-and-authority",
    "03-one-turn",
    "04-runtime-boundaries",
    "05-connect-existing-project",
    "06-codex-app",
    "07-codex-cli",
    "source-protocol-map",
    "source-trace-protocol-chain",
    "source-change-control-plane-rule",
    "source-validation-to-pr",
    "08-extension-placement",
    "09-extension-scaffold",
    "10-extension-lifecycle",
    "11-engineering-boundaries",
    "appendix-reference",
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def validate_rendered_site(site_dir: Path) -> None:
    routes = {
        "index.html": ("LoopX Developer Book", "English edition", "MkDocs Material"),
        "chapters/01-from-session-to-loop/index.html": (
            "从一次会话到长程任务",
        ),
        "chapters/05-connect-existing-project/index.html": (
            "快速阅读路线",
            "让 Agent 帮你接入",
        ),
    }
    english_routes = {
        "index.html": ("LoopX Developer Book", "简体中文版", "MkDocs Material"),
        "chapters/01-from-session-to-loop/index.html": (
            "From one session to long-running work",
        ),
        "chapters/05-connect-existing-project/index.html": (
            "Fast reading path",
            "Delegate onboarding to an Agent",
        ),
    }
    for relative_path, markers in routes.items():
        target = site_dir / relative_path
        assert target.is_file(), f"missing rendered Developer Book route: {relative_path}"
        html = read(target)
        for marker in markers:
            assert marker in html, f"{relative_path}: missing rendered marker {marker}"
        assert ":::: tip" not in html, f"{relative_path}: unrendered VitePress container"
        assert 'data-md-color-scheme="slate"' in html, f"{relative_path}: not dark by default"
        if relative_path == "index.html":
            chapter_links = set(re.findall(r'href="[^"]*chapters/[^"#?]+/?(?:index\.html)?"', html))
            assert len(chapter_links) == len(CHAPTERS), (
                f"{relative_path}: expected {len(CHAPTERS)} Chinese chapter links, "
                f"found {len(chapter_links)}"
            )
        else:
            assert html.count("md-nav__item--active md-nav__item--section") == 1, (
                f"{relative_path}: expected exactly one expanded Chinese Part"
            )
        assert "English Chapters" not in html
        assert "Part I — Control-plane foundations" not in html

    english_site_dir = site_dir / "en"
    for relative_path, markers in english_routes.items():
        target = english_site_dir / relative_path
        assert target.is_file(), f"missing rendered English Developer Book route: {relative_path}"
        html = read(target)
        for marker in markers:
            assert marker in html, f"en/{relative_path}: missing rendered marker {marker}"
        assert 'data-md-color-scheme="slate"' in html, f"en/{relative_path}: not dark by default"
        if relative_path == "index.html":
            chapter_links = set(re.findall(r'href="[^"]*chapters/[^"#?]+/?(?:index\.html)?"', html))
            assert len(chapter_links) == len(CHAPTERS), (
                f"en/{relative_path}: expected {len(CHAPTERS)} English chapter links, "
                f"found {len(chapter_links)}"
            )
        else:
            assert html.count("md-nav__item--active md-nav__item--section") == 1, (
                f"en/{relative_path}: expected exactly one expanded English Part"
            )
        for chinese_section in (
            "第一部分：控制面基础",
            "第二部分：接入现有项目",
            "第三部分：开发者贡献",
            "第四部分：工程边界",
        ):
            assert chinese_section not in html


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site-dir", type=Path)
    args = parser.parse_args()

    assert not (BOOK / "labs").exists(), "Dev Book publication must not include Labs"

    mkdocs = read(MKDOCS)
    assert "book/chapters/" not in mkdocs
    assert "book/en/chapters/" not in mkdocs
    assert "book/**" in mkdocs
    docs_home = read(REPO_ROOT / "docs" / "index.md")
    docs_readme = read(REPO_ROOT / "docs" / "README.md")
    assert "Developer Book](/loopx/docs/book/)" in docs_home
    assert "Developer Book](/loopx/docs/book/)" in docs_readme
    assert "English edition](/loopx/docs/book/en/)" in docs_readme

    zh_config = read(MKDOCS_ZH)
    en_config = read(MKDOCS_EN)
    for config in (zh_config, en_config):
        assert "INHERIT: mkdocs.yaml" in config
        assert config.index("scheme: slate") < config.index("scheme: default")
        assert "navigation.sections" in config
        assert "navigation.expand" not in config
    assert "docs_dir: docs/book" in zh_config
    assert "language: zh" in zh_config
    assert "en/**" in zh_config
    assert "docs_dir: docs/book/en" in en_config
    assert "language: en" in en_config
    assert "中文:" not in en_config

    for chapter in CHAPTERS:
        assert f"chapters/{chapter}.md" in zh_config, chapter
        assert f"chapters/{chapter}.md" in en_config, f"en/{chapter}"

    styles = read(BRAND_STYLES)
    for marker in (
        "#050914",
        "#091425",
        "#6eabff",
        "#96c8ff",
        "Iowan Old Style",
        "SFMono-Regular",
        ".md-sidebar",
        ".md-nav__item--section",
        ".md-typeset .grid.cards",
    ):
        assert marker in styles, marker

    homepage = read(HOMEPAGE)
    script = read(HOMEPAGE_SCRIPT)
    assert 'data-devbook-base="__LOOPX_BASE__docs/book"' in homepage
    for path in (
        "/",
        "/chapters/01-from-session-to-loop",
        "/chapters/05-connect-existing-project",
        "/chapters/source-protocol-map",
    ):
        assert f'data-devbook-path="{path}"' in homepage
    assert 'language === "zh" ? "" : "/en"' in script
    assert "developerBookBase" in script

    for locale_root in (BOOK / "index.md", BOOK / "en" / "index.md"):
        text = read(locale_root)
        assert "layout: home" not in text
        assert "theme: brand" not in text
        assert "VitePress" not in text
        assert "MkDocs Material" in text
    assert "/loopx/docs/book/en/" in read(BOOK / "index.md")
    assert "/loopx/docs/book/" in read(BOOK / "en" / "index.md")

    all_markdown = "\n".join(
        read(path) for path in BOOK.rglob("*.md")
    )
    for forbidden in (
        "cocolord.github.io/loopx-book",
        "cocolord/loopx-book-labs",
        "站点生成器：VitePress",
        "Site generator: VitePress",
        "当前站点使用 VitePress",
        "The site uses VitePress",
        ":::: tip",
        ":::: warning",
        ":::: info",
    ):
        assert forbidden not in all_markdown, forbidden

    if args.site_dir is not None:
        validate_rendered_site(args.site_dir)

    print("dev-book-publication-smoke: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
