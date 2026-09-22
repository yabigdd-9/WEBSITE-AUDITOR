import hashlib
import json
from pathlib import Path

from .common import validate_url


VIEWPORTS = {
    "desktop": {"width": 1366, "height": 900},
    "tablet": {"width": 834, "height": 1112},
    "mobile": {"width": 390, "height": 844},
}


def _artifact(path: Path) -> dict:
    return {"path": str(path), "size": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def run_browser_checks(url, output_dir, enabled=True, allow_private=False, axe_path=None):
    if not enabled:
        return {"status": "skipped", "reason": "Disabled in selected audit profile", "evidence": {}}
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    evidence = {
        "mode": "lab",
        "limitations": "No field CWV, legal or accessibility conformance claim.",
    }
    try:
        from playwright.sync_api import sync_playwright

        validate_url(url, allow_private)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    service_workers="block", viewport={"width": 1366, "height": 900}
                )
                blocked, failures = [], []

                def guard(route):
                    try:
                        validate_url(route.request.url, allow_private)
                        if route.request.method not in ("GET", "HEAD", "OPTIONS"):
                            raise ValueError("Audit blocks write requests")
                        route.continue_()
                    except Exception as exc:
                        blocked.append({"reason": str(exc)})
                        route.abort()

                context.route("**/*", guard)
                if hasattr(context, "route_web_socket"):
                    context.route_web_socket("**/*", lambda ws: ws.close())
                page = context.new_page()
                page.on("pageerror", lambda error: failures.append(str(error)[:500]))
                page.goto(url, wait_until="domcontentloaded", timeout=20_000)
                page.wait_for_timeout(700)
                screenshot = output_dir / "screenshot.png"
                page.screenshot(path=str(screenshot), full_page=True, timeout=15000)
                evidence.update(
                    {
                        "screenshot": str(screenshot),
                        "console_errors": failures,
                        "blocked_requests": blocked,
                    }
                )
                # Evidence-grade visual pack: fixed viewports, deterministic
                # names, hashes, layout measurements, and targeted crops.
                visual = {"viewports": {}, "crops": [], "limitations": "Lab captures; no field conversion claim."}
                for viewport_name, viewport in VIEWPORTS.items():
                    page.set_viewport_size(viewport)
                    path = output_dir / f"{viewport_name}.png"
                    if viewport_name == "desktop":
                        path = screenshot
                    else:
                        page.screenshot(path=str(path), full_page=True, timeout=15000)
                    visual["viewports"][viewport_name] = {"viewport": viewport, **_artifact(path)}
                page.set_viewport_size(VIEWPORTS["desktop"])
                visual["layout"] = page.evaluate("""() => ({
                    document_width: document.documentElement.scrollWidth,
                    viewport_width: innerWidth,
                    horizontal_overflow: document.documentElement.scrollWidth > innerWidth,
                    landmarks: [...document.querySelectorAll('header,nav,main,footer,h1,form,[role="button"]')].slice(0,100).map((el,i) => { const r=el.getBoundingClientRect(); return {index:i,tag:el.tagName.toLowerCase(),role:el.getAttribute('role'),text:(el.innerText||'').trim().slice(0,120),x:r.x,y:r.y,width:r.width,height:r.height,visible:!!(r.width&&r.height)}; })
                })""")
                for crop_name, selector in (("hero", "header, main > section, main"), ("primary_cta", "main a, main button, main [role=button]"), ("form", "form"), ("navigation", "nav")):
                    locator = page.locator(selector).first
                    if not locator.count():
                        continue
                    try:
                        box = locator.bounding_box()
                        if box and box["width"] > 1 and box["height"] > 1:
                            crop_path = output_dir / f"crop-{crop_name}.png"
                            page.screenshot(path=str(crop_path), clip=box, timeout=15000)
                            visual["crops"].append({"name": crop_name, "selector": selector, "box": box, **_artifact(crop_path)})
                    except Exception as exc:
                        visual.setdefault("crop_errors", []).append({"name": crop_name, "reason": str(exc)[:300]})
                evidence["visual_pack"] = visual
                evidence["timing"] = page.evaluate(
                    """() => ({navigation: performance.getEntriesByType('navigation').map(x => ({duration:x.duration, domContentLoaded:x.domContentLoadedEventEnd, responseStart:x.responseStart})), paint:performance.getEntriesByType('paint').map(x=>({name:x.name,startTime:x.startTime})), resources:performance.getEntriesByType('resource').slice(0,100).map(x=>({initiatorType:x.initiatorType,duration:x.duration,transferSize:x.transferSize}))})"""
                )
                evidence["images"] = page.locator("img").evaluate_all(
                    """imgs => imgs.map(x=>({src:x.getAttribute('src'), loaded:x.complete && x.naturalWidth>0, alt:x.getAttribute('alt'), loading:x.loading, aboveFold:x.getBoundingClientRect().top<innerHeight}))"""
                )
                evidence["links"] = page.locator("a[href]").evaluate_all(
                    'els=>els.slice(0,100).map(x=>({text:x.textContent,href:x.getAttribute("href")}))'
                )
                evidence["consent"] = {
                    "interaction": "none",
                    "cookies_before_interaction": [
                        {k: c[k] for k in ("name", "domain", "secure", "httpOnly", "sameSite")}
                        for c in context.cookies()
                    ],
                    "limitation": "No consent accepted or forms submitted; cookie purpose requires review.",
                }
                path = Path(axe_path) if axe_path else Path(__file__).parent / "assets/axe.min.js"
                if path.is_file():
                    page.add_script_tag(path=str(path.resolve()))
                    evidence["axe"] = page.evaluate(
                        "async () => {const r=await axe.run(); return {violations:r.violations, incomplete:r.incomplete, passes:r.passes.length, version:r.testEngine.version}}"
                    )
                else:
                    evidence["axe_error"] = (
                        "Pinned axe-core asset is missing; install browser assets."
                    )
                page.set_viewport_size(VIEWPORTS["mobile"])
                evidence["mobile"] = page.evaluate(
                    "()=>({overflow:document.documentElement.scrollWidth>innerWidth,width:innerWidth})"
                )
                mobile = output_dir / "mobile.png"
                # Keep the legacy artifact name while the visual pack uses
                # the same hashed mobile capture.
                page.screenshot(path=str(mobile), full_page=True, timeout=15000)
                evidence["mobile_screenshot"] = str(mobile)
                evidence["visual_pack"]["legacy_mobile_artifact"] = _artifact(mobile)
            finally:
                browser.close()
        return {"status": "ok", "evidence": evidence}
    except Exception as exc:
        return {"status": "error", "reason": str(exc), "evidence": evidence}


