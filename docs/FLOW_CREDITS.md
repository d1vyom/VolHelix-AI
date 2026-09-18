# VolHelix AI - Order Flow Terminal Credits

This project draws visual and structural inspiration from the following open-source projects. 
**VolHelix-AI is licensed under the MIT License and contains no GPL-derived source code.**

## Inspiration & Design References

### 1. Flowsurface
- **Source**: `github.com/flowsurface-rs/flowsurface`
- **License**: GPL-3.0
- **Use in VolHelix-AI**: Visual and UX reference only. The panel taxonomy (Heatmap, Candlestick, Footprint, Time&Sales, DOM), tick-size grouping multipliers, and imbalance studies were used as design inspiration.
- **Note**: No Rust code, binaries, or GPL-3 code from Flowsurface was copied, ported, or vendored into VolHelix-AI.

### 2. OrderflowChart
- **Source**: `github.com/murtazayusuf/OrderflowChart`
- **License**: MIT
- **Use in VolHelix-AI**: Reference for the data shape of a footprint dataset (`bid_size`, `price`, `ask_size`). Our `FootprintCell` and API contracts are deliberately designed to be compatible with this shape.

### 3. CryptoFlow & tyumex-trading-terminal
- **Use in VolHelix-AI**: Used solely as conceptual visual references for browser-based heatmap rendering layered over canvases, multi-chart workspaces, and risk-based order entry ergonomics. No source code was integrated.

## Acknowledgements
We thank the open-source creators above for their innovative UI patterns in the order flow and market microstructure domain.
