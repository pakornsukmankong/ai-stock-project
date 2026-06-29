"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { Activity } from "lucide-react";
import { useToast } from "@/components/toast";

export default function RegisterPage() {
  const { success, error: toastError } = useToast();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const router = useRouter();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    if (password !== confirmPassword) {
      toastError("Passwords do not match");
      return;
    }

    if (password.length < 6) {
      toastError("Password must be at least 6 characters");
      return;
    }

    setIsLoading(true);

    try {
      const supabase = createClient();
      const { error: authError } = await supabase.auth.signUp({
        email,
        password,
      });

      if (authError) {
        toastError(authError.message);
        return;
      }

      success("Account created successfully");
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
            Create your account
          </p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="space-y-4 rounded-lg border border-terminal-border bg-terminal-panel p-6"
        >
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

          <div>
            <label htmlFor="confirmPassword" className="block font-mono text-xs font-medium text-muted-foreground">
              Confirm Password
            </label>
            <input
              id="confirmPassword"
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
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
            {isLoading ? "Creating account..." : "Create Account"}
          </button>
        </form>

        <p className="text-center font-mono text-xs text-muted-foreground">
          Already have an account?{" "}
          <Link href="/login" className="text-terminal-green hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </main>
  );
}
