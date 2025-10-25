import aiohttp
import asyncio
import logging
from typing import List, Dict, Optional, Any
from config import BinanceConfig
from src.binance.rate_limiter import BinanceRateLimiter

logger = logging.getLogger(__name__)


class BinanceRESTClient:
    
    def __init__(self, config: BinanceConfig, rate_limiter: BinanceRateLimiter):
        self.config = config
        self.rate_limiter = rate_limiter
        self.base_url = config.futures_rest_base_url
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def start(self):
        timeout = aiohttp.ClientTimeout(total=self.config.rest_timeout)
        self.session = aiohttp.ClientSession(timeout=timeout)
        logger.info("REST client started")
    
    async def stop(self):
        if self.session:
            await self.session.close()
        logger.info("REST client stopped")
    
    async def _request(self, method: str, endpoint: str, params: Optional[Dict] = None, weight: int = 1) -> Optional[Any]:
        if not self.session:
            raise RuntimeError("REST client not started")
        
        await self.rate_limiter.acquire(weight)
        
        url = f"{self.base_url}{endpoint}"
        
        for attempt in range(self.config.rest_max_retries):
            try:
                async with self.session.request(method, url, params=params) as response:
                    self.rate_limiter.update_from_headers(dict(response.headers))
                    
                    if response.status == 200:
                        return await response.json()
                    elif response.status == 429:
                        retry_after = int(response.headers.get('Retry-After', 60))
                        logger.warning(f"Rate limit exceeded (429), waiting {retry_after}s")
                        await asyncio.sleep(retry_after)
                        continue
                    else:
                        text = await response.text()
                        logger.error(f"Request failed: {response.status} - {text}")
                        return None
                        
            except asyncio.TimeoutError:
                logger.error(f"Request timeout (attempt {attempt + 1}/{self.config.rest_max_retries})")
                if attempt < self.config.rest_max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
            except Exception as e:
                logger.error(f"Request error: {e}")
                if attempt < self.config.rest_max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
        
        return None
    
    async def get_exchange_info(self) -> Optional[Dict]:
        return await self._request('GET', '/fapi/v1/exchangeInfo', weight=1)
    
    async def get_all_usdt_perps(self) -> List[str]:
        info = await self.get_exchange_info()
        if not info:
            return []
        
        symbols = []
        for symbol_info in info.get('symbols', []):
            if (symbol_info.get('quoteAsset') == 'USDT' and 
                symbol_info.get('contractType') == 'PERPETUAL' and
                symbol_info.get('status') == 'TRADING'):
                symbols.append(symbol_info['symbol'])
        
        logger.info(f"Found {len(symbols)} active USDT perpetual contracts")
        return symbols
    
    async def get_24h_ticker(self, symbol: Optional[str] = None) -> Optional[Any]:
        params = {'symbol': symbol} if symbol else {}
        weight = 1 if symbol else 40
        return await self._request('GET', '/fapi/v1/ticker/24hr', params=params, weight=weight)
    
    async def get_all_24h_tickers(self) -> List[Dict]:
        data = await self.get_24h_ticker()
        return data if data and isinstance(data, list) else []
    
    async def get_open_interest(self, symbol: str) -> Optional[Dict]:
        params = {'symbol': symbol}
        return await self._request('GET', '/fapi/v1/openInterest', params=params, weight=1)
    
    async def get_open_interest_hist(self, symbol: str, period: str = '5m', limit: int = 500) -> Optional[List[Dict]]:
        params = {
            'symbol': symbol,
            'period': period,
            'limit': limit
        }
        return await self._request('GET', '/futures/data/openInterestHist', params=params, weight=1)
    
    async def get_klines(self, symbol: str, interval: str, limit: int = 500, start_time: Optional[int] = None) -> Optional[List]:
        params = {
            'symbol': symbol,
            'interval': interval,
            'limit': min(limit, 1500)
        }
        if start_time:
            params['startTime'] = start_time
        
        weight = max(1, limit // 500)
        return await self._request('GET', '/fapi/v1/klines', params=params, weight=weight)
    
    async def get_batch_klines(self, symbols: List[str], interval: str, limit: int = 200) -> Dict[str, List]:
        tasks = []
        for symbol in symbols:
            tasks.append(self.get_klines(symbol, interval, limit))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        klines_data = {}
        for symbol, result in zip(symbols, results):
            if isinstance(result, Exception):
                logger.error(f"Failed to get klines for {symbol}: {result}")
            elif result:
                klines_data[symbol] = result
        
        return klines_data
