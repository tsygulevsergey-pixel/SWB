import asyncio
import logging
from typing import Dict, List, Optional, Deque
from collections import deque, defaultdict
from datetime import datetime, timedelta
import time

logger = logging.getLogger(__name__)


class CandleCache:
    
    def __init__(self, max_candles: int = 200):
        self.max_candles = max_candles
        self._candles: Dict[str, Deque[dict]] = defaultdict(lambda: deque(maxlen=max_candles))
        self._last_update: Dict[str, float] = {}
    
    def add_candle(self, symbol: str, candle: dict):
        self._candles[symbol].append(candle)
        self._last_update[symbol] = time.time()
    
    def get_candles(self, symbol: str, limit: Optional[int] = None) -> List[dict]:
        candles = list(self._candles[symbol])
        if limit:
            return candles[-limit:]
        return candles
    
    def get_last_candle(self, symbol: str) -> Optional[dict]:
        candles = self._candles.get(symbol)
        if candles:
            return candles[-1]
        return None
    
    def get_last_n_candles(self, symbol: str, n: int) -> List[dict]:
        candles = list(self._candles[symbol])
        return candles[-n:] if len(candles) >= n else candles
    
    def has_enough_data(self, symbol: str, required: int) -> bool:
        return len(self._candles[symbol]) >= required
    
    def get_symbols_with_data(self) -> List[str]:
        return [s for s in self._candles.keys() if len(self._candles[s]) > 0]
    
    def clear_symbol(self, symbol: str):
        if symbol in self._candles:
            del self._candles[symbol]
        if symbol in self._last_update:
            del self._last_update[symbol]


class OICache:
    
    def __init__(self):
        self._oi_current: Dict[str, dict] = {}
        self._oi_history: Dict[str, Deque[dict]] = defaultdict(lambda: deque(maxlen=100))
        self._last_update: Dict[str, float] = {}
    
    def update_oi(self, symbol: str, oi_value: float, timestamp: int):
        oi_data = {
            'value': oi_value,
            'timestamp': timestamp,
            'time': time.time()
        }
        
        self._oi_current[symbol] = oi_data
        self._oi_history[symbol].append(oi_data)
        self._last_update[symbol] = time.time()
    
    def get_current_oi(self, symbol: str) -> Optional[float]:
        oi_data = self._oi_current.get(symbol)
        if oi_data:
            return oi_data['value']
        return None
    
    def get_oi_history(self, symbol: str, minutes: int = 60) -> List[dict]:
        cutoff_time = time.time() - (minutes * 60)
        history = self._oi_history.get(symbol, deque())
        return [oi for oi in history if oi['time'] >= cutoff_time]
    
    def calculate_oi_delta(self, symbol: str, periods: int = 3) -> Optional[float]:
        history = list(self._oi_history.get(symbol, deque()))
        
        if len(history) < periods:
            return None
        
        old_oi = history[-periods]['value']
        new_oi = history[-1]['value']
        
        if old_oi == 0:
            return None
        
        delta_percent = ((new_oi - old_oi) / old_oi) * 100
        return delta_percent
    
    def get_symbols_with_data(self) -> List[str]:
        return list(self._oi_current.keys())


class ZoneCache:
    
    def __init__(self):
        self._zones: Dict[str, List[dict]] = defaultdict(list)
        self._last_update: Dict[str, float] = {}
    
    def update_zones(self, symbol: str, zones: List[dict]):
        self._zones[symbol] = sorted(zones, key=lambda z: z['price'])
        self._last_update[symbol] = time.time()
    
    def add_zone(self, symbol: str, zone: dict):
        self._zones[symbol].append(zone)
        self._zones[symbol] = sorted(self._zones[symbol], key=lambda z: z['price'])
        self._last_update[symbol] = time.time()
    
    def get_zones(self, symbol: str, zone_type: Optional[str] = None) -> List[dict]:
        zones = self._zones.get(symbol, [])
        if zone_type:
            return [z for z in zones if z.get('type') == zone_type]
        return zones
    
    def get_nearest_resistance(self, symbol: str, current_price: float) -> Optional[dict]:
        zones = self._zones.get(symbol, [])
        resistances = [z for z in zones if z['price'] > current_price and z.get('type') == 'resistance']
        
        if resistances:
            return min(resistances, key=lambda z: abs(z['price'] - current_price))
        return None
    
    def get_nearest_support(self, symbol: str, current_price: float) -> Optional[dict]:
        zones = self._zones.get(symbol, [])
        supports = [z for z in zones if z['price'] < current_price and z.get('type') == 'support']
        
        if supports:
            return min(supports, key=lambda z: abs(z['price'] - current_price))
        return None
    
    def get_zone_at_price(self, symbol: str, price: float, tolerance_percent: float = 0.5) -> Optional[dict]:
        zones = self._zones.get(symbol, [])
        
        for zone in zones:
            zone_price = zone['price']
            zone_width = zone.get('width', zone_price * 0.002)
            
            if abs(price - zone_price) / zone_price * 100 <= tolerance_percent:
                return zone
        
        return None
    
    def cleanup_old_zones(self, symbol: str, max_age_days: int = 14):
        cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)
        
        zones = self._zones.get(symbol, [])
        self._zones[symbol] = [z for z in zones if z.get('created_at', time.time()) >= cutoff_time]


