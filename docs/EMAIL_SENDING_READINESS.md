# Email preparation and exact-message review

The local CATALYX Gmail bridge supports credential and connection checks using
macOS Keychain. A successful SMTP login proves authentication only; it does not
prove delivery or authorize sending. IMAP checks select the inbox read-only.

Use the bridge's existing Keychain-enabled environment:

```sh
.venv/bin/python integrations/catalyx_gmail_bridge.py check --account team.catalyxlabs@gmail.com
```

Never copy credentials into source, reports or command arguments. The bridge
configuration must retain its external-send-disabled setting.

To inspect an existing draft without writing to the database or contacting a
provider, run from the selected runtime repository:

```sh
PYTHONPATH=money-machine .venv-email/bin/python money-machine/mm_operator.py email-send-preflight MESSAGE_ID
```

This checks the exact recipient/body hash, the latest approval record, current
verified recipient selection, suppression and existing approval gates. A later
rejection, edited body, changed recipient, invalidated draft or sent message is a
hold. Missing schema or policy information fails closed. The command does not
approve a draft, create a delivery intent, migrate schema, or send a message.

`message_ready_for_transport_review` means the draft passed these checks.
`ready_to_send` remains false: the current MoneyMachine transport is review-only
with provider `none` and a zero send cap. Actual sending requires a separately
reviewed transport and explicit approval of the exact recipients and messages.
Do not activate transport by weakening those controls. SMTP authentication does
not establish consent or satisfy message approval.

Operator JSON inputs (transport packets, review bundles, holdout evaluations and
imported browser decisions) must be staged inside the selected runtime root as
`.json` files, at most 8 MiB. Paths resolving outside that root, including symlink
escapes, are rejected before reading. Keep any sensitive staged inputs in an
ignored private state directory; do not commit them.
