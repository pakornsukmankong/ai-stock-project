-- Users table (extends Supabase Auth)
CREATE TABLE IF NOT EXISTS public.users (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    line_user_id TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Watchlists table
CREATE TABLE IF NOT EXISTS public.watchlists (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id)
);

-- Watchlist stocks table
CREATE TABLE IF NOT EXISTS public.watchlist_stocks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    watchlist_id UUID NOT NULL REFERENCES public.watchlists(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    is_enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(watchlist_id, symbol)
);

-- Analysis cache table
CREATE TABLE IF NOT EXISTS public.analysis_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol TEXT NOT NULL,
    ai_summary TEXT NOT NULL,
    confidence TEXT NOT NULL,
    reasons JSONB DEFAULT '[]',
    cached_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    UNIQUE(symbol)
);

-- Alerts history table
CREATE TABLE IF NOT EXISTS public.alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    stock_symbol TEXT NOT NULL,
    signal_type TEXT NOT NULL DEFAULT 'BUY',
    ai_summary TEXT NOT NULL,
    confidence TEXT,
    reasons JSONB DEFAULT '[]',
    sent_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_watchlist_stocks_symbol ON public.watchlist_stocks(symbol);
CREATE INDEX IF NOT EXISTS idx_watchlist_stocks_enabled ON public.watchlist_stocks(is_enabled);
CREATE INDEX IF NOT EXISTS idx_analysis_cache_symbol ON public.analysis_cache(symbol);
CREATE INDEX IF NOT EXISTS idx_analysis_cache_expires ON public.analysis_cache(expires_at);
CREATE INDEX IF NOT EXISTS idx_alerts_user_id ON public.alerts(user_id);
CREATE INDEX IF NOT EXISTS idx_alerts_sent_at ON public.alerts(sent_at DESC);

-- Row Level Security
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.watchlists ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.watchlist_stocks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.alerts ENABLE ROW LEVEL SECURITY;

-- RLS Policies
CREATE POLICY "Users can view own profile"
    ON public.users FOR SELECT
    USING (auth.uid() = id);

CREATE POLICY "Users can update own profile"
    ON public.users FOR UPDATE
    USING (auth.uid() = id);

CREATE POLICY "Users can view own watchlist"
    ON public.watchlists FOR ALL
    USING (auth.uid() = user_id);

CREATE POLICY "Users can manage own watchlist stocks"
    ON public.watchlist_stocks FOR ALL
    USING (
        watchlist_id IN (
            SELECT id FROM public.watchlists WHERE user_id = auth.uid()
        )
    );

CREATE POLICY "Users can view own alerts"
    ON public.alerts FOR SELECT
    USING (auth.uid() = user_id);

-- Function to auto-create user profile on signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.users (id, email)
    VALUES (NEW.id, NEW.email);

    INSERT INTO public.watchlists (user_id)
    VALUES (NEW.id);

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger for new user signup
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
