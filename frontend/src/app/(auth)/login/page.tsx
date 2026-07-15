"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { Activity } from "lucide-react";
import { useToast } from "@/components/toast";
import { GoogleSignInButton } from "@/components/google-sign-in-button";

export default function LoginPage() {
  const { success, error: toastError } = useToast();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const router = useRouter();

  // Surface a failed OAuth round-trip (the callback route redirects here with
  // ?error=oauth) without pulling in useSearchParams / a Suspense boundary.
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("error") === "oauth") {
      toastError("Google sign-in failed. Please try again.");
      window.history.replaceState({}, "", "/login");
    }
  }, [toastError]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setIsLoading(true);

    try {
      const supabase = createClient();
      const { error: authError } = await supabase.auth.signInWithPassword({
        email,
        password,
      });

      if (authError) {
        toastError(authError.message);
        return;
      }

      success("Signed in successfully");
      router.push("/dashboard");
    } catch {
      toastError("An unexpected error occurred");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-terminal-dark px-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="text-center">
          <div className="flex items-center justify-center gap-2">
            <Activity className="h-6 w-6 text-terminal-green" />
            <span className="font-mono text-xl font-bold text-terminal-green text-glow">
              AI Stock Alert
            </span>
          </div>
          <p className="mt-2 font-mono text-xs text-muted-foreground">
            Sign in to your account
          </p>
        </div>

        <div className="space-y-4 rounded-lg border border-terminal-border bg-terminal-panel p-6">
          <GoogleSignInButton label="Sign in with Google" />

          <div className="flex items-center gap-3">
            <div className="h-px flex-1 bg-terminal-border" />
            <span className="font-mono text-[10px] uppercase text-muted-foreground">
              or
            </span>
            <div className="h-px flex-1 bg-terminal-border" />
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="email" className="block font-mono text-xs font-medium text-muted-foreground">
                Email
              </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="mt-1 block w-full rounded-md border border-terminal-border bg-terminal-dark px-3 py-2 font-mono text-sm text-foreground placeholder:text-muted-foreground focus:border-terminal-green/50 focus:outline-none focus:ring-1 focus:ring-terminal-green/50"
              placeholder="you@example.com"
            />
          </div>

          <div>
            <label htmlFor="password" className="block font-mono text-xs font-medium text-muted-foreground">
              Password
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="mt-1 block w-full rounded-md border border-terminal-border bg-terminal-dark px-3 py-2 font-mono text-sm text-foreground placeholder:text-muted-foreground focus:border-terminal-green/50 focus:outline-none focus:ring-1 focus:ring-terminal-green/50"
              placeholder="••••••••"
            />
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="glow-green w-full rounded-md bg-terminal-green px-4 py-2 font-mono text-sm font-medium text-black transition-all hover:bg-terminal-green-glow disabled:opacity-50"
          >
            {isLoading ? "Connecting..." : "Sign In"}
          </button>
          </form>
        </div>

        <p className="text-center font-mono text-xs text-muted-foreground">
          Don&apos;t have an account?{" "}
          <Link href="/register" className="text-terminal-green hover:underline">
            Sign up
          </Link>
        </p>
      </div>
    </main>
  );
}
