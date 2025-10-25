import logging
from typing import Optional, Any
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from config import TelegramConfig
import pytz
from datetime import datetime

logger = logging.getLogger(__name__)


class TradingBot:
    
    def __init__(self, config: TelegramConfig):
        self.config = config
        self.app: Optional[Application] = None
        self.tz = pytz.timezone('Europe/Kiev')
        
        self.stats = {
            'total_signals': 0,
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'tp1_hits': 0,
            'tp2_hits': 0,
            'sl_hits': 0,
            'total_pnl_percent': 0.0
        }
        
        self.active_trades = {}
    
    async def start(self):
        if not self.config.bot_token:
            logger.error("Telegram bot token not configured")
            return
        
        self.app = Application.builder().token(self.config.bot_token).build()
        
        self.app.add_handler(CommandHandler("stats", self.cmd_stats))
        self.app.add_handler(CommandHandler("status", self.cmd_status))
        
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()
        
        logger.info("Telegram bot started")
    
    async def stop(self):
        if self.app:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
        logger.info("Telegram bot stopped")
    
    async def cmd_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            win_rate = 0
            if self.stats['total_trades'] > 0:
                win_rate = (self.stats['winning_trades'] / self.stats['total_trades']) * 100
            
            avg_pnl = 0
            if self.stats['total_trades'] > 0:
                avg_pnl = self.stats['total_pnl_percent'] / self.stats['total_trades']
            
            message = f"""
📊 <b>Статистика торговли LSFP-15</b>

🔔 Сигналы: {self.stats['total_signals']}
📈 Всего сделок: {self.stats['total_trades']}

✅ Выигрышных: {self.stats['winning_trades']}
❌ Проигрышных: {self.stats['losing_trades']}

🎯 Win Rate: {win_rate:.2f}%

💰 PnL:
  • Общий: {self.stats['total_pnl_percent']:.2f}%
  • Средний: {avg_pnl:.2f}%

🎯 Тейки:
  • TP1: {self.stats['tp1_hits']}
  • TP2: {self.stats['tp2_hits']}

🛑 Стопы: {self.stats['sl_hits']}

⏰ Время: {datetime.now(self.tz).strftime('%Y-%m-%d %H:%M:%S')} (Киев)
"""
            
            await self._send_message(message)
            
        except Exception as e:
            logger.error(f"Error in cmd_stats: {e}")
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self.active_trades:
                message = "📭 Нет открытых позиций"
            else:
                message = f"📊 <b>Открытые позиции ({len(self.active_trades)})</b>\n\n"
                
                for symbol, trade in self.active_trades.items():
                    direction = "🟢 LONG" if trade['direction'] == 'LONG' else "🔴 SHORT"
                    pnl = trade.get('pnl_percent', 0)
                    pnl_emoji = "✅" if pnl > 0 else "❌" if pnl < 0 else "⚪"
                    
                    message += f"{direction} {symbol}\n"
                    message += f"  • Вход: {trade['entry_price']:.4f}\n"
                    message += f"  • Текущая: {trade.get('current_price', 0):.4f}\n"
                    message += f"  • {pnl_emoji} PnL: {pnl:.2f}%\n"
                    message += f"  • Баров в сделке: {trade.get('bars_in_trade', 0)}\n\n"
            
            message += f"\n⏰ {datetime.now(self.tz).strftime('%Y-%m-%d %H:%M:%S')} (Киев)"
            
            await self._send_message(message)
            
        except Exception as e:
            logger.error(f"Error in cmd_status: {e}")
    
    async def send_signal(self, signal: dict):
        try:
            direction = "🟢 LONG" if signal['direction'] == 'LONG' else "🔴 SHORT"
            
            message = f"""
🚨 <b>Новый сигнал LSFP-15</b>

{direction} <b>{signal['symbol']}</b>

💵 Вход: {signal['entry_price']:.4f}
🛑 SL: {signal['stop_loss']:.4f}
🎯 TP1: {signal['take_profit_1']:.4f}
🎯 TP2: {signal['take_profit_2']:.4f}

📊 Размер: {signal.get('position_size_percent', 1.0)}% баланса

📝 Причина:
{signal.get('reason', 'N/A')}

📍 Зоны:
  • Сопротивление: {signal.get('nearest_resistance', 'N/A')}
  • Поддержка: {signal.get('nearest_support', 'N/A')}

⏰ {datetime.now(self.tz).strftime('%Y-%m-%d %H:%M:%S')} (Киев)
"""
            
            await self._send_message(message)
            self.stats['total_signals'] += 1
            
        except Exception as e:
            logger.error(f"Error sending signal: {e}")
    
    async def _send_message(self, message: str):
        if not self.config.chat_id:
            logger.warning("Chat ID not configured, message not sent")
            return
        
        if len(message) > self.config.max_message_length:
            chunks = self._split_message(message)
            for chunk in chunks:
                await self.app.bot.send_message(
                    chat_id=self.config.chat_id,
                    text=chunk,
                    parse_mode='HTML'
                )
        else:
            await self.app.bot.send_message(
                chat_id=self.config.chat_id,
                text=message,
                parse_mode='HTML'
            )
    
    def _split_message(self, message: str) -> list:
        max_len = self.config.max_message_length
        chunks = []
        
        while len(message) > max_len:
            split_pos = message.rfind('\n', 0, max_len)
            if split_pos == -1:
                split_pos = max_len
            
            chunks.append(message[:split_pos])
            message = message[split_pos:].lstrip()
        
        if message:
            chunks.append(message)
        
        return chunks
    
    def update_trade(self, symbol: str, trade_data: dict):
        self.active_trades[symbol] = trade_data
    
    def close_trade(self, symbol: str, won: bool, pnl_percent: float, exit_reason: str):
        if symbol in self.active_trades:
            del self.active_trades[symbol]
        
        self.stats['total_trades'] += 1
        self.stats['total_pnl_percent'] += pnl_percent
        
        if won:
            self.stats['winning_trades'] += 1
        else:
            self.stats['losing_trades'] += 1
        
        if 'TP1' in exit_reason:
            self.stats['tp1_hits'] += 1
        elif 'TP2' in exit_reason:
            self.stats['tp2_hits'] += 1
        elif 'SL' in exit_reason:
            self.stats['sl_hits'] += 1
