import { createClient } from "@/lib/supabase/client";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ApiOptions {
  method?: string;
  body?: unknown;
  headers?: Record<string, string>;
}

async function getAuthToken(): Promise<string> {
  const supabase = createClient();
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;

  if (!token) {
    throw new Error("Not authenticated");
  }

  return token;
}

async function apiRequest<T>(endpoint: string, options: ApiOptions = {}): Promise<T> {
  const { method = "GET", body, headers = {} } = options;

  const token = await getAuthToken();

  const response = await fetch(`${API_URL}/api/v1${endpoint}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...headers,
    },
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(error.detail || `API Error: ${response.status}`);
  }

  return response.json();
}

// Watchlist API
export const watchlistApi = {
  getStocks: () =>
    apiRequest<{ stocks: WatchlistStock[] }>("/watchlist/stocks"),

  addStock: (symbol: string) =>
    apiRequest<{ stock: WatchlistStock }>("/watchlist/stocks", {
      method: "POST",
      body: { symbol, is_enabled: true },
    }),

  removeStock: (symbol: string) =>
    apiRequest(`/watchlist/stocks/${symbol}`, {
      method: "DELETE",
    }),

  toggleStock: (symbol: string, isEnabled: boolean) =>
    apiRequest(`/watchlist/stocks/${symbol}/toggle?is_enabled=${isEnabled}`, {
      method: "PATCH",
    }),
};

// Alerts API
export const alertsApi = {
  getAlerts: (limit = 20, offset = 0) =>
    apiRequest<{ alerts: Alert[]; total: number }>(
      `/alerts/?limit=${limit}&offset=${offset}`
    ),

  getRecent: () =>
    apiRequest<{ alerts: Alert[] }>("/alerts/recent"),

  getStats: () =>
    apiRequest<{ signals_today: number }>("/alerts/stats"),
};

// Market API
export const marketApi = {
  getChartData: (symbol: string, interval = "1d", period = "3mo") =>
    apiRequest<ChartData>(
      `/market/chart/${symbol}?interval=${interval}&period=${period}`
    ),
};

// Search API
export const searchApi = {
  searchStocks: (query: string) =>
    apiRequest<{ results: StockSearchResult[] }>(`/search/stocks?q=${encodeURIComponent(query)}`),
};

// User API
export const userApi = {
  getProfile: () =>
    apiRequest<{ user: UserProfile }>("/user/profile"),

  connectLine: (lineUserId: string) =>
    apiRequest("/user/connect-line", {
      method: "POST",
      body: { line_user_id: lineUserId },
    }),

  disconnectLine: () =>
    apiRequest("/user/disconnect-line", {
      method: "DELETE",
    }),

  updateNotificationPreference: (minConfidence: string) =>
    apiRequest("/user/notification-preference", {
      method: "PATCH",
      body: { min_confidence: minConfidence },
    }),
};

// Types
export interface WatchlistStock {
  id: string;
  symbol: string;
  is_enabled: boolean;
  created_at: string;
}

export interface Alert {
  id: string;
  user_id: string;
  stock_symbol: string;
  signal_type: string;
  ai_summary: string;
  confidence: string;
  reasons: string[];
  sent_at: string;
}

export interface UserProfile {
  id: string;
  email: string;
  line_user_id: string | null;
  is_active: boolean;
  min_confidence: string;
}

export interface CandleData {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface VolumeData {
  time: number;
  value: number;
  color: string;
}

export interface ChartData {
  symbol: string;
  candles: CandleData[];
  volumes: VolumeData[];
}

export interface StockSearchResult {
  symbol: string;
  name: string;
  exchange: string;
  type: string;
}
