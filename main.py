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
from src.cache import MarketCache
from src.strategy import (
    LiquidityFilter, SymbolPrioritizer, ZoneDetector,
    LiquidationAggregator, OICalculator, LSFPDetector,
    PairClustering, SignalScorer, PositionCalculator, VirtualTrader
)

logger = logging.getLogger(__name__)


class LSFPBot:
    
    def __init__(self):
        self.running = False
        self.db_pool = None
        self.data_provider: BinanceDataProvider = None
        self.telegram_bot = None
        
        self.cache: MarketCache = None
        self.liquidity_filter: LiquidityFilter = None
        self.prioritizer: SymbolPrioritizer = None
        self.zone_detector: ZoneDetector = None
        self.liq_aggregator: LiquidationAggregator = None
        self.oi_calculator: OICalculator = None
        self.lsfp_detector: LSFPDetector = None
        self.clustering: PairClustering = None
        self.scorer: SignalScorer = None
        self.position_calc: PositionCalculator = None
        self.virtual_trader: VirtualTrader = None
        
        self.symbols_list = []
        self.hot_symbols_1m = []
    
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
            self.symbols_list = await self.data_provider.get_all_usdt_perps()
            logger.info(f"Found {len(self.symbols_list)} USDT perpetual pairs")
            
            if not self.symbols_list:
                logger.error("No symbols found, cannot continue")
                return
            
            logger.info("Initializing Telegram bot...")
            self.telegram_bot = TradingBot(config.telegram)
            await self.telegram_bot.start()
            
            logger.info("Initializing market cache...")
            self.cache = MarketCache(self.db_pool, config.database.sync_interval_minutes)
            await self.cache.start()
            
            logger.info("Initializing strategy modules...")
            
            self.liquidity_filter = LiquidityFilter(config.strategy, self.data_provider, self.cache)
            await self.liquidity_filter.start(update_interval_minutes=15)
            
            self.prioritizer = SymbolPrioritizer(self.cache, config.strategy.hot_pool_size, config.strategy.cold_pool_size)
            await self.prioritizer.start(update_interval_minutes=10)
            
            self.zone_detector = ZoneDetector(config.strategy, self.cache)
            await self.zone_detector.start(update_interval_minutes=30)
            
            self.liq_aggregator = LiquidationAggregator(self.cache)
            await self.liq_aggregator.start(update_interval_hours=6)
            
            self.oi_calculator = OICalculator(config.strategy, self.cache, self.data_provider)
            await self.oi_calculator.start(update_interval_minutes=5)
            
            self.clustering = PairClustering(config, self.cache, self.data_provider)
            await self.clustering.start(recalc_hour=config.cluster_recalc_hour)
            
            self.lsfp_detector = LSFPDetector(config.strategy, self.cache, self.liq_aggregator, self.oi_calculator)
            
            self.scorer = SignalScorer(config.strategy, self.cache, self.clustering, self.zone_detector)
            
            self.position_calc = PositionCalculator(config.strategy)
            
            self.virtual_trader = VirtualTrader(config.strategy, self.cache, self.telegram_bot)
            await self.virtual_trader.start(update_interval_seconds=60)
            
            logger.info("Loading historical data for symbols...")
            await self._load_initial_data(limit=len(self.symbols_list))
            
            logger.info("Setting up WebSocket connections...")
            await self._setup_websockets()
            
            logger.info("=== LSFP-15 Bot started successfully ===")
            logger.info(f"Data mode: {'🎭 MOCK' if config.use_mock_data else '📡 REAL'}")
            logger.info(f"Monitoring {len(self.symbols_list)} symbols")
            logger.info(f"Timezone: {config.timezone}")
            logger.info(f"Telegram bot active: {bool(config.telegram.bot_token and config.telegram.chat_id)}")
            
            self.running = True
            
            await self._run_main_loop()
            
        except Exception as e:
            logger.critical(f"Fatal error during startup: {e}", exc_info=True)
            await self.stop()
    
    async def _load_initial_data(self, limit: int = 100):
        try:
            for symbol in self.symbols_list[:limit]:
                try:
                    klines = await self.data_provider.get_klines(symbol, '15m', limit=200)
                    
                    for kline_data in klines:
                        candle = {
                            'symbol': symbol,
                            'interval': '15m',
                            'open_time': int(kline_data[0]),
                            'open': float(kline_data[1]),
                            'high': float(kline_data[2]),
                            'low': float(kline_data[3]),
                            'close': float(kline_data[4]),
                            'volume': float(kline_data[5]),
                            'close_time': int(kline_data[6]),
                            'quote_volume': float(kline_data[7]),
                            'trades': int(kline_data[8]),
                            'taker_buy_base': float(kline_data[9]),
                            'taker_buy_quote': float(kline_data[10])
                        }
                        self.cache.candles.add_candle(symbol, candle)
                    
                    await asyncio.sleep(0.1)
                
                except Exception as e:
                    logger.debug(f"Error loading data for {symbol}: {e}")
            
            logger.info(f"Loaded historical data for {len(self.cache.candles.get_symbols_with_data())} symbols")
        
        except Exception as e:
            logger.error(f"Error loading initial data: {e}")
    
    async def _setup_websockets(self):
        symbols_to_monitor = self.symbols_list
        
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
        
        await self._update_hot_symbols_1m()
    
    async def _handle_kline_15m(self, data: dict):
        try:
            if data.get('e') != 'kline':
                return
            
            kline = data.get('k', {})
            symbol = data.get('s')
            
            candle = {
                'symbol': symbol,
                'interval': kline.get('i', '15m'),
                'open_time': kline.get('t'),
                'open': float(kline.get('o')),
                'high': float(kline.get('h')),
                'low': float(kline.get('l')),
                'close': float(kline.get('c')),
                'volume': float(kline.get('v')),
                'close_time': kline.get('T'),
                'quote_volume': float(kline.get('q')),
                'trades': kline.get('n'),
                'taker_buy_base': float(kline.get('V', 0)),
                'taker_buy_quote': float(kline.get('Q', 0)),
                'is_closed': kline.get('x', False)
            }
            
            self.cache.candles.add_candle(symbol, candle)
            
            if candle['is_closed']:
                asyncio.create_task(self._process_closed_candle(symbol, candle))
            
        except Exception as e:
            logger.error(f"Error handling 15m kline: {e}")
    
    async def _process_closed_candle(self, symbol: str, candle: dict):
        try:
            await asyncio.sleep(config.candle_close_delay_seconds)
            
            if not self.liquidity_filter.is_symbol_filtered(symbol):
                return
            
            pattern = await self.lsfp_detector.detect_pattern(symbol, candle)
            
            if not pattern:
                return
            
            scored_signal = self.scorer.score_signal(pattern)
            
            if not scored_signal:
                return
            
            if scored_signal['scores']['final'] < 6.0:
                logger.debug(f"Signal score too low for {symbol}: {scored_signal['scores']['final']:.2f}")
                return
            
            position_data = self.position_calc.calculate_entry_sl_tp(scored_signal)
            
            if not position_data:
                return
            
            await self.virtual_trader.open_trade(position_data, scored_signal)
            
        except Exception as e:
            logger.error(f"Error processing closed candle for {symbol}: {e}")
    
    async def _handle_kline_1m(self, data: dict):
        try:
            if data.get('e') != 'kline':
                return
            
            kline = data.get('k', {})
            symbol = data.get('s')
            
            candle = {
                'symbol': symbol,
                'interval': kline.get('i', '1m'),
                'open_time': kline.get('t'),
                'open': float(kline.get('o')),
                'high': float(kline.get('h')),
                'low': float(kline.get('l')),
                'close': float(kline.get('c')),
                'volume': float(kline.get('v')),
                'close_time': kline.get('T'),
                'quote_volume': float(kline.get('q')),
                'trades': kline.get('n'),
                'taker_buy_base': float(kline.get('V', 0)),
                'taker_buy_quote': float(kline.get('Q', 0)),
                'is_closed': kline.get('x', False)
            }
            
            self.cache.candles.add_candle(symbol, candle)
            
        except Exception as e:
            logger.error(f"Error handling 1m kline: {e}")
    
    async def _handle_liquidation(self, data: dict):
        try:
            if data.get('e') != 'forceOrder':
                return
            
            order = data.get('o', {})
            symbol = order.get('s')
            side = order.get('S')
            price = float(order.get('p', 0))
            qty = float(order.get('q', 0))
            timestamp = data.get('E', data.get('T', 0))
            
            liquidation = {
                'symbol': symbol,
                'side': side,
                'price': price,
                'quantity': qty,
                'timestamp': timestamp
            }
            
            self.cache.liquidations.add_liquidation(symbol, liquidation)
            
        except Exception as e:
            logger.error(f"Error handling liquidation: {e}")
    
    async def _update_hot_symbols_1m(self):
        try:
            hot_symbols = self.prioritizer.get_hot_pool()
            
            if not hot_symbols:
                logger.debug("Hot pool empty, skipping 1m subscription")
                return
            
            top_hot = hot_symbols[:config.strategy.hot_pool_1m_size]
            
            if set(top_hot) == set(self.hot_symbols_1m):
                logger.debug("Hot symbols for 1m unchanged, skipping resubscription")
                return
            
            if self.hot_symbols_1m:
                logger.info(f"Updating 1m WebSocket: {len(top_hot)} hot symbols")
                if hasattr(self.data_provider, 'unsubscribe_klines'):
                    await self.data_provider.unsubscribe_klines(self.hot_symbols_1m, '1m')
            
            await self.data_provider.subscribe_klines(
                symbols=top_hot,
                interval='1m',
                callback=self._handle_kline_1m
            )
            
            self.hot_symbols_1m = top_hot
            logger.info(f"WebSocket 1m: subscribed to {len(top_hot)} hot symbols")
            
        except Exception as e:
            logger.error(f"Error updating hot symbols 1m: {e}")
    
    async def _run_main_loop(self):
        logger.info("Entering main event loop...")
        
        update_counter = 0
        last_hot_update = 0
        
        while self.running:
            try:
                await asyncio.sleep(30)
                
                update_counter += 1
                
                if update_counter % 2 == 0:
                    stats = self.virtual_trader.get_stats()
                    cache_stats = self.cache.get_cache_stats()
                    
                    logger.info(
                        f"Trading stats: {stats['total_trades']} trades, "
                        f"Win rate: {stats['win_rate']:.1f}%, "
                        f"Cache: {cache_stats['symbols_with_candles']} symbols"
                    )
                
                hot_update_interval = config.strategy.hot_pool_1m_update_minutes * 60 / 30
                if update_counter - last_hot_update >= hot_update_interval:
                    await self._update_hot_symbols_1m()
                    last_hot_update = update_counter
                
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(5)
    
    async def stop(self):
        logger.info("Stopping LSFP-15 Bot...")
        self.running = False
        
        if self.virtual_trader:
            await self.virtual_trader.stop()
        
        if self.oi_calculator:
            await self.oi_calculator.stop()
        
        if self.liq_aggregator:
            await self.liq_aggregator.stop()
        
        if self.zone_detector:
            await self.zone_detector.stop()
        
        if self.prioritizer:
            await self.prioritizer.stop()
        
        if self.liquidity_filter:
            await self.liquidity_filter.stop()
        
        if self.cache:
            await self.cache.stop()
        
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
