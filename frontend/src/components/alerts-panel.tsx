"use client";

import { useEffect, useState } from "react";
import { alertsApi, type Alert } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import { Bell, ArrowUpRight } from "lucide-react";

export function AlertsPanel() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function loadAlerts() {
      try {
        const response = await alertsApi.getRecent();
        setAlerts(response.alerts);
      } catch {
        // Silently handle error
      } finally {
        setIsLoading(false);
      }
    }

    loadAlerts();
  }, []);

  if (isLoading) {
    return (
      <div className="rounded-lg border border-terminal-border bg-terminal-panel p-6">
        <div className="animate-pulse-green font-mono text-xs text-terminal-green">
          Loading alerts...
        </div>
      </div>
    );
  }

  if (alerts.length === 0) {
    return (
      <div className="rounded-lg border border-terminal-border bg-terminal-panel p-8 text-center">
        <Bell className="mx-auto h-6 w-6 text-muted-foreground" />
        <p className="mt-2 font-mono text-xs text-muted-foreground">
          No alerts yet. Signals will appear here when buy conditions are detected.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {alerts.map((alert) => (
        <div
          key={alert.id}
          className="rounded-lg border border-terminal-border bg-terminal-panel p-4 transition-all hover:border-terminal-green/30"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <ArrowUpRight className="h-3.5 w-3.5 text-terminal-green" />
              <span className="font-mono text-sm font-bold text-foreground">
                {alert.stock_symbol}
              </span>
              <span className="rounded bg-terminal-green/10 px-1.5 py-0.5 font-mono text-[10px] font-medium text-terminal-green">
                {alert.signal_type}
              </span>
            </div>
            <span className="font-mono text-[10px] text-muted-foreground">
              {formatDate(alert.sent_at)}
            </span>
          </div>

          <p className="mt-2 font-mono text-xs leading-relaxed text-muted-foreground">
            {alert.ai_summary}
          </p>

          {alert.confidence && (
            <div className="mt-2 flex items-center gap-2">
              <span className="font-mono text-[10px] text-muted-foreground">Confidence:</span>
              <span
                className={`font-mono text-[10px] font-medium ${
                  alert.confidence === "High"
                    ? "text-terminal-green"
                    : alert.confidence === "Medium"
                    ? "text-yellow-500"
                    : "text-muted-foreground"
                }`}
              >
                {alert.confidence}
              </span>
              <ConfidenceBar level={alert.confidence} />
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function ConfidenceBar({ level }: { level: string }) {
  const bars = level === "High" ? 3 : level === "Medium" ? 2 : 1;
  return (
    <div className="flex gap-0.5">
      {[1, 2, 3].map((i) => (
        <div
          key={i}
          className={`h-2 w-1 rounded-sm ${
            i <= bars ? "bg-terminal-green" : "bg-terminal-border"
          }`}
        />
      ))}
    </div>
  );
}
