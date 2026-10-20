"""Static choice/decline-copy evidence shared by canonical and plugin APIs."""

from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from typing import Any

from bs4 import BeautifulSoup, Comment, Doctype, Tag

from .checks import Finding, dedupe_findings

METHOD = "static-ux-choice-evidence-v2"
MAX_HTML_CHARACTERS = 8 * 1024 * 1024
MAX_CONTROLS = 5000
LABELABLE = {"input", "button", "select", "textarea", "meter", "output", "progress"}
SHAMING_PHRASES = ("no thanks, i", "no, i prefer", "i will pay full price", "i hate saving")
MARKETING = re.compile(r"\b(marketing|newsletter|promotional|promotions)\b")
SUBSCRIBE = re.compile(
    r"\bsubscribe\b.*\b(email|news|updates|offers)\b|\b(email|news|updates|offers)\b.*\bsubscribe\b"
)
NEGATIVE = re.compile(
    r"\b(no|not|never|unsubscribe|decline|optout)\b|\bdon't\b|\bdo not\b|\bopt out\b"
)
AFFIRMATIVE = re.compile(r"\b(yes|agree|receive|subscribe)\b|\bsend me\b")


def _attr(tag: Tag, name: str) -> str:
    value = tag.get(name)
    return value if isinstance(value, str) else ""


def _words(value: str) -> str:
    value = re.sub(r"([a-z])([A-Z])", r"\1 \2", value)
    return " ".join(value.replace("_", " ").replace("-", " ").replace("’", "'").lower().split())


def _text(tag: Tag, *, allow_hidden: bool = False) -> str:
    parts = []
    for value in tag.find_all(string=True):
        if isinstance(value, (Comment, Doctype)):
            continue
        if value.find_parent(["script", "style", "template", "noscript"]):
            continue
        if not allow_hidden and value.find_parent(attrs={"hidden": True}):
            continue
        parts.append(str(value))
    return " ".join(" ".join(parts).split())


def _context(value: str) -> dict[str, str | bool]:
    return {
        "text": value[:256],
        "truncated": len(value) > 256,
        "sha256": hashlib.sha256(value.encode()).hexdigest(),
    }


def _inactive(tag: Tag) -> str:
    if tag.find_parent(["template", "noscript", "script", "style"]):
        return "INACTIVE_MARKUP_CONTEXT"
    if tag.has_attr("disabled"):
        return "DISABLED_ATTRIBUTE"
    if tag.has_attr("hidden") or tag.find_parent(attrs={"hidden": True}):
        return "HIDDEN_ATTRIBUTE_CONTEXT"
    if tag.find_parent("fieldset", attrs={"disabled": True}):
        # First-legend exceptions and browser state are not inferred here.
        return "DISABLED_FIELDSET_CONTEXT_UNRESOLVED"
    return ""


