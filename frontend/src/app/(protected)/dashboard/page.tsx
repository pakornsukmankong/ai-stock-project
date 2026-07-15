"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { watchlistApi, alertsApi, type WatchlistStock } from "@/lib/api";
import { WatchlistPanel } from "@/components/watchlist-panel";
import { AlertsPanel } from "@/components/alerts-panel";
import { StockChart } from "@/components/stock-chart";
import { Activity, BarChart3, List, Bell } from "lucide-react";

export default function DashboardPage() {
  const [isLoading, setIsLoading] = useState(true);
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [watchlistStocks, setWatchlistStocks] = useState<WatchlistStock[]>([]);
  const [signalsToday, setSignalsToday] = useState(0);
  const router = useRouter();

  useEffect(() => {
    async function init() {
      const supabase = createClient();
      const { data: { user } } = await supabase.auth.getUser();

      if (!user) {
        router.push("/login");
        return;
      }

      try {
        const [watchlistRes, statsRes] = await Promise.all([
          watchlistApi.getStocks(),
          alertsApi.getStats(),
        ]);
        setWatchlistStocks(watchlistRes.stocks);
        setSignalsToday(statsRes.signals_today);
        if (watchlistRes.stocks.length > 0) {
          setSelectedSymbol(watchlistRes.stocks[0].symbol);
        }
      } catch {
        // Ignore
      }

      setIsLoading(false);
    }

    init();
  }, [router]);

  // Keeps the chart's symbol tabs in sync when the panel adds/removes a stock.
  const handleStocksChange = useCallback((stocks: WatchlistStock[]) => {
    setWatchlistStocks(stocks);
    setSelectedSymbol((current) => {
      if (current && stocks.some((s) => s.symbol === current)) return current;
      return stocks.length > 0 ? stocks[0].symbol : null;
    });
  }, []);

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="flex items-center gap-2 font-mono text-sm text-terminal-green animate-pulse-green">
          <Activity className="h-4 w-4" />
          Connecting...
        </div>
      </div>
    );
  }

  return (
    <main className="p-4 sm:p-6">
      {/* Top Bar */}
      <div className="mb-6 flex items-center justify-between gap-3">
        <div>
          <h1 className="font-mono text-lg font-bold text-foreground">Dashboard</h1>
          <p className="font-mono text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1">
              <span className="h-1.5 w-1.5 animate-pulse-green rounded-full bg-terminal-green" />
              Live monitoring active
            </span>
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-md border border-terminal-border bg-terminal-panel px-3 py-1.5">
          <span className="font-mono text-xs text-muted-foreground">Status:</span>
          <span className="font-mono text-xs text-terminal-green">Online</span>
        </div>
      </div>

      {/* Stats Row */}
      <div className="mb-6 grid grid-cols-3 gap-3 sm:gap-4">
        <StatCard label="Watchlist" value={String(watchlistStocks.length)} suffix="stocks" />
        <StatCard label="Signals Today" value={String(signalsToday)} suffix="alerts" />
        <StatCard label="Next Scan" value="5" suffix="min" />
      </div>

      {/* Chart Section */}
      {selectedSymbol && (
        <section className="mb-6">
          <div className="mb-3 flex items-center gap-3">
            <BarChart3 className="h-4 w-4 text-terminal-green" />
            <h2 className="font-mono text-sm font-semibold">Chart</h2>
          </div>
          {/* Symbol Tabs - scrollable, show all */}
          <div className="mb-3 flex gap-1 overflow-x-auto pb-1">
            {watchlistStocks.map((stock) => (
              <button
                key={stock.id}
                onClick={() => setSelectedSymbol(stock.symbol)}
                className={`shrink-0 rounded px-2.5 py-1 font-mono text-xs transition-all ${
                  selectedSymbol === stock.symbol
                    ? "bg-terminal-green/10 text-terminal-green border border-terminal-green/30"
                    : "border border-terminal-border text-muted-foreground hover:border-terminal-green/20 hover:text-foreground"
                }`}
              >
                {stock.symbol}
              </button>
            ))}
          </div>
          <StockChart symbol={selectedSymbol} />
        </section>
      )}

      {/* Main Grid */}
      <div className="grid gap-6 lg:grid-cols-5">
        {/* Watchlist */}
        <section id="watchlist" className="lg:col-span-3">
          <div className="mb-3 flex items-center gap-2">
            <List className="h-4 w-4 text-terminal-green" />
            <h2 className="font-mono text-sm font-semibold">Watchlist</h2>
          </div>
          <WatchlistPanel
            stocks={watchlistStocks}
            onStocksChange={handleStocksChange}
          />
        </section>

        {/* Alerts */}
        <section id="alerts" className="lg:col-span-2">
          <div className="mb-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Bell className="h-4 w-4 text-terminal-green" />
              <h2 className="font-mono text-sm font-semibold">Recent Alerts</h2>
            </div>
            <button
              onClick={() => router.push("/alerts")}
              className="font-mono text-[10px] text-muted-foreground transition-colors hover:text-terminal-green"
            >
              View all →
            </button>
          </div>
          <AlertsPanel />
        </section>
      </div>
    </main>
  );
}

function StatCard({
  label,
  value,
  suffix,
}: {
  label: string;
  value: string;
  suffix: string;
}) {
  return (
    <div className="rounded-lg border border-terminal-border bg-terminal-panel p-4">
      <p className="font-mono text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 font-mono text-xl font-bold text-terminal-green">
        {value}
        <span className="ml-1 text-xs text-muted-foreground">{suffix}</span>
      </p>
    </div>
  );
}
