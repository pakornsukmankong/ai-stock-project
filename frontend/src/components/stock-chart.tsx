"use client";

import { useEffect, useRef, useState } from "react";
import { createChart, type IChartApi, ColorType } from "lightweight-charts";
import { marketApi, type ChartData } from "@/lib/api";
import { Activity } from "lucide-react";

interface StockChartProps {
  symbol: string;
}

type TimeInterval = "5m" | "15m" | "1h" | "4h" | "1d" | "1wk";
type TimePeriod = "1d" | "5d" | "1mo" | "3mo" | "6mo" | "1y" | "2y";

interface TimeOption {
  label: string;
  interval: TimeInterval;
  period: TimePeriod;
}

const TIME_OPTIONS: TimeOption[] = [
  { label: "5min", interval: "5m", period: "1d" },
  { label: "15min", interval: "15m", period: "5d" },
  { label: "1H", interval: "1h", period: "1mo" },
  { label: "4H", interval: "4h", period: "3mo" },
  { label: "1D", interval: "1d", period: "1y" },
  { label: "1W", interval: "1wk", period: "2y" },
];

type ChartType = "candle" | "line" | "area";

export function StockChart({ symbol }: StockChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [lastPrice, setLastPrice] = useState<number | null>(null);
  const [priceChange, setPriceChange] = useState<number | null>(null);
  const [selectedTime, setSelectedTime] = useState<TimeOption>(TIME_OPTIONS[3]); // 3M default
  const [chartType, setChartType] = useState<ChartType>("candle");

  useEffect(() => {
    if (!chartContainerRef.current) return;

    // Remove existing chart
    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    // Create chart
    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#0a0a0a" },
        textColor: "#8b8b8b",
      },
      grid: {
        vertLines: { color: "#1a1a1a" },
        horzLines: { color: "#1a1a1a" },
      },
      width: chartContainerRef.current.clientWidth,
      height: 400,
      crosshair: {
        vertLine: { color: "#22c55e", width: 1, style: 2 },
        horzLine: { color: "#22c55e", width: 1, style: 2 },
      },
      timeScale: {
        borderColor: "#1f1f1f",
        timeVisible: true,
        secondsVisible: false,
      },
      rightPriceScale: {
        borderColor: "#1f1f1f",
      },
    });

    chartRef.current = chart;

    // Add series based on chart type
    let mainSeries: any;

    if (chartType === "candle") {
      mainSeries = chart.addCandlestickSeries({
        upColor: "#22c55e",
        downColor: "#ef4444",
        borderUpColor: "#22c55e",
        borderDownColor: "#ef4444",
        wickUpColor: "#22c55e",
        wickDownColor: "#ef4444",
      });
    } else if (chartType === "line") {
      mainSeries = chart.addLineSeries({
        color: "#22c55e",
        lineWidth: 2,
      });
    } else {
      mainSeries = chart.addAreaSeries({
        topColor: "rgba(34, 197, 94, 0.3)",
        bottomColor: "rgba(34, 197, 94, 0.02)",
        lineColor: "#22c55e",
        lineWidth: 2,
      });
    }

    // Volume series
    const volumeSeries = chart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "",
    });

    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.85, bottom: 0 },
    });

    // Fetch data
    async function loadData() {
      setIsLoading(true);
      setError("");

      try {
        const data = await marketApi.getChartData(
          symbol,
          selectedTime.interval,
          selectedTime.period,
        );

        if (data.candles.length === 0) {
          setError("No chart data available");
          return;
        }

        if (chartType === "candle") {
          mainSeries.setData(data.candles as any);
        } else {
          // Line/Area uses close price
          const lineData = data.candles.map((c) => ({
            time: c.time,
            value: c.close,
          }));
          mainSeries.setData(lineData as any);
        }

        volumeSeries.setData(data.volumes as any);

        // Calculate price info
        const latest = data.candles[data.candles.length - 1];
        const first = data.candles[0];
        setLastPrice(latest.close);
        setPriceChange(((latest.close - first.close) / first.close) * 100);

        chart.timeScale().fitContent();
      } catch (err) {
        if (err instanceof Error) {
          setError(err.message);
        }
      } finally {
        setIsLoading(false);
      }
    }

    loadData();

    // Resize handler
    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };

    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
      chartRef.current = null;
    };
  }, [symbol, selectedTime, chartType]);

  return (
    <div className="rounded-lg border border-terminal-border bg-terminal-panel">
      {/* Chart Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-terminal-border px-4 py-3">
        <div className="flex items-center gap-3">
          <span className="font-mono text-sm font-bold text-foreground">{symbol}</span>
          {lastPrice !== null && (
            <span className="font-mono text-sm text-foreground">
              ${lastPrice.toFixed(2)}
            </span>
          )}
          {priceChange !== null && (
            <span
              className={`font-mono text-xs ${
                priceChange >= 0 ? "text-terminal-green" : "text-terminal-red"
              }`}
            >
              {priceChange >= 0 ? "+" : ""}
              {priceChange.toFixed(2)}%
            </span>
          )}
        </div>

        <div className="flex items-center gap-3">
          {/* Chart Type Selector */}
          <div className="flex rounded-md border border-terminal-border">
            {(["candle", "line", "area"] as ChartType[]).map((type) => (
              <button
                key={type}
                onClick={() => setChartType(type)}
                className={`px-2 py-1 font-mono text-[10px] capitalize transition-all ${
                  chartType === type
                    ? "bg-terminal-green/10 text-terminal-green"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {type}
              </button>
            ))}
          </div>

          {/* Time Period Selector */}
          <div className="flex rounded-md border border-terminal-border">
            {TIME_OPTIONS.map((option) => (
              <button
                key={option.label}
                onClick={() => setSelectedTime(option)}
                className={`px-2 py-1 font-mono text-[10px] transition-all ${
                  selectedTime.label === option.label
                    ? "bg-terminal-green/10 text-terminal-green"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Chart */}
      <div className="relative">
        {isLoading && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-terminal-panel/80">
            <div className="flex items-center gap-2 font-mono text-xs text-terminal-green animate-pulse-green">
              <Activity className="h-4 w-4" />
              Loading chart...
            </div>
          </div>
        )}
        {error && !isLoading && (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-terminal-panel">
            <p className="font-mono text-xs text-muted-foreground">{error}</p>
          </div>
        )}
        <div ref={chartContainerRef} />
      </div>
    </div>
  );
}
