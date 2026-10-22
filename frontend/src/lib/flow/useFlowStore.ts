import { useSyncExternalStore } from "react";

import {
  FootprintBar, TapeEntry, DomAnalytics, HeatmapFrame,
  VolumeProfileSnapshot, FlowMetrics, StreamHealth
} from "./flowTypes";
import { getTape, getFootprint, getDom, getMetrics, getVolumeProfile, getHeatmap } from "./flowApi";

import type { Market } from "../market";

export interface FlowState {
  market: Market;
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
    market:"spot",
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
  private generation=0;
  private controller:AbortController|null=null;

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

  reset(market:Market,symbol:string) {
    this.generation++;this.controller?.abort();
    this.state={market,symbol,bars:{},tape:[],dom:null,heatmapFrames:[],metrics:null,profile:null,health:null};this.emit();
  }
  async hydrate(market:Market,symbol:string) {
    if(this.state.market!==market||this.state.symbol!==symbol)return;
    this.controller?.abort();const controller=new AbortController();this.controller=controller;
    const generation=this.generation, initial=this.state;
    const [tape,dom,metrics,footprint,profile,heatmap]=await Promise.all([
      getTape(symbol,200,undefined,market,controller.signal),getDom(symbol,20,undefined,market,controller.signal),getMetrics(symbol,market,controller.signal),getFootprint(symbol,'1m',60,undefined,market,controller.signal),getVolumeProfile(symbol,'SESSION',undefined,undefined,undefined,market,controller.signal),getHeatmap(symbol,undefined,undefined,market,controller.signal)
    ]);
    if(controller.signal.aborted||generation!==this.generation)return;
    this.state={...this.state,
      tape:this.state.tape===initial.tape ? tape?.entries||[] : this.state.tape,
      dom:this.state.dom===initial.dom ? dom : this.state.dom,
      metrics:this.state.metrics===initial.metrics ? metrics : this.state.metrics,
      health:this.state.health===initial.health ? metrics?.health||this.state.health : this.state.health,
      bars:this.state.bars===initial.bars ? {'1m':footprint?.bars||[]} : this.state.bars,
      profile,heatmapFrames:this.state.heatmapFrames===initial.heatmapFrames ? heatmap?.frames||[] : this.state.heatmapFrames
    };this.emit();
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  dispatch(action: { type: string, payload: any }) {
    if (action.payload?.symbol !== this.state.symbol || action.payload?.market !== this.state.market) {
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
        this.state = { ...this.state, metrics: action.payload, health: action.payload.health || this.state.health };
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
