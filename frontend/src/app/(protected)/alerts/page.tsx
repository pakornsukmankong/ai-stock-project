"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { alertsApi, type Alert, type PaginationMeta } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import {
  Activity,
  ArrowUpRight,
  Bell,
  Filter,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";

const CONFIDENCE_OPTIONS = ["All", "High", "Medium", "Low"];
const PER_PAGE = 20;

export default function AlertsHistoryPage() {
  const [isLoading, setIsLoading] = useState(true);
  const [filterSymbol, setFilterSymbol] = useState("");
  const [filterConfidence, setFilterConfidence] = useState("All");
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [pagination, setPagination] = useState<PaginationMeta>({
    page: 1,
    per_page: PER_PAGE,
    total: 0,
    total_pages: 1,
    has_next: false,
    has_prev: false,
  });
  const [page, setPage] = useState(1);
  const router = useRouter();

  const fetchAlerts = useCallback(async (pageNum: number) => {
    try {
      setIsLoading(true);
      const response = await alertsApi.getAlerts(pageNum, PER_PAGE);
      setAlerts(response.alerts);
      setPagination(response.pagination);
    } catch {
      // Handle error silently
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    async function init() {
      const supabase = createClient();
      const { data: { user } } = await supabase.auth.getUser();
      if (!user) {
        router.push("/login");
        return;
      }
      await fetchAlerts(1);
    }
    init();
  }, [router, fetchAlerts]);

  useEffect(() => {
    if (alerts.length > 0) {
      fetchAlerts(page);
    }
  }, [page, fetchAlerts, alerts.length]);

  // Client-side filters (applied to current page data)
  const filteredAlerts = alerts.filter((alert) => {
    const matchesSymbol =
      !filterSymbol || alert.stock_symbol.toLowerCase().includes(filterSymbol.toLowerCase());
    const matchesConfidence =
      filterConfidence === "All" || alert.confidence === filterConfidence;
    return matchesSymbol && matchesConfidence;
  });

  // Get unique symbols from current page
  const uniqueSymbols = [...new Set(alerts.map((a) => a.stock_symbol))];

  const handlePrevPage = () => {
    if (pagination.has_prev) {
      setPage((prev) => prev - 1);
    }
  };

  const handleNextPage = () => {
    if (pagination.has_next) {
      setPage((prev) => prev + 1);
    }
  };

  if (isLoading && alerts.length === 0) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="flex items-center gap-2 font-mono text-sm text-terminal-green animate-pulse-green">
          <Activity className="h-4 w-4" />
          Loading...
        </div>
      </div>
    );
  }

  return (
    <main className="p-6">
      <div className="mx-auto max-w-4xl">
        {/* Header */}
        <div className="mb-6 flex items-center gap-3">
          <Bell className="h-5 w-5 text-terminal-green" />
          <h1 className="font-mono text-lg font-bold text-foreground">Alert History</h1>
          <span className="font-mono text-xs text-muted-foreground">
            {pagination.total} alerts
          </span>
        </div>

        {/* Filters */}
        <div className="mb-4 flex flex-wrap items-center gap-3 rounded-lg border border-terminal-border bg-terminal-panel p-4">
          <Filter className="h-4 w-4 text-muted-foreground" />

          <input
            type="text"
            value={filterSymbol}
            onChange={(e) => setFilterSymbol(e.target.value)}
            placeholder="Filter by symbol..."
            className="w-40 rounded-md border border-terminal-border bg-terminal-dark px-3 py-1.5 font-mono text-xs text-foreground placeholder:text-muted-foreground focus:border-terminal-green/50 focus:outline-none"
          />

          <div className="flex rounded-md border border-terminal-border">
            {CONFIDENCE_OPTIONS.map((option) => (
              <button
                key={option}
                onClick={() => setFilterConfidence(option)}
                className={`px-2.5 py-1.5 font-mono text-[10px] transition-all ${
                  filterConfidence === option
                    ? "bg-terminal-green/10 text-terminal-green"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {option}
              </button>
            ))}
          </div>

          {uniqueSymbols.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {uniqueSymbols.map((sym) => (
                <button
                  key={sym}
                  onClick={() => setFilterSymbol(filterSymbol === sym ? "" : sym)}
                  className={`rounded px-2 py-1 font-mono text-[10px] transition-all ${
                    filterSymbol === sym
                      ? "bg-terminal-green/10 text-terminal-green border border-terminal-green/30"
                      : "border border-terminal-border text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {sym}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Alert List */}
        {filteredAlerts.length === 0 ? (
          <div className="rounded-lg border border-terminal-border bg-terminal-panel p-12 text-center">
            <Bell className="mx-auto h-8 w-8 text-muted-foreground" />
            <p className="mt-3 font-mono text-xs text-muted-foreground">
              {pagination.total === 0
                ? "No alerts yet. Alerts will appear here when buy signals are detected."
                : "No alerts match your filters."}
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {filteredAlerts.map((alert) => (
              <AlertCard key={alert.id} alert={alert} />
            ))}
          </div>
        )}

        {/* Pagination */}
        {pagination.total_pages > 1 && (
          <div className="mt-4 flex items-center justify-between rounded-lg border border-terminal-border bg-terminal-panel px-4 py-3">
            <span className="font-mono text-xs text-muted-foreground">
              Page {pagination.page} of {pagination.total_pages} ({pagination.total} total)
            </span>
            <div className="flex gap-2">
              <button
                onClick={handlePrevPage}
                disabled={!pagination.has_prev}
                className="flex items-center gap-1 rounded-md border border-terminal-border px-2 py-1 font-mono text-xs text-muted-foreground transition-all hover:border-terminal-green/50 hover:text-terminal-green disabled:opacity-30"
              >
                <ChevronLeft className="h-3 w-3" />
                Prev
              </button>
              <button
                onClick={handleNextPage}
                disabled={!pagination.has_next}
                className="flex items-center gap-1 rounded-md border border-terminal-border px-2 py-1 font-mono text-xs text-muted-foreground transition-all hover:border-terminal-green/50 hover:text-terminal-green disabled:opacity-30"
              >
                Next
                <ChevronRight className="h-3 w-3" />
              </button>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}

function AlertCard({ alert }: { alert: Alert }) {
  return (
    <div className="rounded-lg border border-terminal-border bg-terminal-panel p-4 transition-all hover:border-terminal-green/20">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ArrowUpRight className="h-3.5 w-3.5 text-terminal-green" />
          <span className="font-mono text-sm font-bold text-foreground">
            {alert.stock_symbol}
          </span>
          <span className="rounded bg-terminal-green/10 px-1.5 py-0.5 font-mono text-[10px] font-medium text-terminal-green">
            {alert.signal_type}
          </span>
          {alert.confidence && (
            <span
              className={`rounded px-1.5 py-0.5 font-mono text-[10px] font-medium ${
                alert.confidence === "High"
                  ? "bg-terminal-green/10 text-terminal-green"
                  : alert.confidence === "Medium"
                  ? "bg-yellow-500/10 text-yellow-500"
                  : "bg-muted text-muted-foreground"
              }`}
            >
              {alert.confidence}
            </span>
          )}
        </div>
        <span className="font-mono text-[10px] text-muted-foreground">
          {formatDate(alert.sent_at)}
        </span>
      </div>

      <p className="mt-2 font-mono text-xs leading-relaxed text-muted-foreground">
        {alert.ai_summary}
      </p>

      {alert.reasons && alert.reasons.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {alert.reasons.map((reason, i) => (
            <span
              key={i}
              className="rounded border border-terminal-border px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground"
            >
              {reason}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
