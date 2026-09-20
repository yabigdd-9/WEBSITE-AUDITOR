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

# Fix 2: Create project structure
echo ""
echo "📁 Creating project structure..."
mkdir -p website_auditor/actions website_auditor/connectors website_auditor/ai \
         website_auditor/portal website_auditor/outreach website_auditor/monitoring \
         config outputs/actions outputs/patches outputs/snapshots outputs/outreach \
         outputs/remediations outputs/reports

touch website_auditor/__init__.py website_auditor/actions/__init__.py \
      website_auditor/connectors/__init__.py website_auditor/ai/__init__.py \
      website_auditor/portal/__init__.py website_auditor/outreach/__init__.py \
      website_auditor/monitoring/__init__.py

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

# Fix 5: Check if Ollama is available
echo ""
echo "🧠 Checking AI (Ollama)..."
if command -v ollama &>/dev/null; then
    echo "   ✅ Ollama installed"
    if curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
        echo "   ✅ Ollama server running"
    else
        echo "   ⚠️  Ollama not running (start with: ollama serve &)"
    fi
else
    echo "   ℹ️  Ollama not installed — AI will use template fallback (still works!)"
fi

# Fix 6: Check Git
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
echo "║   Portal: python3 -m website_auditor.portal.server ║"
echo "║   CLI:  python3 wa.py status            ║"
echo "╚══════════════════════════════════════════╝"
