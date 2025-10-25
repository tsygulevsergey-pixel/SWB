import asyncio
import logging
from typing import Dict, List, Optional
import time
import numpy as np
from collections import deque, defaultdict

logger = logging.getLogger(__name__)


class LiquidationAggregator:
    
    def __init__(self, cache):
        self.cache = cache
        
        self._percentiles_cache: Dict[str, dict] = {}
        
        self._history_days = 30
        self._update_task = None
        self._running = False
    
    async def start(self, update_interval_hours: int = 6):
        self._running = True
        self._update_task = asyncio.create_task(
            self._update_loop(update_interval_hours)
        )
        logger.info(f"Liquidation aggregator started (update interval: {update_interval_hours}h)")
    
    async def stop(self):
        self._running = False
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
        logger.info("Liquidation aggregator stopped")
    
    async def _update_loop(self, interval_hours: int):
        while self._running:
            try:
                await self.update_percentiles()
                await asyncio.sleep(interval_hours * 3600)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in liquidation aggregator update loop: {e}")
                await asyncio.sleep(600)
    
    async def update_percentiles(self):
        try:
            symbols = self.cache.candles.get_symbols_with_data()
            
            updated_count = 0
            for symbol in symbols[:100]:
                try:
                    percentiles = await self._calculate_percentiles(symbol)
                    if percentiles:
                        self._percentiles_cache[symbol] = percentiles
                        updated_count += 1
                except Exception as e:
                    logger.debug(f"Error calculating percentiles for {symbol}: {e}")
            
            logger.info(f"Updated liquidation percentiles for {updated_count} symbols")
        
        except Exception as e:
            logger.error(f"Error updating percentiles: {e}")
    
    async def _calculate_percentiles(self, symbol: str) -> Optional[dict]:
        liquidations = self.cache.liquidations.get_liquidations(symbol, minutes=self._history_days * 24 * 60)
        
        if len(liquidations) < 100:
            return None
        
        window_minutes = 4
        windows_data = self._aggregate_into_windows(liquidations, window_minutes)
        
        if not windows_data:
            return None
        
        volumes = [w['total_volume'] for w in windows_data]
        counts = [w['count'] for w in windows_data]
        
        percentiles = {
            'volume_p90': np.percentile(volumes, 90),
            'volume_p95': np.percentile(volumes, 95),
            'volume_p97': np.percentile(volumes, 97),
            'count_p90': np.percentile(counts, 90),
            'count_p95': np.percentile(counts, 95),
            'count_p97': np.percentile(counts, 97),
            'last_updated': time.time(),
            'sample_size': len(windows_data)
        }
        
        return percentiles
    
    def _aggregate_into_windows(self, liquidations: List[dict], window_minutes: int) -> List[dict]:
        if not liquidations:
            return []
        
        window_seconds = window_minutes * 60
        
        windows = defaultdict(lambda: {'total_volume': 0, 'count': 0, 'long_liq': 0, 'short_liq': 0})
        
        for liq in liquidations:
            timestamp = liq.get('timestamp', liq.get('cached_at', time.time()))
            
            window_key = int(timestamp // window_seconds)
            
            volume = liq.get('quantity', 0) * liq.get('price', 0)
            
            windows[window_key]['total_volume'] += volume
            windows[window_key]['count'] += 1
            
            side = liq.get('side', '')
            if side == 'BUY':
                windows[window_key]['short_liq'] += volume
            elif side == 'SELL':
                windows[window_key]['long_liq'] += volume
        
        return list(windows.values())
    
    def get_liquidation_cluster_score(self, symbol: str, minutes: int = 4) -> Optional[float]:
        percentiles = self._percentiles_cache.get(symbol)
        
        if not percentiles:
            return 7.0
        
        recent_volume = self.cache.liquidations.get_liquidation_volume(symbol, minutes)
        
        volume_p95 = percentiles['volume_p95']
        volume_p97 = percentiles['volume_p97']
        
        if recent_volume >= volume_p97:
            return 10.0
        elif recent_volume >= volume_p95:
            return 7.0 + (recent_volume - volume_p95) / (volume_p97 - volume_p95) * 3.0
        else:
            return (recent_volume / volume_p95) * 7.0 if volume_p95 > 0 else 0.0
    
    def is_liquidation_cluster(self, symbol: str, minutes: int = 4, threshold_percentile: int = 95) -> bool:
        percentiles = self._percentiles_cache.get(symbol)
        
        recent_volume = self.cache.liquidations.get_liquidation_volume(symbol, minutes)
        
        if not percentiles:
            min_absolute_threshold = 100000
            return recent_volume >= min_absolute_threshold
        
        threshold_key = f'volume_p{threshold_percentile}'
        threshold_value = percentiles.get(threshold_key, float('inf'))
        
        return recent_volume >= threshold_value
    
    def get_liquidation_bias(self, symbol: str, minutes: int = 4) -> Optional[str]:
        liquidations = self.cache.liquidations.get_liquidations(symbol, minutes)
        
        if not liquidations:
            return None
        
        long_liq_volume = sum(
            liq.get('quantity', 0) * liq.get('price', 0)
            for liq in liquidations
            if liq.get('side') == 'SELL'
        )
        
        short_liq_volume = sum(
            liq.get('quantity', 0) * liq.get('price', 0)
            for liq in liquidations
            if liq.get('side') == 'BUY'
        )
        
        total = long_liq_volume + short_liq_volume
        
        if total == 0:
            return None
        
        if long_liq_volume / total > 0.65:
            return 'LONG'
        elif short_liq_volume / total > 0.65:
            return 'SHORT'
        else:
            return 'MIXED'
    
    def get_stats(self, symbol: str) -> Optional[dict]:
        percentiles = self._percentiles_cache.get(symbol)
        
        if not percentiles:
            return None
        
        recent_volume = self.cache.liquidations.get_liquidation_volume(symbol, minutes=4)
        recent_count = self.cache.liquidations.get_liquidation_count(symbol, minutes=4)
        
        return {
            'percentiles': percentiles,
            'recent_volume_4m': recent_volume,
            'recent_count_4m': recent_count,
            'cluster_score': self.get_liquidation_cluster_score(symbol),
            'bias': self.get_liquidation_bias(symbol)
        }
