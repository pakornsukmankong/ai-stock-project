-- Performance tracking now covers BUY and SELL alerts, not just BUY.
-- The old partial index (003) was restricted to signal_type = 'BUY'; the
-- performance queries now filter on (user_id, alert_price IS NOT NULL) ordered by
-- sent_at across both sides. Add an index that matches that shape. The old index
-- is left in place (harmless) — dropping it is optional.
CREATE INDEX IF NOT EXISTS idx_alerts_perf_tracked
ON public.alerts (user_id, sent_at DESC)
WHERE alert_price IS NOT NULL;
