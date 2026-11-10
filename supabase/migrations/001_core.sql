cat << 'EOF' > supabase/migrations/001_core.sql
-- 
═══════════════════════════════════════════════════════════
-- CORE TABLE
-- 
═══════════════════════════════════════════════════════════
CREATE TABLE companies_master (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  domain TEXT UNIQUE,
  name TEXT NOT NULL,
  country_code TEXT NOT NULL CHECK (country_code IN ('ZA','US','IN')),

  registry_id TEXT,
  registry_status TEXT,
  last_filing_date DATE,

  website TEXT,
  email TEXT,
  email_source_url TEXT,
  email_collected_at TIMESTAMPTZ,

  sector_label TEXT,
  hs_codes TEXT[] DEFAULT '{}',

  verification_tier TEXT,
  shell_risk_score NUMERIC(5,2),

  evidence JSONB DEFAULT '{}'::jsonb,
  source TEXT,
  suppressed BOOLEAN DEFAULT false,
  updated_at TIMESTAMPTZ DEFAULT now(),

  search_vector tsvector GENERATED ALWAYS AS (
    to_tsvector('simple'::regconfig,
      coalesce(name,'') || ' ' ||
      coalesce(sector_label,'') || ' ' ||
      coalesce(array_to_string(hs_codes,' '),'')
    )
  ) STORED
);

CREATE INDEX idx_cm_country   ON companies_master (country_code);
CREATE INDEX idx_cm_tier      ON companies_master (verification_tier);
CREATE INDEX idx_cm_hs        ON companies_master USING GIN (hs_codes);
CREATE INDEX idx_cm_search    ON companies_master USING GIN 
(search_vector);

-- 
═══════════════════════════════════════════════════════════
-- SCORING ENGINE
-- 
═══════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION compute_verification(
  p_status TEXT,
  p_evidence JSONB
) RETURNS TABLE(score NUMERIC, tier TEXT)
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
  s NUMERIC := 0;
  tier3 INT := 0;
  e JSONB := coalesce(p_evidence, '{}'::jsonb);
