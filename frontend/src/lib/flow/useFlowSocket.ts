import { useEffect, useState, useRef } from "react";
import { io, Socket } from "socket.io-client";
import { flowStore } from "./useFlowStore";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "";

// Module-level singleton
let socket: Socket | null = null;
let activeSymbol: string | null = null;
let activePanels: string[] = [];

type FlowStatus = "CONNECTING" | "LIVE" | "RECONNECTING" | "OFFLINE";

export function getFlowSocket(): Socket {
  if (!socket) {
    socket = io(API_BASE, {
      reconnectionDelay: 1000,
      reconnectionDelayMax: 60000,
      transports: ["websocket"],
      autoConnect: true,
    });

    socket.on("connect", () => {
      // Re-subscribe if we had an active symbol
      if (activeSymbol) {
        socket?.emit("flow:subscribe", { symbol: activeSymbol, panels: activePanels });
        // Hydrate from REST (handled by component or store)
        flowStore.hydrate(activeSymbol);
      }
    });

    socket.on("disconnect", () => {
      // Handled by connection state
    });

    // Event routing
    socket.on("flow:tape", (data) => flowStore.dispatch({ type: "TAPE", payload: data }));
    socket.on("flow:dom", (data) => flowStore.dispatch({ type: "DOM", payload: data }));
    socket.on("flow:footprint", (data) => flowStore.dispatch({ type: "FOOTPRINT", payload: data }));
    socket.on("flow:heatmap", (data) => flowStore.dispatch({ type: "HEATMAP", payload: data }));
    socket.on("flow:metrics", (data) => flowStore.dispatch({ type: "METRICS", payload: data }));
    socket.on("flow:health", (data) => flowStore.dispatch({ type: "HEALTH", payload: data }));
  }
  return socket;
}

export function useFlowSocket(symbol: string, panels: string[] = []) {
  const [status, setStatus] = useState<FlowStatus>(() => {
    // Only access getFlowSocket if in browser
    if (typeof window !== "undefined") {
      return getFlowSocket().connected ? "LIVE" : "CONNECTING";
    }
    return "CONNECTING";
  });
  const [lastEventTs, setLastEventTs] = useState<number>(0);
  
  // Use a ref for panels to avoid infinite loops if passed inline
  const panelsRef = useRef(panels);
  useEffect(() => {
    panelsRef.current = panels;
  }, [panels]);
  
  useEffect(() => {
    const s = getFlowSocket();
    
    // Unsubscribe from previous if symbol changed
    if (activeSymbol && activeSymbol !== symbol) {
      s.emit("flow:unsubscribe", { symbol: activeSymbol });
    }
    
    activeSymbol = symbol;
    activePanels = panels;
    
    if (s.connected) {
      s.emit("flow:subscribe", { symbol, panels: panelsRef.current });
      flowStore.hydrate(symbol);
    }

    const onConnect = () => setStatus("LIVE");
    const onDisconnect = (reason: string) => {
      setStatus(reason === "io server disconnect" ? "OFFLINE" : "RECONNECTING");
    };
    const onAnyEvent = () => setLastEventTs(Date.now());
    
    s.on("connect", onConnect);
    s.on("disconnect", onDisconnect);
    s.onAny(onAnyEvent);
    
    return () => {
      s.off("connect", onConnect);
      s.off("disconnect", onDisconnect);
      s.offAny(onAnyEvent);
      // NOTE: We don't automatically unsubscribe on unmount here if we want to share across panels,
      // but if the whole terminal unmounts, we should. We'll handle it by checking if this is the last subscriber,
      // or simply rely on the socket closing eventually if the whole app unmounts.
      // A proper refcount per symbol would be better if multiple components use this hook.
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol]);

  return { status, lastEventTs };
}
