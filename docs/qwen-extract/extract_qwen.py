#!/usr/bin/env python3
"""
Extract every message + phase from Qwen chat export JSON files into readable
Markdown, and pull each fenced code block out into a standalone artifact file.

Usage:
    python3 extract_qwen.py <export.json> [<export.json> ...]
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

OUT_ROOT = Path(__file__).resolve().parent
ARTIFACT_ROOT = OUT_ROOT / "artifacts"

FENCE_RE = re.compile(r"^(`{3,}|~{3,})[ \t]*([^\n`]*)$")
PATH_HINT_RE = re.compile(
    r"(?:`|\*\*|\b)([A-Za-z0-9_./-]+\.(?:py|ts|tsx|js|yml|yaml|md|sh|json|html|css|toml|cfg|ini|txt))"
)


def ts(value) -> str:
    if value is None:
        return "-"
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return str(value)


def slugify(text: str, limit: int = 60) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return (text[:limit].strip("-") or "untitled")


def safe_fence(text: str, lang: str = "") -> str:
    """Wrap text in a fence that cannot be broken by its own backticks."""
    longest = 0
    for match in re.finditer(r"`{3,}", text):
        longest = max(longest, len(match.group(0)))
    fence = "`" * max(3, longest + 1)
    return f"{fence}{lang}\n{text}\n{fence}"


def ordered_messages(history: dict) -> list[dict]:
    messages = history.get("messages") or {}
    if not messages:
        return []
    roots = [k for k, v in messages.items() if not v.get("parentId")]
    order: list[str] = []
    seen: set[str] = set()
    stack = roots or list(messages)
    while stack:
        mid = stack.pop(0)
        if mid in seen or mid not in messages:
            continue
        seen.add(mid)
        order.append(mid)
        stack = list(messages[mid].get("childrenIds") or []) + stack
    for mid in messages:
        if mid not in seen:
            order.append(mid)
    return [messages[mid] for mid in order]


def split_fenced_blocks(text: str) -> list[dict]:
    """Return [{lang, code, start}] for every fenced code block (CommonMark rules)."""
    lines = text.split("\n")
    blocks: list[dict] = []
    i = 0
    offset = 0
    while i < len(lines):
        m = FENCE_RE.match(lines[i])
        if not m:
            offset += len(lines[i]) + 1
            i += 1
            continue
        fence, lang = m.group(1), m.group(2).strip()
        start = offset
        body: list[str] = []
        i += 1
        offset += len(lines[i - 1]) + 1
        while i < len(lines):
            if lines[i].rstrip() == fence:
                break
            body.append(lines[i])
            offset += len(lines[i]) + 1
            i += 1
        blocks.append({"lang": lang, "code": "\n".join(body), "start": start,
                       "context": text[max(0, start - 700):start]})
        offset += len(lines[i]) + 1 if i < len(lines) else 0
        i += 1
    return blocks


def artifact_name(index: int, lang: str, code: str, context: str) -> str:
    hints = PATH_HINT_RE.findall(context[-500:] if context else "")
    hint = hints[-1] if hints else ""
    stem = hint.strip("./") if hint else f"block-{index:03d}.{lang or 'txt'}"
    stem = re.sub(r"[^A-Za-z0-9_./-]", "_", stem).lstrip("/").replace("..", "_")
    return stem


def unique_path(base: Path, name: str) -> Path:
    target = base / name
    if not target.exists():
        return target
    stem, suffix = target.stem, target.suffix
    n = 2
    while (base / f"{stem}-{n}{suffix}").exists():
        n += 1
    return base / f"{stem}-{n}{suffix}"
def render(data: dict, source: Path) -> tuple[Path, list[dict]]:
    history = data["chat"]["history"]
    title = data.get("title") or "untitled"
    slug = slugify(title)
    md_path = OUT_ROOT / f"{slug}.md"
    artifacts: list[dict] = []

    msgs = ordered_messages(history)
    out: list[str] = []
    out.append(f"# {title}\n")
    out.append("| field | value |")
    out.append("| --- | --- |")
    out.append(f"| chat id | `{data.get('id')}` |")
    out.append(f"| share id | `{data.get('share_id')}` |")
    out.append(f"| created | {ts(data.get('created_at'))} |")
    out.append(f"| updated | {ts(data.get('updated_at'))} |")
    out.append(f"| messages | {len(msgs)} |")
    out.append(f"| source export | `{source.name}` |")
    out.append("")

    toc: list[str] = ["## Contents\n"]
    trace: list[str] = ["\n---\n", "# Appendix: internal reasoning & tool trace\n",
                        "_Everything produced outside the final answer: thinking summaries, "
                        "reasoning (`think`) phases and raw tool observations (web extraction)._\n"]
    code_index = 0

    for n, msg in enumerate(msgs, 1):
        role = msg.get("role", "?")
        mid = msg.get("id")
        model = msg.get("modelName") or msg.get("model") or ""
        stamp = ts(msg.get("timestamp"))
        toc.append(f"{n}. **{role}** — {stamp}" + (f" · `{model}`" if model else ""))

        out.append(f"\n<a id=\"msg-{n}\"></a>\n")
        out.append(f"## Message {n} — {role}" + (f"  (`{model}`)" if model else ""))
        out.append(f"_{stamp}_ · id `{mid}`\n")

        files = msg.get("files") or []
        if files:
            out.append("**Attachments:** " + ", ".join(
                f"`{f.get('name') or f.get('url') or 'file'}` ({f.get('type') or f.get('file_class') or '?'})"
                for f in files) + "\n")

        body_text = msg.get("content") or ""
        if isinstance(body_text, (dict, list)):
            body_text = json.dumps(body_text, indent=2, ensure_ascii=False)
        phases = msg.get("content_list") or []

        answer_parts: list[str] = []
        if body_text.strip():
            answer_parts.append(body_text.strip())
        for entry in phases:
            if entry.get("phase") == "answer" and (entry.get("content") or "").strip():
                answer_parts.append(entry["content"].strip())

        if answer_parts:
            answer = "\n\n".join(answer_parts)
            out.append("### Answer\n")
            out.append(answer)
            out.append("")
            msg_dir = ARTIFACT_ROOT / slug / f"msg-{n:02d}-{role}"
            for block in split_fenced_blocks(answer):
                code_index += 1
                name = artifact_name(code_index, block["lang"], block["code"], block.get("context", ""))
                art_path = unique_path(msg_dir, name)
                art_path.parent.mkdir(parents=True, exist_ok=True)
                art_path.write_text(block["code"] + "\n", encoding="utf-8")
                artifacts.append({
                    "chat": title, "message": n, "role": role,
                    "lang": block["lang"], "path": str(art_path.relative_to(OUT_ROOT)),
                    "lines": block["code"].count("\n") + 1, "bytes": len(block["code"].encode()),
                })
        elif role == "user":
            out.append("_Empty user message._\n")
        else:
            out.append("_No answer text (see trace appendix)._\n")

        reasoning = msg.get("reasoning_content")
        if isinstance(reasoning, str) and reasoning.strip():
            trace.append(f"\n<a id=\"trace-{n}-reasoning\"></a>\n### Message {n} ({role}) — reasoning_content\n")
            trace.append(safe_fence(reasoning.strip(), "text") + "\n")

        for entry in phases:
            phase = entry.get("phase")
            if phase == "answer":
                continue
            text = entry.get("content") or ""
            extra = entry.get("extra") or {}
            usage = entry.get("usage") or {}
            trace.append(f"\n<a id=\"trace-{n}-{phase}\"></a>\n### Message {n} ({role}) — phase `{phase}`")
            bits = []
            if entry.get("status"):
                bits.append(f"status={entry['status']}")
            if usage.get("output_tokens") is not None:
                bits.append(f"output_tokens={usage['output_tokens']}")
            if bits:
                trace.append("_" + " · ".join(bits) + "_\n")
            wrote = False
            summary = extra.get("summary_title") or {}
            if summary.get("content"):
                trace.append("**Summary title:** " + " ".join(summary["content"]) + "\n")
                wrote = True
            thought = extra.get("summary_thought") or {}
            if thought.get("content"):
                trace.append("**Thinking summary:**\n")
                trace.append(safe_fence("\n".join(thought["content"]), "text") + "\n")
                wrote = True
            observation = (extra.get("tool_result") or {}).get("tool_observation")
            if isinstance(observation, dict):
                observation = json.dumps(observation, indent=2, ensure_ascii=False)
            if observation and str(observation).strip():
                trace.append("**Tool observation:**\n")
                trace.append(safe_fence(str(observation).strip(), "text") + "\n")
                wrote = True
            if text.strip():
                trace.append(safe_fence(text.strip(), "text") + "\n")
                wrote = True
            if not wrote:
                trace.append("_(no payload)_\n")

    final = "\n".join(out[:9]) + "\n" + "\n".join(toc) + "\n" + "\n".join(out[9:])
    final += "\n" + "\n".join(trace)
    md_path.write_text(final, encoding="utf-8")
    return md_path, artifacts


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    for arg in argv:
        src = Path(arg)
        raw = json.loads(src.read_text(encoding="utf-8"))
        data = raw[0] if isinstance(raw, list) else raw
        md_path, artifacts = render(data, src)
        manifest.append({
            "title": data.get("title"),
            "chat_id": data.get("id"),
            "share_id": data.get("share_id"),
            "messages": len(ordered_messages(data["chat"]["history"])),
            "markdown": md_path.name,
            "markdown_bytes": md_path.stat().st_size,
            "artifacts": len(artifacts),
            "artifact_detail": artifacts,
        })
        print(f"[ok] {md_path}  ({md_path.stat().st_size:,} bytes, {len(artifacts)} code artifacts)")
    lines = ["# Qwen chat extraction manifest\n"]
    for item in manifest:
        lines.append(f"\n## {item['title']}\n")
        lines.append(f"- chat id: `{item['chat_id']}`")
        lines.append(f"- share id: `{item['share_id']}`")
        lines.append(f"- messages: {item['messages']}")
        lines.append(f"- markdown: `{item['markdown']}` ({item['markdown_bytes']:,} bytes)")
        lines.append(f"- code artifacts: {item['artifacts']}")
        for art in item["artifact_detail"]:
            lines.append(f"  - `{art['path']}` — msg {art['message']} ({art['role']}), {art['lines']} lines")
    (OUT_ROOT / "MANIFEST.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (OUT_ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"[ok] {OUT_ROOT / 'MANIFEST.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))