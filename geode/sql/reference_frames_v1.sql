-- Additive frame provenance, shared by processing startup and Django 0038.
-- Scientific rows and their SQL primary keys/API IDs are preserved.
SELECT pg_advisory_xact_lock(73501927);
ALTER TABLE public.stacks ADD COLUMN IF NOT EXISTS engine VARCHAR(10) NOT NULL DEFAULT 'gamit';
ALTER TABLE public.stacks ADD COLUMN IF NOT EXISTS ppp_reference_frame VARCHAR(20);
ALTER TABLE public.stacks ALTER COLUMN "Project" DROP NOT NULL;
ALTER TABLE public.stations ADD COLUMN IF NOT EXISTS plate VARCHAR(2);

CREATE TABLE IF NOT EXISTS public.gamit_projects (
    project VARCHAR(20) PRIMARY KEY,
    api_id SERIAL NOT NULL UNIQUE
);
COMMENT ON TABLE public.gamit_projects IS
    'GAMIT project identifiers only; historical processing settings are not inferred.';
INSERT INTO public.gamit_projects(project)
    SELECT "Project" FROM public.gamit_soln
    UNION SELECT "Project" FROM public.gamit_soln_excl
    UNION SELECT "Project" FROM public.gamit_subnets
    UNION SELECT "Project" FROM public.gamit_stats
    ON CONFLICT (project) DO NOTHING;

CREATE TABLE IF NOT EXISTS public.reference_frames (
    frame_name VARCHAR(20) PRIMARY KEY,
    engine VARCHAR(10) NOT NULL CHECK (engine IN ('gamit', 'ppp')),
    project VARCHAR(20) NOT NULL,
    source_projects JSONB NOT NULL DEFAULT '{}',
    source_stack VARCHAR(20),
    fixed_plate VARCHAR(2),
    euler_pole DOUBLE PRECISION[],
    euler_pole_stations VARCHAR(8)[],
    translation_rate DOUBLE PRECISION[],
    first_epoch TIMESTAMP WITHOUT TIME ZONE,
    last_epoch TIMESTAMP WITHOUT TIME ZONE,
    created TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    modified TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
    api_id SERIAL NOT NULL UNIQUE,
    CHECK (euler_pole IS NULL OR (array_ndims(euler_pole) = 1 AND cardinality(euler_pole) = 3)),
    CHECK (translation_rate IS NULL OR (array_ndims(translation_rate) = 1 AND cardinality(translation_rate) = 3)),
    CHECK (first_epoch IS NULL OR last_epoch IS NULL OR first_epoch <= last_epoch)
);
COMMENT ON COLUMN public.reference_frames.euler_pole IS 'ECEF rotation vector [X,Y,Z], mas/yr.';
COMMENT ON COLUMN public.reference_frames.translation_rate IS 'Fitted VREF translation parameters [X,Y,Z], m/yr, in the existing FixPlate design convention.';
COMMENT ON COLUMN public.reference_frames.source_projects IS 'Counts of stored station-days per source project; project is the largest count, ties resolved lexicographically. PPP uses gpspace.';
COMMENT ON COLUMN public.reference_frames.frame_name IS 'Globally unique physical stacks.name across GAMIT and PPP. Metadata deletion/rename never cascades into scientific rows.';

CREATE TABLE IF NOT EXISTS public.reference_frame_constraints (
    constraints_id VARCHAR(20) NOT NULL REFERENCES public.reference_frames(frame_name) ON DELETE RESTRICT ON UPDATE RESTRICT,
    network_code VARCHAR(3) NOT NULL,
    station_code VARCHAR(4) NOT NULL,
    vx DOUBLE PRECISION NOT NULL,
    vy DOUBLE PRECISION NOT NULL,
    vz DOUBLE PRECISION NOT NULL,
    api_id SERIAL NOT NULL UNIQUE,
    PRIMARY KEY (constraints_id, network_code, station_code),
    FOREIGN KEY (network_code, station_code) REFERENCES public.stations("NetworkCode", "StationCode") ON DELETE RESTRICT ON UPDATE CASCADE
);
COMMENT ON TABLE public.reference_frame_constraints IS 'Frame-owned VREF constraints in ECEF m/yr, converted from the external local up velocity (north=east=0).';

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid = 'public.stacks'::regclass AND conname = 'stacks_engine_project_check') THEN
        ALTER TABLE public.stacks ADD CONSTRAINT stacks_engine_project_check CHECK (
            (engine = 'gamit' AND "Project" IS NOT NULL AND ppp_reference_frame IS NULL) OR
            (engine = 'ppp' AND "Project" IS NULL AND ppp_reference_frame IS NOT NULL));
        ALTER TABLE public.stacks ADD CONSTRAINT stacks_ppp_soln_fkey
            FOREIGN KEY ("NetworkCode", "StationCode", "Year", "DOY", ppp_reference_frame)
            REFERENCES public.ppp_soln("NetworkCode", "StationCode", "Year", "DOY", "ReferenceFrame")
            ON DELETE RESTRICT ON UPDATE CASCADE;
    END IF;
