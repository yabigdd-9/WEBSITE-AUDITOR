cat << 'EOF' > integrations/deepseek-harness/README.md
# DeepSeek Harness Integration (Phase A: Shadow Mode)

This module adds a parallel agentic layer to WEBSITE-AUDITOR without modifying the core Python logic.

## Structure
- `config.yaml`: Global constraints (NZD 0 cost, no auto-send).
- `tools/mm_bridge.py`: Safe Python wrappers around `website_auditor.py` and `remediation-engine.py`.
- `workflows/agents.yml`: Definitions for Auditor, Critic, and Architect agents.
- `policies/permissions.yml`: Strict allow/deny lists for tool access.

## Usage
1. Install DeepSeek Harness locally.
2. Point it to this directory.
3. Load `tools/mm_bridge.py` as the tool provider.
4. Run in **Shadow Mode**: Compare Harness outputs against manual/standard audits.

## Safety
- **No Direct Shell Access**: Agents cannot run arbitrary commands.
- **No Paid APIs**: Restricted to local Ollama/Llama.cpp.
- **Human Gate**: Outreach sending is physically disabled in this layer.
EOF

cat << 'EOF' > integrations/deepseek-harness/SECURITY.md
# Security Policy

## Threat Model
- **Risk**: Agent hallucination leading to incorrect audit data.
  - **Mitigation**: `critic_agent` verifies evidence; `mm_bridge` enforces deterministic source of truth.
- **Risk**: Accidental credential exposure.
  - **Mitigation**: Secrets are never passed into model context. Wrappers handle auth internally if needed (currently none required).
- **Risk**: Unauthorized outbound actions.
  - **Mitigation**: `send_email` and `deploy` tools are marked `FORBIDDEN` in `permissions.yml`.

## Compliance
- Adheres to Core Rule R6: NO PAID INFERENCE.
- Adheres to Core Rule R7: NO AUTO-SEND OUTREACH.
EOF
