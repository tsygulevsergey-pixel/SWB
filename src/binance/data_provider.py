from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import asyncio


class BinanceDataProvider(ABC):
    
    @abstractmethod
    async def start(self):
        pass
    
    @abstractmethod
    async def stop(self):
        pass
    
    @abstractmethod
    async def get_all_usdt_perps(self) -> List[str]:
        pass
    
    @abstractmethod
    async def get_exchange_info(self) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    async def get_24h_ticker(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        pass
    
    @abstractmethod
    async def get_open_interest(self, symbol: str) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    async def get_klines(self, symbol: str, interval: str, limit: int = 500, start_time: Optional[int] = None, end_time: Optional[int] = None) -> List[List]:
        pass
    
    @abstractmethod
    async def subscribe_klines(self, symbols: List[str], interval: str, callback):
        pass
    
    @abstractmethod
    async def subscribe_liquidations(self, callback):
        pass
    
    @abstractmethod
    async def unsubscribe_all(self):
        pass
