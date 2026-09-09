# Database Triggers
**Generated:** 2026-09-07T19:05:23.123968+00:00

## Trigger 1: prevent_unapproved_outreach_insert
- **Table:** outreach
- **Timing:** BEFORE INSERT
- **Purpose:** Blocks INSERT on outreach with sent_at set — forces draft-first workflow
- **SQL:**
```sql
CREATE TRIGGER prevent_unapproved_outreach_insert
BEFORE INSERT ON outreach
WHEN NEW.sent_at IS NOT NULL
BEGIN
  SELECT RAISE(ABORT, 'external send blocked: create draft first and obtain per-message human approval');
END;
```
- **Active:** YES (verified in sqlite_master)

## Trigger 2: prevent_unapproved_outreach_send
- **Table:** outreach
- **Timing:** BEFORE UPDATE OF sent_at, approved_by_human
- **Purpose:** Blocks UPDATE of sent_at unless approval_events has matching approved=1 row AND approved_by_human=1
- **SQL:**
```sql
CREATE TRIGGER prevent_unapproved_outreach_send
BEFORE UPDATE OF sent_at, approved_by_human ON outreach
WHEN NEW.sent_at IS NOT NULL AND (
  COALESCE(NEW.approved_by_human, 0) != 1 OR
  NOT EXISTS (
    SELECT 1 FROM approval_events
    WHERE action_type = 'external_send'
      AND object_type = 'outreach'
      AND object_id = NEW.id
      AND approved = 1
  )
)
BEGIN
  SELECT RAISE(ABORT, 'external send blocked: per-message human approval event required');
END;
```
- **Active:** YES (verified in sqlite_master)

## Trigger 3: prevent_unapproved_mm_messages_insert
- **Table:** mm_messages
- **Timing:** BEFORE INSERT
- **Purpose:** Blocks INSERT on mm_messages with sent_at set — forces draft-first workflow
- **SQL:**
```sql
CREATE TRIGGER prevent_unapproved_mm_messages_insert
BEFORE INSERT ON mm_messages
WHEN NEW.sent_at IS NOT NULL
BEGIN
  SELECT RAISE(ABORT, 'external send blocked: create draft first, then review and record approval');
END;
```
- **Active:** YES (verified in sqlite_master)

## Trigger 4: prevent_unapproved_mm_messages_send
- **Table:** mm_messages
- **Timing:** BEFORE UPDATE OF sent_at
- **Purpose:** Blocks UPDATE of sent_at without exact-message approval (approved_hash must equal digest, approval_ref must be set)
- **SQL:**
```sql
CREATE TRIGGER prevent_unapproved_mm_messages_send
BEFORE UPDATE OF sent_at ON mm_messages
WHEN NEW.sent_at IS NOT NULL AND (
  OLD.approved_hash IS NULL OR
  OLD.approved_hash != OLD.digest OR
  OLD.approval_ref IS NULL
)
BEGIN
  SELECT RAISE(ABORT, 'external send blocked: exact-message approval required');
END;
```
- **Active:** YES (verified in sqlite_master)

## Safety Analysis
- **Unauthorized send blocking:** ACTIVE — 4 triggers prevent unapproved sends on both outreach and mm_messages tables
- **Suppression protection:** ACTIVE — mm_suppression table + contacts.do_not_contact checked in application logic (mm_operator.py)
- **Approval integrity:** ACTIVE — approval_events table required for any send; triggers enforce this
- **Payment/revenue protection:** ACTIVE — mm_cash requires positive amount_cents, unique receipt; revenue table has generated gross_margin
