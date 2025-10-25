import asyncio
import logging
from typing import Optional, Dict, List
import time
import numpy as np
from config import StrategyConfig

logger = logging.getLogger(__name__)


class LSFPDetector:
    
    def __init__(self, config: StrategyConfig, cache, liq_aggregator, oi_calculator):
        self.config = config
        self.cache = cache
        self.liq_aggregator = liq_aggregator
        self.oi_calculator = oi_calculator
    
    async def detect_pattern(self, symbol: str, candle: dict) -> Optional[Dict]:
        try:
            if not candle.get('is_closed', False):
                return None
            
            candles = self.cache.candles.get_last_n_candles(symbol, 25)
            
            if len(candles) < 22:
                return None
            
            current_candle = candles[-1]
            prev_candles = candles[-22:-1]
            
            atr = self._calculate_atr(candles[-15:], 14)
            if atr == 0:
                return None
            
            sweep_result = self._check_sweep(current_candle, prev_candles, atr)
            if not sweep_result:
                return None
            
            direction = sweep_result['direction']
            
            wick_result = self._check_wick_body_ratio(current_candle, direction)
            if not wick_result:
                return None
            
            if not self.liq_aggregator.is_liquidation_cluster(symbol, minutes=4, threshold_percentile=95):
                return None
            
            oi_delta = self.oi_calculator.calculate_oi_delta_15m(symbol)
            if oi_delta is None or oi_delta > self.config.oi_delta_min_percent:
                return None
            
            volume_result = self._check_volume(current_candle, candles, atr)
            if not volume_result:
                return None
            
            return_result = self._check_price_return(current_candle, sweep_result, direction)
            if not return_result:
                return None
            
            pattern = {
                'symbol': symbol,
                'direction': direction,
                'timestamp': current_candle.get('close_time', time.time() * 1000),
                'sweep': sweep_result,
                'wick': wick_result,
                'liquidation_score': self.liq_aggregator.get_liquidation_cluster_score(symbol),
                'oi_delta': oi_delta,
                'volume': volume_result,
                'return': return_result,
                'atr': atr,
                'candle': current_candle
            }
            
            logger.info(f"LSFP-15 pattern detected: {symbol} {direction}")
            
            return pattern
        
        except Exception as e:
            logger.error(f"Error detecting LSFP pattern for {symbol}: {e}")
            return None
    
    def _check_sweep(self, candle: dict, prev_candles: List[dict], atr: float) -> Optional[Dict]:
        lookback = 20
        recent_candles = prev_candles[-lookback:]
        
        if len(recent_candles) < lookback:
            return None
        
        recent_highs = [c['high'] for c in recent_candles]
        recent_lows = [c['low'] for c in recent_candles]
        
        max_high = max(recent_highs)
        min_low = min(recent_lows)
        
        current_high = candle['high']
        current_low = candle['low']
        
        high_sweep_amount = current_high - max_high
        low_sweep_amount = min_low - current_low
        
        min_sweep = atr * self.config.sweep_min_atr
        
        if high_sweep_amount >= min_sweep:
            return {
                'direction': 'SHORT',
                'type': 'high_sweep',
                'sweep_level': max_high,
                'sweep_amount': high_sweep_amount,
                'sweep_atr_ratio': high_sweep_amount / atr
            }
        
        if low_sweep_amount >= min_sweep:
            return {
                'direction': 'LONG',
                'type': 'low_sweep',
                'sweep_level': min_low,
                'sweep_amount': low_sweep_amount,
                'sweep_atr_ratio': low_sweep_amount / atr
            }
        
        return None
    
    def _check_wick_body_ratio(self, candle: dict, direction: str) -> Optional[Dict]:
        body_size = abs(candle['close'] - candle['open'])
        
        if body_size == 0:
            body_size = candle['high'] * 0.0001
        
        upper_wick = candle['high'] - max(candle['open'], candle['close'])
        lower_wick = min(candle['open'], candle['close']) - candle['low']
        
        if direction == 'SHORT':
            relevant_wick = upper_wick
            wick_ratio = relevant_wick / body_size
            
            if wick_ratio >= self.config.wick_body_ratio:
                return {
                    'wick_size': relevant_wick,
                    'body_size': body_size,
                    'ratio': wick_ratio,
                    'type': 'upper_wick'
                }
        
        elif direction == 'LONG':
            relevant_wick = lower_wick
            wick_ratio = relevant_wick / body_size
            
            if wick_ratio >= self.config.wick_body_ratio:
                return {
                    'wick_size': relevant_wick,
                    'body_size': body_size,
                    'ratio': wick_ratio,
                    'type': 'lower_wick'
                }
        
        return None
    
    def _check_volume(self, candle: dict, candles: List[dict], atr: float) -> Optional[Dict]:
        lookback = min(self.config.volume_lookback_bars, len(candles) - 1)
        
        if lookback < 10:
            return None
        
        recent_candles = candles[-lookback-1:-1]
        volumes = [c['volume'] for c in recent_candles]
        
        volume_p90 = np.percentile(volumes, self.config.volume_percentile)
        
        current_volume = candle['volume']
        
        if current_volume >= volume_p90:
            return {
                'current_volume': current_volume,
                'p90_volume': volume_p90,
                'volume_ratio': current_volume / volume_p90 if volume_p90 > 0 else 0
            }
        
        return None
    
    def _check_price_return(self, candle: dict, sweep_result: dict, direction: str) -> Optional[Dict]:
        sweep_level = sweep_result['sweep_level']
        close_price = candle['close']
        
        if direction == 'SHORT':
            if close_price < sweep_level:
                return {
                    'returned': True,
                    'return_amount': sweep_level - close_price,
                    'return_percent': ((sweep_level - close_price) / sweep_level) * 100
                }
        
        elif direction == 'LONG':
            if close_price > sweep_level:
                return {
                    'returned': True,
                    'return_amount': close_price - sweep_level,
                    'return_percent': ((close_price - sweep_level) / sweep_level) * 100
                }
        
        return None
    
    def _calculate_atr(self, candles: List[dict], period: int = 14) -> float:
        if len(candles) < 2:
            return 0.0
        
        trs = []
        for i in range(1, min(len(candles), period + 1)):
            current = candles[-i]
            previous = candles[-i-1] if i < len(candles) else candles[-i]
            
            high = current['high']
            low = current['low']
            prev_close = previous['close']
            
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            trs.append(tr)
        
        return sum(trs) / len(trs) if trs else 0.0
