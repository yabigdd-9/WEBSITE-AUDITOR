-- Harden receipt format without rewriting the already-applied migration 004.
CREATE TRIGGER email_release_receipt_insert BEFORE INSERT ON email_release_policy
 WHEN NEW.mode='PRODUCTION' AND (NEW.precision_receipt IS NULL
  OR typeof(NEW.precision_receipt)!='text' OR length(NEW.precision_receipt)!=64
  OR NEW.precision_receipt GLOB '*[^0-9a-f]*')
 BEGIN SELECT RAISE(ABORT,'production requires a lowercase SHA-256 precision receipt'); END;
CREATE TRIGGER email_release_receipt_update BEFORE UPDATE ON email_release_policy
 WHEN NEW.mode='PRODUCTION' AND (NEW.precision_receipt IS NULL
  OR typeof(NEW.precision_receipt)!='text' OR length(NEW.precision_receipt)!=64
  OR NEW.precision_receipt GLOB '*[^0-9a-f]*')
 BEGIN SELECT RAISE(ABORT,'production requires a lowercase SHA-256 precision receipt'); END;
