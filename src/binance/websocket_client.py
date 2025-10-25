import asyncio
import websockets
import json
import logging
from typing import List, Callable, Optional, Dict, Any
from config import BinanceConfig

logger = logging.getLogger(__name__)


class BinanceWebSocketClient:
    
    def __init__(self, config: BinanceConfig, name: str = "WSClient"):
        self.config = config
        self.name = name
        self.ws_url = config.futures_ws_base_url
        self.ws: Optional[Any] = None
        self.running = False
        self.reconnect_delay = config.ws_reconnect_delay
        self.max_reconnect_delay = config.ws_reconnect_max_delay
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = config.ws_max_reconnect_attempts
        
        self.callbacks: Dict[str, List[Callable]] = {}
        self.streams: List[str] = []
    
    def subscribe_callback(self, stream_type: str, callback: Callable):
        if stream_type not in self.callbacks:
            self.callbacks[stream_type] = []
        self.callbacks[stream_type].append(callback)
    
    async def connect(self, streams: List[str]):
        self.streams = streams
        self.running = True
        
        while self.running:
            try:
                await self._connect_and_listen()
            except Exception as e:
                logger.error(f"{self.name} connection error: {e}")
                if self.running:
                    delay = min(self.reconnect_delay * (2 ** self.reconnect_attempts), self.max_reconnect_delay)
                    self.reconnect_attempts += 1
                    
                    if self.reconnect_attempts > self.max_reconnect_attempts:
                        logger.critical(f"{self.name} max reconnect attempts reached, stopping")
                        self.running = False
                        break
                    
                    logger.info(f"{self.name} reconnecting in {delay}s (attempt {self.reconnect_attempts})")
                    await asyncio.sleep(delay)
    
    async def _connect_and_listen(self):
        if not self.streams:
            logger.warning(f"{self.name} no streams to subscribe")
            return
        
        streams_param = '/'.join(self.streams)
        url = f"{self.ws_url}/stream?streams={streams_param}"
        
        logger.info(f"{self.name} connecting to {len(self.streams)} streams")
        
        async with websockets.connect(url, ping_interval=self.config.ws_ping_interval) as ws:
            self.ws = ws
            self.reconnect_attempts = 0
            logger.info(f"{self.name} connected successfully")
            
            async for message in ws:
                if not self.running:
                    break
                
                try:
                    data = json.loads(message)
                    await self._handle_message(data)
                except json.JSONDecodeError as e:
                    logger.error(f"{self.name} JSON decode error: {e}")
                except Exception as e:
                    logger.error(f"{self.name} message handling error: {e}")
    
    async def _handle_message(self, data: Dict[str, Any]):
        if 'stream' not in data or 'data' not in data:
            return
        
        stream = data['stream']
        message_data = data['data']
        
        if '@kline' in stream:
            await self._dispatch_callback('kline', message_data)
        elif 'forceOrder' in stream:
            await self._dispatch_callback('liquidation', message_data)
        elif '@markPrice' in stream:
            await self._dispatch_callback('markPrice', message_data)
    
    async def _dispatch_callback(self, stream_type: str, data: Any):
        if stream_type in self.callbacks:
            for callback in self.callbacks[stream_type]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(data)
                    else:
                        callback(data)
                except Exception as e:
                    logger.error(f"{self.name} callback error for {stream_type}: {e}")
    
    async def stop(self):
        self.running = False
        if self.ws:
            await self.ws.close()
        logger.info(f"{self.name} stopped")
