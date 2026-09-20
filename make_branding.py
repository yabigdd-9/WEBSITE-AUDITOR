import pathlib

pathlib.Path("config").mkdir(parents=True, exist_ok=True)

branding = """agency:
  name: "Your Agency Name"
  tagline: "Evidence-First Website Optimization"
  logo_url: ""  # Optional: path to logo file
  primary_color: "#06b6d4"
  secondary_color: "#0f172a"
  accent_color: "#10b981"

contact:
  email: "hello@youragency.co.nz"
  phone: "+64 21 123 4567"
  website: "youragency.co.nz"
  address: "Auckland, New Zealand"

reporting:
  auto_email: false          # Set true when SMTP configured
  smtp_host: "smtp.gmail.com"
  smtp_port: 587
  smtp_user: ""              # Your email
  smtp_password: ""          # App password (not your real password)
  send_day: 1                # Day of month to send (1 = first)

clients:
  # Add your clients here. Revenue assumptions override defaults.
  - domain: "clyne-bennie.co.nz"
    client_name: "Clyne Bennie"
    client_email: "client@example.co.nz"
    monthly_visitors: 1500
    avg_lead_value: 180
  - domain: "prodecorators.co.nz"
    client_name: "Pro Decorators"
    client_email: "client@example.co.nz"
    monthly_visitors: 2500
    avg_lead_value: 250
  - domain: "jcconstruction.co.nz"
    client_name: "JC Construction"
    client_email: "client@example.co.nz"
    monthly_visitors: 1800
    avg_lead_value: 350
"""
pathlib.Path("config/branding.yaml").write_text(branding)
print("✅ config/branding.yaml created")
