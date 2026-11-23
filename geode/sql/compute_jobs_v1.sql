-- Serialize concurrent native CLI startups and Django migrations.
SELECT pg_advisory_xact_lock(hashtext('geode_compute_jobs_v1'));
CREATE TABLE IF NOT EXISTS public.geode_compute_jobs (
    id uuid PRIMARY KEY,
    operation text NOT NULL,
    fingerprint text NOT NULL CHECK (length(fingerprint) = 64),
    label text,
    state text NOT NULL DEFAULT 'queued'
        CHECK (state IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
    submitted_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    finished_at timestamptz,
    detail text
);

-- An old queued worker cannot publish into a newer run of the same project/day.
CREATE TABLE IF NOT EXISTS public.geode_gamit_runs (
    project text NOT NULL,
    year integer NOT NULL,
    doy integer NOT NULL CHECK (doy BETWEEN 1 AND 366),
    run_id uuid NOT NULL,
    PRIMARY KEY (project, year, doy)
);
