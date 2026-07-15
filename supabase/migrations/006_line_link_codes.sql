-- ---------------------------------------------------------------------------
-- LINE account-linking codes
-- ---------------------------------------------------------------------------
-- Short-lived, single-use codes that connect a web user to their LINE identity
-- without the user having to hunt down their opaque LINE User ID.
--
-- Flow: the web app generates a code for the signed-in user and stores it here;
-- the user sends that code to the Official Account; the LINE webhook looks the
-- code up, writes users.line_user_id, and deletes the row. Codes expire so a
-- leaked/screenshotted code cannot be redeemed later.
--
-- One active code per user (user_id PRIMARY KEY): regenerating replaces the
-- previous code via UPSERT. `code` is UNIQUE so the webhook can look up by code
-- alone, and so two users can never hold the same code simultaneously.
CREATE TABLE IF NOT EXISTS public.line_link_codes (
    user_id    UUID PRIMARY KEY REFERENCES public.users(id) ON DELETE CASCADE,
    code       TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- The cleanup job deletes expired rows by expires_at.
CREATE INDEX IF NOT EXISTS idx_line_link_codes_expires
    ON public.line_link_codes (expires_at);

-- Only the backend (service-role key) ever touches this table: the web endpoint
-- writes codes and the webhook consumes them. RLS-on + zero-policies closes it
-- to the anon/authenticated roles (which ship in the frontend bundle), so an
-- end user can neither read someone else's code nor forge one. Service-role
-- bypasses RLS. Same pattern as analysis_cache in migration 005.
ALTER TABLE public.line_link_codes ENABLE ROW LEVEL SECURITY;
