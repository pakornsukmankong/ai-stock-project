"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { userApi, type UserProfile } from "@/lib/api";
import { Activity, MessageCircle, User, Bell } from "lucide-react";

export default function SettingsPage() {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [lineUserId, setLineUserId] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState("");
  const router = useRouter();

  useEffect(() => {
    async function loadProfile() {
      const supabase = createClient();
      const { data: { user } } = await supabase.auth.getUser();

      if (!user) {
        router.push("/login");
        return;
      }

      try {
        const response = await userApi.getProfile();
        setProfile(response.user);
        setLineUserId(response.user.line_user_id || "");
      } catch {
        // Handle error
      } finally {
        setIsLoading(false);
      }
    }

    loadProfile();
  }, [router]);

  async function handleConnectLine(e: React.FormEvent) {
    e.preventDefault();
    if (!lineUserId.trim()) return;

    setIsSaving(true);
    setMessage("");

    try {
      await userApi.connectLine(lineUserId.trim());
      setMessage("LINE account connected successfully");
    } catch {
      setMessage("Failed to connect LINE account");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleDisconnectLine() {
    setIsSaving(true);
    try {
      await userApi.disconnectLine();
      setLineUserId("");
      setMessage("LINE account disconnected");
    } catch {
      setMessage("Failed to disconnect LINE account");
    } finally {
      setIsSaving(false);
    }
  }

  if (isLoading) {
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
      <div className="mx-auto max-w-2xl">
        <h1 className="mb-6 font-mono text-lg font-bold text-foreground">Settings</h1>

        {/* LINE Connection */}
        <section className="rounded-lg border border-terminal-border bg-terminal-panel p-6">
          <div className="mb-4 flex items-center gap-2">
            <MessageCircle className="h-4 w-4 text-terminal-green" />
            <h2 className="font-mono text-sm font-semibold">LINE Notification</h2>
          </div>

          <p className="mb-4 font-mono text-xs text-muted-foreground">
            Connect your LINE account to receive buy signal notifications.
            You need your LINE User ID from the LINE Official Account.
          </p>

          {message && (
            <div className="mb-4 rounded-md border border-terminal-green/30 bg-terminal-green/5 p-3 font-mono text-xs text-terminal-green">
              {message}
            </div>
          )}

          <form onSubmit={handleConnectLine} className="space-y-4">
            <div>
              <label htmlFor="lineUserId" className="block font-mono text-xs font-medium text-muted-foreground">
                LINE User ID
              </label>
              <input
                id="lineUserId"
                type="text"
                value={lineUserId}
                onChange={(e) => setLineUserId(e.target.value)}
                placeholder="U1234567890abcdef..."
                className="mt-1 block w-full rounded-md border border-terminal-border bg-terminal-dark px-3 py-2 font-mono text-xs text-foreground placeholder:text-muted-foreground focus:border-terminal-green/50 focus:outline-none focus:ring-1 focus:ring-terminal-green/50"
              />
            </div>

            <div className="flex gap-2">
              <button
                type="submit"
                disabled={isSaving || !lineUserId.trim()}
                className="rounded-md bg-terminal-green px-4 py-2 font-mono text-xs font-medium text-black transition-all hover:bg-terminal-green-glow disabled:opacity-50"
              >
                {isSaving ? "Saving..." : "Connect LINE"}
              </button>

              {profile?.line_user_id && (
                <button
                  type="button"
                  onClick={handleDisconnectLine}
                  disabled={isSaving}
                  className="rounded-md border border-terminal-border px-4 py-2 font-mono text-xs font-medium text-muted-foreground transition-all hover:border-terminal-red/50 hover:text-terminal-red disabled:opacity-50"
                >
                  Disconnect
                </button>
              )}
            </div>
          </form>
        </section>

        {/* Notification Preferences */}
        <section className="mt-4 rounded-lg border border-terminal-border bg-terminal-panel p-6">
          <div className="mb-4 flex items-center gap-2">
            <Bell className="h-4 w-4 text-terminal-green" />
            <h2 className="font-mono text-sm font-semibold">Notification Preferences</h2>
          </div>

          <p className="mb-4 font-mono text-xs text-muted-foreground">
            Choose the minimum confidence level for receiving alerts.
          </p>

          <div className="flex gap-2">
            {(["All", "Medium", "High"] as const).map((option) => (
              <button
                key={option}
                onClick={async () => {
                  try {
                    await userApi.updateNotificationPreference(option);
                    setProfile((prev) => prev ? { ...prev, min_confidence: option } : prev);
                    setMessage(`Notification preference set to: ${option}`);
                  } catch {
                    setMessage("Failed to update preference");
                  }
                }}
                className={`rounded-md px-4 py-2 font-mono text-xs font-medium transition-all ${
                  profile?.min_confidence === option
                    ? "bg-terminal-green text-black"
                    : "border border-terminal-border text-muted-foreground hover:border-terminal-green/50 hover:text-terminal-green"
                }`}
              >
                {option === "All" ? "All Signals" : `${option}+ Only`}
              </button>
            ))}
          </div>

          <p className="mt-3 font-mono text-[10px] text-muted-foreground">
            {profile?.min_confidence === "All" && "You will receive all buy signal alerts."}
            {profile?.min_confidence === "Medium" && "You will receive Medium and High confidence alerts."}
            {profile?.min_confidence === "High" && "You will only receive High confidence alerts."}
          </p>
        </section>

        {/* Account Info */}
        <section className="mt-4 rounded-lg border border-terminal-border bg-terminal-panel p-6">
          <div className="mb-4 flex items-center gap-2">
            <User className="h-4 w-4 text-terminal-green" />
            <h2 className="font-mono text-sm font-semibold">Account</h2>
          </div>
          <div className="space-y-3">
            <InfoRow label="Email" value={profile?.email || "—"} />
            <InfoRow
              label="Status"
              value={profile?.is_active ? "Active" : "Inactive"}
              valueClass={profile?.is_active ? "text-terminal-green" : "text-terminal-red"}
            />
            <InfoRow
              label="LINE"
              value={profile?.line_user_id ? "Connected" : "Not connected"}
              valueClass={profile?.line_user_id ? "text-terminal-green" : "text-muted-foreground"}
            />
          </div>
        </section>
      </div>
    </main>
  );
}

function InfoRow({
  label,
  value,
  valueClass,
}: {
  label: string;
  value: string;
  valueClass?: string;
}) {
  return (
    <div className="flex items-center justify-between border-b border-terminal-border/50 pb-2">
      <span className="font-mono text-xs text-muted-foreground">{label}</span>
      <span className={`font-mono text-xs ${valueClass || "text-foreground"}`}>{value}</span>
    </div>
  );
}
