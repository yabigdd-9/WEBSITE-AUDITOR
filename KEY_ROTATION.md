# Key Rotation Tracker

## Status
- [x] PAGESPEED_API_KEY: old key (terminated interaction with API Explorer,
unusable for production audits — requires rotation before high-volume use)
- [ ] PAGESPEED_API_KEY: NEW key stored securely (rotate in Cloud Console)
- [ ] RANKNIBBLER_API_KEY: old key (exposed in conversation, needs rotation)
- [ ] RANKNIBBLER_API_KEY: NEW key stored securely (rotate at ranknibbler.com/dashboard)

## Rotation Checklist
1. [ ] Rotate PageSpeed API key (restrict to PageSpeed Insights API only)
2. [ ] Rotate RankNibbler API key (regenerate at dashboard)
3. [ ] Update ~/.zshrc with new values (never commit .zshrc)
4. [ ] Verify: python3 -c "import os; print('pagespeed:', bool(os.environ.get('PAGESPEED_API_KEY'))); print('ranknibbler:', bool(os.environ.get('RANKNIBBLER_API_KEY')))"
5. [ ] Run full enriched audit to confirm: python website_auditor.py https://example.com --enrich --format json