END $$;

-- Serialize owner assignment, including writers which do not create metadata.
CREATE OR REPLACE FUNCTION public.validate_stack_owner() RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(NEW.name, 73501927));
    IF EXISTS (SELECT 1 FROM public.reference_frames WHERE frame_name = NEW.name AND engine <> NEW.engine)
       OR EXISTS (SELECT 1 FROM public.stacks WHERE name = NEW.name AND engine <> NEW.engine) THEN
        RAISE EXCEPTION 'Stack % is owned by another processing engine', NEW.name;
    END IF;
    RETURN NEW;
END $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS stacks_owner_trigger ON public.stacks;
CREATE TRIGGER stacks_owner_trigger BEFORE INSERT OR UPDATE OF name, engine ON public.stacks
    FOR EACH ROW EXECUTE FUNCTION public.validate_stack_owner();

CREATE OR REPLACE FUNCTION public.validate_reference_frame() RETURNS TRIGGER AS $$
DECLARE source_project TEXT;
BEGIN
    IF TG_OP = 'DELETE' THEN
        PERFORM pg_advisory_xact_lock(hashtextextended(OLD.frame_name, 73501927));
        IF EXISTS (SELECT 1 FROM public.stacks WHERE name = OLD.frame_name) THEN
            RAISE EXCEPTION 'Remove stack rows explicitly before deleting frame %', OLD.frame_name;
        END IF;
        RETURN OLD;
    END IF;
    IF TG_OP = 'UPDATE' AND (OLD.frame_name <> NEW.frame_name OR OLD.engine <> NEW.engine) THEN
        RAISE EXCEPTION 'Frame identity is immutable; rebuild with a new stack name';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended(NEW.frame_name, 73501927));
    IF EXISTS (SELECT 1 FROM public.stacks WHERE name = NEW.frame_name AND engine <> NEW.engine) THEN
        RAISE EXCEPTION 'Stack % is owned by another processing engine', NEW.frame_name;
    END IF;
    IF NEW.engine = 'gamit' THEN
        FOR source_project IN SELECT NEW.project UNION SELECT jsonb_object_keys(NEW.source_projects) ORDER BY 1 LOOP
            PERFORM 1 FROM public.gamit_projects WHERE project = source_project FOR KEY SHARE;
            IF NOT FOUND THEN RAISE EXCEPTION 'Unknown GAMIT project %', source_project; END IF;
        END LOOP;
    END IF;
    NEW.modified = now();
    RETURN NEW;
END $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS reference_frames_validate_trigger ON public.reference_frames;
CREATE TRIGGER reference_frames_validate_trigger BEFORE INSERT OR UPDATE OR DELETE ON public.reference_frames
    FOR EACH ROW EXECUTE FUNCTION public.validate_reference_frame();

CREATE OR REPLACE FUNCTION public.protect_frame_projects() RETURNS TRIGGER AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.reference_frames WHERE engine = 'gamit'
               AND (project = OLD.project OR source_projects ? OLD.project)) THEN
        RAISE EXCEPTION 'Project % is referenced by a saved frame', OLD.project;
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS gamit_projects_protect_trigger ON public.gamit_projects;
CREATE TRIGGER gamit_projects_protect_trigger BEFORE DELETE OR UPDATE OF project ON public.gamit_projects
    FOR EACH ROW EXECUTE FUNCTION public.protect_frame_projects();
