import logging
from typing import Dict, Optional
import time

logger = logging.getLogger(__name__)


class SignalScorer:
    
    def __init__(self, config, cache, clustering, zone_detector):
        self.config = config
        self.cache = cache
        self.clustering = clustering
        self.zone_detector = zone_detector
        
        self._recent_signals: Dict[str, float] = {}
    
    def score_signal(self, pattern: Dict) -> Optional[Dict]:
        try:
            symbol = pattern['symbol']
            direction = pattern['direction']
            
            if not self.clustering.can_add_position_to_cluster(symbol):
                logger.debug(f"Cluster full for {symbol}, rejecting signal")
                return None
            
            sweep_score = min(pattern['sweep']['sweep_atr_ratio'] / 0.5 * 10, 10.0)
            
            wick_score = min(pattern['wick']['ratio'] / 3.0 * 10, 10.0)
            
            liq_score = pattern.get('liquidation_score', 5.0)
            
            oi_delta = pattern.get('oi_delta', 0)
            oi_score = min(abs(oi_delta) / 3.0 * 10, 10.0)
            
            volume_score = min(pattern['volume']['volume_ratio'] * 5, 10.0)
            
            base_score = (
                sweep_score * 0.25 +
                wick_score * 0.20 +
                liq_score * 0.25 +
                oi_score * 0.20 +
                volume_score * 0.10
            )
            
            cluster_penalty = self.clustering.get_cluster_penalty(symbol)
            
            leader_bonus = 0
            if self.clustering.is_leader_symbol(symbol):
                leader_bonus = 2.0
            else:
                leader_corr = self.clustering.get_correlation_with_leaders(symbol)
                leader_bonus = leader_corr * 1.5
            
            candle = pattern['candle']
            atr = pattern['atr']
            
            current_price = candle['close']
            
            nearest_zone = self._get_blocking_zone(symbol, current_price, direction, atr)
            
            if nearest_zone:
                zone_distance = abs(nearest_zone['price'] - current_price)
                risk_to_zone = zone_distance / atr
                
                if risk_to_zone < self.config.min_rr_to_zone:
                    logger.debug(f"Zone too close for {symbol}, RR: {risk_to_zone:.2f}R")
                    return None
                
                rr_bonus = min((risk_to_zone - 1.0) * 2, 3.0)
            else:
                rr_bonus = 3.0
            
            if self._is_duplicate_signal(symbol, direction):
                logger.debug(f"Duplicate signal for {symbol} {direction}")
                return None
            
            final_score = base_score - cluster_penalty + leader_bonus + rr_bonus
            final_score = max(0, min(final_score, 10.0))
            
            scored_signal = {
                **pattern,
                'scores': {
                    'sweep': sweep_score,
                    'wick': wick_score,
                    'liquidation': liq_score,
                    'oi': oi_score,
                    'volume': volume_score,
                    'base': base_score,
                    'cluster_penalty': cluster_penalty,
                    'leader_bonus': leader_bonus,
                    'rr_bonus': rr_bonus,
                    'final': final_score
                },
                'nearest_zone': nearest_zone,
                'scored_at': time.time()
            }
            
            self._recent_signals[f"{symbol}_{direction}"] = time.time()
            
            return scored_signal
        
        except Exception as e:
            logger.error(f"Error scoring signal: {e}")
            return None
    
    def _get_blocking_zone(self, symbol: str, current_price: float, direction: str, atr: float) -> Optional[Dict]:
        if direction == 'SHORT':
            zone = self.cache.zones.get_nearest_support(symbol, current_price)
        else:
            zone = self.cache.zones.get_nearest_resistance(symbol, current_price)
        
        return zone
    
    def _is_duplicate_signal(self, symbol: str, direction: str, cooldown_bars: int = 3) -> bool:
        key = f"{symbol}_{direction}"
        
        last_signal_time = self._recent_signals.get(key)
        
        if last_signal_time is None:
            return False
        
        time_since = time.time() - last_signal_time
        
        cooldown_seconds = cooldown_bars * 15 * 60
        
        return time_since < cooldown_seconds
    
    def cleanup_old_signals(self, max_age_hours: int = 24):
        cutoff_time = time.time() - (max_age_hours * 3600)
        
        to_remove = [
            key for key, timestamp in self._recent_signals.items()
            if timestamp < cutoff_time
        ]
        
        for key in to_remove:
            del self._recent_signals[key]