def export_pdf(html_path, pdf_path, opts=None):
    use_gotenberg = False
    gotenberg_url = "http://localhost:3000"
    if opts is not None:
        use_gotenberg = getattr(opts, 'use_gotenberg', False)
        # Allow overriding via environment variable
        import os
        gotenberg_url = os.getenv("GOTENBERG_URL", gotenberg_url)

    if use_gotenberg:
        try:
            import requests
            # Read the HTML file
            html_content = Path(html_path).read_text()
            # Send to Gotenberg
            response = requests.post(
                f"{gotenberg_url}/forms/html",
                files={"index.html": ("index.html", html_content, "text/html")},
                data={"margin": "0.5in"},  # optional
                timeout=30,
            )
            response.raise_for_status()
            # Write the PDF
            Path(pdf_path).write_bytes(response.content)
            return
        except Exception:
            # Fall back to Playwright if Gotenberg fails
            pass

    # Fallback to Playwright method
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.route(
                "**/*",
                lambda route: (
                    route.abort()
                    if route.request.url.startswith(("http:", "https:"))
                    else route.continue_()
                ),
            )
            page.goto(Path(html_path).resolve().as_uri())
            temporary = Path(pdf_path).with_suffix(".tmp.pdf")
            page.pdf(path=str(temporary), format="A4", print_background=True)
            temporary.replace(pdf_path)
        finally:
            browser.close()
