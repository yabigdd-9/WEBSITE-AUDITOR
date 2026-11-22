# Outreach mockups

Include one tailored mockup for each distinct function pitched in an outreach email. For multiple functions, include a separate mockup for each and label them clearly in the email. Verify the recipient can open every attachment or link before sending. Label illustrative prices and keep demo submissions local unless a live integration has been explicitly requested.

## What to offer and reference

- Review the prospect's website and audit evidence for all relevant fixes and new functions. Offer the full set that applies to the business, leading with the highest-impact items. Group related offers so the email remains easy to scan.
- For each offer, include a short reference to the relevant public page or shareable audit evidence. Explain what was observed and what the proposed change would do. Label new ideas as proposals and avoid unsupported claims about defects, costs, or results.
- Pair each distinct fix or function pitched with its own clearly labelled mockup. Check that references and mockups are accessible to the recipient before sending.

## Sending and reply handling

- Run `./mm scout-preflight` for the exact recipient, draft, references, and mockups. Check the sending account's Sent folder for prior contact and open each attachment or link before sending.
- After Gmail confirms the send, run `./mm scout-record-send --id ID --recipient EMAIL --gmail-id MESSAGE_ID` using the returned Gmail message ID.
- When a recipient asks to stop receiving outreach, run `./mm scout-record-optout --recipient EMAIL` before preparing any follow-up. Check replies in the sending account before any follow-up.
