-- The official PostgreSQL image runs this file only when initializing a new volume.
\getenv db POSTGRES_DB
\getenv owner GEODE_OWNER
\getenv owner_password GEODE_OWNER_PASSWORD
\getenv app GEODE_APP
\getenv app_password GEODE_APP_PASSWORD

BEGIN;
CREATE ROLE :"owner" LOGIN;
CREATE ROLE :"app" LOGIN;
ALTER ROLE :"owner" PASSWORD :'owner_password';
ALTER ROLE :"app" PASSWORD :'app_password';
ALTER DATABASE :"db" OWNER TO :"owner";
COMMIT;
