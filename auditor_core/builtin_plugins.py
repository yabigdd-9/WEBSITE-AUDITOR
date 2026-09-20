"""Built-in passive plugins registered with the executable check registry."""
from __future__ import annotations

import urllib.parse

from .check_plugins import AuditCheckContext, register_plugin
from .passive import accessibility_basics, cookie_security, nz_business_signals, passive_stack_and_images


@register_plugin(
    "accessibility.basics",
    description="Passive HTML language, form-label and button-name checks.",
)
def accessibility_plugin(context: AuditCheckContext):
    return accessibility_basics(context.soup)


@register_plugin(
    "security.cookies",
    description="Conservative Secure/SameSite checks for observed cookies.",
)
def cookie_plugin(context: AuditCheckContext):
    return cookie_security(
        context.headers,
        is_https=urllib.parse.urlsplit(context.final_url).scheme == "https",
    )


@register_plugin(
    "technology.stack_images",
    description="Technology/CMS fingerprints and image optimization evidence.",
)
def technology_plugin(context: AuditCheckContext):
    return [], passive_stack_and_images(context.html, context.headers)


@register_plugin(
    "nz.business_signals",
    description="Passive NZ phone, postcode/address and .nz signals.",
)
def nz_signals_plugin(context: AuditCheckContext):
    return [], nz_business_signals(context.body_text, context.html)
