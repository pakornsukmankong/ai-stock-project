-- Add notification preference column to users table
-- Values: 'All', 'High', 'Medium'
ALTER TABLE public.users
ADD COLUMN IF NOT EXISTS min_confidence TEXT DEFAULT 'All';