class LiquidationCache:
    
    def __init__(self):
        self._liquidations: Dict[str, Deque[dict]] = defaultdict(lambda: deque(maxlen=500))
    
    def add_liquidation(self, symbol: str, liquidation: dict):
        liquidation['cached_at'] = time.time()
        self._liquidations[symbol].append(liquidation)
    
    def get_liquidations(self, symbol: str, minutes: int = 5) -> List[dict]:
        cutoff_time = time.time() - (minutes * 60)
        liquidations = self._liquidations.get(symbol, deque())
        return [liq for liq in liquidations if liq.get('cached_at', 0) >= cutoff_time]
    
    def get_liquidation_volume(self, symbol: str, minutes: int = 4, side: Optional[str] = None) -> float:
        liquidations = self.get_liquidations(symbol, minutes)
        
        if side:
            liquidations = [liq for liq in liquidations if liq.get('side') == side]
        
        total_volume = sum(liq.get('quantity', 0) * liq.get('price', 0) for liq in liquidations)
        return total_volume
    
    def get_liquidation_count(self, symbol: str, minutes: int = 4, side: Optional[str] = None) -> int:
        liquidations = self.get_liquidations(symbol, minutes)
        
        if side:
            liquidations = [liq for liq in liquidations if liq.get('side') == side]
        
        return len(liquidations)


class MarketCache:
    
    def __init__(self, db_pool=None, sync_interval_minutes: int = 5):
        self.candles = CandleCache(max_candles=200)
        self.oi = OICache()
        self.zones = ZoneCache()
        self.liquidations = LiquidationCache()
        
        self.db_pool = db_pool
        self.sync_interval = sync_interval_minutes * 60
        
        self._sync_task = None
        self._running = False
        
        self._symbol_metadata: Dict[str, dict] = {}
    
    async def start(self):
        self._running = True
        if self.db_pool:
            self._sync_task = asyncio.create_task(self._sync_loop())
        logger.info(f"Market cache started (sync interval: {self.sync_interval}s)")
    
    async def stop(self):
        self._running = False
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
        logger.info("Market cache stopped")
    
    async def _sync_loop(self):
        while self._running:
            try:
                await asyncio.sleep(self.sync_interval)
                await self._sync_to_database()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cache sync loop: {e}")
                await asyncio.sleep(60)
    
    async def _sync_to_database(self):
        if not self.db_pool:
            return
        
        try:
            symbols = self.candles.get_symbols_with_data()
            
            synced_count = 0
            for symbol in symbols[:10]:
                candles = self.candles.get_last_n_candles(symbol, 50)
                
                if candles:
                    await self._save_candles_to_db(symbol, candles)
                    synced_count += 1
            
            if synced_count > 0:
                logger.debug(f"Synced {synced_count} symbols to database")
        
        except Exception as e:
            logger.error(f"Error syncing to database: {e}")
    
    async def _save_candles_to_db(self, symbol: str, candles: List[dict]):
        try:
            async with self.db_pool.acquire() as conn:
                for candle in candles[-10:]:
                    interval = candle.get('interval', '15m')
                    table_name = f"klines_{interval}"
                    
                    await conn.execute(f"""
                        INSERT INTO {table_name} (
                            symbol, open_time, close_time,
                            open, high, low, close, volume, quote_volume, trades
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                        ON CONFLICT (symbol, open_time) DO UPDATE SET
                            close = EXCLUDED.close,
                            high = EXCLUDED.high,
                            low = EXCLUDED.low,
                            volume = EXCLUDED.volume
                    """, 
                        symbol,
                        candle['open_time'],
                        candle['close_time'],
                        candle['open'],
                        candle['high'],
                        candle['low'],
                        candle['close'],
                        candle['volume'],
                        candle.get('quote_volume', 0),
                        candle.get('trades', 0)
                    )
        except Exception as e:
            logger.error(f"Error saving candles to DB for {symbol}: {e}")
    
    def update_symbol_metadata(self, symbol: str, metadata: dict):
        self._symbol_metadata[symbol] = metadata
    
    def get_symbol_metadata(self, symbol: str) -> Optional[dict]:
        return self._symbol_metadata.get(symbol)
    
    def get_cache_stats(self) -> dict:
        return {
            'symbols_with_candles': len(self.candles.get_symbols_with_data()),
            'symbols_with_oi': len(self.oi.get_symbols_with_data()),
            'total_zones': sum(len(self.zones.get_zones(s)) for s in self.zones._zones.keys()),
            'sync_interval': self.sync_interval,
        }
