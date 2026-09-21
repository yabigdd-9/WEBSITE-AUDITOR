
"""
PDF Export: Converts HTML reports to PDF using Playwright headless browser.
Falls back to HTML-only if Playwright is not installed.
"""
from pathlib import Path


def html_to_pdf(html_path, pdf_path=None):
    """Convert an HTML file to PDF using Playwright."""
    html_path = Path(html_path)
    if pdf_path is None:
        pdf_path = html_path.with_suffix(".pdf")
    else:
        pdf_path = Path(pdf_path)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {
            "status": "html_only",
            "reason": "Playwright not installed. Run: python3 -m pip install playwright && python3 -m playwright install chromium",
            "html_path": str(html_path),
        }

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"file://{html_path.resolve()}")
            page.wait_for_load_state("networkidle")
            page.pdf(
                path=str(pdf_path),
                format="A4",
                margin={"top": "10mm", "bottom": "10mm", "left": "10mm", "right": "10mm"},
                print_background=True,
            )
            browser.close()
        return {"status": "success", "pdf_path": str(pdf_path)}
    except Exception as e:
        return {"status": "error", "error": str(e), "html_path": str(html_path)}
