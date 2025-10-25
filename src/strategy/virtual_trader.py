import asyncio
import logging
from typing import Dict, List, Optional
import time

logger = logging.getLogger(__name__)


class VirtualTrader:
    
    def __init__(self, config, cache, telegram_bot):
        self.config = config
        self.cache = cache
        self.telegram_bot = telegram_bot
        
        self._active_trades: Dict[str, dict] = {}
        
        self._closed_trades: List[dict] = []
        
        self._update_task = None
        self._running = False
    
    async def start(self, update_interval_seconds: int = 60):
        self._running = True
        self._update_task = asyncio.create_task(
            self._update_loop(update_interval_seconds)
        )
        logger.info(f"Virtual trader started (update interval: {update_interval_seconds}s)")
    
    async def stop(self):
        self._running = False
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
        logger.info("Virtual trader stopped")
    
    async def _update_loop(self, interval_seconds: int):
        while self._running:
            try:
                await self.update_all_trades()
                await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in virtual trader update loop: {e}")
                await asyncio.sleep(10)
    
    async def open_trade(self, position_data: dict, signal: dict):
        try:
            symbol = position_data['symbol']
            
            if symbol in self._active_trades:
                logger.warning(f"Trade already open for {symbol}")
                return
            
            trade = {
                **position_data,
                'signal': signal,
                'opened_at': time.time(),
                'bars_in_trade': 0,
                'current_price': position_data['entry_price'],
                'pnl_percent': 0.0,
                'highest_r': 0.0,
                'status': 'OPEN'
            }
            
            self._active_trades[symbol] = trade
            
            if self.telegram_bot:
                await self.telegram_bot.send_signal({
                    'symbol': symbol,
                    'direction': position_data['direction'],
                    'entry_price': position_data['entry_price'],
                    'stop_loss': position_data['stop_loss'],
                    'take_profit_1': position_data['take_profit_1'],
                    'take_profit_2': position_data['take_profit_2'],
                    'position_size_percent': position_data['position_size_percent'],
                    'reason': self._format_signal_reason(signal),
                    'nearest_resistance': signal.get('nearest_zone', {}).get('price') if position_data['direction'] == 'SHORT' else 'N/A',
                    'nearest_support': signal.get('nearest_zone', {}).get('price') if position_data['direction'] == 'LONG' else 'N/A'
                })
            
            logger.info(f"Opened virtual trade: {symbol} {position_data['direction']} @ {position_data['entry_price']}")
        
        except Exception as e:
            logger.error(f"Error opening trade: {e}")
    
    async def update_all_trades(self):
        try:
            for symbol in list(self._active_trades.keys()):
                await self.update_trade(symbol)
        except Exception as e:
            logger.error(f"Error updating all trades: {e}")
    
    async def update_trade(self, symbol: str):
        try:
            trade = self._active_trades.get(symbol)
            
            if not trade:
                return
            
            last_candle = self.cache.candles.get_last_candle(symbol)
            
            if not last_candle:
                return
            
            current_price = last_candle['close']
            
            trade['current_price'] = current_price
            trade['bars_in_trade'] += 1
            
            pnl_percent = self._calculate_pnl(trade, current_price)
            trade['pnl_percent'] = pnl_percent
            
            risk_distance = trade['risk_distance']
            r_achieved = abs(pnl_percent / trade['risk_percent'])
            trade['highest_r'] = max(trade.get('highest_r', 0), r_achieved)
            
            exit_reason = self._check_exit_conditions(trade, current_price)
            
            if exit_reason:
                await self.close_trade(symbol, exit_reason)
            else:
                if self.telegram_bot:
                    self.telegram_bot.update_trade(symbol, trade)
        
        except Exception as e:
            logger.error(f"Error updating trade for {symbol}: {e}")
    
    def _calculate_pnl(self, trade: dict, current_price: float) -> float:
        entry = trade['entry_price']
        direction = trade['direction']
        
        if direction == 'SHORT':
            pnl_percent = ((entry - current_price) / entry) * 100
        else:
            pnl_percent = ((current_price - entry) / entry) * 100
        
        return pnl_percent
    
    def _check_exit_conditions(self, trade: dict, current_price: float) -> Optional[str]:
        direction = trade['direction']
        
        tp1_hit = False
        tp2_hit = False
        sl_hit = False
        
        if direction == 'SHORT':
            if current_price <= trade['take_profit_2']:
                tp2_hit = True
            elif current_price <= trade['take_profit_1']:
                tp1_hit = True
            elif current_price >= trade['stop_loss']:
                sl_hit = True
        else:
            if current_price >= trade['take_profit_2']:
                tp2_hit = True
            elif current_price >= trade['take_profit_1']:
                tp1_hit = True
            elif current_price <= trade['stop_loss']:
                sl_hit = True
        
        if tp2_hit:
            return 'TP2'
        elif tp1_hit:
            return 'TP1'
        elif sl_hit:
            return 'SL'
        
        bars_in_trade = trade['bars_in_trade']
        highest_r = trade.get('highest_r', 0)
        
        if bars_in_trade >= self.config.time_stop_bars:
            if highest_r < self.config.time_stop_min_r:
                return 'TIME_STOP'
        
        if bars_in_trade >= self.config.time_stop_bars_max:
            return 'TIME_STOP_MAX'
        
        return None
    
    async def close_trade(self, symbol: str, exit_reason: str):
        try:
            trade = self._active_trades.get(symbol)
            
            if not trade:
                return
            
            trade['exit_reason'] = exit_reason
            trade['exit_price'] = trade['current_price']
            trade['closed_at'] = time.time()
            trade['status'] = 'CLOSED'
            
            final_pnl = trade['pnl_percent']
            
            won = final_pnl > 0
            
            self._closed_trades.append(trade)
            
            del self._active_trades[symbol]
            
            if self.telegram_bot:
                self.telegram_bot.close_trade(symbol, won, final_pnl, exit_reason)
            
            logger.info(
                f"Closed virtual trade: {symbol} {trade['direction']} | "
                f"Exit: {exit_reason} | PnL: {final_pnl:.2f}% | Bars: {trade['bars_in_trade']}"
            )
        
        except Exception as e:
            logger.error(f"Error closing trade for {symbol}: {e}")
    
    def _format_signal_reason(self, signal: dict) -> str:
        reasons = []
        
        sweep_ratio = signal['sweep'].get('sweep_atr_ratio', 0)
        reasons.append(f"Sweep: {sweep_ratio:.2f} ATR")
        
        wick_ratio = signal['wick'].get('ratio', 0)
        reasons.append(f"Wick/Body: {wick_ratio:.2f}x")
        
        liq_score = signal.get('liquidation_score', 0)
        reasons.append(f"Liq: {liq_score:.1f}/10")
        
        oi_delta = signal.get('oi_delta', 0)
        reasons.append(f"ΔOI: {oi_delta:.2f}%")
        
        volume_ratio = signal['volume'].get('volume_ratio', 0)
        reasons.append(f"Vol: {volume_ratio:.2f}x p90")
        
        return " | ".join(reasons)
    
    def get_active_trades(self) -> Dict[str, dict]:
        return self._active_trades.copy()
    
    def get_closed_trades(self, limit: int = 100) -> List[dict]:
        return self._closed_trades[-limit:]
    
    def get_stats(self) -> dict:
        total_trades = len(self._closed_trades)
        
        if total_trades == 0:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
                'total_pnl_percent': 0.0,
                'avg_pnl_percent': 0.0,
                'tp1_hits': 0,
                'tp2_hits': 0,
                'sl_hits': 0
            }
        
        winning_trades = sum(1 for t in self._closed_trades if t['pnl_percent'] > 0)
        losing_trades = total_trades - winning_trades
        
        win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0
        
        total_pnl = sum(t['pnl_percent'] for t in self._closed_trades)
        avg_pnl = total_pnl / total_trades if total_trades > 0 else 0
        
        tp1_hits = sum(1 for t in self._closed_trades if t.get('exit_reason') == 'TP1')
        tp2_hits = sum(1 for t in self._closed_trades if t.get('exit_reason') == 'TP2')
        sl_hits = sum(1 for t in self._closed_trades if t.get('exit_reason') == 'SL')
        
        return {
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'total_pnl_percent': total_pnl,
            'avg_pnl_percent': avg_pnl,
            'tp1_hits': tp1_hits,
            'tp2_hits': tp2_hits,
            'sl_hits': sl_hits
        }