BEGIN
  IF p_status IS NULL
     OR lower(p_status) NOT IN ('active','in business','in good 
standing','good standing') THEN
    RETURN QUERY SELECT 0::NUMERIC, 'excluded'::TEXT;
    RETURN;
  END IF;

  IF (e->>'agent_not_mass_formation')::boolean IS TRUE THEN s := s + 1; 
END IF;
  IF (e->>'no_filing_gap')::boolean        IS TRUE THEN s := s + 1; END 
IF;
  IF (e->>'website_specific')::boolean     IS TRUE THEN s := s + 2; END 
IF;
  IF (e->>'physical_address')::boolean     IS TRUE THEN s := s + 2; END 
IF;
  IF (e->>'named_person')::boolean         IS TRUE THEN s := s + 1; END 
IF;
  IF (e->>'directory_listing')::boolean    IS TRUE THEN s := s + 1; END 
IF;
  IF (e->>'association_member')::boolean   IS TRUE THEN s := s + 2; END 
IF;
  
  IF (e->>'iec_verified')::boolean         IS TRUE THEN s := s + 3; tier3 
:= tier3 + 1; END IF;
  IF (e->>'epc_member')::boolean           IS TRUE THEN s := s + 2; tier3 
:= tier3 + 1; END IF;
  IF (e->>'importyeti_present')::boolean   IS TRUE THEN s := s + 3; tier3 
:= tier3 + 1; END IF;
  IF (e->>'trade_association')::boolean    IS TRUE THEN s := s + 2; tier3 
:= tier3 + 1; END IF;

  IF s >= 6 AND tier3 >= 1 THEN
    RETURN QUERY SELECT s, 'verified'::TEXT;
  ELSIF s >= 3 THEN
    RETURN QUERY SELECT s, 'probable'::TEXT;
  ELSE
    RETURN QUERY SELECT s, 'shell_risk'::TEXT;
  END IF;
END;
$$;

CREATE OR REPLACE FUNCTION rescore_all()
RETURNS void LANGUAGE sql AS $$
  UPDATE companies_master c
  SET shell_risk_score = v.score,
      verification_tier = v.tier,
      updated_at = now()
  FROM (
    SELECT id, (compute_verification(registry_status, evidence)).*
    FROM companies_master
  ) v
  WHERE c.id = v.id;
$$;

-- 
═══════════════════════════════════════════════════════════
-- MATERIALIZED VIEW & PUBLIC API
-- 
═══════════════════════════════════════════════════════════
CREATE SCHEMA IF NOT EXISTS private;

CREATE MATERIALIZED VIEW private.company_directory AS
SELECT id, name, country_code, website, email, sector_label,
       hs_codes, verification_tier, shell_risk_score, search_vector
FROM companies_master
WHERE suppressed = false;

CREATE UNIQUE INDEX idx_cd_id ON private.company_directory (id);
CREATE INDEX idx_cd_search ON private.company_directory USING GIN 
(search_vector);
CREATE INDEX idx_cd_country ON private.company_directory (country_code, 
verification_tier);

CREATE OR REPLACE VIEW public.company_listing
WITH (security_invoker = true) AS
SELECT * FROM private.company_directory;

REVOKE ALL ON private.company_directory FROM anon, authenticated;
GRANT SELECT ON public.company_listing TO anon, authenticated;

-- 
═══════════════════════════════════════════════════════════
-- AI QUOTA & CACHE
-- 
═══════════════════════════════════════════════════════════
CREATE TABLE ai_usage_log (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_aiu_user_time ON ai_usage_log (user_id, created_at 
DESC);

CREATE TABLE ai_cache (
  query_hash TEXT PRIMARY KEY,
  answer TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE OR REPLACE FUNCTION check_ai_quota(
  p_user UUID,
  p_limit INT DEFAULT 20,
  p_window INTERVAL DEFAULT '1 hour'
) RETURNS BOOLEAN
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE c INT;
BEGIN
  PERFORM pg_advisory_xact_lock(hashtext(p_user::text));
  SELECT count(*) INTO c FROM ai_usage_log
   WHERE user_id = p_user AND created_at > now() - p_window;
  IF c >= p_limit THEN RETURN false; END IF;
  INSERT INTO ai_usage_log (user_id) VALUES (p_user);
  RETURN true;
END;
$$;

ALTER TABLE companies_master ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_usage_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_cache ENABLE ROW LEVEL SECURITY;

CREATE POLICY "public read non-suppressed" ON companies_master FOR SELECT 
USING (suppressed = false);
REVOKE ALL ON companies_master FROM anon, authenticated;
REVOKE ALL ON ai_usage_log FROM anon, authenticated;
REVOKE ALL ON ai_cache FROM anon, authenticated;

CREATE OR REPLACE FUNCTION refresh_directory() RETURNS void
LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
  PERFORM rescore_all();
  REFRESH MATERIALIZED VIEW CONCURRENTLY private.company_directory;
END;
$$;
EOF- 
═══════════════════════════════════════════════════════════
-- CORE TABLE
-- 
═══════════════════════════════════════════════════════════
CREATE TABLE companies_master (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  domain TEXT UNIQUE,
  name TEXT NOT NULL,
  country_code TEXT NOT NULL CHECK (country_code IN ('ZA','US','IN')),

  registry_id TEXT,
  registry_status TEXT,
  last_filing_date DATE,

  website TEXT,
  email TEXT,
  email_source_url TEXT,
  email_collected_at TIMESTAMPTZ,

  sector_label TEXT,
  hs_codes TEXT[] DEFAULT '{}',

  verification_tier TEXT,
  shell_risk_score NUMERIC(5,2),

  evidence JSONB DEFAULT '{}'::jsonb,
  source TEXT,
  suppressed BOOLEAN DEFAULT false,
  updated_at TIMESTAMPTZ DEFAULT now(),

  search_vector tsvector GENERATED ALWAYS AS (
    to_tsvector('simple',
      coalesce(name,'') || ' ' ||
      coalesce(sector_label,'') || ' ' ||
      coalesce(array_to_string(hs_codes,' '),'')
    )
  ) STORED
);

CREATE INDEX idx_cm_country   ON companies_master (country_code);
CREATE INDEX idx_cm_tier      ON companies_master (verification_tier);
CREATE INDEX idx_cm_hs        ON companies_master USING GIN (hs_codes);
CREATE INDEX idx_cm_search    ON companies_master USING GIN 
(search_vector);

-- 
═══════════════════════════════════════════════════════════
-- SCORING ENGINE
-- 
═══════════════════════════════════════════════════════════
CREATE OR REPLACE FUNCTION compute_verification(
  p_status TEXT,
  p_evidence JSONB
) RETURNS TABLE(score NUMERIC, tier TEXT)
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
  s NUMERIC := 0;
  tier3 INT := 0;
  e JSONB := coalesce(p_evidence, '{}'::jsonb);
BEGIN
  IF p_status IS NULL
     OR lower(p_status) NOT IN ('active','in business','in good 
standing','good standing') THEN
    RETURN QUERY SELECT 0::NUMERIC, 'excluded'::TEXT;
    RETURN;
  END IF;

  IF (e->>'agent_not_mass_formation')::boolean IS TRUE THEN s := s + 1; 
END IF;
  IF (e->>'no_filing_gap')::boolean        IS TRUE THEN s := s + 1; END 
IF;
  IF (e->>'website_specific')::boolean     IS TRUE THEN s := s + 2; END 
IF;
  IF (e->>'physical_address')::boolean     IS TRUE THEN s := s + 2; END 
IF;
  IF (e->>'named_person')::boolean         IS TRUE THEN s := s + 1; END 
IF;
  IF (e->>'directory_listing')::boolean    IS TRUE THEN s := s + 1; END 
IF;
  IF (e->>'association_member')::boolean   IS TRUE THEN s := s + 2; END 
IF;
  
  IF (e->>'iec_verified')::boolean         IS TRUE THEN s := s + 3; tier3 
:= tier3 + 1; END IF;
  IF (e->>'epc_member')::boolean           IS TRUE THEN s := s + 2; tier3 
:= tier3 + 1; END IF;
  IF (e->>'importyeti_present')::boolean   IS TRUE THEN s := s + 3; tier3 
:= tier3 + 1; END IF;
  IF (e->>'trade_association')::boolean    IS TRUE THEN s := s + 2; tier3 
:= tier3 + 1; END IF;

  IF s >= 6 AND tier3 >= 1 THEN
    RETURN QUERY SELECT s, 'verified'::TEXT;
  ELSIF s >= 3 THEN
    RETURN QUERY SELECT s, 'probable'::TEXT;
  ELSE
    RETURN QUERY SELECT s, 'shell_risk'::TEXT;
  END IF;
END;
$$;

CREATE OR REPLACE FUNCTION rescore_all()
RETURNS void LANGUAGE sql AS $$
  UPDATE companies_master c
  SET shell_risk_score = v.score,
      verification_tier = v.tier,
      updated_at = now()
  FROM (
    SELECT id, (compute_verification(registry_status, evidence)).*
    FROM companies_master
  ) v
  WHERE c.id = v.id;
$$;

-- 
═══════════════════════════════════════════════════════════
-- MATERIALIZED VIEW & PUBLIC API
-- 
═══════════════════════════════════════════════════════════
CREATE SCHEMA IF NOT EXISTS private;

CREATE MATERIALIZED VIEW private.company_directory AS
SELECT id, name, country_code, website, email, sector_label,
       hs_codes, verification_tier, shell_risk_score, search_vector
FROM companies_master
WHERE suppressed = false;

CREATE UNIQUE INDEX idx_cd_id ON private.company_directory (id);
CREATE INDEX idx_cd_search ON private.company_directory USING GIN 
(search_vector);
CREATE INDEX idx_cd_country ON private.company_directory (country_code, 
verification_tier);

CREATE OR REPLACE VIEW public.company_listing
WITH (security_invoker = true) AS
SELECT * FROM private.company_directory;

REVOKE ALL ON private.company_directory FROM anon, authenticated;
GRANT SELECT ON public.company_listing TO anon, authenticated;

-- 
═══════════════════════════════════════════════════════════
-- AI QUOTA & CACHE
-- 
═══════════════════════════════════════════════════════════
CREATE TABLE ai_usage_log (
  id BIGSERIAL PRIMARY KEY,
  user_id UUID NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_aiu_user_time ON ai_usage_log (user_id, created_at DESC);

CREATE TABLE ai_cache (
  query_hash TEXT PRIMARY KEY,
  answer TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE OR REPLACE FUNCTION check_ai_quota(
  p_user UUID,
  p_limit INT DEFAULT 20,
  p_window INTERVAL DEFAULT '1 hour'
) RETURNS BOOLEAN
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE c INT;
BEGIN
  PERFORM pg_advisory_xact_lock(hashtext(p_user::text));
  SELECT count(*) INTO c FROM ai_usage_log
   WHERE user_id = p_user AND created_at > now() - p_window;
  IF c >= p_limit THEN RETURN false; END IF;
  INSERT INTO ai_usage_log (user_id) VALUES (p_user);
  RETURN true;
END;
$$;

ALTER TABLE companies_master ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_usage_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_cache ENABLE ROW LEVEL SECURITY;

CREATE POLICY "public read non-suppressed" ON companies_master FOR SELECT 
USING (suppressed = false);
REVOKE ALL ON companies_master FROM anon, authenticated;
REVOKE ALL ON ai_usage_log FROM anon, authenticated;
REVOKE ALL ON ai_cache FROM anon, authenticated;

CREATE OR REPLACE FUNCTION refresh_directory() RETURNS void
LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
  PERFORM rescore_all();
  REFRESH MATERIALIZED VIEW CONCURRENTLY private.company_directory;
END;
$$;
