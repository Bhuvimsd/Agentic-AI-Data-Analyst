-- ==============================================================================
-- Project: Agentic AI Data Analyst
-- Component: Phase 5 Least-Privilege PostgreSQL Security Role Architecture
-- Target Engine: PostgreSQL 14+
-- ==============================================================================

-- 1. Create dedicated restricted role for AI query execution if not exists
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'analyst_readonly') THEN
        CREATE ROLE analyst_readonly WITH LOGIN PASSWORD 'analyst_password123';
    END IF;
END
$$;

-- 2. Revoke all ambient privileges on database, schema, and tables
REVOKE ALL ON DATABASE agentic_ai_analytics FROM analyst_readonly;
REVOKE ALL ON SCHEMA public FROM analyst_readonly;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM analyst_readonly;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM analyst_readonly;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM analyst_readonly;

-- 3. Grant connection and schema traversal permissions
GRANT CONNECT ON DATABASE agentic_ai_analytics TO analyst_readonly;
GRANT USAGE ON SCHEMA public TO analyst_readonly;

-- 4. Grant strict SELECT-only permissions on explicitly approved tables
GRANT SELECT ON TABLE customers TO analyst_readonly;
GRANT SELECT ON TABLE products TO analyst_readonly;
GRANT SELECT ON TABLE stores TO analyst_readonly;
GRANT SELECT ON TABLE orders TO analyst_readonly;
GRANT SELECT ON TABLE order_items TO analyst_readonly;
GRANT SELECT ON TABLE payments TO analyst_readonly;

-- 5. Revoke default privileges for future objects (Immunity against new tables)
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM analyst_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM analyst_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM analyst_readonly;

-- 6. Enforce hard runtime boundaries at the PostgreSQL role level
ALTER ROLE analyst_readonly SET default_transaction_read_only = on;
ALTER ROLE analyst_readonly SET statement_timeout = '10000'; -- 10 seconds timeout
ALTER ROLE analyst_readonly SET search_path = public;
