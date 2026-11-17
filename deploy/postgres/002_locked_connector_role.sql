-- Reproducible record of the connector-role migration applied to
-- Supabase project srymerkhraklwuttzexi on 18 November 2026.
-- Safe to review, but do not rerun migrations without owner approval.
-- NO password, LOGIN permission, secret, or connection settings are included.
BEGIN;
DO $locked_connector$
DECLARE
  is_login boolean;
  is_super boolean;
  can_create_db boolean;
  can_create_role boolean;
  can_replicate boolean;
  can_bypass_rls boolean;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='mm_pipeline_connector') THEN
    CREATE ROLE mm_pipeline_connector
      NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
      NOREPLICATION NOBYPASSRLS INHERIT;
  END IF;
  SELECT rolcanlogin,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls
    INTO is_login,is_super,can_create_db,can_create_role,can_replicate,can_bypass_rls
    FROM pg_roles WHERE rolname='mm_pipeline_connector';
  IF is_login OR is_super OR can_create_db OR can_create_role OR can_replicate OR can_bypass_rls THEN
    RAISE EXCEPTION 'Unexpected connector account privileges; manual review needed';
  END IF;
END
$locked_connector$;
GRANT mm_checkpoint_writer TO mm_pipeline_connector;
COMMIT;
