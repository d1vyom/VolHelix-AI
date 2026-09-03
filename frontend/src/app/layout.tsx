import type { Metadata } from "next";
import { AppLayout } from "../components/AppLayout";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "VolHelix AI — Autonomous Multi-Agent Options Orchestrator",
  description: "Autonomous multi-agent options trading and dynamic volatility regime orchestrator on Alpaca MCP.",
  icons: {
    icon: "/volhelix-logo.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased text-neutral-100 min-h-screen flex flex-col`}
        suppressHydrationWarning
      >
        <AppLayout>{children}</AppLayout>
      </body>
    </html>
  );
}