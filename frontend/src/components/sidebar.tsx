"use client";

import { usePathname, useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { Activity, BarChart3, Bell, Settings, LogOut } from "lucide-react";

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();

  async function handleLogout() {
    const supabase = createClient();
    await supabase.auth.signOut();
    router.push("/login");
  }

  return (
    <aside className="fixed left-0 top-0 z-40 h-screen w-16 border-r border-terminal-border bg-terminal-panel">
      <div className="flex h-full flex-col items-center justify-between py-4">
        <div className="space-y-4">
          <div className="flex h-10 w-10 items-center justify-center">
            <Activity className="h-5 w-5 text-terminal-green" />
          </div>
          <div className="h-px w-8 bg-terminal-border" />
          <NavIcon
            icon={<BarChart3 className="h-5 w-5" />}
            label="Dashboard"
            isActive={pathname === "/dashboard"}
            onClick={() => router.push("/dashboard")}
          />
          <NavIcon
            icon={<Bell className="h-5 w-5" />}
            label="Alerts"
            isActive={pathname === "/alerts"}
            onClick={() => router.push("/alerts")}
          />
          <NavIcon
            icon={<Settings className="h-5 w-5" />}
            label="Settings"
            isActive={pathname === "/settings"}
            onClick={() => router.push("/settings")}
          />
        </div>
        <div>
          <NavIcon
            icon={<LogOut className="h-5 w-5" />}
            label="Logout"
            onClick={handleLogout}
          />
        </div>
      </div>
    </aside>
  );
}

function NavIcon({
  icon,
  isActive,
  label,
  onClick,
}: {
  icon: React.ReactNode;
  isActive?: boolean;
  label: string;
  onClick?: () => void;
}) {
  return (
    <button
      onClick={onClick}
      title={label}
      className={`flex h-10 w-10 items-center justify-center rounded-md transition-all ${
        isActive
          ? "bg-terminal-green/10 text-terminal-green"
          : "text-muted-foreground hover:bg-terminal-border hover:text-terminal-green"
      }`}
    >
      {icon}
    </button>
  );
}
