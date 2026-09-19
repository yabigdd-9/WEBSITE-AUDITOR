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
