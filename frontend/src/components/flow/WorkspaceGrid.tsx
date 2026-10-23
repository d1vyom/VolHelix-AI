"use client";

import React, { useState, useSyncExternalStore } from "react";
import dynamic from "next/dynamic";
import { Panel, Group as PanelGroup, Separator as PanelResizeHandle } from "react-resizable-panels";
import { FlowMetricsStrip } from "./FlowMetricsStrip";

const FootprintChart = dynamic(() => import("./FootprintChart").then(mod => mod.FootprintChart), { ssr: false });
const DOMLadder = dynamic(() => import("./DOMLadder").then(mod => mod.DOMLadder), { ssr: false });
const TimeAndSales = dynamic(() => import("./TimeAndSales").then(mod => mod.TimeAndSales), { ssr: false });
const LiquidityHeatmap = dynamic(() => import("./LiquidityHeatmap").then(mod => mod.LiquidityHeatmap), { ssr: false });
const CVDPanel = dynamic(() => import("./CVDPanel").then(mod => mod.CVDPanel), { ssr: false });
const VolumeProfile = dynamic(() => import("./VolumeProfile").then(mod => mod.VolumeProfile), { ssr: false });

const getLayout = (id: string) => {
  if (typeof window === "undefined") return undefined;
  const val = localStorage.getItem(id);
  try { return val ? JSON.parse(val) : undefined; } catch { return undefined; }
};

const saveLayout = (id: string, layout: unknown) => {
  if (typeof window !== "undefined") {
    try { localStorage.setItem(id, JSON.stringify(layout)); } catch { /* Storage may be unavailable. */ }
  }
};

export type WorkspacePreset = "ORDER_FLOW" | "LIQUIDITY" | "ANALYSIS";

interface WorkspaceGridProps {
  symbol: string;
}

function ResizeHandle({ direction = "horizontal" }: { direction?: "horizontal" | "vertical" }) {
  if (direction === "vertical") {
    return <PanelResizeHandle className="h-1 w-full bg-[#1C1C1E] hover:bg-[#007AFF] transition-colors cursor-row-resize" />;
  }
  return <PanelResizeHandle className="w-1 h-full bg-[#1C1C1E] hover:bg-[#007AFF] transition-colors cursor-col-resize" />;
}

const subscribeNarrow = (notify: () => void) => {
  const query = window.matchMedia('(max-width: 1100px)');
  query.addEventListener('change', notify);
  return () => query.removeEventListener('change', notify);
};

