-- Per-user toggles for which signal types push to LINE.
-- notify_buy defaults TRUE so existing users keep receiving buy alerts (current
-- behaviour). notify_sell defaults FALSE — the sell (take-profit) alert is a new
-- opt-in feature, so nobody starts getting it without turning it on in Settings.
ALTER TABLE public.users
ADD COLUMN IF NOT EXISTS notify_buy BOOLEAN NOT NULL DEFAULT TRUE,
ADD COLUMN IF NOT EXISTS notify_sell BOOLEAN NOT NULL DEFAULT FALSE;
