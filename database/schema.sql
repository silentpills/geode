-- Compatibility entry point for fresh processing-only SQL installations.
-- Django and CLI startup share the same versioned migrations.
\ir ../geode/sql/bootstrap_v1/schema.sql
BEGIN;
\ir ../geode/sql/reference_frames_v1.sql
COMMIT;
