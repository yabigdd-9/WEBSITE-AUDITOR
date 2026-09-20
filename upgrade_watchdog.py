"""Watchdog upgrade: portfolio-level monitoring."""
CONFIG = """
# monitoring.yaml (create this file)
watchdog:
  schedule: "0 7 * * *"  # Daily at 7 AM NZST
  timezone: Pacific/Auckland
  alert_channels:
    - type: slack
      webhook: ${ALERT_WEBHOOK_URL}
    - type: email
      to: you@agency.co.nz
  thresholds:
    critical_regression: 1  # Alert immediately
    score_drop: 10          # Alert if score drops 10+ points
    ssl_expiry_days: 14     # Alert 14 days before SSL expires
  portfolio:
    - domain: clyne-bennie.co.nz
    - domain: prodecorators.co.nz
    - domain: jcconstruction.co.nz
"""
print(CONFIG)