export function WorkspaceGrid({ symbol }: WorkspaceGridProps) {
  const narrow = useSyncExternalStore(subscribeNarrow, () => window.matchMedia('(max-width: 1100px)').matches, () => false);
  const [preset, setPreset] = useState<WorkspacePreset>(() => {
    if (typeof window !== "undefined") {
      try {
        const saved = localStorage.getItem("volhelix.workspace.v1.preset");
        if (saved && ["ORDER_FLOW", "LIQUIDITY", "ANALYSIS"].includes(saved)) {
          return saved as WorkspacePreset;
        }
      } catch {
        // ignore
      }
    }
    return "ORDER_FLOW";
  });

  const handlePresetChange = (newPreset: WorkspacePreset) => {
    setPreset(newPreset);
    try {
      localStorage.setItem("volhelix.workspace.v1.preset", newPreset);
    } catch {
      // ignore
    }
  };

  const renderPreset = () => {
    if (narrow) return <div className="compact-flow-grid">
      <div className="compact-flow-chart">{preset === 'LIQUIDITY' ? <LiquidityHeatmap symbol={symbol} /> : <FootprintChart symbol={symbol} />}</div>
      {preset !== 'LIQUIDITY' && <div className="compact-flow-cvd"><CVDPanel symbol={symbol} /></div>}
      {preset !== 'ANALYSIS' && <><div className="compact-flow-dom"><DOMLadder symbol={symbol} /></div><div className="compact-flow-tape"><TimeAndSales symbol={symbol} /></div></>}
      {preset !== 'ORDER_FLOW' && <div className="compact-flow-profile"><VolumeProfile symbol={symbol} /></div>}
    </div>;
    switch (preset) {
      case "ORDER_FLOW":
        return (
          <PanelGroup 
            orientation="horizontal" 
            defaultLayout={getLayout("volhelix.workspace.v1.orderflow")}
            onLayoutChange={(l) => saveLayout("volhelix.workspace.v1.orderflow", l)}
          >
            <Panel defaultSize={52} minSize={30}>
              <PanelGroup orientation="vertical">
                <Panel defaultSize={75} minSize={30}>
                  <FootprintChart symbol={symbol} />
                </Panel>
                <ResizeHandle direction="vertical" />
                <Panel defaultSize={25} minSize={10}>
                  <CVDPanel symbol={symbol} />
                </Panel>
              </PanelGroup>
            </Panel>
            <ResizeHandle direction="horizontal" />
            <Panel defaultSize={48} minSize={30}>
              <PanelGroup orientation="vertical">
                <Panel defaultSize={60} minSize={30}>
                  <DOMLadder symbol={symbol} />
                </Panel>
                <ResizeHandle direction="vertical" />
                <Panel defaultSize={40} minSize={20}>
                  <TimeAndSales symbol={symbol} />
                </Panel>
              </PanelGroup>
            </Panel>
          </PanelGroup>
        );

      case "LIQUIDITY":
        return (
          <PanelGroup 
            orientation="horizontal" 
            defaultLayout={getLayout("volhelix.workspace.v1.liquidity")}
            onLayoutChange={(l) => saveLayout("volhelix.workspace.v1.liquidity", l)}
          >
            <Panel defaultSize={65} minSize={30}>
              <LiquidityHeatmap symbol={symbol} />
            </Panel>
            <ResizeHandle direction="horizontal" />
            <Panel defaultSize={35} minSize={20}>
              <PanelGroup orientation="vertical">
                <Panel defaultSize={50} minSize={20}>
                  <DOMLadder symbol={symbol} />
                </Panel>
                <ResizeHandle direction="vertical" />
                <Panel defaultSize={25} minSize={10}>
                  <TimeAndSales symbol={symbol} />
                </Panel>
                <ResizeHandle direction="vertical" />
                <Panel defaultSize={25} minSize={10}>
                  <VolumeProfile symbol={symbol} />
                </Panel>
              </PanelGroup>
            </Panel>
          </PanelGroup>
        );

      case "ANALYSIS":
        return (
          <PanelGroup 
            orientation="horizontal" 
            defaultLayout={getLayout("volhelix.workspace.v1.analysis")}
            onLayoutChange={(l) => saveLayout("volhelix.workspace.v1.analysis", l)}
          >
            <Panel defaultSize={70} minSize={40}>
              <PanelGroup orientation="vertical">
                <Panel defaultSize={75} minSize={30}>
                  <FootprintChart symbol={symbol} />
                </Panel>
                <ResizeHandle direction="vertical" />
                <Panel defaultSize={25} minSize={10}>
                  <CVDPanel symbol={symbol} />
                </Panel>
              </PanelGroup>
            </Panel>
            <ResizeHandle direction="horizontal" />
            <Panel defaultSize={30} minSize={20}>
              <VolumeProfile symbol={symbol} />
            </Panel>
          </PanelGroup>
        );

      default:
        return null;
    }
  };

  return (
    <div className="flow-workspace flex flex-col h-full w-full bg-[#121214] text-neutral-100 p-1.5 gap-1.5 overflow-hidden">
      {/* Metrics Strip */}
      <div className="shrink-0 rounded overflow-hidden">
        <FlowMetricsStrip />
      </div>

      <div className="shrink-0 flex items-center justify-end gap-2 px-1">
        <span className="text-xs text-neutral-400 uppercase tracking-wider font-bold">Workspace:</span>
        <select
          aria-label="Workspace layout"
          value={preset}
          onChange={(e) => handlePresetChange(e.target.value as WorkspacePreset)}
          className="bg-[#1C1C1E] text-white px-2 py-1 text-xs rounded border border-[#2C2C2E] outline-none focus:border-[#f7a600] font-mono cursor-pointer"
        >
          <option value="ORDER_FLOW">Order Flow</option>
          <option value="LIQUIDITY">Liquidity</option>
          <option value="ANALYSIS">Analysis</option>
        </select>
      </div>

      {/* Grid Area */}
      <div className="flow-grid-area grow min-h-0 rounded overflow-hidden">
        {renderPreset()}
      </div>
    </div>
  );
}
