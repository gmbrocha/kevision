from __future__ import annotations

import re
import threading
from pathlib import Path

import pytest
from werkzeug.serving import make_server

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import expect, sync_playwright
except ImportError:
    PlaywrightError = Exception
    expect = None
    sync_playwright = None

from webapp.app import create_app

from tests.smoke_helpers import build_smoke_workspace


@pytest.fixture()
def browser_page():
    if sync_playwright is None:
        pytest.skip("Playwright is optional for browser smoke tests.")
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True)
        except PlaywrightError as exc:
            pytest.skip(f"Playwright browser is not installed: {exc}")
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        try:
            yield page
        finally:
            browser.close()


@pytest.fixture()
def empty_live_server(tmp_path: Path):
    yield from _serve_app(tmp_path)


@pytest.fixture()
def smoke_live_server(tmp_path: Path):
    smoke = build_smoke_workspace(tmp_path)
    yield from _serve_app(smoke.app_data_dir)


def test_browser_smoke_create_project(empty_live_server: str, browser_page):
    page = browser_page
    page.goto(f"{empty_live_server}/projects")

    expect(page.get_by_role("heading", name="Projects")).to_be_visible()
    page.locator('input[name="name"]').fill("Browser Smoke")
    page.get_by_role("button", name="Create project").click()

    expect(page).to_have_url(re.compile(r"/overview$"))
    expect(page.get_by_role("heading", name="Browser Smoke")).to_be_visible()


def test_browser_smoke_overview_package_controls(smoke_live_server: str, browser_page):
    page = browser_page
    page.goto(f"{smoke_live_server}/overview")

    expect(page.locator("td.cell-mono", has_text="Revision #1 - Smoke").first).to_be_visible()
    expect(page.locator("td.cell-mono", has_text="Revision #2 - Smoke").first).to_be_visible()
    expect(page.get_by_text("Revision #", exact=True).first).to_be_visible()
    expect(page.get_by_text("Browse local files").first).to_be_visible()
    expect(page.get_by_role("button", name="Populate Workspace")).to_be_visible()


def test_browser_smoke_review_filter_and_detail_actions(smoke_live_server: str, browser_page):
    page = browser_page
    page.goto(f"{smoke_live_server}/changes")
    page.get_by_role("link", name=re.compile(r"Newest package")).click()

    body_text = page.locator("body").inner_text()
    assert "Smoke scope revision 2" in body_text
    assert "Smoke scope revision 1" not in body_text

    page.locator('a[href*="/changes/change-r2"]').last.click()
    expect(page.get_by_role("button", name="Mark as legend")).to_be_visible()
    expect(page.get_by_role("button", name="Adjust crop")).to_be_visible()
    expect(page.get_by_role("button", name="Correct overmerge")).to_be_visible()


def test_browser_smoke_sheet_overlay_coordinate_attrs(smoke_live_server: str, browser_page):
    page = browser_page
    page.goto(f"{smoke_live_server}/sheets/sheet-r1")

    stage = page.locator(".js-image-stage")
    bbox = page.locator(".bbox").first
    expect(stage).to_have_attribute("data-coordinate-width", "400")
    expect(stage).to_have_attribute("data-coordinate-height", "240")
    expect(bbox).to_have_attribute("data-x", "80.0")
    expect(bbox).to_have_attribute("data-w", "120.0")


def _serve_app(app_data_dir: Path):
    app = create_app(app_data_dir)
    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
