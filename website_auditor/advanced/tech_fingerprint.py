"""Legacy page-builder/cache/CDN view over canonical passive evidence."""


def fingerprint(headers, html_source):
    from auditor_toolkit.technology.observations import observe_technologies

    found = {"page_builder": [], "caching": [], "cdn": []}
    for row in observe_technologies(html_source or "", headers or {}):
        if row["category"] not in found:
            continue
        name = "AWS CloudFront" if row["name"] == "CloudFront" else row["name"]
        if name not in found[row["category"]]:
            found[row["category"]].append(name)
    return found
