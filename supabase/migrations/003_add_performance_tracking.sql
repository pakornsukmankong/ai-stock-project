-- Add performance tracking columns to alerts table
ALTER TABLE public.alerts
ADD COLUMN IF NOT EXISTS alert_price NUMERIC,
ADD COLUMN IF NOT EXISTS price_after_1d NUMERIC,
ADD COLUMN IF NOT EXISTS price_after_3d NUMERIC,
ADD COLUMN IF NOT EXISTS price_after_7d NUMERIC,
ADD COLUMN IF NOT EXISTS return_1d NUMERIC,
ADD COLUMN IF NOT EXISTS return_3d NUMERIC,
ADD COLUMN IF NOT EXISTS return_7d NUMERIC,
ADD COLUMN IF NOT EXISTS is_successful BOOLEAN;

-- Index for performance tracking queries
CREATE INDEX IF NOT EXISTS idx_alerts_performance ON public.alerts(sent_at, is_successful)
WHERE signal_type = 'BUY';
