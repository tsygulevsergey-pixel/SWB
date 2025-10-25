import asyncio
import logging
from typing import List, Dict, Optional
import time
import numpy as np
from config import StrategyConfig

logger = logging.getLogger(__name__)


class ZoneDetector:
    
    def __init__(self, config: StrategyConfig, cache):
        self.config = config
        self.cache = cache
        
        self._update_task = None
        self._running = False
    
    async def start(self, update_interval_minutes: int = 30):
        self._running = True
        self._update_task = asyncio.create_task(
            self._update_loop(update_interval_minutes)
        )
        logger.info(f"Zone detector started (update interval: {update_interval_minutes}m)")
    
    async def stop(self):
        self._running = False
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
        logger.info("Zone detector stopped")
    
    async def _update_loop(self, interval_minutes: int):
        while self._running:
            try:
                await self.update_all_zones()
                await asyncio.sleep(interval_minutes * 60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in zone detector update loop: {e}")
                await asyncio.sleep(60)
    
    async def update_all_zones(self):
        try:
            symbols = self.cache.candles.get_symbols_with_data()
            
            updated_count = 0
            for symbol in symbols[:100]:
                try:
                    zones = await self.detect_zones(symbol)
                    if zones:
                        self.cache.zones.update_zones(symbol, zones)
                        updated_count += 1
                except Exception as e:
                    logger.debug(f"Error detecting zones for {symbol}: {e}")
            
            logger.info(f"Updated zones for {updated_count} symbols")
        
        except Exception as e:
            logger.error(f"Error updating all zones: {e}")
    
    async def detect_zones(self, symbol: str) -> List[dict]:
        candles_15m = self.cache.candles.get_candles(symbol, limit=200)
        
        if len(candles_15m) < 50:
            return []
        
        zones = []
        
        donchian_zones = self._detect_donchian_zones(candles_15m, symbol, '15m')
        zones.extend(donchian_zones)
        
        swing_zones = self._detect_swing_zones(candles_15m, symbol)
        zones.extend(swing_zones)
        
        wick_zones = self._detect_wick_zones(candles_15m, symbol)
        zones.extend(wick_zones)
        
        merged_zones = self._merge_close_zones(zones, symbol)
        
        scored_zones = self._score_zones(merged_zones, candles_15m)
        
        return scored_zones
    
    def _detect_donchian_zones(self, candles: List[dict], symbol: str, interval: str) -> List[dict]:
        zones = []
        
        if interval == '15m':
            period = self.config.donchian_15m_period
        else:
            period = 50
        
        if len(candles) < period:
            return zones
        
        highs = [c['high'] for c in candles[-period:]]
        lows = [c['low'] for c in candles[-period:]]
        
        don_high = max(highs)
        don_low = min(lows)
        
        last_close = candles[-1]['close']
        atr = self._calculate_atr(candles, 14)
        zone_width = atr * self.config.zone_width_atr_multiplier
        
        zones.append({
            'symbol': symbol,
            'price': don_high,
            'width': zone_width,
            'type': 'resistance',
            'source': f'donchian_{interval}',
            'score': 5.0,
            'created_at': time.time(),
            'touches': 1
        })
        
        zones.append({
            'symbol': symbol,
            'price': don_low,
            'width': zone_width,
            'type': 'support',
            'source': f'donchian_{interval}',
            'score': 5.0,
            'created_at': time.time(),
            'touches': 1
        })
        
        return zones
    
    def _detect_swing_zones(self, candles: List[dict], symbol: str, lookback: int = 10) -> List[dict]:
        zones = []
        
        if len(candles) < lookback * 2:
            return zones
        
        for i in range(lookback, len(candles) - lookback):
            is_swing_high = True
            is_swing_low = True
            
            current_high = candles[i]['high']
            current_low = candles[i]['low']
            
            for j in range(i - lookback, i + lookback + 1):
                if j == i:
                    continue
                
                if candles[j]['high'] >= current_high:
                    is_swing_high = False
                if candles[j]['low'] <= current_low:
                    is_swing_low = False
            
            atr = self._calculate_atr(candles[max(0, i-14):i+1], 14)
            zone_width = atr * self.config.zone_width_atr_multiplier
            
            if is_swing_high:
                zones.append({
                    'symbol': symbol,
                    'price': current_high,
                    'width': zone_width,
                    'type': 'resistance',
                    'source': 'swing_high',
                    'score': 6.0,
                    'created_at': time.time(),
                    'touches': 1
                })
            
            if is_swing_low:
                zones.append({
                    'symbol': symbol,
                    'price': current_low,
                    'width': zone_width,
                    'type': 'support',
                    'source': 'swing_low',
                    'score': 6.0,
                    'created_at': time.time(),
                    'touches': 1
                })
        
        return zones[-20:] if len(zones) > 20 else zones
    
    def _detect_wick_zones(self, candles: List[dict], symbol: str) -> List[dict]:
        zones = []
        
        if len(candles) < 20:
            return zones
        
        for i in range(10, len(candles)):
            candle = candles[i]
            
            body_size = abs(candle['close'] - candle['open'])
            upper_wick = candle['high'] - max(candle['open'], candle['close'])
            lower_wick = min(candle['open'], candle['close']) - candle['low']
            
            volume = candle['volume']
            avg_volume = np.mean([c['volume'] for c in candles[max(0, i-20):i]])
            
            atr = self._calculate_atr(candles[max(0, i-14):i+1], 14)
            zone_width = atr * self.config.zone_width_atr_multiplier
            
            if upper_wick > body_size * 2 and volume > avg_volume * 1.5:
                zones.append({
                    'symbol': symbol,
                    'price': candle['high'],
                    'width': zone_width,
                    'type': 'resistance',
                    'source': 'wick_rejection',
                    'score': 7.0,
                    'created_at': time.time(),
                    'touches': 1
                })
            
            if lower_wick > body_size * 2 and volume > avg_volume * 1.5:
                zones.append({
                    'symbol': symbol,
                    'price': candle['low'],
                    'width': zone_width,
                    'type': 'support',
                    'source': 'wick_rejection',
                    'score': 7.0,
                    'created_at': time.time(),
                    'touches': 1
                })
        
        return zones[-10:] if len(zones) > 10 else zones
    
    def _merge_close_zones(self, zones: List[dict], symbol: str) -> List[dict]:
        if not zones:
            return []
        
        sorted_zones = sorted(zones, key=lambda z: z['price'])
        
        merged = []
        current_zone = sorted_zones[0].copy()
        
        for next_zone in sorted_zones[1:]:
            price_diff = abs(next_zone['price'] - current_zone['price'])
            merge_threshold = current_zone['width'] + next_zone['width']
            
            if price_diff <= merge_threshold and current_zone['type'] == next_zone['type']:
                current_zone['price'] = (current_zone['price'] + next_zone['price']) / 2
                current_zone['score'] = max(current_zone['score'], next_zone['score']) + 1
                current_zone['touches'] += 1
                current_zone['width'] = max(current_zone['width'], next_zone['width'])
            else:
                merged.append(current_zone)
                current_zone = next_zone.copy()
        
        merged.append(current_zone)
        
        return merged
    
    def _score_zones(self, zones: List[dict], candles: List[dict]) -> List[dict]:
        if not candles:
            return zones
        
        recent_candles = candles[-50:]
        
        for zone in zones:
            zone_price = zone['price']
            zone_width = zone['width']
            
            touches = 0
            for candle in recent_candles:
                if abs(candle['high'] - zone_price) / zone_price <= 0.005:
                    touches += 1
                if abs(candle['low'] - zone_price) / zone_price <= 0.005:
                    touches += 1
            
            zone['touches'] = max(zone.get('touches', 1), touches)
            
            base_score = zone.get('score', 5.0)
            touch_bonus = min(touches * 0.5, 3.0)
            
            zone['score'] = min(base_score + touch_bonus, 10.0)
        
        return zones
    
    def _calculate_atr(self, candles: List[dict], period: int = 14) -> float:
        if len(candles) < period:
            return 0.0
        
        trs = []
        for i in range(1, min(len(candles), period + 1)):
            high = candles[-i]['high']
            low = candles[-i]['low']
            prev_close = candles[-i-1]['close'] if i < len(candles) else candles[-i]['close']
            
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            trs.append(tr)
        
        return sum(trs) / len(trs) if trs else 0.0
