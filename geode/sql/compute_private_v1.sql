-- The bundled web login receives DML privileges on public tables.
-- Keep the scientific coordinator and its worker as the only writers here.
SELECT pg_advisory_xact_lock(hashtext('geode_compute_jobs_v1'));
CREATE SCHEMA IF NOT EXISTS geode_compute;
REVOKE ALL ON SCHEMA geode_compute FROM PUBLIC;
DO $$
DECLARE
    grant_row record;
BEGIN
    IF to_regclass('public.geode_compute_jobs') IS NOT NULL THEN
        ALTER TABLE public.geode_compute_jobs SET SCHEMA geode_compute;
        ALTER TABLE geode_compute.geode_compute_jobs RENAME TO jobs;
    END IF;
    IF to_regclass('public.geode_gamit_runs') IS NOT NULL THEN
        ALTER TABLE public.geode_gamit_runs SET SCHEMA geode_compute;
        ALTER TABLE geode_compute.geode_gamit_runs RENAME TO gamit_runs;
    END IF;

    FOR grant_row IN
        SELECT DISTINCT c.relname, p.grantee
        FROM pg_class c CROSS JOIN LATERAL aclexplode(c.relacl) p
        WHERE c.relnamespace = 'geode_compute'::regnamespace
          AND c.relname IN ('jobs', 'gamit_runs') AND p.grantee <> c.relowner
    LOOP
        EXECUTE format('REVOKE ALL ON TABLE geode_compute.%I FROM %s',
            grant_row.relname, CASE WHEN grant_row.grantee = 0 THEN 'PUBLIC'
            ELSE quote_ident(pg_get_userbyid(grant_row.grantee)) END);
    END LOOP;
END $$;
