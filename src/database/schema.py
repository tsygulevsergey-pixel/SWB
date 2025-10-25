import asyncpg
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class DatabaseSchema:
    
    @staticmethod
    async def create_tables(conn: asyncpg.Connection):
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS symbols (
                symbol VARCHAR(20) PRIMARY KEY,
                is_active BOOLEAN DEFAULT TRUE,
                base_asset VARCHAR(10),
                quote_asset VARCHAR(10),
                tick_size DECIMAL,
                lot_size DECIMAL,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );
            
            CREATE INDEX IF NOT EXISTS idx_symbols_active ON symbols(is_active);
        ''')
        
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS klines_15m (
                id BIGSERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                open_time BIGINT NOT NULL,
                open DECIMAL NOT NULL,
                high DECIMAL NOT NULL,
                low DECIMAL NOT NULL,
                close DECIMAL NOT NULL,
                volume DECIMAL NOT NULL,
                close_time BIGINT NOT NULL,
                quote_volume DECIMAL,
                trades INTEGER,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(symbol, open_time)
            );
            
            CREATE INDEX IF NOT EXISTS idx_klines_15m_symbol_time ON klines_15m(symbol, open_time DESC);
        ''')
        
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS klines_1h (
                id BIGSERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                open_time BIGINT NOT NULL,
                open DECIMAL NOT NULL,
                high DECIMAL NOT NULL,
                low DECIMAL NOT NULL,
                close DECIMAL NOT NULL,
                volume DECIMAL NOT NULL,
                close_time BIGINT NOT NULL,
                quote_volume DECIMAL,
                trades INTEGER,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(symbol, open_time)
            );
            
            CREATE INDEX IF NOT EXISTS idx_klines_1h_symbol_time ON klines_1h(symbol, open_time DESC);
        ''')
        
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS klines_4h (
                id BIGSERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                open_time BIGINT NOT NULL,
                open DECIMAL NOT NULL,
                high DECIMAL NOT NULL,
                low DECIMAL NOT NULL,
                close DECIMAL NOT NULL,
                volume DECIMAL NOT NULL,
                close_time BIGINT NOT NULL,
                quote_volume DECIMAL,
                trades INTEGER,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(symbol, open_time)
            );
            
            CREATE INDEX IF NOT EXISTS idx_klines_4h_symbol_time ON klines_4h(symbol, open_time DESC);
        ''')
        
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS liquidations (
                id BIGSERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                side VARCHAR(10) NOT NULL,
                order_type VARCHAR(20),
                time_in_force VARCHAR(10),
                original_quantity DECIMAL,
                price DECIMAL,
                average_price DECIMAL,
                order_status VARCHAR(20),
                last_filled_quantity DECIMAL,
                filled_accumulated_quantity DECIMAL,
                event_time BIGINT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
            
            CREATE INDEX IF NOT EXISTS idx_liquidations_symbol_time ON liquidations(symbol, event_time DESC);
        ''')
        
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS open_interest (
                id BIGSERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                open_interest DECIMAL NOT NULL,
                timestamp BIGINT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(symbol, timestamp)
            );
            
            CREATE INDEX IF NOT EXISTS idx_oi_symbol_time ON open_interest(symbol, timestamp DESC);
        ''')
        
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS sr_zones (
                id BIGSERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                timeframe VARCHAR(10) NOT NULL,
                zone_type VARCHAR(20) NOT NULL,
                upper_price DECIMAL NOT NULL,
                lower_price DECIMAL NOT NULL,
                mid_price DECIMAL NOT NULL,
                strength DECIMAL NOT NULL DEFAULT 0,
                touches INTEGER DEFAULT 0,
                last_touch_time BIGINT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );
            
            CREATE INDEX IF NOT EXISTS idx_zones_symbol_tf ON sr_zones(symbol, timeframe);
            CREATE INDEX IF NOT EXISTS idx_zones_strength ON sr_zones(strength DESC);
        ''')
        
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS signals (
                id BIGSERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                direction VARCHAR(10) NOT NULL,
                entry_price DECIMAL NOT NULL,
                stop_loss DECIMAL NOT NULL,
                take_profit_1 DECIMAL NOT NULL,
                take_profit_2 DECIMAL NOT NULL,
                position_size_percent DECIMAL DEFAULT 1.0,
                reason TEXT,
                lsfp_score DECIMAL,
                signal_time BIGINT NOT NULL,
                candle_close_time BIGINT,
                sweep_atr DECIMAL,
                liq_sum DECIMAL,
                oi_delta_percent DECIMAL,
                volume_percentile DECIMAL,
                nearest_resistance DECIMAL,
                nearest_support DECIMAL,
                cluster_name VARCHAR(50),
                created_at TIMESTAMP DEFAULT NOW()
            );
            
            CREATE INDEX IF NOT EXISTS idx_signals_symbol_time ON signals(symbol, signal_time DESC);
            CREATE INDEX IF NOT EXISTS idx_signals_direction ON signals(direction);
        ''')
        
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id BIGSERIAL PRIMARY KEY,
                signal_id BIGINT REFERENCES signals(id),
                symbol VARCHAR(20) NOT NULL,
                direction VARCHAR(10) NOT NULL,
                entry_price DECIMAL NOT NULL,
                entry_time BIGINT NOT NULL,
                exit_price DECIMAL,
                exit_time BIGINT,
                stop_loss DECIMAL NOT NULL,
                take_profit_1 DECIMAL NOT NULL,
                take_profit_2 DECIMAL NOT NULL,
                current_price DECIMAL,
                status VARCHAR(20) NOT NULL,
                exit_reason VARCHAR(50),
                pnl_percent DECIMAL,
                pnl_usd DECIMAL,
                bars_in_trade INTEGER DEFAULT 0,
                hit_tp1 BOOLEAN DEFAULT FALSE,
                hit_tp2 BOOLEAN DEFAULT FALSE,
                moved_to_be BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );
            
            CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
            CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
            CREATE INDEX IF NOT EXISTS idx_trades_signal ON trades(signal_id);
        ''')
        
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS symbol_metrics (
                id BIGSERIAL PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL,
                volume_24h DECIMAL,
                quote_volume_24h DECIMAL,
                open_interest DECIMAL,
                atr_percent DECIMAL,
                priority_score DECIMAL,
                is_hot BOOLEAN DEFAULT FALSE,
                cluster_name VARCHAR(50),
                correlation_to_leader DECIMAL,
                last_updated BIGINT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(symbol)
            );
            
            CREATE INDEX IF NOT EXISTS idx_metrics_symbol ON symbol_metrics(symbol);
            CREATE INDEX IF NOT EXISTS idx_metrics_hot ON symbol_metrics(is_hot);
        ''')
        
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS clusters (
                id BIGSERIAL PRIMARY KEY,
                cluster_name VARCHAR(50) UNIQUE NOT NULL,
                leader_symbol VARCHAR(20),
                member_count INTEGER DEFAULT 0,
                avg_correlation DECIMAL,
                open_positions INTEGER DEFAULT 0,
                total_risk_percent DECIMAL DEFAULT 0,
                cooldown_until BIGINT,
                last_updated BIGINT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            );
            
            CREATE INDEX IF NOT EXISTS idx_clusters_name ON clusters(cluster_name);
        ''')
        
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS statistics (
                id BIGSERIAL PRIMARY KEY,
                timeframe VARCHAR(20) NOT NULL,
                total_signals INTEGER DEFAULT 0,
                total_trades INTEGER DEFAULT 0,
                winning_trades INTEGER DEFAULT 0,
                losing_trades INTEGER DEFAULT 0,
                tp1_hits INTEGER DEFAULT 0,
                tp2_hits INTEGER DEFAULT 0,
                sl_hits INTEGER DEFAULT 0,
                win_rate DECIMAL,
                total_pnl_percent DECIMAL DEFAULT 0,
                avg_pnl_percent DECIMAL,
                max_pnl_percent DECIMAL,
                min_pnl_percent DECIMAL,
                period_start BIGINT,
                period_end BIGINT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            );
            
            CREATE INDEX IF NOT EXISTS idx_statistics_timeframe ON statistics(timeframe);
        ''')
        
        logger.info("Database schema created successfully")


async def init_database(database_url: str) -> asyncpg.Pool:
    pool = await asyncpg.create_pool(
        database_url,
        min_size=5,
        max_size=20,
        command_timeout=30
    )
    
    async with pool.acquire() as conn:
        await DatabaseSchema.create_tables(conn)
    
    logger.info("Database initialized successfully")
    return pool
