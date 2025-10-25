import asyncio
import random
import time
import logging
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime, timedelta
import pytz

from .data_provider import BinanceDataProvider

logger = logging.getLogger(__name__)


class MockBinanceProvider(BinanceDataProvider):
    
    def __init__(self):
        self.running = False
        self.kline_tasks = {}
        self.liquidation_task = None
        self.kline_callbacks = []
        self.liquidation_callbacks = []
        
        self.mock_symbols = self._generate_mock_symbols()
        self.symbol_prices = self._initialize_prices()
        
    def _generate_mock_symbols(self) -> List[str]:
        major_pairs = [
            'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT',
            'ADAUSDT', 'DOGEUSDT', 'MATICUSDT', 'DOTUSDT', 'AVAXUSDT',
            'LINKUSDT', 'ATOMUSDT', 'UNIUSDT', 'ETCUSDT', 'LTCUSDT',
            'NEARUSDT', 'ALGOUSDT', 'VETUSDT', 'ICPUSDT', 'FILUSDT',
            'APTUSDT', 'ARBUSDT', 'OPUSDT', 'SUIUSDT', 'INJUSDT',
            'SEIUSDT', 'TIAUSDT', 'WLDUSDT', 'STXUSDT', 'RENDERUSDT'
        ]
        
        mid_pairs = [
            f"COIN{i}USDT" for i in range(1, 71)
        ]
        
        return major_pairs + mid_pairs
    
    def _initialize_prices(self) -> Dict[str, float]:
        prices = {
            'BTCUSDT': 67500.0,
            'ETHUSDT': 2650.0,
            'BNBUSDT': 585.0,
            'SOLUSDT': 165.0,
            'XRPUSDT': 0.52,
            'ADAUSDT': 0.35,
            'DOGEUSDT': 0.145,
            'MATICUSDT': 0.68,
            'DOTUSDT': 4.25,
            'AVAXUSDT': 27.5,
        }
        
        for symbol in self.mock_symbols:
            if symbol not in prices:
                prices[symbol] = random.uniform(0.5, 100.0)
        
        return prices
    
    async def start(self):
        self.running = True
        logger.info("Mock Binance provider started")
    
    async def stop(self):
        self.running = False
        
        for task in self.kline_tasks.values():
            task.cancel()
        
        if self.liquidation_task:
            self.liquidation_task.cancel()
        
        logger.info("Mock Binance provider stopped")
    
    async def get_all_usdt_perps(self) -> List[str]:
        await asyncio.sleep(0.1)
        return self.mock_symbols.copy()
    
    async def get_exchange_info(self) -> Dict[str, Any]:
        await asyncio.sleep(0.1)
        
        symbols_info = []
        for symbol in self.mock_symbols:
            symbols_info.append({
                'symbol': symbol,
                'status': 'TRADING',
                'baseAsset': symbol.replace('USDT', ''),
                'quoteAsset': 'USDT',
                'contractType': 'PERPETUAL',
                'pricePrecision': 2,
                'quantityPrecision': 3,
            })
        
        return {
            'timezone': 'UTC',
            'serverTime': int(time.time() * 1000),
            'symbols': symbols_info
        }
    
    async def get_24h_ticker(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        await asyncio.sleep(0.05)
        
        if symbol:
            symbols = [symbol]
        else:
            symbols = self.mock_symbols
        
        tickers = []
        for sym in symbols:
            price = self.symbol_prices.get(sym, 100.0)
            
            volume_base = price * 1_000_000
            if sym in ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT']:
                volume_base *= random.uniform(50, 200)
            else:
                volume_base *= random.uniform(5, 30)
            
            tickers.append({
                'symbol': sym,
                'priceChange': price * random.uniform(-0.05, 0.05),
                'priceChangePercent': random.uniform(-5, 5),
                'lastPrice': str(price),
                'volume': str(volume_base / price),
                'quoteVolume': str(volume_base),
                'openPrice': str(price * random.uniform(0.95, 1.05)),
                'highPrice': str(price * random.uniform(1.00, 1.08)),
                'lowPrice': str(price * random.uniform(0.92, 1.00)),
                'count': random.randint(50000, 500000)
            })
        
        return tickers
    
    async def get_open_interest(self, symbol: str) -> Dict[str, Any]:
        await asyncio.sleep(0.05)
        
        price = self.symbol_prices.get(symbol, 100.0)
        
        oi_value = random.uniform(2_000_000, 50_000_000)
        
        return {
            'symbol': symbol,
            'openInterest': str(oi_value / price),
            'time': int(time.time() * 1000)
        }
    
    async def get_klines(self, symbol: str, interval: str, limit: int = 500, 
                        start_time: Optional[int] = None, end_time: Optional[int] = None) -> List[List]:
        await asyncio.sleep(0.1)
        
        interval_ms = self._interval_to_ms(interval)
        
        now = int(time.time() * 1000)
        if end_time:
            current_time = end_time
        else:
            current_time = now
        
        klines = []
        price = self.symbol_prices.get(symbol, 100.0)
        
        for i in range(limit):
            open_time = current_time - (limit - i) * interval_ms
            close_time = open_time + interval_ms - 1
            
            volatility = 0.015
            open_price = price * (1 + random.uniform(-volatility, volatility))
            close_price = open_price * (1 + random.uniform(-volatility, volatility))
            high_price = max(open_price, close_price) * (1 + random.uniform(0, volatility * 0.5))
            low_price = min(open_price, close_price) * (1 - random.uniform(0, volatility * 0.5))
            
            volume = random.uniform(1000, 10000)
            
            klines.append([
                open_time,
                f"{open_price:.4f}",
                f"{high_price:.4f}",
                f"{low_price:.4f}",
                f"{close_price:.4f}",
                f"{volume:.2f}",
                close_time,
                f"{volume * close_price:.2f}",
                random.randint(100, 1000),
                f"{volume * 0.6:.2f}",
                f"{volume * close_price * 0.6:.2f}",
                "0"
            ])
            
            price = close_price
        
        return klines
    
    def _interval_to_ms(self, interval: str) -> int:
        unit = interval[-1]
        value = int(interval[:-1])
        
        if unit == 'm':
            return value * 60 * 1000
        elif unit == 'h':
            return value * 60 * 60 * 1000
        elif unit == 'd':
            return value * 24 * 60 * 60 * 1000
        else:
            return 60 * 1000
    
    async def subscribe_klines(self, symbols: List[str], interval: str, callback):
        task_key = f"{interval}_{'-'.join(sorted(symbols[:5]))}"
        
        if task_key in self.kline_tasks:
            logger.warning(f"Mock: task for {interval} already exists, cancelling old one")
            self.kline_tasks[task_key].cancel()
        
        self.kline_callbacks.append((symbols, interval, callback))
        
        task = asyncio.create_task(self._kline_emitter(symbols, interval, callback))
        self.kline_tasks[task_key] = task
        
        logger.info(f"Mock: subscribed to {len(symbols)} symbols for {interval} klines")
    
    async def unsubscribe_klines(self, symbols: List[str], interval: str):
        task_key = f"{interval}_{'-'.join(sorted(symbols[:5]))}"
        
        if task_key in self.kline_tasks:
            self.kline_tasks[task_key].cancel()
            del self.kline_tasks[task_key]
            logger.info(f"Mock: unsubscribed from {len(symbols)} symbols for {interval} klines")
        
        self.kline_callbacks = [
            (s, i, c) for s, i, c in self.kline_callbacks
            if not (i == interval and set(s) == set(symbols))
        ]
    
    async def _kline_emitter(self, symbols: List[str], interval: str, callback: Callable):
        interval_seconds = self._interval_to_ms(interval) / 1000
        
        while self.running:
            try:
                for symbol in symbols:
                    if not self.running:
                        break
                    
                    await self._emit_kline(symbol, interval, callback)
                    await asyncio.sleep(0.01)
                
                await asyncio.sleep(max(1, interval_seconds / 10))
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in kline emitter: {e}")
                await asyncio.sleep(1)
    
    async def _emit_kline(self, symbol: str, interval: str, callback: Callable):
        price = self.symbol_prices.get(symbol, 100.0)
        
        now = int(time.time() * 1000)
        interval_ms = self._interval_to_ms(interval)
        
        open_time = (now // interval_ms) * interval_ms
        close_time = open_time + interval_ms - 1
        
        is_closed = random.random() < 0.15
        
        volatility = 0.01
        open_price = price
        close_price = price * (1 + random.uniform(-volatility, volatility))
        high_price = max(open_price, close_price) * (1 + random.uniform(0, volatility * 0.5))
        low_price = min(open_price, close_price) * (1 - random.uniform(0, volatility * 0.5))
        
        volume = random.uniform(1000, 5000)
        
        kline_data = {
            'e': 'kline',
            'E': now,
            's': symbol,
            'k': {
                't': open_time,
                'T': close_time,
                's': symbol,
                'i': interval,
                'o': f"{open_price:.4f}",
                'c': f"{close_price:.4f}",
                'h': f"{high_price:.4f}",
                'l': f"{low_price:.4f}",
                'v': f"{volume:.2f}",
                'n': random.randint(100, 500),
                'x': is_closed,
                'q': f"{volume * close_price:.2f}",
            }
        }
        
        if is_closed:
            self.symbol_prices[symbol] = close_price
        
        await callback(kline_data)
    
    async def subscribe_liquidations(self, callback):
        self.liquidation_callbacks.append(callback)
        
        self.liquidation_task = asyncio.create_task(self._liquidation_emitter(callback))
        
        logger.info("Mock: subscribed to liquidation events")
    
    async def _liquidation_emitter(self, callback: Callable):
        while self.running:
            try:
                await asyncio.sleep(random.uniform(2, 8))
                
                if not self.running:
                    break
                
                symbol = random.choice(self.mock_symbols)
                price = self.symbol_prices.get(symbol, 100.0)
                
                side = random.choice(['BUY', 'SELL'])
                quantity = random.uniform(100, 5000)
                
                liquidation_data = {
                    'e': 'forceOrder',
                    'E': int(time.time() * 1000),
                    'o': {
                        's': symbol,
                        'S': side,
                        'o': 'LIMIT',
                        'f': 'IOC',
                        'q': f"{quantity:.2f}",
                        'p': f"{price:.4f}",
                        'ap': f"{price:.4f}",
                        'X': 'FILLED',
                        'l': f"{quantity:.2f}",
                        'z': f"{quantity:.2f}",
                        'T': int(time.time() * 1000),
                    }
                }
                
                await callback(liquidation_data)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in liquidation emitter: {e}")
                await asyncio.sleep(1)
    
    async def unsubscribe_all(self):
        await self.stop()
