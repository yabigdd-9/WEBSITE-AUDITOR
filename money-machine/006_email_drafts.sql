CREATE TABLE IF NOT EXISTS mm_email_drafts(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id INTEGER NOT NULL REFERENCES mm_messages(id),
  business_id INTEGER NOT NULL REFERENCES businesses(id),
  recipient TEXT NOT NULL,
  draft_body TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('DRAFT_READY', 'APPROVED', 'INVALIDATED')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS mm_email_drafts_message ON mm_email_drafts(message_id);
