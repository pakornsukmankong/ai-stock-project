"use client";

import { useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { useToast } from "@/components/toast";

/**
 * Starts Supabase's Google OAuth flow. On success the browser is redirected to
 * Google and then back to /auth/callback, which finalizes the session — so this
 * button never resolves "in place"; it just kicks off the redirect.
 */
export function GoogleSignInButton({ label = "Continue with Google" }: { label?: string }) {
  const { error: toastError } = useToast();
  const [isLoading, setIsLoading] = useState(false);

  async function handleGoogle() {
    setIsLoading(true);
    try {
      const supabase = createClient();
      const { error } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: {
          redirectTo: `${window.location.origin}/auth/callback?next=/dashboard`,
        },
      });
      if (error) {
        toastError(error.message);
        setIsLoading(false);
      }
      // On success the page navigates away to Google; no further UI here.
    } catch {
      toastError("Could not start Google sign-in");
      setIsLoading(false);
    }
  }

  return (
    <button
      type="button"
      onClick={handleGoogle}
      disabled={isLoading}
      className="flex w-full items-center justify-center gap-2 rounded-md border border-terminal-border bg-terminal-dark px-4 py-2 font-mono text-sm font-medium text-foreground transition-all hover:border-terminal-green/50 disabled:opacity-50"
    >
      <GoogleLogo />
      {isLoading ? "Redirecting…" : label}
    </button>
  );
}

function GoogleLogo() {
  return (
    <svg className="h-4 w-4" viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1Z"
      />
      <path
        fill="#34A853"
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23Z"
      />
      <path
        fill="#FBBC05"
        d="M5.84 14.1a6.6 6.6 0 0 1 0-4.2V7.06H2.18a11 11 0 0 0 0 9.88l3.66-2.84Z"
      />
      <path
        fill="#EA4335"
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1A11 11 0 0 0 2.18 7.06l3.66 2.84C6.71 7.3 9.14 5.38 12 5.38Z"
      />
    </svg>
  );
}
