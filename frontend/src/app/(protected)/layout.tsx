import { Sidebar } from "@/components/sidebar";

export default function ProtectedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="min-h-screen bg-terminal-dark">
      <Sidebar />
      <div className="ml-14 sm:ml-16">{children}</div>
    </div>
  );
}
