"""Legacy name-list adapter to the canonical passive technology detector."""


def detect_tech_stack(html_content, headers, url=""):
    from auditor_toolkit.tech import detect_technology

    names = {"Vue": "Vue.js"}
    return sorted(
        {
            names.get(row.technology, row.technology)
            for row in detect_technology(html_content, url, headers)
        },
        key=str.casefold,
    )
