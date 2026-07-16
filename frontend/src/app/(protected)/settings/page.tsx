"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { userApi, analysisApi, type UserProfile } from "@/lib/api";
import {
  Activity,
  MessageCircle,
  User,
  Bell,
  ExternalLink,
  Copy,
  Check,
  Loader2,
  RefreshCw,
  Newspaper,
} from "lucide-react";
import { useToast } from "@/components/toast";

// Add-friend link for the LINE Official Account that sends alerts. Differs per
// deployment, so it is configured via env rather than hardcoded. Example:
// https://lin.ee/xxxxxxx  or  https://line.me/R/ti/p/@your-basic-id
const LINE_OA_ADD_URL = process.env.NEXT_PUBLIC_LINE_OA_ADD_URL;

export default function SettingsPage() {
  const { success, error: toastError } = useToast();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [lineUserId, setLineUserId] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [linkCode, setLinkCode] = useState<string | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [copied, setCopied] = useState(false);
  const [showManual, setShowManual] = useState(false);
  const [isSendingBriefing, setIsSendingBriefing] = useState(false);
  const router = useRouter();

  const isLineConnected = Boolean(profile?.line_user_id);

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

    try {
      await userApi.connectLine(lineUserId.trim());
      setProfile((prev) => (prev ? { ...prev, line_user_id: lineUserId.trim() } : prev));
      success("LINE account connected successfully");
    } catch {
      toastError("Failed to connect LINE account");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleDisconnectLine() {
    setIsSaving(true);
    try {
      await userApi.disconnectLine();
      setLineUserId("");
      setLinkCode(null);
      setProfile((prev) => (prev ? { ...prev, line_user_id: null } : prev));
      success("LINE account disconnected");
    } catch {
      toastError("Failed to disconnect LINE account");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleGenerateCode() {
    setIsGenerating(true);
    try {
      const res = await userApi.generateLineLinkCode();
      setLinkCode(res.code);
    } catch {
      toastError("Failed to generate linking code");
    } finally {
      setIsGenerating(false);
    }
  }

  // One-tap re-link: drop the current LINE ID and immediately mint a fresh code,
  // landing straight in the "send this code" state (codes are single-use, so a
  // new one is always required).
  async function handleReconnect() {
    setIsSaving(true);
    try {
      await userApi.disconnectLine();
      setLineUserId("");
      setProfile((prev) => (prev ? { ...prev, line_user_id: null } : prev));
      const res = await userApi.generateLineLinkCode();
      setLinkCode(res.code);
    } catch {
      toastError("Failed to start reconnect");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleSendBriefing() {
    setIsSendingBriefing(true);
    try {
      const res = await analysisApi.triggerBriefing();
      if (res.sent_markets.length > 0) {
        success(res.detail);
      } else {
        toastError(res.detail);
      }
    } catch (err) {
      // Surfaces the server's message, incl. the per-user cooldown on 429.
      toastError(err instanceof Error ? err.message : "Failed to send briefing");
    } finally {
      setIsSendingBriefing(false);
    }
  }

  const handleCopyCode = useCallback(() => {
    if (!linkCode) return;
    navigator.clipboard?.writeText(linkCode);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [linkCode]);

  // While a linking code is outstanding, poll the profile so the UI flips to
  // "connected" the moment the webhook redeems the code — no manual refresh.
  useEffect(() => {
    if (!linkCode || isLineConnected) return;

    const poll = setInterval(async () => {
      try {
        const res = await userApi.getProfile();
        if (res.user.line_user_id) {
          setProfile(res.user);
          setLinkCode(null);
          success("LINE account linked successfully");
        }
      } catch {
        // transient — keep polling
      }
    }, 4000);

    // Codes expire server-side (~10 min); stop polling a bit after that.
    const stop = setTimeout(() => clearInterval(poll), 11 * 60 * 1000);

    return () => {
      clearInterval(poll);
      clearTimeout(stop);
    };
  }, [linkCode, isLineConnected, success]);

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
    <main className="p-4 sm:p-6">
      <div className="mx-auto max-w-2xl">
        <h1 className="mb-6 font-mono text-lg font-bold text-foreground">Settings</h1>

        {/* LINE Connection */}
        <section className="rounded-lg border border-terminal-border bg-terminal-panel p-4 sm:p-6">
          <div className="mb-4 flex items-center gap-2">
            <MessageCircle className="h-4 w-4 text-terminal-green" />
            <h2 className="font-mono text-sm font-semibold">LINE Notification</h2>
          </div>

          <p className="mb-4 font-mono text-xs text-muted-foreground">
            Connect your LINE account to receive buy signal notifications.
            Push messages only reach you if you have added our LINE Official
            Account as a friend first.
          </p>

          {/* Step 1 — add the OA as a friend (required for push to work) */}
          <div className="mb-4 rounded-md border border-terminal-border/60 bg-terminal-dark/40 p-4">
            <p className="mb-3 font-mono text-xs font-medium text-foreground">
              <span className="text-terminal-green">Step 1.</span> Add our LINE
              Official Account
            </p>
            {LINE_OA_ADD_URL ? (
              <a
                href={LINE_OA_ADD_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 rounded-md bg-terminal-green px-4 py-2 font-mono text-xs font-medium text-black transition-all hover:bg-terminal-green-glow"
              >
                <MessageCircle className="h-4 w-4" />
                Add LINE Official Account
                <ExternalLink className="h-3 w-3" />
              </a>
            ) : (
              <p className="font-mono text-[11px] text-terminal-red">
                LINE OA link is not configured. Set NEXT_PUBLIC_LINE_OA_ADD_URL.
              </p>
            )}
            <p className="mt-3 font-mono text-[10px] leading-relaxed text-muted-foreground">
              Adding the account as a friend is required — LINE blocks push
              messages to anyone who has not. Then link your account below.
            </p>
          </div>

          {/* Step 2 — link the account */}
          {isLineConnected ? (
            <div className="rounded-md border border-terminal-green/40 bg-terminal-green/5 p-4">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <Check className="h-4 w-4 text-terminal-green" />
                  <span className="font-mono text-xs font-medium text-terminal-green">
                    LINE account linked
                  </span>
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={handleReconnect}
                    disabled={isSaving}
                    title="Disconnect and generate a new linking code"
                    className="inline-flex items-center gap-1.5 rounded-md border border-terminal-border px-3 py-1.5 font-mono text-xs font-medium text-muted-foreground transition-all hover:border-terminal-green/50 hover:text-terminal-green disabled:opacity-50"
                  >
                    {isSaving ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <RefreshCw className="h-3.5 w-3.5" />
                    )}
                    Reconnect
                  </button>
                  <button
                    type="button"
                    onClick={handleDisconnectLine}
                    disabled={isSaving}
                    className="rounded-md border border-terminal-border px-3 py-1.5 font-mono text-xs font-medium text-muted-foreground transition-all hover:border-terminal-red/50 hover:text-terminal-red disabled:opacity-50"
                  >
                    Disconnect
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div className="rounded-md border border-terminal-border/60 bg-terminal-dark/40 p-4">
              <p className="mb-3 font-mono text-xs font-medium text-foreground">
                <span className="text-terminal-green">Step 2.</span> Link your
                account
              </p>

              {linkCode ? (
                <div className="space-y-3">
                  <p className="font-mono text-[11px] leading-relaxed text-muted-foreground">
                    Send this code as a chat message to the Official Account:
                  </p>
                  <div className="flex items-center gap-2">
                    <code className="flex-1 rounded-md border border-terminal-green/40 bg-terminal-dark px-4 py-3 text-center font-mono text-lg font-bold tracking-[0.3em] text-terminal-green">
                      {linkCode}
                    </code>
                    <button
                      type="button"
                      onClick={handleCopyCode}
                      title="Copy code"
                      className="rounded-md border border-terminal-border p-3 text-muted-foreground transition-all hover:border-terminal-green/50 hover:text-terminal-green"
                    >
                      {copied ? (
                        <Check className="h-4 w-4 text-terminal-green" />
                      ) : (
                        <Copy className="h-4 w-4" />
                      )}
                    </button>
                  </div>
                  <div className="flex items-center gap-2 font-mono text-[11px] text-muted-foreground">
                    <Loader2 className="h-3 w-3 animate-spin text-terminal-green" />
                    Waiting for you to send the code… this updates automatically.
                  </div>
                  <p className="font-mono text-[10px] text-muted-foreground">
                    Code expires in about 10 minutes.{" "}
                    <button
                      type="button"
                      onClick={handleGenerateCode}
                      disabled={isGenerating}
                      className="text-terminal-green underline-offset-2 hover:underline disabled:opacity-50"
                    >
                      Generate a new one
                    </button>
                  </p>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={handleGenerateCode}
                  disabled={isGenerating}
                  className="inline-flex items-center gap-2 rounded-md bg-terminal-green px-4 py-2 font-mono text-xs font-medium text-black transition-all hover:bg-terminal-green-glow disabled:opacity-50"
                >
                  {isGenerating ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Generating…
                    </>
                  ) : (
                    "Generate linking code"
                  )}
                </button>
              )}

              {/* Fallback: paste the raw LINE User ID (advanced) */}
              <div className="mt-4 border-t border-terminal-border/50 pt-3">
                {showManual ? (
                  <form onSubmit={handleConnectLine} className="space-y-3">
                    <label
                      htmlFor="lineUserId"
                      className="block font-mono text-[11px] font-medium text-muted-foreground"
                    >
                      Enter LINE User ID manually
                    </label>
                    <input
                      id="lineUserId"
                      type="text"
                      value={lineUserId}
                      onChange={(e) => setLineUserId(e.target.value)}
                      placeholder="U1234567890abcdef..."
                      className="block w-full rounded-md border border-terminal-border bg-terminal-dark px-3 py-2 font-mono text-xs text-foreground placeholder:text-muted-foreground focus:border-terminal-green/50 focus:outline-none focus:ring-1 focus:ring-terminal-green/50"
                    />
                    <button
                      type="submit"
                      disabled={isSaving || !lineUserId.trim()}
                      className="rounded-md border border-terminal-border px-4 py-2 font-mono text-xs font-medium text-muted-foreground transition-all hover:border-terminal-green/50 hover:text-terminal-green disabled:opacity-50"
                    >
                      {isSaving ? "Saving…" : "Connect with User ID"}
                    </button>
                  </form>
                ) : (
                  <button
                    type="button"
                    onClick={() => setShowManual(true)}
                    className="font-mono text-[10px] text-muted-foreground underline-offset-2 hover:text-terminal-green hover:underline"
                  >
                    Advanced: enter LINE User ID manually
                  </button>
                )}
              </div>
            </div>
          )}
        </section>

        {/* Notification Preferences */}
        <section className="mt-4 rounded-lg border border-terminal-border bg-terminal-panel p-4 sm:p-6">
          <div className="mb-4 flex items-center gap-2">
            <Bell className="h-4 w-4 text-terminal-green" />
            <h2 className="font-mono text-sm font-semibold">Notification Preferences</h2>
          </div>

          <p className="mb-4 font-mono text-xs text-muted-foreground">
            Choose the minimum confidence level for receiving alerts.
          </p>

          <div className="flex flex-wrap gap-2">
            {(["All", "Medium", "High"] as const).map((option) => (
              <button
                key={option}
                onClick={async () => {
                  try {
                    await userApi.updateNotificationPreference(option);
                    setProfile((prev) => prev ? { ...prev, min_confidence: option } : prev);
                    success(`Notification preference set to: ${option}`);
                  } catch {
                    toastError("Failed to update preference");
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

        {/* Daily Briefing */}
        <section className="mt-4 rounded-lg border border-terminal-border bg-terminal-panel p-4 sm:p-6">
          <div className="mb-4 flex items-center gap-2">
            <Newspaper className="h-4 w-4 text-terminal-green" />
            <h2 className="font-mono text-sm font-semibold">Daily Briefing</h2>
          </div>

          <p className="mb-4 font-mono text-xs text-muted-foreground">
            A news briefing is sent to your LINE ~1 hour before each market opens
            (SET 09:00 ICT, US 8:30 ET). Send one now to test it.
          </p>

          <button
            type="button"
            onClick={handleSendBriefing}
            disabled={isSendingBriefing || !isLineConnected}
            className="inline-flex items-center gap-2 rounded-md bg-terminal-green px-4 py-2 font-mono text-xs font-medium text-black transition-all hover:bg-terminal-green-glow disabled:opacity-50"
          >
            {isSendingBriefing ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Sending…
              </>
            ) : (
              <>
                <Newspaper className="h-4 w-4" />
                Send briefing now
              </>
            )}
          </button>

          <p className="mt-3 font-mono text-[10px] leading-relaxed text-muted-foreground">
            {isLineConnected
              ? "Covers every market you hold stocks in. Limited to one send every few minutes — it calls the AI and uses your LINE message quota."
              : "Connect your LINE account above to enable this."}
          </p>
        </section>

        {/* Account Info */}
        <section className="mt-4 rounded-lg border border-terminal-border bg-terminal-panel p-4 sm:p-6">
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