def inspect_soup(
    soup: BeautifulSoup, url: str, source_hash: str = ""
) -> tuple[list[Finding], dict[str, Any]]:
    """Inspect a static parse; labels, checkedness and visibility need browser confirmation."""
    ids: dict[str, list[Tag]] = defaultdict(list)
    labels: dict[str, list[Tag]] = defaultdict(list)
    ordinals = {}
    tag_counts: Counter[str] = Counter()
    for tag in soup.find_all(True):
        tag_counts[tag.name] += 1
        ordinals[id(tag)] = tag_counts[tag.name]
        identifier = _attr(tag, "id")
        if identifier:
            ids[identifier].append(tag)
        if tag.name == "label" and _attr(tag, "for"):
            labels[_attr(tag, "for")].append(tag)
    inputs = soup.find_all("input")
    controls = soup.find_all(["button", "a", "input"])
    roles = [
        tag
        for tag in soup.find_all(attrs={"role": "button"})
        if tag.name not in {"button", "a", "input"}
    ]
    if len(controls) + len(roles) > MAX_CONTROLS:
        raise ValueError("UX control limit exceeded; required coverage is incomplete")
    findings: list[Finding] = []
    choices = []
    declines = []
    counts: Counter[str] = Counter()
    for index, element in enumerate(inputs, 1):
        kind = _attr(element, "type").lower()
        if kind not in {"checkbox", "radio"}:
            continue
        selector = f"xpath=(//input)[{index}]"
        contexts = []
        ambiguous = False
        identifier = _attr(element, "id")
        if identifier and labels.get(identifier):
            if len(ids[identifier]) != 1 or ids[identifier][0] is not element:
                ambiguous = True
            else:
                contexts.extend(("label_for", _text(label)) for label in labels[identifier])
        parent = element.find_parent("label")
        if parent is not None and not parent.has_attr("for"):
            nested = [
                tag
                for tag in parent.find_all(LABELABLE)
                if tag.name != "input" or _attr(tag, "type").lower() != "hidden"
            ]
            if len(nested) == 1 and nested[0] is element:
                contexts.append(("nested_label", _text(parent)))
            else:
                ambiguous = True
        if _attr(element, "aria-label"):
            contexts.append(("aria_label_hint", _attr(element, "aria-label")))
        for reference in _attr(element, "aria-labelledby").split():
            if len(ids.get(reference, [])) != 1:
                ambiguous = True
            else:
                contexts.append(
                    ("aria_labelledby_hint", _text(ids[reference][0], allow_hidden=True))
                )
        fieldset = element.find_parent("fieldset")
        legend = fieldset.find("legend", recursive=False) if fieldset is not None else None
        group_text = _text(legend) if legend is not None else ""
        names = " ".join((_attr(element, "name"), identifier))
        option_text = " ".join(text for _, text in contexts)
        cue = _words(" ".join((names, option_text, group_text)))
        polarity_text = _words(" ".join((names, option_text)))
        value = _words(_attr(element, "value"))
        marketing = bool(MARKETING.search(cue) or SUBSCRIBE.search(cue))
        negative = bool(
            NEGATIVE.search(polarity_text)
            or value in {"no", "false", "0", "off", "decline", "unsubscribe"}
        )
        affirmative = value in {"yes", "true", "1", "on"} or bool(
            AFFIRMATIVE.search(_words(option_text))
        )
        status = _inactive(element)
        if not status:
            if not element.has_attr("checked"):
                status = "UNCHECKED_MARKUP"
            elif ambiguous:
                status = "LABEL_BINDING_UNRESOLVED"
            elif not marketing:
                status = "NO_MARKETING_CUE"
            elif negative:
                status = "DECLINE_OR_OPTOUT_HINT"
            elif kind == "radio" and not affirmative:
                status = "RADIO_OPTION_POLARITY_UNRESOLVED"
            else:
                status = "CHECKED_MARKETING_MARKUP_REVIEW"
        counts[status] += 1
        choices.append(
            {
                "selector": selector,
                "type": kind,
                "status": status,
                "checked_attribute_present": element.has_attr("checked"),
                "name_id_context": _context(names),
                "label_context": [
                    {"source": source, **_context(text)} for source, text in contexts
                ],
                "fieldset_legend_context": _context(group_text),
                "marketing_cue": marketing,
                "negative_choice_hint": negative,
                "affirmative_option_hint": affirmative,
                "rendered_checkedness": None,
                "actual_consent_behaviour": None,
            }
        )
        if status == "CHECKED_MARKETING_MARKUP_REVIEW":
            findings.append(
                Finding(
                    "consent_prechecked",
                    "Checked marketing-choice markup",
                    "Review default selection and actual choice wording",
                    "medium",
                    url,
                    check="ux",
                    selector=selector,
                    confidence="heuristic",
                    evidence_source="static-dom:" + selector,
                    observed="checked attribute present on a checkbox/radio with a marketing cue; no decline hint detected",
                    business_impact="A default marketing choice may differ from user intent; actual consent is unverified.",
                    remediation_action="Review label and actual rendered/server behaviour; leave an affirmative marketing option unselected by default.",
                    remediation_automation="HUMAN_REVIEW",
                    effort_band="XS",
                )
            )
    for element in [*controls, *roles]:
        selector = f"xpath=(//{element.name})[{ordinals[id(element)]}]"
        is_input_button = element.name == "input" and _attr(element, "type").lower() in {
            "button",
            "submit",
            "reset",
        }
        if element.name == "input" and not is_input_button:
            continue
        if (
            element.name == "a"
            and not element.has_attr("href")
            and _attr(element, "role") != "button"
        ):
            continue
        if _inactive(element):
            continue
        text = " ".join(
            (
                _text(element),
                _attr(element, "aria-label"),
                _attr(element, "value") if is_input_button else "",
            )
        )
        normalized = _words(text)
        phrase = next((phrase for phrase in SHAMING_PHRASES if phrase in normalized), None)
        if phrase is None:
            continue
        declines.append(
            {
                "selector": selector,
                "matched_phrase": phrase,
                "copy": _context(text),
                "interpretation": "heuristic_editorial_review",
                "rendered_visibility": None,
            }
        )
        findings.append(
            Finding(
                "confirmshaming_review",
                "Possible shaming decline copy",
                "Review the control's wording and surrounding interaction",
                "low",
                url,
                check="ux",
                selector=selector,
                confidence="heuristic",
                evidence_source="static-dom:" + selector,
                observed="control copy contains legacy review phrase: " + phrase,
                business_impact="Decline wording may pressure a user; intent and rendered context remain unverified.",
                remediation_action="Review the actual decline flow and use a neutral refusal label where appropriate.",
                remediation_automation="HUMAN_REVIEW",
                effort_band="XS",
            )
        )
    return dedupe_findings(findings), {
        "method": METHOD,
        "html_sha256": source_hash,
        "scope": "static_checkbox_radio_and_decline_control_markup",
        "choices": choices,
        "choice_status_counts": dict(sorted(counts.items())),
        "decline_copy_reviews": declines,
        "legal_compliance_assessed": False,
        "consent_behaviour_verified": False,
        "selector_scope": "static_parse_requires_browser_confirmation",
        "limitations": [
            "No browser interaction, CSS visibility, script state or server-side consent inspection.",
            "Common label/ARIA bindings are hints, not a full accessible-name computation.",
            "Decline phrases are editorial heuristics; neutral choices and false positives require review.",
            "Ambiguous labels, negative options, disabled/hidden/inactive contexts are held without consent findings.",
        ],
    }


def analyse_html(html: str, url: str, headers=None) -> tuple[list[Finding], dict[str, Any]]:
    if not isinstance(html, str) or len(html) > MAX_HTML_CHARACTERS:
        raise ValueError("UX analysis requires HTML within the declared character limit")
    return inspect_soup(BeautifulSoup(html, "lxml"), url, hashlib.sha256(html.encode()).hexdigest())
