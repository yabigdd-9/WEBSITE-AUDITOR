#!/usr/bin/env python3
"""Demo Factory — tiny HTTP server (scaffold).

Serves a single-page app with a brief form. On submit it calls the local
`generate_demo` templating function and renders the resulting demo (HTML view
+ raw Markdown, downloadable). Stdlib only — no pip install required.

Run:
    python3 server.py            # serves on http://localhost:8000
    python3 server.py --port 9000

Endpoints:
    GET  /            -> brief form (+ result if submitted)
    POST /            -> accepts form fields, renders generated demo
"""

from __future__ import annotations

import argparse
import html
import re
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from demo_factory import generate_demo, slugify


FORM_HTML = """\
<form method="post" action="/">
  <label>Product name<br><input name="name" value="{name}" required></label><br>
  <label>Category<br><input name="category" value="{category}" placeholder="e.g. saas, marketplace"></label><br>
  <label>One-liner<br><input name="one_liner" value="{one_liner}" placeholder="One sentence of value"></label><br>
  <label>Audience (optional)<br><input name="audience" value="{audience}"></label><br>
  <label>CTA URL<br><input name="cta_url" value="{cta_url}"></label><br>
  <button type="submit">Generate demo</button>
</form>
"""


def _page(title: str, body: str) -> bytes:
    doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:760px;margin:2rem auto;padding:0 1rem}}
textarea{{width:100%;height:18rem;font-family:ui-monospace,monospace}}
.box{{border:1px solid #ccc;border-radius:8px;padding:1rem;margin:1rem 0}}
label{{display:block;margin:.5rem 0}}input{{width:100%;padding:.4rem}}</style>
</head><body>{body}</body></html>"""
    return doc.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = (
            "<h1>Demo Factory</h1><p>Enter a brief to generate a demo page.</p>"
            + FORM_HTML.format(
                name="", category="", one_liner="", audience="", cta_url="#"
            )
        )
        self._respond(_page("Demo Factory", body))

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8", "replace")
        fields = urllib.parse.parse_qs(raw)
        brief = {
            k: (fields.get(k, [""])[0])
            for k in ("name", "category", "one_liner", "audience", "cta_url")
        }
        brief["name"] = brief["name"] or "Untitled Product"

        demo_md = generate_demo(brief)
        demo_html = _md_to_html(demo_md)
        slug = slugify(brief["name"])

        body = (
            "<h1>Demo Factory</h1>"
            + FORM_HTML.format(
                name=html.escape(brief["name"]),
                category=html.escape(brief["category"]),
                one_liner=html.escape(brief["one_liner"]),
                audience=html.escape(brief["audience"]),
                cta_url=html.escape(brief["cta_url"]),
            )
            + f'<div class="box"><h2>Generated demo &mdash; {html.escape(slug)}</h2>'
            + demo_html
            + "</div>"
            + '<div class="box"><h2>Raw Markdown</h2>'
            + f'<textarea readonly>{html.escape(demo_md)}</textarea></div>'
        )
        self._respond(_page(f"Demo: {brief['name']}", body))

    def _respond(self, payload: bytes):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # quiet
        return


def _md_to_html(md: str) -> str:
    """Very small Markdown->HTML for the scaffold (headings, lists, links, em)."""
    out = []
    in_list = False
    for line in md.splitlines():
        if line.startswith("## "):
            if in_list:
                out.append("</ul>"); in_list = False
            out.append(f"<h2>{_inline(line[3:])}</h2>")
        elif line.startswith("# "):
            if in_list:
                out.append("</ul>"); in_list = False
            out.append(f"<h1>{_inline(line[2:])}</h1>")
        elif line.startswith("- ") or (line[:2].isdigit() and line[2:3] == "."):
            if not in_list:
                out.append("<ul>"); in_list = True
            out.append(f"<li>{_inline(line.split('. ', 1)[-1].lstrip('- '))}</li>")
        elif line.startswith("---"):
            if in_list:
                out.append("</ul>"); in_list = False
            out.append("<hr>")
        elif line.strip() == "":
            if in_list:
                out.append("</ul>"); in_list = False
        else:
            if in_list:
                out.append("</ul>"); in_list = False
            out.append(f"<p>{_inline(line)}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def _inline(text: str) -> str:
    text = html.escape(text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    text = text.replace("**", "<strong>", 1)  # naive; balanced below
    text = text.replace("**", "</strong>")
    text = text.replace("_", "<em>", 1)
    text = text.replace("_", "</em>")
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Demo Factory running at http://{args.host}:{args.port}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
