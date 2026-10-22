"use client";

import { useState, useEffect } from "react";
import { usePathname } from "next/navigation";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";
import { MarketProvider } from "./MarketProvider";

export function AppLayout({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const pathname = usePathname();
  const isFullBleed = pathname?.startsWith("/terminal");

  useEffect(() => {
    const handleSidebarToggle = (e: Event) => {
      const customEvent = e as CustomEvent<boolean>;
      setCollapsed(customEvent.detail);
    };
    window.addEventListener("volhelix:sidebar-toggle", handleSidebarToggle);
    return () => window.removeEventListener("volhelix:sidebar-toggle", handleSidebarToggle);
  }, []);

  return (
    <MarketProvider><div className="flex min-h-screen bg-[#121214]">
      <Sidebar collapsed={collapsed} onToggle={setCollapsed} />
      <div
        className={`app-content min-w-0 flex-1 flex flex-col min-h-screen transition-all duration-200 ${
          collapsed ? "pl-[68px]" : "pl-[240px]"
        }`}
      >
        <Header />
        <main
          className={`flex-1 w-full mx-auto ${
            isFullBleed
              ? "p-0 max-w-none min-h-[calc(100vh-56px)]"
              : "p-4 md:p-6 max-w-7xl"
          }`}
        >
          {children}
        </main>
      </div>
    </div></MarketProvider>
  );
}