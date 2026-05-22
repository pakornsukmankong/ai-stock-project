import Link from "next/link";
import { Bell, Shield, Zap, Activity } from "lucide-react";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-background">
      {/* Header */}
      <header className="border-b border-terminal-border bg-terminal-dark/80 backdrop-blur-sm">
        <div className="container mx-auto flex items-center justify-between px-4 py-4">
          <div className="flex items-center gap-2">
            <Activity className="h-6 w-6 text-terminal-green" />
            <span className="font-mono text-xl font-bold text-terminal-green text-glow">
              AI Stock Alert
            </span>
          </div>
          <nav className="flex items-center gap-4">
            <Link
              href="/login"
              className="font-mono text-sm text-muted-foreground transition-colors hover:text-terminal-green"
            >
              Login
            </Link>
            <Link
              href="/register"
              className="glow-green rounded-md bg-terminal-green px-4 py-2 font-mono text-sm font-medium text-black transition-all hover:bg-terminal-green-glow"
            >
              Get Started
            </Link>
          </nav>
        </div>
      </header>

      {/* Hero */}
      <section className="container mx-auto px-4 py-24 text-center">
        <div className="mx-auto mb-6 flex items-center justify-center gap-2">
          <div className="h-2 w-2 animate-pulse-green rounded-full bg-terminal-green" />
          <span className="font-mono text-xs uppercase tracking-widest text-terminal-green">
            Live Market Analysis
          </span>
        </div>
        <h1 className="font-mono text-4xl font-bold tracking-tight sm:text-6xl">
          AI-Powered Stock
          <span className="text-terminal-green text-glow"> Buy Alerts</span>
        </h1>
        <p className="mx-auto mt-6 max-w-2xl text-lg text-muted-foreground">
          Get notified via LINE when AI detects potential buy opportunities.
          Technical analysis meets artificial intelligence for smarter trading decisions.
        </p>
        <div className="mt-10 flex items-center justify-center gap-4">
          <Link
            href="/register"
            className="glow-green rounded-md bg-terminal-green px-6 py-3 font-mono text-sm font-medium text-black transition-all hover:bg-terminal-green-glow"
          >
            Start Free →
          </Link>
          <Link
            href="#features"
            className="rounded-md border border-terminal-border px-6 py-3 font-mono text-sm font-medium text-muted-foreground transition-all hover:border-terminal-green/50 hover:text-terminal-green"
          >
            Learn More
          </Link>
        </div>

        {/* Terminal-style stats */}
        <div className="mx-auto mt-16 grid max-w-3xl grid-cols-3 gap-4">
          <StatCard label="Signals/Day" value="120+" />
          <StatCard label="Accuracy" value="87%" />
          <StatCard label="Avg Response" value="<5min" />
        </div>
      </section>

      {/* Features */}
      <section id="features" className="container mx-auto px-4 py-16">
        <div className="grid gap-4 md:grid-cols-3">
          <FeatureCard
            icon={<Zap className="h-6 w-6 text-terminal-green" />}
            title="Real-time Analysis"
            description="Technical indicators calculated every 5 minutes. RSI, MACD, EMA, volume analysis, and support/resistance detection."
          />
          <FeatureCard
            icon={<Shield className="h-6 w-6 text-terminal-green" />}
            title="Smart Filtering"
            description="Rule-based signal engine filters noise. AI only activates when multiple buy conditions align."
          />
          <FeatureCard
            icon={<Bell className="h-6 w-6 text-terminal-green" />}
            title="LINE Notifications"
            description="Instant push notifications to your LINE account with clear buy reasons and confidence levels."
          />
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-terminal-border py-8">
        <div className="container mx-auto px-4 text-center">
          <p className="font-mono text-xs text-muted-foreground">
            © 2026 Pakorn Sukmankong. All rights reserved.
          </p>
        </div>
      </footer>
    </main>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-terminal-border bg-terminal-panel p-4">
      <p className="font-mono text-2xl font-bold text-terminal-green text-glow">
        {value}
      </p>
      <p className="mt-1 font-mono text-xs text-muted-foreground">{label}</p>
    </div>
  );
}

function FeatureCard({
  icon,
  title,
  description,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
}) {
  return (
    <div className="rounded-lg border border-terminal-border bg-terminal-panel p-6 transition-all hover:border-terminal-green/30 hover:border-glow">
      <div className="mb-4">{icon}</div>
      <h3 className="mb-2 font-mono text-sm font-semibold text-foreground">{title}</h3>
      <p className="text-sm text-muted-foreground">{description}</p>
    </div>
  );
}
