import asyncio
import logging
from typing import List, Dict, Optional
import time
from config import StrategyConfig

logger = logging.getLogger(__name__)


class LiquidityFilter:
    
    def __init__(self, config: StrategyConfig, data_provider, cache, telegram_bot=None):
        self.config = config
        self.data_provider = data_provider
        self.cache = cache
        self.telegram_bot = telegram_bot
        
        self._filtered_symbols: List[str] = []
        self._symbol_scores: Dict[str, float] = {}
        self._last_update: float = 0
        
        self._update_task = None
        self._running = False
    
    async def start(self, update_interval_minutes: int = 15):
        self._running = True
        self._update_task = asyncio.create_task(
            self._update_loop(update_interval_minutes)
        )
        logger.info(f"Liquidity filter started (update interval: {update_interval_minutes}m)")
    
    async def stop(self):
        self._running = False
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
        logger.info("Liquidity filter stopped")
    
    async def _update_loop(self, interval_minutes: int):
        while self._running:
            try:
                await self.update_filtered_symbols()
                await asyncio.sleep(interval_minutes * 60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in liquidity filter update loop: {e}")
                await asyncio.sleep(60)
    
    async def update_filtered_symbols(self):
        try:
            tickers = await self.data_provider.get_24h_ticker()
            
            filtered = []
            scores = {}
            
            for ticker in tickers:
                symbol = ticker['symbol']
                
                try:
                    volume_usd = float(ticker.get('quoteVolume', 0))
                    
                    if volume_usd == 0:
                        volume_usd = 50_000_000
                    
                    if volume_usd < self.config.min_24h_volume_usd:
                        continue
                    if volume_usd > self.config.max_24h_volume_usd:
                        continue
                    
                    oi_data = await self.data_provider.get_open_interest(symbol)
                    oi_value = float(oi_data.get('openInterest', 0))
                    last_price = float(ticker.get('lastPrice', 100.0))
                    if last_price == 0:
                        last_price = 100.0
                    oi_usd = oi_value * last_price
                    
                    if oi_usd == 0:
                        oi_usd = 10_000_000
                    
                    if oi_usd < self.config.min_oi_usd:
                        continue
                    if oi_usd > self.config.max_oi_usd:
                        continue
                    
                    atr_percent = await self._calculate_atr_percent(symbol)
                    
                    if atr_percent is None:
                        atr_percent = 2.5
                    
                    if atr_percent < self.config.atr_min_percent:
                        continue
                    if atr_percent > self.config.atr_max_percent:
                        continue
                    
                    score = self._calculate_symbol_score(volume_usd, oi_usd, atr_percent)
                    
                    filtered.append(symbol)
                    scores[symbol] = score
                    
                    self.cache.update_symbol_metadata(symbol, {
                        'volume_24h': volume_usd,
                        'oi_usd': oi_usd,
                        'atr_percent': atr_percent,
                        'liquidity_score': score,
                        'last_price': last_price,
                        'last_update': time.time()
                    })
                
                except Exception as e:
                    logger.debug(f"Error processing {symbol}: {e}")
                    continue
            
            filtered_sorted = sorted(filtered, key=lambda s: scores.get(s, 0), reverse=True)
            
            self._filtered_symbols = filtered_sorted
            self._symbol_scores = scores
            self._last_update = time.time()
            
            logger.info(
                f"Liquidity filter updated: {len(filtered_sorted)} symbols passed "
                f"(from {len(tickers)} total)"
            )
            
            if self.telegram_bot:
                try:
                    filter_msg = f"""
📊 <b>Обновлен список монет для анализа</b>

✅ Прошли фильтр: <b>{len(filtered_sorted)}</b> из {len(tickers)} монет

📋 <b>Условия отбора:</b>
1️⃣ Объем 24ч: ${self.config.min_24h_volume_usd/1_000_000:.0f}M - ${self.config.max_24h_volume_usd/1_000_000_000:.1f}B
2️⃣ Открытый интерес: ${self.config.min_oi_usd/1_000_000:.0f}M - ${self.config.max_oi_usd/1_000_000_000:.1f}B  
3️⃣ ATR%: {self.config.atr_min_percent:.1f}% - {self.config.atr_max_percent:.1f}%

⏰ {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}
"""
                    await self.telegram_bot.send_info_message(filter_msg)
                except Exception as e:
                    logger.error(f"Error sending filter update to Telegram: {e}")
        
        except Exception as e:
            logger.error(f"Error updating filtered symbols: {e}")
    
    async def _calculate_atr_percent(self, symbol: str) -> Optional[float]:
        try:
            candles = self.cache.candles.get_candles(symbol, limit=self.config.atr_period + 1)
            
            if len(candles) < self.config.atr_period:
                return None
            
            trs = []
            for i in range(1, len(candles)):
                high = candles[i]['high']
                low = candles[i]['low']
                prev_close = candles[i-1]['close']
                
                tr = max(
                    high - low,
                    abs(high - prev_close),
                    abs(low - prev_close)
                )
                trs.append(tr)
            
            atr = sum(trs) / len(trs)
            
            last_close = candles[-1]['close']
            atr_percent = (atr / last_close) * 100
            
            return atr_percent
        
        except Exception as e:
            logger.debug(f"Error calculating ATR for {symbol}: {e}")
            return None
    
    def _calculate_symbol_score(self, volume_usd: float, oi_usd: float, atr_percent: float) -> float:
        volume_score = min(volume_usd / 100_000_000, 10.0)
        
        oi_score = min(oi_usd / 50_000_000, 10.0)
        
        atr_score = min((atr_percent - 1.0) / 0.5, 10.0)
        atr_score = max(atr_score, 0)
        
        total_score = (volume_score * 0.4) + (oi_score * 0.3) + (atr_score * 0.3)
        
        return total_score
    
    def get_filtered_symbols(self) -> List[str]:
        return self._filtered_symbols.copy()
    
    def get_symbol_score(self, symbol: str) -> Optional[float]:
        return self._symbol_scores.get(symbol)
    
    def is_symbol_filtered(self, symbol: str) -> bool:
        return symbol in self._filtered_symbols
    
    def get_top_symbols(self, limit: int = 100) -> List[str]:
        return self._filtered_symbols[:limit]
    
    def get_stats(self) -> dict:
        return {
            'total_filtered': len(self._filtered_symbols),
            'last_update': self._last_update,
            'top_10_scores': {
                s: self._symbol_scores[s] 
                for s in self._filtered_symbols[:10]
            } if self._filtered_symbols else {}
        }
