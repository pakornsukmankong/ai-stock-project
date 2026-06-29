"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { CheckCircle2, XCircle, Info, X } from "lucide-react";

type ToastType = "success" | "error" | "info";

interface Toast {
  id: number;
  type: ToastType;
  message: string;
}

interface ToastContextValue {
  toast: (message: string, type?: ToastType) => void;
  success: (message: string) => void;
  error: (message: string) => void;
  info: (message: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const DURATION = 4000;

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return ctx;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const remove = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const toast = useCallback(
    (message: string, type: ToastType = "info") => {
      const id = Date.now() + Math.random();
      setToasts((prev) => [...prev, { id, type, message }]);
      setTimeout(() => remove(id), DURATION);
    },
    [remove]
  );

  const value = useMemo<ToastContextValue>(
    () => ({
      toast,
      success: (m: string) => toast(m, "success"),
      error: (m: string) => toast(m, "error"),
      info: (m: string) => toast(m, "info"),
    }),
    [toast]
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-full max-w-xs flex-col gap-2">
        {toasts.map((t) => (
          <ToastItem key={t.id} toast={t} onClose={() => remove(t.id)} />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

const STYLES: Record<
  ToastType,
  { container: string; icon: ReactNode }
> = {
  success: {
    container: "border-terminal-green/40 bg-terminal-green/10 text-terminal-green",
    icon: <CheckCircle2 className="h-4 w-4 shrink-0" />,
  },
  error: {
    container: "border-terminal-red/40 bg-terminal-red/10 text-terminal-red",
    icon: <XCircle className="h-4 w-4 shrink-0" />,
  },
  info: {
    container: "border-terminal-border bg-terminal-panel text-foreground",
    icon: <Info className="h-4 w-4 shrink-0 text-terminal-green" />,
  },
};

function ToastItem({ toast, onClose }: { toast: Toast; onClose: () => void }) {
  const style = STYLES[toast.type];
  return (
    <div
      role="status"
      className={`pointer-events-auto flex items-start gap-2 rounded-md border p-3 font-mono text-xs shadow-lg animate-toast-in ${style.container}`}
    >
      {style.icon}
      <span className="flex-1 break-words leading-relaxed">{toast.message}</span>
      <button
        onClick={onClose}
        aria-label="Dismiss"
        className="shrink-0 opacity-60 transition-opacity hover:opacity-100"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
