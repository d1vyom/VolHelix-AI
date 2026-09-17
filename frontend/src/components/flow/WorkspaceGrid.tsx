"use client";

import React, { useState } from "react";
import { Panel, Group as PanelGroup, Separator as PanelResizeHandle } from "react-resizable-panels";
import { FlowMetricsStrip } from "./FlowMetricsStrip";
import { FootprintChart } from "./FootprintChart";
import { DOMLadder } from "./DOMLadder";
import { TimeAndSales } from "./TimeAndSales";
import { LiquidityHeatmap } from "./LiquidityHeatmap";
import { CVDPanel } from "./CVDPanel";
import { VolumeProfile } from "./VolumeProfile";

const getLayout = (id: string) => {
  if (typeof window === "undefined") return undefined;
  const val = localStorage.getItem(id);
  return val ? JSON.parse(val) : undefined;
};

const saveLayout = (id: string, layout: any) => {
  if (typeof window !== "undefined") {
    localStorage.setItem(id, JSON.stringify(layout));
  }
};

export type WorkspacePreset = "ORDER_FLOW" | "LIQUIDITY" | "ANALYSIS";

interface WorkspaceGridProps {
  symbol: string;
}

function ResizeHandle() {
  return (
    <PanelResizeHandle className="w-1 h-full bg-[#1C1C1E] hover:bg-[#007AFF] transition-colors cursor-col-resize group-data-[direction=vertical]:h-1 group-data-[direction=vertical]:w-full group-data-[direction=vertical]:cursor-row-resize" />
  );
}

export function WorkspaceGrid({ symbol }: WorkspaceGridProps) {
  const [preset, setPreset] = useState<WorkspacePreset>(() => {
    if (typeof window !== "undefined") {
      try {
        const saved = localStorage.getItem("volhelix.workspace.v1.preset");
        if (saved && ["ORDER_FLOW", "LIQUIDITY", "ANALYSIS"].includes(saved)) {
          return saved as WorkspacePreset;
        }
      } catch (e) {
        // ignore
      }
    }
    return "ORDER_FLOW";
  });

  const handlePresetChange = (newPreset: WorkspacePreset) => {
    setPreset(newPreset);
    try {
      localStorage.setItem("volhelix.workspace.v1.preset", newPreset);
    } catch (e) {
      // ignore
    }
  };

  const renderPreset = () => {
    switch (preset) {
      case "ORDER_FLOW":
        return (
          <PanelGroup 
            orientation="horizontal" 
            defaultLayout={getLayout("volhelix.workspace.v1.orderflow")}
            onLayoutChange={(l) => saveLayout("volhelix.workspace.v1.orderflow", l)}
          >
            <Panel defaultSize={65} minSize={30}>
              <PanelGroup orientation="vertical">
                <Panel defaultSize={75} minSize={30}>
                  <FootprintChart symbol={symbol} />
                </Panel>
                <ResizeHandle />
                <Panel defaultSize={25} minSize={10}>
                  <CVDPanel symbol={symbol} />
                </Panel>
              </PanelGroup>
            </Panel>
            <ResizeHandle />
            <Panel defaultSize={35} minSize={20}>
              <PanelGroup orientation="horizontal">
                <Panel defaultSize={60} minSize={30}>
                  <DOMLadder symbol={symbol} />
                </Panel>
                <ResizeHandle />
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
            <ResizeHandle />
            <Panel defaultSize={35} minSize={20}>
              <PanelGroup orientation="horizontal">
                <Panel defaultSize={50} minSize={20}>
                  <DOMLadder symbol={symbol} />
                </Panel>
                <ResizeHandle />
                <Panel defaultSize={25} minSize={10}>
                  <TimeAndSales symbol={symbol} />
                </Panel>
                <ResizeHandle />
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
                <ResizeHandle />
                <Panel defaultSize={25} minSize={10}>
                  <CVDPanel symbol={symbol} />
                </Panel>
              </PanelGroup>
            </Panel>
            <ResizeHandle />
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
    <div className="flex flex-col h-full w-full bg-[#121214] text-neutral-100 p-1.5 gap-1.5 overflow-hidden">
      {/* Metrics Strip */}
      <div className="shrink-0 rounded overflow-hidden">
        <FlowMetricsStrip symbol={symbol} />
      </div>

      <div className="shrink-0 flex items-center justify-end gap-2 px-1">
        <span className="text-xs text-neutral-400 uppercase tracking-wider font-bold">Workspace:</span>
        <select
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
      <div className="grow min-h-0 rounded overflow-hidden">
        {renderPreset()}
      </div>
    </div>
  );
}
