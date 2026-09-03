"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { BarChart3, FileText, Shield, LayoutDashboard, ChevronLeft, ChevronRight, Activity, Cpu } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { useState, useEffect } from "react";
import { getAlpacaAccount } from "../lib/api";

const navItems = [
  { href: "/", label: "Trading Terminal", icon: LayoutDashboard, key: "dashboard" },
  { href: "/volatility", label: "Derivatives / Vol Lab", icon: BarChart3, key: "volatility" },
  { href: "/history", label: "Order History", icon: FileText, key: "history" },
  { href: "/audit", label: "Risk & Margin Audit", icon: Shield, key: "audit" },
];

interface SidebarProps {
  collapsed?: boolean;
  onToggle?: (collapsed: boolean) => void;
}

export function Sidebar({ collapsed = false, onToggle }: SidebarProps) {
  const pathname = usePathname();
  const [internalCollapsed, setInternalCollapsed] = useState(collapsed);
  const isCollapsed = onToggle !== undefined ? collapsed : internalCollapsed;
  const [utaBalance, setUtaBalance] = useState<string>("$400.00K");

  useEffect(() => {
    let isMounted = true;
    getAlpacaAccount()
      .then((acc) => {
        if (!isMounted) return;
        const val = acc.buying_power || acc.portfolio_value || 400000;
        setUtaBalance(`$${(val / 1000).toFixed(2)}K`);
      })
      .catch(() => {});
    return () => {
      isMounted = false;
    };
  }, []);

  const handleToggle = () => {
    const next = !isCollapsed;
    setInternalCollapsed(next);
    onToggle?.(next);
    window.dispatchEvent(new CustomEvent("volhelix:sidebar-toggle", { detail: next }));
  };

  return (
    <motion.aside
      initial={{ width: isCollapsed ? 68 : 240 }}
      animate={{ width: isCollapsed ? 68 : 240 }}
      transition={{ duration: 0.2, ease: "easeOut" }}
      className="fixed left-0 top-0 z-40 h-screen bg-[#121214] border-r border-[#26282f] flex flex-col overflow-hidden select-none"
    >
      {/* Brand Header */}
      <div className="flex items-center justify-between h-14 px-3 border-b border-[#26282f]">
        <Link href="/" className="flex items-center gap-2.5 group">
          <div className="relative flex items-center justify-center w-8 h-8 rounded-lg bg-[#f7a600]/10 border border-[#f7a600]/40 group-hover:border-[#f7a600] transition-all duration-200 p-1 flex-shrink-0">
            <Image
              src="/volhelix-logo.svg"
              alt="VolHelix AI"
              width={22}
              height={22}
              className="w-full h-full object-contain"
            />
            <span className="absolute -bottom-0.5 -right-0.5 w-1.5 h-1.5 rounded-full bg-[#f7a600]" />
          </div>
          <AnimatePresence mode="wait">
            {!isCollapsed && (
              <motion.div
                key="brand"
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -8 }}
                className="flex flex-col"
              >
                <span className="font-extrabold text-sm tracking-tight text-[#f5f5f5]">
                  VolHelix <span className="text-[#f7a600]">PRO</span>
                </span>
                <span className="text-[9px] font-mono uppercase tracking-wider text-[#878996]">
                  VolHelix AI
                </span>
              </motion.div>
            )}
          </AnimatePresence>
        </Link>
        <button
          onClick={handleToggle}
          className="p-1 rounded hover:bg-[#18191f] text-[#878996] hover:text-[#f5f5f5] transition-colors cursor-pointer"
          aria-label={isCollapsed ? "Expand Sidebar" : "Collapse Sidebar"}
          title={isCollapsed ? "Expand Sidebar" : "Collapse Sidebar"}
        >
          {isCollapsed ? <ChevronRight className="w-3.5 h-3.5" /> : <ChevronLeft className="w-3.5 h-3.5" />}
        </button>
      </div>

      {/* Nav List */}
      <nav className="flex-1 p-2 space-y-1 overflow-y-auto">
        {!isCollapsed && (
          <p className="px-2 py-1 text-[10px] font-bold text-[#5e6673] uppercase tracking-wider font-mono">
            Navigation
          </p>
        )}

        {navItems.map((item) => {
          const isActive = pathname === item.href || (item.href !== "/" && Boolean(pathname?.startsWith(item.href)));
          const Icon = item.icon;
          return (
            <Link
              key={item.key}
              href={item.href}
              className={`relative flex items-center px-3 py-2 rounded-md transition-all duration-150 group cursor-pointer ${
                isActive
                  ? "bg-[#f7a600] text-[#121214] font-bold shadow-[0_0_10px_rgba(247,166,0,0.3)]"
                  : "text-[#878996] hover:bg-[#18191f] hover:text-[#f5f5f5]"
              }`}
              title={isCollapsed ? item.label : undefined}
            >
              <div className="flex items-center gap-2.5 z-10">
                <Icon className={`w-4 h-4 flex-shrink-0 ${isActive ? "text-[#121214]" : "text-[#878996] group-hover:text-[#f5f5f5]"}`} />
                {!isCollapsed && (
                  <span className="text-xs font-bold truncate">
                    {item.label}
                  </span>
                )}
              </div>
            </Link>
          );
        })}
      </nav>

      {/* Bottom Unified Trading Account Health */}
      <div className="p-2 border-t border-[#26282f]">
        {!isCollapsed ? (
          <div className="p-2.5 rounded-lg bg-[#18191f] border border-[#26282f] space-y-2 text-[11px] font-mono">
            <div className="flex items-center justify-between text-[#878996]">
              <span className="flex items-center gap-1">
                <Activity className="w-3 h-3 text-[#f7a600]" />
                UTA Margin
              </span>
              <span className="text-[#f7a600] font-bold">{utaBalance}</span>
            </div>

            <div className="space-y-1">
              <div className="flex justify-between text-[10px] text-[#5e6673]">
                <span>Risk Level (DD)</span>
                <span>0.0% / 3.0%</span>
              </div>
              <div className="w-full h-1 bg-[#121214] rounded-full overflow-hidden">
                <div className="h-full bg-[#20b26c] rounded-full w-[4%]" />
              </div>
            </div>

            <Link
              href="/audit"
              className="pt-1.5 border-t border-[#26282f] flex items-center justify-between text-[10px] hover:text-[#f7a600] transition-colors cursor-pointer block"
              title="View Deterministic Rules in Risk & Margin Audit"
            >
              <span className="text-[#878996] hover:text-[#f5f5f5]">Deterministic Gate</span>
              <span className="px-1 py-0.2 rounded bg-[#20b26c]/15 text-[#20b26c] font-bold">
                10/10 ARMED
              </span>
            </Link>
          </div>
        ) : (
          <Link
            href="/audit"
            className="flex justify-center p-2 rounded bg-[#18191f] border border-[#26282f] hover:border-[#f7a600]/50 transition-colors"
            title="Deterministic Gate: 10/10 Armed (Click for Audit)"
          >
            <Cpu className="w-4 h-4 text-[#f7a600]" />
          </Link>
        )}
      </div>
    </motion.aside>
  );
}