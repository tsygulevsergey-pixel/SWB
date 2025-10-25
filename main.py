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
from src.binance import MockBinanceProvider, RealBinanceProvider, BinanceDataProvider
from src.telegram_bot.bot import TradingBot

logger = logging.getLogger(__name__)


class LSFPBot:
    
    def __init__(self):
        self.running = False
        self.db_pool = None
        self.data_provider: BinanceDataProvider = None
        self.telegram_bot = None
        
        self.symbols_cache = []
        self.hot_symbols = []
    
    async def start(self):
        logger.info("=== Starting LSFP-15 Trading Bot ===")
        
        try:
            logger.info("Initializing database...")
            self.db_pool = await init_database(config.database.url)
            
            if config.use_mock_data:
                logger.info("🎭 Using MOCK data provider (development mode)")
                self.data_provider = MockBinanceProvider()
            else:
                logger.info("📡 Using REAL Binance API (production mode)")
                self.data_provider = RealBinanceProvider(config.binance)
            
            await self.data_provider.start()
            
            logger.info("Fetching USDT perpetual symbols...")
            self.symbols_cache = await self.data_provider.get_all_usdt_perps()
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
            logger.info(f"Data mode: {'🎭 MOCK' if config.use_mock_data else '📡 REAL'}")
            logger.info(f"Monitoring {len(self.symbols_cache)} symbols")
            logger.info(f"Timezone: {config.timezone}")
            logger.info(f"Telegram bot active: {bool(config.telegram.bot_token and config.telegram.chat_id)}")
            
            self.running = True
            
            await self._run_main_loop()
            
        except Exception as e:
            logger.critical(f"Fatal error during startup: {e}", exc_info=True)
            await self.stop()
    
    async def _setup_websockets(self):
        symbols_to_monitor = self.symbols_cache[:900]
        
        await self.data_provider.subscribe_klines(
            symbols=symbols_to_monitor,
            interval='15m',
            callback=self._handle_kline_15m
        )
        
        logger.info(f"WebSocket 15m: subscribed to {len(symbols_to_monitor)} symbols")
        
        await self.data_provider.subscribe_liquidations(
            callback=self._handle_liquidation
        )
        
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
                
                if update_counter % 6 == 0 and not config.use_mock_data:
                    pass
                
                if update_counter % 30 == 0:
                    logger.info(f"Bot running, monitoring {len(self.symbols_cache)} symbols")
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(5)
    
    async def stop(self):
        logger.info("Stopping LSFP-15 Bot...")
        self.running = False
        
        if self.data_provider:
            await self.data_provider.stop()
        
        if self.telegram_bot:
            await self.telegram_bot.stop()
        
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
