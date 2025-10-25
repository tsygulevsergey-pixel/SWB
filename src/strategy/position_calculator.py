import logging
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class PositionCalculator:
    
    def __init__(self, config):
        self.config = config
    
    def calculate_entry_sl_tp(self, signal: Dict) -> Optional[Dict]:
        try:
            symbol = signal['symbol']
            direction = signal['direction']
            candle = signal['candle']
            atr = signal['atr']
            sweep_level = signal['sweep']['sweep_level']
            
            entry_price = self._calculate_entry(candle, direction, sweep_level)
            
            stop_loss = self._calculate_stop_loss(entry_price, direction, candle, atr)
            
            risk_distance = abs(entry_price - stop_loss)
            risk_percent = (risk_distance / entry_price) * 100
            
            if risk_percent > self.config.sl_max_percent:
                logger.debug(f"Risk too high for {symbol}: {risk_percent:.2f}%")
                return None
            
            tp1, tp2 = self._calculate_take_profits(entry_price, stop_loss, direction, risk_distance)
            
            position_data = {
                'symbol': symbol,
                'direction': direction,
                'entry_price': entry_price,
                'stop_loss': stop_loss,
                'take_profit_1': tp1,
                'take_profit_2': tp2,
                'risk_percent': risk_percent,
                'risk_distance': risk_distance,
                'atr': atr,
                'position_size_percent': 1.0,
                'sweep_level': sweep_level,
                'candle_time': candle.get('close_time')
            }
            
            return position_data
        
        except Exception as e:
            logger.error(f"Error calculating position: {e}")
            return None
    
    def _calculate_entry(self, candle: dict, direction: str, sweep_level: float) -> float:
        candle_open = candle['open']
        candle_close = candle['close']
        
        body_high = max(candle_open, candle_close)
        body_low = min(candle_open, candle_close)
        body_size = abs(candle_close - candle_open)
        
        if direction == 'SHORT':
            retracement_50 = body_high - (body_size * 0.50)
            retracement_62 = body_high - (body_size * 0.62)
            
            entry = (retracement_50 + retracement_62) / 2
        
        else:
            retracement_50 = body_low + (body_size * 0.50)
            retracement_62 = body_low + (body_size * 0.62)
            
            entry = (retracement_50 + retracement_62) / 2
        
        return entry
    
    def _calculate_stop_loss(self, entry: float, direction: str, candle: dict, atr: float) -> float:
        if direction == 'SHORT':
            extremum = candle['high']
            
            sl_atr_multiplier = (self.config.sl_atr_min + self.config.sl_atr_max) / 2
            
            stop_loss = extremum + (atr * sl_atr_multiplier)
        
        else:
            extremum = candle['low']
            
            sl_atr_multiplier = (self.config.sl_atr_min + self.config.sl_atr_max) / 2
            
            stop_loss = extremum - (atr * sl_atr_multiplier)
        
        risk_percent = abs((stop_loss - entry) / entry) * 100
        
        if risk_percent > self.config.sl_max_percent:
            if direction == 'SHORT':
                stop_loss = entry * (1 + self.config.sl_max_percent / 100)
            else:
                stop_loss = entry * (1 - self.config.sl_max_percent / 100)
        
        return stop_loss
    
    def _calculate_take_profits(self, entry: float, stop_loss: float, direction: str, risk_distance: float) -> Tuple[float, float]:
        r_multiplier_tp1 = self.config.tp1_r
        
        if direction == 'SHORT':
            tp1_by_r = entry - (risk_distance * r_multiplier_tp1)
            tp1_by_percent = entry * (1 - self.config.tp1_percent / 100)
            
            tp1 = max(tp1_by_r, tp1_by_percent)
            
            tp2_min = entry * (1 - self.config.tp2_min_percent / 100)
            tp2_max = entry * (1 - self.config.tp2_max_percent / 100)
            
            tp2_by_r_min = entry - (risk_distance * self.config.tp2_r_min)
            tp2_by_r_max = entry - (risk_distance * self.config.tp2_r_max)
            
            tp2 = min(max(tp2_by_r_min, tp2_max), tp2_min)
        
        else:
            tp1_by_r = entry + (risk_distance * r_multiplier_tp1)
            tp1_by_percent = entry * (1 + self.config.tp1_percent / 100)
            
            tp1 = min(tp1_by_r, tp1_by_percent)
            
            tp2_min = entry * (1 + self.config.tp2_min_percent / 100)
            tp2_max = entry * (1 + self.config.tp2_max_percent / 100)
            
            tp2_by_r_min = entry + (risk_distance * self.config.tp2_r_min)
            tp2_by_r_max = entry + (risk_distance * self.config.tp2_r_max)
            
            tp2 = max(min(tp2_by_r_min, tp2_max), tp2_min)
        
        return tp1, tp2
