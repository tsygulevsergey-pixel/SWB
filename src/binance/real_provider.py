import asyncio
import logging
from typing import List, Dict, Any, Optional, Callable

from .data_provider import BinanceDataProvider
from .rest_client import BinanceRESTClient
from .websocket_client import BinanceWebSocketClient
from .rate_limiter import BinanceRateLimiter
from config import BinanceConfig

logger = logging.getLogger(__name__)


class RealBinanceProvider(BinanceDataProvider):
    
    def __init__(self, config: BinanceConfig):
        self.config = config
        self.rate_limiter = BinanceRateLimiter(config)
        self.rest_client = BinanceRESTClient(config, self.rate_limiter)
        self.ws_clients: Dict[str, BinanceWebSocketClient] = {}
    
    async def start(self):
        await self.rest_client.start()
        logger.info("Real Binance provider started")
    
    async def stop(self):
        await self.rest_client.stop()
        
        for ws_client in self.ws_clients.values():
            await ws_client.stop()
        
        logger.info("Real Binance provider stopped")
    
    async def get_all_usdt_perps(self) -> List[str]:
        return await self.rest_client.get_all_usdt_perps()
    
    async def get_exchange_info(self) -> Dict[str, Any]:
        return await self.rest_client.get_exchange_info()
    
    async def get_24h_ticker(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        return await self.rest_client.get_24h_ticker(symbol)
    
    async def get_open_interest(self, symbol: str) -> Dict[str, Any]:
        return await self.rest_client.get_open_interest(symbol)
    
    async def get_klines(self, symbol: str, interval: str, limit: int = 500,
                        start_time: Optional[int] = None, end_time: Optional[int] = None) -> List[List]:
        return await self.rest_client.get_klines(symbol, interval, limit, start_time, end_time)
    
    async def subscribe_klines(self, symbols: List[str], interval: str, callback: Callable):
        ws_key = f"klines_{interval}"
        
        if ws_key in self.ws_clients:
            logger.info(f"Replacing WebSocket for {interval} klines with new symbols")
            await self.ws_clients[ws_key].stop()
            del self.ws_clients[ws_key]
        
        ws_client = BinanceWebSocketClient(self.config, f"WS-{interval}")
        ws_client.subscribe_callback('kline', callback)
        
        streams = [f"{s.lower()}@kline_{interval}" for s in symbols]
        
        asyncio.create_task(ws_client.connect(streams))
        
        self.ws_clients[ws_key] = ws_client
        
        logger.info(f"Subscribed to {len(symbols)} symbols for {interval} klines")
    
    async def unsubscribe_klines(self, symbols: List[str], interval: str):
        ws_key = f"klines_{interval}"
        
        if ws_key in self.ws_clients:
            await self.ws_clients[ws_key].stop()
            del self.ws_clients[ws_key]
            logger.info(f"Unsubscribed from {interval} klines")
    
    async def subscribe_liquidations(self, callback: Callable):
        ws_key = "liquidations"
        
        if ws_key in self.ws_clients:
            logger.warning("WebSocket for liquidations already exists")
            return
        
        ws_client = BinanceWebSocketClient(self.config, "WS-Liquidations")
        ws_client.subscribe_callback('liquidation', callback)
        
        streams = ['!forceOrder@arr']
        
        asyncio.create_task(ws_client.connect(streams))
        
        self.ws_clients[ws_key] = ws_client
        
        logger.info("Subscribed to liquidation events")
    
    async def unsubscribe_all(self):
        for ws_client in self.ws_clients.values():
            await ws_client.stop()
        
        self.ws_clients.clear()
