-- GramCare PostgreSQL initialization script
-- This runs on first container start

-- Create extension for UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Create sync version sequence
CREATE SEQUENCE IF NOT EXISTS sync_version_seq START 1 INCREMENT 1;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE gramcare TO gramcare_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO gramcare_user;
