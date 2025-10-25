import asyncio
import logging
from typing import Dict, Optional
import time

logger = logging.getLogger(__name__)


class OICalculator:
    
    def __init__(self, config, cache, data_provider):
        self.config = config
        self.cache = cache
        self.data_provider = data_provider
        
        self._update_task = None
        self._running = False
    
    async def start(self, update_interval_minutes: int = 5):
        self._running = True
        self._update_task = asyncio.create_task(
            self._update_loop(update_interval_minutes)
        )
        logger.info(f"OI calculator started (update interval: {update_interval_minutes}m)")
    
    async def stop(self):
        self._running = False
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
        logger.info("OI calculator stopped")
    
    async def _update_loop(self, interval_minutes: int):
        while self._running:
            try:
                await self.update_all_oi()
                await asyncio.sleep(interval_minutes * 60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in OI calculator update loop: {e}")
                await asyncio.sleep(60)
    
    async def update_all_oi(self):
        try:
            symbols = self.cache.candles.get_symbols_with_data()
            
            updated_count = 0
            for symbol in symbols[:100]:
                try:
                    oi_data = await self.data_provider.get_open_interest(symbol)
                    
                    oi_value = float(oi_data.get('openInterest', 0))
                    timestamp = int(oi_data.get('time', time.time() * 1000))
                    
                    self.cache.oi.update_oi(symbol, oi_value, timestamp)
                    
                    updated_count += 1
                    
                    await asyncio.sleep(0.05)
                
                except Exception as e:
                    logger.debug(f"Error updating OI for {symbol}: {e}")
            
            if updated_count > 0:
                logger.debug(f"Updated OI for {updated_count} symbols")
        
        except Exception as e:
            logger.error(f"Error updating all OI: {e}")
    
    def calculate_oi_delta_15m(self, symbol: str) -> Optional[float]:
        delta = self.cache.oi.calculate_oi_delta(symbol, periods=3)
        return delta
    
    def is_oi_drop_significant(self, symbol: str) -> bool:
        delta = self.calculate_oi_delta_15m(symbol)
        
        if delta is None:
            return False
        
        if delta <= self.config.oi_delta_max_percent:
            return True
        
        return False
    
    def is_oi_drop_strict(self, symbol: str) -> bool:
        delta = self.calculate_oi_delta_15m(symbol)
        
        if delta is None:
            return False
        
        if delta <= self.config.oi_delta_strict_percent:
            return True
        
        return False
    
    def get_oi_drop_score(self, symbol: str) -> float:
        delta = self.calculate_oi_delta_15m(symbol)
        
        if delta is None:
            return 0.0
        
        if delta >= self.config.oi_delta_min_percent:
            return 0.0
        
        if delta <= self.config.oi_delta_max_percent:
            score = abs(delta / self.config.oi_delta_max_percent) * 10.0
            return min(score, 10.0)
        
        score = abs((delta - self.config.oi_delta_min_percent) / 
                   (self.config.oi_delta_max_percent - self.config.oi_delta_min_percent)) * 10.0
        
        return min(score, 10.0)
    
    def get_current_oi_usd(self, symbol: str) -> Optional[float]:
        oi_value = self.cache.oi.get_current_oi(symbol)
        
        if oi_value is None:
            return None
        
        last_candle = self.cache.candles.get_last_candle(symbol)
        
        if not last_candle:
            return None
        
        price = last_candle['close']
        oi_usd = oi_value * price
        
        return oi_usd
    
    def get_stats(self, symbol: str) -> Optional[dict]:
        oi_current = self.cache.oi.get_current_oi(symbol)
        oi_delta = self.calculate_oi_delta_15m(symbol)
        oi_usd = self.get_current_oi_usd(symbol)
        
        if oi_current is None:
            return None
        
        return {
            'oi_current': oi_current,
            'oi_usd': oi_usd,
            'oi_delta_15m_percent': oi_delta,
            'is_significant_drop': self.is_oi_drop_significant(symbol),
            'drop_score': self.get_oi_drop_score(symbol)
        }
