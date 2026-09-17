import { useSyncExternalStore } from "react";
import {
  FootprintBar, TapeEntry, DomAnalytics, HeatmapFrame,
  VolumeProfileSnapshot, FlowMetrics, StreamHealth
} from "./types";
import { getTape, getFootprint, getDom, getMetrics } from "./flowApi";

export interface FlowState {
  symbol: string;
  bars: Record<string, FootprintBar[]>;
  tape: TapeEntry[];
  dom: DomAnalytics | null;
  heatmapFrames: HeatmapFrame[];
  metrics: FlowMetrics | null;
  profile: VolumeProfileSnapshot | null;
  health: StreamHealth | null;
}

class FlowStore {
  private state: FlowState = {
    symbol: "",
    bars: {},
    tape: [],
    dom: null,
    heatmapFrames: [],
    metrics: null,
    profile: null,
    health: null
  };
  private listeners: Set<() => void> = new Set();
  private isHydrating = false;

  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  getSnapshot = () => {
    return this.state;
  };

  private emit() {
    for (const listener of this.listeners) {
      listener();
    }
  }

  async hydrate(symbol: string) {
    if (this.isHydrating && this.state.symbol === symbol) return;
    this.isHydrating = true;
    
    // reset state for new symbol
    if (this.state.symbol !== symbol) {
      this.state = {
        symbol,
        bars: {},
        tape: [],
        dom: null,
        heatmapFrames: [],
        metrics: null,
        profile: null,
        health: null
      };
      this.emit();
    }

    try {
      const [tapeRes, domRes, metricsRes, fpRes] = await Promise.all([
        getTape(symbol, 200),
        getDom(symbol, 20),
        getMetrics(symbol),
        getFootprint(symbol, "1m", 60)
      ]);

      this.state = {
        ...this.state,
        tape: tapeRes?.entries || [],
        dom: domRes,
        metrics: metricsRes,
        bars: {
          ...this.state.bars,
          "1m": fpRes?.bars || []
        }
      };
      this.emit();
    } catch (e) {
      console.error("Hydration failed", e);
    } finally {
      this.isHydrating = false;
    }
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  dispatch(action: { type: string, payload: any }) {
    if (action.payload?.symbol && action.payload.symbol !== this.state.symbol) {
      return; // Ignore events for other symbols
    }

    switch (action.type) {
      case "TAPE": {
        const entries = action.payload.entries || [];
        const newTape = [...this.state.tape, ...entries].slice(-500); // cap 500
        this.state = { ...this.state, tape: newTape };
        break;
      }
      case "DOM": {
        this.state = { ...this.state, dom: action.payload };
        break;
      }
      case "FOOTPRINT": {
        const { interval, bar } = action.payload;
        if (!interval || !bar) break;
        const currentBars = this.state.bars[interval] || [];
        const newBars = [...currentBars];
        
        if (newBars.length > 0 && newBars[newBars.length - 1].open_time === bar.open_time) {
          newBars[newBars.length - 1] = bar;
        } else {
          newBars.push(bar);
        }
        
        this.state = {
          ...this.state,
          bars: { ...this.state.bars, [interval]: newBars.slice(-240) } // cap FLOW_FOOTPRINT_BARS
        };
        break;
      }
      case "HEATMAP": {
        const frame = action.payload;
        if (!frame) break;
        const newFrames = [...this.state.heatmapFrames, frame].slice(-600); // cap window
        this.state = { ...this.state, heatmapFrames: newFrames };
        break;
      }
      case "METRICS": {
        this.state = { ...this.state, metrics: action.payload };
        break;
      }
      case "HEALTH": {
        this.state = { ...this.state, health: action.payload };
        break;
      }
    }
    this.emit();
  }
}

export const flowStore = new FlowStore();

export function useFlowStore(): FlowState {
  return useSyncExternalStore(flowStore.subscribe, flowStore.getSnapshot, flowStore.getSnapshot);
}
