import { ReactNode } from "react";
import { Settings, Maximize2, X } from "lucide-react";
import { StreamHealthBadge } from "./StreamHealthBadge";
import { StreamHealth } from "@/lib/flow/flowTypes";

interface PanelFrameProps {
  title: string;
  symbol: string;
  health?: StreamHealth | null;
  children: ReactNode;
  onSettingsClick?: () => void;
  onCloseClick?: () => void;
  onMaximizeClick?: () => void;
  className?: string;
}

export function PanelFrame({
  title,
  symbol,
  health,
  children,
  onSettingsClick,
  onCloseClick,
  onMaximizeClick,
  className = "",
}: PanelFrameProps) {
  return (
    <div className={`flex flex-col bg-[#1C1C1E] border border-[#2C2C2E] rounded-md overflow-hidden ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between px-2 py-1.5 bg-[#2C2C2E]/30 border-b border-[#2C2C2E] shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-neutral-200 tracking-wide">{title}</span>
          <span className="text-[10px] font-mono font-bold px-1.5 py-0.5 bg-[#3A3A3C] text-neutral-300 rounded">
            {symbol}
          </span>
          <StreamHealthBadge health={health} />
        </div>
        <div className="flex items-center gap-1 text-neutral-500">
          {onSettingsClick && (
            <button
              onClick={onSettingsClick}
              className="p-1 hover:text-neutral-200 hover:bg-[#3A3A3C] rounded transition-colors"
              title="Settings"
            >
              <Settings className="w-3.5 h-3.5" />
            </button>
          )}
          {onMaximizeClick && (
            <button
              onClick={onMaximizeClick}
              className="p-1 hover:text-neutral-200 hover:bg-[#3A3A3C] rounded transition-colors"
              title="Maximize"
            >
              <Maximize2 className="w-3.5 h-3.5" />
            </button>
          )}
          {onCloseClick && (
            <button
              onClick={onCloseClick}
              className="p-1 hover:text-neutral-200 hover:bg-[#FF453A]/20 rounded transition-colors"
              title="Close"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>
      
      {/* Content Body */}
      <div className="flex-1 relative min-h-0 overflow-hidden">
        {children}
      </div>
    </div>
  );
}
