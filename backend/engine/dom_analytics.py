import time
import statistics
from typing import List, Dict, Tuple
from backend.marketdata.models import LadderLevel, BookSnapshot, Trade
from backend.engine.flow_models import DomAnalytics
from backend.engine.footprint import round_to_tick
from backend.config import settings

class IcebergDetector:
    def __init__(self):
        self.levels: Dict[float, dict] = {}

    def update_book(self, grouped_bids: Dict[float, float], grouped_asks: Dict[float, float], ts: int):
        # Heuristic: A level drops significantly then bounces back >= 3 times in 10s
        for p, s in list(grouped_bids.items()) + list(grouped_asks.items()):
            if p not in self.levels:
                self.levels[p] = {'last_size': s, 'refills': [], 'min_size': s, 'max_size': s}
            else:
                st = self.levels[p]
                prev = st['last_size']
                if s > prev * 1.5 and prev < st['max_size'] * 0.5:
                    st['refills'].append(ts)
                st['last_size'] = s
                st['min_size'] = min(st['min_size'], s)
                st['max_size'] = max(st['max_size'], s)
                
                st['refills'] = [rt for rt in st['refills'] if ts - rt <= 10000]

    def is_iceberg(self, price: float) -> bool:
        if price in self.levels:
            return len(self.levels[price]['refills']) >= 3
        return False

class DomEngine:
    def __init__(self, symbol: str, tick_size: float):
        self.symbol = symbol.upper()
        self.tick_group = tick_size * settings.FLOW_TICK_GROUP_MULTIPLIER
        self.iceberg_detector = IcebergDetector()
        self.walls_state: Dict[float, dict] = {}

    def compute_analytics(self, book: BookSnapshot, trades_1m: List[Trade]) -> DomAnalytics:
        now = int(time.time() * 1000)
        
        bids: Dict[float, float] = {}
        asks: Dict[float, float] = {}
        
        for p, s in book.bids:
            bucket = round_to_tick(p, self.tick_group)
            bids[bucket] = bids.get(bucket, 0.0) + s
            
        for p, s in book.asks:
            bucket = round_to_tick(p, self.tick_group)
            asks[bucket] = asks.get(bucket, 0.0) + s
            
        self.iceberg_detector.update_book(bids, asks, now)
        
        best_bid = max(bids.keys()) if bids else 0.0
        best_ask = min(asks.keys()) if asks else 0.0
        mid = (best_bid + best_ask) / 2.0 if best_bid and best_ask else (best_bid or best_ask)
        
        spread = best_ask - best_bid if best_ask and best_bid else 0.0
        spread_bps = (spread / mid * 10000.0) if mid > 0 else 0.0
        
        all_sizes = list(bids.values()) + list(asks.values())
        median_size = statistics.median(all_sizes) if all_sizes else 0.0
        wall_threshold = median_size * settings.FLOW_WALL_MULTIPLIER
        
        current_walls = set()
        for p, s in bids.items():
            if s >= wall_threshold: current_walls.add((p, "BID", s))
        for p, s in asks.items():
            if s >= wall_threshold: current_walls.add((p, "ASK", s))
            
        for p, side, s in current_walls:
            if p not in self.walls_state:
                self.walls_state[p] = {'first_seen': now, 'side': side, 'history': [(now, True)], 'last_size': s}
            else:
                self.walls_state[p]['history'].append((now, True))
                self.walls_state[p]['last_size'] = s
                self.walls_state[p]['side'] = side
                
        for p in list(self.walls_state.keys()):
            if not any(cw[0] == p for cw in current_walls):
                self.walls_state[p]['history'].append((now, False))
                
        active_walls = []
        for p, st in list(self.walls_state.items()):
            st['history'] = [(t, v) for t, v in st['history'] if now - t <= 30000]
            if not st['history']:
                del self.walls_state[p]
                continue
                
            trues = sum(1 for _, v in st['history'] if v)
            persistence = trues / len(st['history'])
            
            if st['history'][-1][1]:
                active_walls.append({
                    "price": p,
                    "side": st['side'],
                    "size": st['last_size'],
                    "age_sec": (now - st['first_seen']) / 1000.0,
                    "persistence": persistence
                })
                
        N = 60
        bid_prices = sorted(list(bids.keys()), reverse=True)[:N]
        ask_prices = sorted(list(asks.keys()))[:N]
        
        trade_vol_buy = {}
        trade_vol_sell = {}
        cutoff = now - 60000
        for t in trades_1m:
            if t.ts >= cutoff:
                bucket = round_to_tick(t.price, self.tick_group)
                if t.side == "BUY":
                    trade_vol_buy[bucket] = trade_vol_buy.get(bucket, 0.0) + t.qty
                else:
                    trade_vol_sell[bucket] = trade_vol_sell.get(bucket, 0.0) + t.qty
                    
        ladder = []
        for p in ask_prices[::-1]:
            ladder.append(LadderLevel(
                price=p,
                ask_size=asks[p],
                traded_buy=trade_vol_buy.get(p, 0.0),
                traded_sell=trade_vol_sell.get(p, 0.0),
                is_wall=any(w['price'] == p for w in active_walls),
                iceberg_suspected=self.iceberg_detector.is_iceberg(p)
            ))
            
        for p in bid_prices:
            ladder.append(LadderLevel(
                price=p,
                bid_size=bids[p],
                traded_buy=trade_vol_buy.get(p, 0.0),
                traded_sell=trade_vol_sell.get(p, 0.0),
                is_wall=any(w['price'] == p for w in active_walls),
                iceberg_suspected=self.iceberg_detector.is_iceberg(p)
            ))
            
        bid_depth_20 = sum(bids[p] for p in bid_prices[:20])
        ask_depth_20 = sum(asks[p] for p in ask_prices[:20])
        imbalance = 0.0
        if (bid_depth_20 + ask_depth_20) > 0:
            imbalance = (bid_depth_20 - ask_depth_20) / (bid_depth_20 + ask_depth_20)
            
        return DomAnalytics(
            symbol=self.symbol,
            best_bid=best_bid,
            best_ask=best_ask,
            spread=spread,
            spread_bps=spread_bps,
            mid=mid,
            bid_depth_n=bid_depth_20,
            ask_depth_n=ask_depth_20,
            book_imbalance=imbalance,
            walls=active_walls,
            levels=ladder
        )
