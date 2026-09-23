# False-Positive Catalogue

This document catalogues common reasons deterministic website checks produce misleading findings.

## Technology
- filename contains jquery but file is not jQuery
- generator metadata stale
- framework detection via common JS libraries that are actually used for other purposes
- technology detected via CSS framework but site uses custom CSS that resembles framework

## Performance
- large hero image intentionally high resolution (for visual impact)
- CRUX unavailable due to low traffic
- server-side optimizations not captured by client-side metrics
- render-blocking resources that are intentional for above-the-fold content

## SEO
- intentional noindex (e.g., thank-you pages, login pages)
- canonical intentionally points to master page (for syndicated content)
- structured data present but hidden from users (JSON-LD in footer)
- duplicate content due to printer-friendly versions or AMP pages

## Local
- service-area business has no public street address (by design)
- business uses virtual office or co-working space address
- multiple businesses share same address (e.g., shopping mall, office building)
- business has moved but old citations remain

## Accessibility
- automated tool incomplete result (e.g., cannot detect ARIA dynamic updates)
- false positives due to iframe content
- color contrast issues due to background images or text over images
- keyboard navigation issues in custom widgets

## Privacy
- cookie exists but purpose unknown (may be essential for functionality)
- tracker detected but consent mechanism not triggered (pre-consent)
- third-party resource loaded but not actually tracking (e.g., hosted library)
- fingerprinting suspicion based on canvas usage (may be for drawing or charts)

## Vulnerability
- technology detected but version unknown (cannot confirm vulnerability)
- version inferred from comments or metadata (may be outdated)
- known vulnerable library present but not actually loaded or used
- vulnerability patched via backport but version number not updated
- false positive from security header that is present but misconfigured