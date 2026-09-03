"use client";

import { useState, useEffect } from "react";
import { Sidebar } from "./Sidebar";
import { Header } from "./Header";

export function AppLayout({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    const handleSidebarToggle = (e: Event) => {
      const customEvent = e as CustomEvent<boolean>;
      setCollapsed(customEvent.detail);
    };
    window.addEventListener("volhelix:sidebar-toggle", handleSidebarToggle);
    return () => window.removeEventListener("volhelix:sidebar-toggle", handleSidebarToggle);
  }, []);

  return (
    <div className="flex min-h-screen bg-[#121214]">
      <Sidebar collapsed={collapsed} onToggle={setCollapsed} />
      <div
        className={`flex-1 flex flex-col min-h-screen transition-all duration-200 ${
          collapsed ? "pl-[68px]" : "pl-[240px]"
        }`}
      >
        <Header />
        <main className="flex-1 p-4 md:p-6 max-w-7xl w-full mx-auto">
          {children}
        </main>
      </div>
    </div>
  );
}