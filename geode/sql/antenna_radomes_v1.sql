-- Immutable migration shared by processing startup and Django 0035.
-- Keep antenna models (and their existing API IDs/height conversions) intact.
LOCK TABLE public.stationinfo IN SHARE ROW EXCLUSIVE MODE;
CREATE TABLE IF NOT EXISTS public.antenna_radomes (
    api_id SERIAL PRIMARY KEY,
    "AntennaCode" VARCHAR(22) NOT NULL,
    "RadomeCode" VARCHAR(7) NOT NULL,
    CONSTRAINT antenna_radomes_pair_key UNIQUE ("AntennaCode", "RadomeCode"),
    CONSTRAINT antenna_radomes_antenna_fk FOREIGN KEY ("AntennaCode")
        REFERENCES public.antennas ("AntennaCode")
        ON UPDATE CASCADE ON DELETE RESTRICT
);
COMMENT ON TABLE public.antenna_radomes IS
    'Registered antenna/radome combinations; registration does not establish calibration availability.';
-- Preserve historical values exactly, including legacy blank/unknown codes.
-- Do not invent NONE combinations for every antenna model.
INSERT INTO public.antenna_radomes ("AntennaCode", "RadomeCode")
    SELECT DISTINCT "AntennaCode", "RadomeCode" FROM public.stationinfo
    ON CONFLICT ("AntennaCode", "RadomeCode") DO NOTHING;
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.stationinfo'::regclass
          AND conname = 'stationinfo_antenna_radome_fk'
    ) THEN
        ALTER TABLE public.stationinfo
            ADD CONSTRAINT stationinfo_antenna_radome_fk
            FOREIGN KEY ("AntennaCode", "RadomeCode")
            REFERENCES public.antenna_radomes ("AntennaCode", "RadomeCode")
            ON UPDATE CASCADE ON DELETE RESTRICT;
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS stationinfo_antenna_radome_index
    ON public.stationinfo ("AntennaCode", "RadomeCode");
