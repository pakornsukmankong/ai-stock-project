import { ImageResponse } from "next/og";

// Social-share preview card (Open Graph). Next renders this JSX to a PNG, so the
// link shows a branded image when pasted into Facebook, X, LINE, Discord, etc.
export const alt = "AI Stock Alert — rule-based signals + AI, delivered to LINE";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const GREEN = "#22c55e";
const RED = "#ef4444";
const BG = "#0a0a0a";

// A small candlestick motif so the card reads as a trading product at a glance.
const CANDLES = [
  { h: 90, o: 30, up: true },
  { h: 140, o: 60, up: false },
  { h: 110, o: 20, up: true },
  { h: 170, o: 40, up: true },
  { h: 130, o: 70, up: false },
  { h: 200, o: 30, up: true },
  { h: 160, o: 50, up: true },
];

export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          background: BG,
          backgroundImage: `radial-gradient(1200px 500px at 15% 0%, rgba(34,197,94,0.18), transparent 60%)`,
          padding: 72,
          fontFamily: "sans-serif",
        }}
      >
        {/* Brand row */}
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div
            style={{
              width: 20,
              height: 20,
              borderRadius: 9999,
              background: GREEN,
              boxShadow: `0 0 24px ${GREEN}`,
            }}
          />
          <span
            style={{
              color: "#8b8b8b",
              fontSize: 26,
              letterSpacing: 6,
              fontWeight: 600,
            }}
          >
            AI STOCK ALERT
          </span>
        </div>

        {/* Headline */}
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div
            style={{
              display: "flex",
              color: GREEN,
              fontSize: 92,
              fontWeight: 800,
              lineHeight: 1.05,
              textShadow: `0 0 40px rgba(34,197,94,0.45)`,
            }}
          >
            Buy signals, on autopilot
          </div>
          <div style={{ display: "flex", color: "#c8c8c8", fontSize: 38, fontWeight: 500 }}>
            Rule-based technical analysis + AI, pushed to your LINE.
          </div>
        </div>

        {/* Footer: candlesticks + domain */}
        <div
          style={{
            display: "flex",
            alignItems: "flex-end",
            justifyContent: "space-between",
          }}
        >
          <div style={{ display: "flex", alignItems: "flex-end", gap: 18, height: 220 }}>
            {CANDLES.map((c, i) => {
              const color = c.up ? GREEN : RED;
              return (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    justifyContent: "flex-end",
                    height: "100%",
                  }}
                >
                  {/* upper wick */}
                  <div style={{ width: 3, height: c.o, background: color, opacity: 0.7 }} />
                  {/* body */}
                  <div style={{ width: 26, height: c.h, background: color, borderRadius: 4 }} />
                  {/* lower wick */}
                  <div style={{ width: 3, height: 24, background: color, opacity: 0.7 }} />
                </div>
              );
            })}
          </div>
          <span style={{ color: "#6b6b6b", fontSize: 28, fontWeight: 500 }}>
            ai-stock-project-five.vercel.app
          </span>
        </div>
      </div>
    ),
    { ...size }
  );
}
