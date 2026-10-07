-- Silent "armed" BUY setups.
--
-- The first time the buy gate fires for a symbol nothing is sent; the price is
-- remembered here. A BUY alert goes out only if the gate is active again within
-- the confirmation window at a price BUY_CONFIRM_DROP_PCT lower. Stored (rather
-- than kept in memory) so a redeploy does not forget what is armed.
CREATE TABLE IF NOT EXISTS public.buy_arms (
    symbol       TEXT PRIMARY KEY,
    armed_price  NUMERIC NOT NULL,
    armed_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Backend-only table (service role bypasses RLS); no client policies on purpose.
ALTER TABLE public.buy_arms ENABLE ROW LEVEL SECURITY;
