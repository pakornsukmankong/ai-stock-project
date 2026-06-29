-- Add action column to analysis_cache so cached AI decisions (BUY/SELL/HOLD)
-- are persisted. Without this, cache hits defaulted to "BUY" and could trigger
-- false notifications for stocks the AI actually rated HOLD/SELL.
ALTER TABLE public.analysis_cache
ADD COLUMN IF NOT EXISTS action TEXT NOT NULL DEFAULT 'BUY';
