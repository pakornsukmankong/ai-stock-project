-- Take-profit target captured at BUY time.
--
-- A SELL alert is a take-profit on the position a BUY alert opened, and the
-- target is the swing high price had fallen from AT THAT MOMENT. Re-reading the
-- latest swing high each cycle instead makes the target drift DOWN during the
-- dip (a lower high forms while price falls), which exits far too early:
-- backtest Jan-2020->2026 gave +3.9% / 78% win with a moving target versus
-- +12.8% / 97% with the target frozen at entry.
ALTER TABLE public.alerts
ADD COLUMN IF NOT EXISTS target_high NUMERIC;
