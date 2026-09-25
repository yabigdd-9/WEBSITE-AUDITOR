#!/bin/bash
set -e
echo "╔══════════════════════════════════════════╗"
echo "║   WEBSITE-AUDITOR — Full Setup          ║"
echo "╚══════════════════════════════════════════╝"

# Fix 1: SSL certificates (macOS Homebrew Python issue)
echo ""
echo "🔧 Fixing SSL certificates..."
export SSL_CERT_FILE="/etc/ssl/cert.pem"
export REQUESTS_CA_BUNDLE="/etc/ssl/cert.pem"

# Write to shell profile so it persists
if ! grep -q "SSL_CERT_FILE" ~/.zshrc 2>/dev/null; then
    echo 'export SSL_CERT_FILE="/etc/ssl/cert.pem"' >> ~/.zshrc
    echo 'export REQUESTS_CA_BUNDLE="/etc/ssl/cert.pem"' >> ~/.zshrc
    echo "   ✅ Added SSL fix to ~/.zshrc (permanent)"
else
    echo "   ✅ SSL fix already in ~/.zshrc"
fi

# Fix 2: Create project structure (Legacy directories preserved for backward compatibility if required, but new work belongs in auditor_toolkit/)
echo ""
echo "📁 Creating project structure..."
mkdir -p auditor_toolkit/actions auditor_toolkit/connectors auditor_toolkit/ai \
         auditor_toolkit/portal auditor_toolkit/outreach auditor_toolkit/monitoring \
         config outputs/actions outputs/patches outputs/snapshots outputs/outreach \
         outputs/remediations outputs/reports

touch auditor_toolkit/__init__.py auditor_toolkit/actions/__init__.py \
      auditor_toolkit/connectors/__init__.py auditor_toolkit/ai/__init__.py \
      auditor_toolkit/portal/__init__.py auditor_toolkit/outreach/__init__.py \
      auditor_toolkit/monitoring/__init__.py

echo "   ✅ All folders and modules created"

# Fix 3: Create default policy config
echo ""
echo "⚙️  Creating policy config..."
cat > config/actions.json << 'POLICY'
{
  "enabled": true,
  "mode": "dry_run",
  "allow_production_changes": false,
  "allow_external_emails": false,
  "allow_external_connectors": false,
  "auto_approve_risks": ["low"],
  "require_approval_risks": ["medium", "high", "critical"],
  "environments_allowed_for_auto": ["local", "staging"],
  "blocked_categories": ["dns_write", "tls_install", "production_deploy", "outreach_send"]
}
POLICY
echo "   ✅ Policy config created (safe dry_run mode)"

# Fix 4: Check Python dependencies
echo ""
echo "🐍 Checking Python dependencies..."
python3 -c "import httpx" 2>/dev/null && echo "   ✅ httpx OK" || echo "   ⚠️  httpx missing (run: pip3 install httpx --break-system-packages)"
python3 -c "import certifi" 2>/dev/null && echo "   ✅ certifi OK" || echo "   ⚠️  certifi missing"

# Fix 5: Check Git
echo ""
echo "🔀 Checking Git..."
if command -v git &>/dev/null; then
    echo "   ✅ Git available"
    if git rev-parse --is-inside-work-tree &>/dev/null; then
        echo "   ✅ Inside Git repo"
    else
        echo "   ℹ️  Not a Git repo (run: git init)"
    fi
else
    echo "   ⚠️  Git not found"
fi

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   ✅ SETUP COMPLETE                     ║"
echo "╠══════════════════════════════════════════╣"
echo "║   Run:  python3 run_all.py <url>        ║"
echo "║   Portal: python3 -m auditor_toolkit.portal.server ║"
echo "║   CLI:  python3 wa.py status            ║"
echo "╚══════════════════════════════════════════╝"
