#!/usr/bin/env python3
import asyncio
import signal
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from config import config
from src.utils.logging_config import setup_logging
from src.database.schema import init_database
from src.binance.rate_limiter import BinanceRateLimiter
from src.binance.rest_client import BinanceRESTClient
from src.binance.websocket_client import BinanceWebSocketClient
from src.telegram_bot.bot import TradingBot

logger = logging.getLogger(__name__)


class LSFPBot:
    
    def __init__(self):
        self.running = False
        self.db_pool = None
        self.rate_limiter = None
        self.rest_client = None
        self.ws_client_15m = None
        self.ws_client_1m = None
        self.ws_client_liq = None
        self.telegram_bot = None
        
        self.symbols_cache = []
        self.hot_symbols = []
    
    async def start(self):
        logger.info("=== Starting LSFP-15 Trading Bot ===")
        
        try:
            logger.info("Initializing database...")
            self.db_pool = await init_database(config.database.url)
            
            logger.info("Initializing Binance clients...")
            self.rate_limiter = BinanceRateLimiter(config.binance)
            self.rest_client = BinanceRESTClient(config.binance, self.rate_limiter)
            await self.rest_client.start()
            
            logger.info("Fetching USDT perpetual symbols...")
            self.symbols_cache = await self.rest_client.get_all_usdt_perps()
            logger.info(f"Monitoring {len(self.symbols_cache)} USDT perpetual pairs")
            
            if not self.symbols_cache:
                logger.error("No symbols found, cannot continue")
                return
            
            logger.info("Initializing Telegram bot...")
            self.telegram_bot = TradingBot(config.telegram)
            await self.telegram_bot.start()
            
            logger.info("Setting up WebSocket connections...")
            await self._setup_websockets()
            
            logger.info("=== LSFP-15 Bot started successfully ===")
            logger.info(f"Monitoring {len(self.symbols_cache)} symbols")
            logger.info(f"Rate limiter: {config.binance.rate_limit_weight_per_minute}/min")
            logger.info(f"Timezone: {config.timezone}")
            logger.info(f"Telegram bot active: {bool(config.telegram.bot_token and config.telegram.chat_id)}")
            
            self.running = True
            
            await self._run_main_loop()
            
        except Exception as e:
            logger.critical(f"Fatal error during startup: {e}", exc_info=True)
            await self.stop()
    
    async def _setup_websockets(self):
        kline_15m_streams = [f"{s.lower()}@kline_15m" for s in self.symbols_cache[:900]]
        
        self.ws_client_15m = BinanceWebSocketClient(config.binance, "WS-15m")
        self.ws_client_15m.subscribe_callback('kline', self._handle_kline_15m)
        
        asyncio.create_task(self.ws_client_15m.connect(kline_15m_streams))
        
        logger.info(f"WebSocket 15m: subscribed to {len(kline_15m_streams)} streams")
        
        liq_streams = ['!forceOrder@arr']
        self.ws_client_liq = BinanceWebSocketClient(config.binance, "WS-Liquidations")
        self.ws_client_liq.subscribe_callback('liquidation', self._handle_liquidation)
        
        asyncio.create_task(self.ws_client_liq.connect(liq_streams))
        
        logger.info("WebSocket liquidations: subscribed to market-wide force orders")
    
    async def _handle_kline_15m(self, data: dict):
        try:
            if data.get('e') != 'kline':
                return
            
            kline = data.get('k', {})
            if not kline.get('x'):
                return
            
            symbol = data.get('s')
            
            logger.debug(f"15m candle closed: {symbol} at {kline.get('c')}")
            
        except Exception as e:
            logger.error(f"Error handling 15m kline: {e}")
    
    async def _handle_liquidation(self, data: dict):
        try:
            if data.get('e') != 'forceOrder':
                return
            
            order = data.get('o', {})
            symbol = order.get('s')
            side = order.get('S')
            price = order.get('p')
            qty = order.get('q')
            
            logger.debug(f"Liquidation: {symbol} {side} {qty}@{price}")
            
        except Exception as e:
            logger.error(f"Error handling liquidation: {e}")
    
    async def _run_main_loop(self):
        logger.info("Entering main event loop...")
        
        update_counter = 0
        
        while self.running:
            try:
                await asyncio.sleep(10)
                
                update_counter += 1
                
                if update_counter % 6 == 0:
                    status = self.rate_limiter.get_status()
                    logger.info(
                        f"Rate limiter: {status['weight_used']}/{status['max_weight']} "
                        f"({status['usage_percent']:.1f}%), "
                        f"requests: {status['requests_count']}"
                    )
                
                if update_counter % 30 == 0:
                    logger.info(f"Bot running, monitoring {len(self.symbols_cache)} symbols")
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(5)
    
    async def stop(self):
        logger.info("Stopping LSFP-15 Bot...")
        self.running = False
        
        if self.ws_client_15m:
            await self.ws_client_15m.stop()
        
        if self.ws_client_1m:
            await self.ws_client_1m.stop()
        
        if self.ws_client_liq:
            await self.ws_client_liq.stop()
        
        if self.telegram_bot:
            await self.telegram_bot.stop()
        
        if self.rest_client:
            await self.rest_client.stop()
        
        if self.db_pool:
            await self.db_pool.close()
        
        logger.info("=== LSFP-15 Bot stopped ===")


async def main():
    setup_logging(config.log_level)
    
    bot = LSFPBot()
    
    loop = asyncio.get_event_loop()
    
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        asyncio.create_task(bot.stop())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
    finally:
        await bot.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown complete")
