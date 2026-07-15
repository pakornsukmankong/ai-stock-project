"use client";

import { useEffect, useState, useRef } from "react";
import { watchlistApi, searchApi, type WatchlistStock, type StockSearchResult } from "@/lib/api";
import { Plus, Trash2, ToggleLeft, ToggleRight, Search } from "lucide-react";
import { useToast } from "@/components/toast";

interface WatchlistPanelProps {
  /**
   * Stocks already fetched by the parent. When provided, the panel skips its own
   * initial request (the dashboard was fetching the same list twice) and reports
   * changes back through onStocksChange so the parent stays in sync.
   */
  stocks?: WatchlistStock[];
  onStocksChange?: (stocks: WatchlistStock[]) => void;
}

export function WatchlistPanel({ stocks: providedStocks, onStocksChange }: WatchlistPanelProps = {}) {
  const isControlled = providedStocks !== undefined;
  const { success, error: toastError } = useToast();
  const [internalStocks, setInternalStocks] = useState<WatchlistStock[]>([]);
  const stocks = providedStocks ?? internalStocks;
  const [newSymbol, setNewSymbol] = useState("");
  const [isLoading, setIsLoading] = useState(!isControlled);
  const [searchResults, setSearchResults] = useState<StockSearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const searchTimeout = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (!isControlled) loadStocks();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isControlled]);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  async function loadStocks() {
    try {
      const response = await watchlistApi.getStocks();
      setInternalStocks(response.stocks);
      onStocksChange?.(response.stocks);
    } catch {
      toastError("Failed to load watchlist");
    } finally {
      setIsLoading(false);
    }
  }

  function handleInputChange(value: string) {
    setNewSymbol(value);

    // Debounce search
    if (searchTimeout.current) {
      clearTimeout(searchTimeout.current);
    }

    if (value.trim().length < 1) {
      setSearchResults([]);
      setShowDropdown(false);
      return;
    }

    searchTimeout.current = setTimeout(async () => {
      setIsSearching(true);
      try {
        const response = await searchApi.searchStocks(value.trim());
        setSearchResults(response.results);
        setShowDropdown(response.results.length > 0);
      } catch {
        setSearchResults([]);
      } finally {
        setIsSearching(false);
      }
    }, 300);
  }

  async function handleSelectSymbol(symbol: string) {
    setNewSymbol(symbol);
    setShowDropdown(false);
    await handleAddStock(undefined, symbol);
  }

  async function handleAddStock(e?: React.FormEvent, symbolOverride?: string) {
    if (e) e.preventDefault();
    const symbol = symbolOverride || newSymbol.trim().toUpperCase();
    if (!symbol) return;

    setShowDropdown(false);

    try {
      await watchlistApi.addStock(symbol);
      setNewSymbol("");
      setSearchResults([]);
      await loadStocks();
      success(`${symbol} added to watchlist`);
    } catch (err) {
      toastError(err instanceof Error ? err.message : `Failed to add ${symbol}`);
    }
  }

  async function handleRemoveStock(symbol: string) {
    try {
      await watchlistApi.removeStock(symbol);
      await loadStocks();
      success(`${symbol} removed from watchlist`);
    } catch {
      toastError(`Failed to remove ${symbol}`);
    }
  }

  async function handleToggleStock(symbol: string, isEnabled: boolean) {
    try {
      await watchlistApi.toggleStock(symbol, !isEnabled);
      await loadStocks();
      success(`${symbol} tracking ${!isEnabled ? "enabled" : "paused"}`);
    } catch {
      toastError(`Failed to update ${symbol}`);
    }
  }

  if (isLoading) {
    return (
      <div className="rounded-lg border border-terminal-border bg-terminal-panel p-6">
        <div className="animate-pulse-green font-mono text-xs text-terminal-green">
          Loading watchlist...
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-terminal-border bg-terminal-panel">
      {/* Add Stock Form */}
      <div className="border-b border-terminal-border p-4">
        <form onSubmit={(e) => handleAddStock(e)} className="flex gap-2">
          <div className="relative flex-1" ref={dropdownRef}>
            <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              value={newSymbol}
              onChange={(e) => handleInputChange(e.target.value)}
              onFocus={() => {
                if (searchResults.length > 0) setShowDropdown(true);
              }}
              placeholder="Search stocks (e.g., AAPL, Tesla)"
              className="w-full rounded-md border border-terminal-border bg-terminal-dark py-2 pl-9 pr-3 font-mono text-xs text-foreground placeholder:text-muted-foreground focus:border-terminal-green/50 focus:outline-none focus:ring-1 focus:ring-terminal-green/50"
            />

            {/* Autocomplete Dropdown */}
            {showDropdown && (
              <div className="absolute left-0 right-0 top-full z-50 mt-1 max-h-60 overflow-y-auto rounded-md border border-terminal-border bg-terminal-panel shadow-lg">
                {isSearching ? (
                  <div className="p-3 font-mono text-xs text-muted-foreground">
                    Searching...
                  </div>
                ) : (
                  searchResults.map((result) => (
                    <button
                      key={result.symbol}
                      type="button"
                      onClick={() => handleSelectSymbol(result.symbol)}
                      className="flex w-full items-center justify-between px-3 py-2 text-left transition-colors hover:bg-terminal-dark"
                    >
                      <div>
                        <span className="font-mono text-xs font-semibold text-foreground">
                          {result.symbol}
                        </span>
                        <span className="ml-2 font-mono text-[10px] text-muted-foreground">
                          {result.name}
                        </span>
                      </div>
                      <span className="font-mono text-[10px] text-muted-foreground">
                        {result.exchange}
                      </span>
                    </button>
                  ))
                )}
              </div>
            )}
          </div>
          <button
            type="submit"
            className="flex items-center gap-1 rounded-md bg-terminal-green/10 px-3 py-2 font-mono text-xs font-medium text-terminal-green transition-all hover:bg-terminal-green/20"
          >
            <Plus className="h-3.5 w-3.5" />
            Add
          </button>
        </form>
      </div>

      {/* Stock List */}
      <div className="divide-y divide-terminal-border">
        {stocks.length === 0 ? (
          <div className="p-8 text-center">
            <p className="font-mono text-xs text-muted-foreground">
              No stocks in your watchlist. Search and add one above.
            </p>
          </div>
        ) : (
          <>
            {/* Table Header */}
            <div className="grid grid-cols-12 gap-2 px-4 py-2 font-mono text-xs text-muted-foreground">
              <div className="col-span-4">Symbol</div>
              <div className="col-span-4">Status</div>
              <div className="col-span-4 text-right">Actions</div>
            </div>
            {stocks.map((stock) => (
              <div
                key={stock.id}
                className="grid grid-cols-12 items-center gap-2 px-4 py-3 transition-colors hover:bg-terminal-dark/50"
              >
                <div className="col-span-4">
                  <span className="font-mono text-sm font-semibold text-foreground">
                    {stock.symbol}
                  </span>
                </div>
                <div className="col-span-4">
                  <span
                    className={`inline-flex items-center gap-1.5 font-mono text-xs ${
                      stock.is_enabled ? "text-terminal-green" : "text-muted-foreground"
                    }`}
                  >
                    <span
                      className={`h-1.5 w-1.5 rounded-full ${
                        stock.is_enabled ? "bg-terminal-green animate-pulse-green" : "bg-muted-foreground"
                      }`}
                    />
                    {stock.is_enabled ? "Tracking" : "Paused"}
                  </span>
                </div>
                <div className="col-span-4 flex items-center justify-end gap-2">
                  <button
                    onClick={() => handleToggleStock(stock.symbol, stock.is_enabled)}
                    className="rounded p-1 text-muted-foreground transition-colors hover:bg-terminal-border hover:text-foreground"
                    aria-label={stock.is_enabled ? "Disable tracking" : "Enable tracking"}
                  >
                    {stock.is_enabled ? (
                      <ToggleRight className="h-4 w-4 text-terminal-green" />
                    ) : (
                      <ToggleLeft className="h-4 w-4" />
                    )}
                  </button>
                  <button
                    onClick={() => handleRemoveStock(stock.symbol)}
                    className="rounded p-1 text-muted-foreground transition-colors hover:bg-terminal-red/10 hover:text-terminal-red"
                    aria-label="Remove stock"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
