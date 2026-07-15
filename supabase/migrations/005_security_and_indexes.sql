-- ---------------------------------------------------------------------------
-- 1. Lock down analysis_cache (CRITICAL)
-- ---------------------------------------------------------------------------
-- 001 enabled RLS on users/watchlists/watchlist_stocks/alerts but not on
-- analysis_cache. Supabase grants the `anon` and `authenticated` roles full DML
-- on public tables by default, so with RLS off *anyone holding the anon key*
-- (which ships in the frontend bundle) could INSERT/UPDATE rows here.
--
-- That is not just a data-integrity problem: the pipeline reads this table and
-- trusts `action` and `ai_summary` verbatim, pushing them to every user watching
-- the symbol. A forged row = an attacker-authored "BUY" alert delivered over LINE.
--
-- No policies are added: the backend talks to this table with the service-role
-- key, which bypasses RLS. RLS-on + zero-policies = closed to anon/authenticated.
ALTER TABLE public.analysis_cache ENABLE ROW LEVEL SECURITY;

-- Same reasoning for the performance-tracking columns' table: alerts already has
-- a SELECT policy, but no INSERT/UPDATE/DELETE policy, so writes are already
-- closed to end users. Nothing to change there.

-- ---------------------------------------------------------------------------
-- 2. Harden the signup trigger
-- ---------------------------------------------------------------------------
-- A SECURITY DEFINER function with a mutable search_path can be hijacked by a
-- role that creates a same-named table/function earlier in the path.
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    INSERT INTO public.users (id, email)
    VALUES (NEW.id, NEW.email)
    ON CONFLICT (id) DO NOTHING;

    INSERT INTO public.watchlists (user_id)
    VALUES (NEW.id)
    ON CONFLICT (user_id) DO NOTHING;

    RETURN NEW;
END;
$$;

-- ---------------------------------------------------------------------------
-- 3. Indexes
-- ---------------------------------------------------------------------------
-- The alert-cooldown lookup filters on (user_id, stock_symbol, sent_at); only
-- user_id was indexed, so every check scanned all of that user's alerts.
CREATE INDEX IF NOT EXISTS idx_alerts_user_symbol_sent
    ON public.alerts (user_id, stock_symbol, sent_at DESC);

-- The cleanup job and the "already sent today" briefing check both filter on
-- signal_type + sent_at.
CREATE INDEX IF NOT EXISTS idx_alerts_type_sent
    ON public.alerts (signal_type, sent_at DESC);

-- Redundant: UNIQUE(symbol) on analysis_cache already provides this index.
DROP INDEX IF EXISTS public.idx_analysis_cache_symbol;
