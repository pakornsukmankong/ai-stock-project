"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { alertsApi, type PerformanceStats, type PerformanceAlert, type PaginationMeta } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { Activity, TrendingUp, TrendingDown, Target, ChevronLeft, ChevronRight, Trash2 } from "lucide-react";

const PER_PAGE = 20;

export default function PerformancePage() {
  const [stats, setStats] = useState<PerformanceStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isClearing, setIsClearing] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [page, setPage] = useState(1);
  const router = useRouter();

  const fetchPerformance = useCallback(async (pageNum: number) => {
    try {
      setIsLoading(true);
      const response = await alertsApi.getPerformance(pageNum, PER_PAGE);
      setStats(response);
    } catch {
      // Handle error
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
      await fetchPerformance(1);
    }
    init();
  }, [router, fetchPerformance]);

  useEffect(() => {
    if (stats) {
      fetchPerformance(page);
    }
  }, [page, fetchPerformance]);

  if (isLoading && !stats) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="flex items-center gap-2 font-mono text-sm text-terminal-green animate-pulse-green">
          <Activity className="h-4 w-4" />
          Loading...
        </div>
      </div>
    );
  }

  if (!stats) {
    return (
      <main className="p-6">
        <p className="font-mono text-xs text-muted-foreground">Failed to load performance data.</p>
      </main>
    );
  }

  const pagination = stats.pagination;

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

  const handleClearPerformance = async () => {
    try {
      setIsClearing(true);
      await alertsApi.clearPerformance();
      setShowConfirm(false);
      setPage(1);
      await fetchPerformance(1);
    } catch {
      // Handle error
    } finally {
      setIsClearing(false);
    }
  };

  return (
    <main className="p-6">
      <div className="mx-auto max-w-4xl">
        {/* Header */}
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Target className="h-5 w-5 text-terminal-green" />
            <h1 className="font-mono text-lg font-bold text-foreground">Performance Tracking</h1>
            <span className="font-mono text-xs text-muted-foreground">
              {stats.total_alerts} alerts
            </span>
          </div>

          {stats.total_alerts > 0 && (
            <div className="relative">
              {showConfirm ? (
                <div className="flex items-center gap-2 rounded-lg border border-terminal-red/30 bg-terminal-red/5 px-3 py-2">
                  <span className="font-mono text-xs text-terminal-red">Clear all data?</span>
                  <button
                    onClick={handleClearPerformance}
                    disabled={isClearing}
                    className="rounded-md bg-terminal-red/20 px-2 py-1 font-mono text-xs text-terminal-red hover:bg-terminal-red/30 disabled:opacity-50"
                  >
                    {isClearing ? "Clearing..." : "Confirm"}
                  </button>
                  <button
                    onClick={() => setShowConfirm(false)}
                    className="rounded-md border border-terminal-border px-2 py-1 font-mono text-xs text-muted-foreground hover:text-foreground"
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setShowConfirm(true)}
                  className="flex items-center gap-1.5 rounded-md border border-terminal-border px-3 py-1.5 font-mono text-xs text-muted-foreground transition-all hover:border-terminal-red/50 hover:text-terminal-red"
                >
                  <Trash2 className="h-3 w-3" />
                  Clear All
                </button>
              )}
            </div>
          )}
        </div>

        {/* Stats Cards */}
        <div className="mb-6 grid grid-cols-4 gap-4">
          <StatCard label="Total Alerts" value={String(stats.total_alerts)} />
          <StatCard label="Tracked" value={String(stats.tracked)} />
          <StatCard
            label="Win Rate"
            value={`${stats.win_rate}%`}
            valueClass={stats.win_rate >= 50 ? "text-terminal-green" : "text-terminal-red"}
          />
          <StatCard
            label="Avg Return (7d)"
            value={`${stats.avg_return_7d >= 0 ? "+" : ""}${stats.avg_return_7d}%`}
            valueClass={stats.avg_return_7d >= 0 ? "text-terminal-green" : "text-terminal-red"}
          />
        </div>

        {/* Performance Table */}
        {stats.alerts.length === 0 ? (
          <div className="rounded-lg border border-terminal-border bg-terminal-panel p-12 text-center">
            <Target className="mx-auto h-8 w-8 text-muted-foreground" />
            <p className="mt-3 font-mono text-xs text-muted-foreground">
              No performance data yet. Results will appear 1-7 days after alerts are sent.
            </p>
          </div>
        ) : (
          <div className="rounded-lg border border-terminal-border bg-terminal-panel">
            {/* Table Header */}
            <div className="grid grid-cols-12 gap-2 border-b border-terminal-border px-4 py-3 font-mono text-[10px] text-muted-foreground">
              <div className="col-span-2">Symbol</div>
              <div className="col-span-2">Alert Price</div>
              <div className="col-span-2">1D Return</div>
              <div className="col-span-2">3D Return</div>
              <div className="col-span-2">7D Return</div>
              <div className="col-span-2">Date</div>
            </div>

            {/* Rows */}
            {stats.alerts.map((alert, i) => (
              <PerformanceRow key={i} alert={alert} />
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

function PerformanceRow({ alert }: { alert: PerformanceAlert }) {
  return (
    <div className="grid grid-cols-12 items-center gap-2 border-b border-terminal-border/50 px-4 py-3 last:border-0 hover:bg-terminal-dark/50">
      <div className="col-span-2">
        <span className="font-mono text-xs font-semibold text-foreground">
          {alert.stock_symbol}
        </span>
      </div>
      <div className="col-span-2">
        <span className="font-mono text-xs text-muted-foreground">
          {alert.alert_price ? `$${alert.alert_price.toFixed(2)}` : "—"}
        </span>
      </div>
      <div className="col-span-2">
        <ReturnBadge value={alert.return_1d} />
      </div>
      <div className="col-span-2">
        <ReturnBadge value={alert.return_3d} />
      </div>
      <div className="col-span-2">
        <ReturnBadge value={alert.return_7d} />
      </div>
      <div className="col-span-2">
        <span className="font-mono text-[10px] text-muted-foreground">
          {formatDate(alert.sent_at)}
        </span>
      </div>
    </div>
  );
}

function ReturnBadge({ value }: { value: number | null }) {
  if (value === null) {
    return <span className="font-mono text-xs text-muted-foreground">—</span>;
  }

  const isPositive = value >= 0;
  return (
    <span
      className={`inline-flex items-center gap-0.5 font-mono text-xs ${
        isPositive ? "text-terminal-green" : "text-terminal-red"
      }`}
    >
      {isPositive ? (
        <TrendingUp className="h-3 w-3" />
      ) : (
        <TrendingDown className="h-3 w-3" />
      )}
      {isPositive ? "+" : ""}
      {value.toFixed(2)}%
    </span>
  );
}

function StatCard({
  label,
  value,
  valueClass,
}: {
  label: string;
  value: string;
  valueClass?: string;
}) {
  return (
    <div className="rounded-lg border border-terminal-border bg-terminal-panel p-4">
      <p className="font-mono text-xs text-muted-foreground">{label}</p>
      <p className={`mt-1 font-mono text-xl font-bold ${valueClass || "text-terminal-green"}`}>
        {value}
      </p>
    </div>
  );
}
