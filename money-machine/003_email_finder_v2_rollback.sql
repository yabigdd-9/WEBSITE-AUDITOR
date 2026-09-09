-- Safe operational rollback keeps every new candidate, evidence item and check.
-- V1 read-only display remains available. Existing approval/suppression gates stay.
BEGIN IMMEDIATE;
UPDATE email_policy SET mode='v1_hold',changed_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=1;
COMMIT;
-- Full schema/data restoration must use an archived, verified SQLite snapshot,
-- with writers stopped and the post-migration DB archived first. See rollback report.
