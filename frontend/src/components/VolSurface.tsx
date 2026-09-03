"use client";

import React, { useEffect, useRef } from "react";

interface VolSurfaceProps {
  data?: {
    strikes: number[];
    expiries: string[];
    ivMatrix: number[][];
  };
}

const VolSurface: React.FC<VolSurfaceProps> = ({ data }) => {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (typeof window === "undefined" || !ref.current) return;

    const strikes = data?.strikes ?? [90, 95, 100, 105, 110, 115, 120];
    const expiries = data?.expiries ?? ["7d", "14d", "21d", "30d", "45d", "60d", "90d"];
    const ivMatrix = data?.ivMatrix ?? [
      [0.38, 0.30, 0.22, 0.18, 0.20, 0.25, 0.32],
      [0.36, 0.28, 0.20, 0.17, 0.19, 0.23, 0.30],
      [0.35, 0.27, 0.19, 0.16, 0.18, 0.22, 0.29],
      [0.36, 0.28, 0.20, 0.17, 0.19, 0.23, 0.30],
      [0.38, 0.30, 0.22, 0.18, 0.20, 0.25, 0.32],
      [0.40, 0.32, 0.24, 0.20, 0.22, 0.27, 0.34],
      [0.42, 0.34, 0.26, 0.22, 0.24, 0.29, 0.36],
    ];

    import("plotly.js-dist-min").then((Plotly) => {
      const trace = {
        type: "surface" as const,
        x: expiries,
        y: strikes,
        z: ivMatrix,
        colorscale: [
          [0, "#181a20"],
          [0.2, "#2b313a"],
          [0.5, "#b38600"],
          [0.8, "#f0b90b"],
          [1, "#fcd535"],
        ],
        showscale: true,
        colorbar: {
          title: "IV",
          titleside: "right",
          tickformat: ".0%",
          thickness: 14,
          bgcolor: "rgba(0,0,0,0)",
          bordercolor: "#2b313a",
          tickfont: { color: "#848e9c", size: 10 },
          titlefont: { color: "#f0b90b", size: 11 },
        },
        opacity: 0.94,
        contours: {
          x: { show: true, highlight: true, highlightcolor: "#f0b90b", width: 1 },
          y: { show: true, highlight: true, highlightcolor: "#f0b90b", width: 1 },
        },
        hovertemplate: "DTE: %{x}<br>Strike: %{y}<br>IV: %{z:.1%}<extra></extra>",
      };

      const layout = {
        autosize: true,
        scene: {
          xaxis: {
            title: { text: "DTE", font: { color: "#848e9c", size: 11 } },
            tickfont: { color: "#848e9c", size: 9 },
            gridcolor: "#2b313a",
            zerolinecolor: "#3b414d",
            backgroundcolor: "rgba(0,0,0,0)",
          },
          yaxis: {
            title: { text: "Strike", font: { color: "#848e9c", size: 11 } },
            tickfont: { color: "#848e9c", size: 9 },
            gridcolor: "#2b313a",
            zerolinecolor: "#3b414d",
            backgroundcolor: "rgba(0,0,0,0)",
          },
          zaxis: {
            title: { text: "IV", font: { color: "#848e9c", size: 11 } },
            tickfont: { color: "#848e9c", size: 9 },
            tickformat: ".0%",
            gridcolor: "#2b313a",
            zerolinecolor: "#3b414d",
            backgroundcolor: "rgba(0,0,0,0)",
          },
          bgcolor: "rgba(0,0,0,0)",
          camera: { eye: { x: 1.5, y: 1.5, z: 0.85 } },
        },
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        margin: { l: 0, r: 0, t: 15, b: 0 },
        font: { color: "#848e9c" },
      };

      const container = ref.current;
      if (!container) return;

      Plotly.newPlot(container, [trace as unknown as object], layout as unknown as object, {
        responsive: true,
        displayModeBar: false,
        scrollZoom: true,
      });
    });

    const currentRef = ref.current;
    return () => {
      import("plotly.js-dist-min").then((Plotly) => {
        if (currentRef) Plotly.purge(currentRef);
      });
    };
  }, [data]);

  return (
    <div
      ref={ref}
      className="w-full h-full min-h-72"
      style={{ background: "transparent" }}
    />
  );
};

export default VolSurface;
