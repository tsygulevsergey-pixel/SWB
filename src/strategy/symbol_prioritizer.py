import asyncio
import logging
from typing import List, Dict, Tuple
import time

logger = logging.getLogger(__name__)


class SymbolPrioritizer:
    
    def __init__(self, cache, hot_pool_size: int = 400, cold_pool_size: int = 600):
        self.cache = cache
        self.hot_pool_size = hot_pool_size
        self.cold_pool_size = cold_pool_size
        
        self._hot_pool: List[str] = []
        self._cold_pool: List[str] = []
        self._symbol_priorities: Dict[str, float] = {}
        
        self._signal_pressure: Dict[str, int] = {}
        
        self._update_task = None
        self._running = False
    
    async def start(self, update_interval_minutes: int = 10):
        self._running = True
        self._update_task = asyncio.create_task(
            self._update_loop(update_interval_minutes)
        )
        logger.info(f"Symbol prioritizer started (update interval: {update_interval_minutes}m)")
    
    async def stop(self):
        self._running = False
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
        logger.info("Symbol prioritizer stopped")
    
    async def _update_loop(self, interval_minutes: int):
        while self._running:
            try:
                await self.update_pools()
                await asyncio.sleep(interval_minutes * 60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in prioritizer update loop: {e}")
                await asyncio.sleep(60)
    
    async def update_pools(self):
        try:
            symbols = self.cache.candles.get_symbols_with_data()
            
            if not symbols:
                logger.warning("No symbols with data to prioritize")
                return
            
            priorities = {}
            
            for symbol in symbols:
                try:
                    priority = await self._calculate_priority(symbol)
                    if priority is not None:
                        priorities[symbol] = priority
                except Exception as e:
                    logger.debug(f"Error calculating priority for {symbol}: {e}")
            
            sorted_symbols = sorted(priorities.items(), key=lambda x: x[1], reverse=True)
            
            self._hot_pool = [s for s, _ in sorted_symbols[:self.hot_pool_size]]
            self._cold_pool = [s for s, _ in sorted_symbols[self.hot_pool_size:self.hot_pool_size + self.cold_pool_size]]
            self._symbol_priorities = dict(sorted_symbols)
            
            logger.info(
                f"Pools updated: hot={len(self._hot_pool)}, cold={len(self._cold_pool)}, "
                f"top priority={priorities.get(self._hot_pool[0], 0):.2f if self._hot_pool else 0}"
            )
        
        except Exception as e:
            logger.error(f"Error updating pools: {e}")
    
    async def _calculate_priority(self, symbol: str) -> float:
        metadata = self.cache.get_symbol_metadata(symbol)
        
        if not metadata:
            return 0.0
        
        volatility = metadata.get('atr_percent', 0)
        
        volume_usd = metadata.get('volume_24h', 0)
        liquidity = min(volume_usd / 50_000_000, 10.0)
        
        signal_pressure = self._signal_pressure.get(symbol, 0)
        pressure_score = min(signal_pressure / 5.0, 10.0)
        
        liquidations = self.cache.liquidations.get_liquidations(symbol, minutes=15)
        liq_score = min(len(liquidations) / 10.0, 10.0)
        
        priority = (
            volatility * 0.30 +
            liquidity * 0.25 +
            pressure_score * 0.25 +
            liq_score * 0.20
        )
        
        return priority
    
    def increment_signal_pressure(self, symbol: str):
        self._signal_pressure[symbol] = self._signal_pressure.get(symbol, 0) + 1
    
    def decay_signal_pressure(self, decay_rate: float = 0.5):
        for symbol in list(self._signal_pressure.keys()):
            self._signal_pressure[symbol] = max(0, self._signal_pressure[symbol] - decay_rate)
            
            if self._signal_pressure[symbol] == 0:
                del self._signal_pressure[symbol]
    
    def is_hot(self, symbol: str) -> bool:
        return symbol in self._hot_pool
    
    def is_cold(self, symbol: str) -> bool:
        return symbol in self._cold_pool
    
    def get_hot_pool(self) -> List[str]:
        return self._hot_pool.copy()
    
    def get_cold_pool(self) -> List[str]:
        return self._cold_pool.copy()
    
    def get_priority(self, symbol: str) -> float:
        return self._symbol_priorities.get(symbol, 0.0)
    
    def get_top_symbols(self, limit: int = 50) -> List[Tuple[str, float]]:
        sorted_symbols = sorted(
            self._symbol_priorities.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return sorted_symbols[:limit]
