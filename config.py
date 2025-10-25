import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class StrategyConfig:
    min_24h_volume_usd: float = 10_000_000
    max_24h_volume_usd: float = 1_000_000_000
    min_oi_usd: float = 2_000_000
    max_oi_usd: float = 5_000_000_000
    
    atr_min_percent: float = 1.2
    atr_max_percent: float = 5.5
    atr_period: int = 14
    
    sweep_min_atr: float = 0.05
    sweep_min_atr_strict: float = 0.30
    
    wick_body_ratio: float = 0.5
    
    liq_percentile_base: int = 80
    liq_percentile_strict: int = 97
    liq_min_usd: float = 100_000
    liq_window_minutes: int = 4
    
    oi_delta_min_percent: float = -0.5
    oi_delta_max_percent: float = -3.0
    oi_delta_strict_percent: float = -2.5
    
    volume_percentile: int = 90
    volume_lookback_bars: int = 50
    
    donchian_h1_period: int = 50
    donchian_h4_period: int = 50
    donchian_15m_period: int = 20
    
    entry_retracement_min: float = 0.50
    entry_retracement_max: float = 0.62
    
    sl_atr_min: float = 0.15
    sl_atr_max: float = 0.25
    sl_max_percent: float = 2.0
    
    tp1_r: float = 1.0
    tp1_percent: float = 2.0
    tp2_min_percent: float = 3.0
    tp2_max_percent: float = 5.0
    tp2_r_min: float = 2.0
    tp2_r_max: float = 3.0
    
    time_stop_bars: int = 6
    time_stop_bars_max: int = 8
    time_stop_min_r: float = 0.5
    
    cooldown_bars: int = 3
    
    min_rr_to_zone: float = 1.5
    
    rsi_oversold: int = 20
    rsi_overbought: int = 80
    rsi_period: int = 14
    
    cluster_max_positions: int = 2
    cluster_max_risk_percent: float = 1.0
    cluster_correlation_threshold: float = 0.7
    cluster_cooldown_bars: int = 2
    
    zone_width_atr_multiplier: float = 0.25
    zone_width_min_percent: float = 0.10
    zone_merge_distance_atr: float = 0.30
    
    zone_max_h1: int = 30
    zone_max_h4: int = 20
    
    zone_decay_days: int = 14
    zone_decay_score: float = 0.5
    
    hot_pool_size: int = 400
    cold_pool_size: int = 600
    hot_pool_1m_size: int = 100
    pool_update_minutes: int = 15
    hot_pool_1m_update_minutes: int = 10


@dataclass
class BinanceConfig:
    futures_rest_base_url: str = "https://fapi.binance.com"
    futures_ws_base_url: str = "wss://fstream.binance.com"
    
    rate_limit_weight_per_minute: int = 2400
    rate_limit_pause_threshold: float = 0.90
    rate_limit_resume_buffer: int = 5
    
    ws_max_streams_per_connection: int = 900
    ws_ping_interval: int = 20
    ws_pong_timeout: int = 60
    ws_reconnect_delay: int = 5
    ws_reconnect_max_delay: int = 60
    ws_max_reconnect_attempts: int = 10
    
    rest_timeout: int = 10
    rest_max_retries: int = 3


@dataclass
class TelegramConfig:
    bot_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    chat_id: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""))
    max_message_length: int = 4096


@dataclass
class DatabaseConfig:
    url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", ""))
    pool_min_size: int = 5
    pool_max_size: int = 20
    command_timeout: int = 30
    sync_interval_minutes: int = 5


@dataclass
class AppConfig:
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    binance: BinanceConfig = field(default_factory=BinanceConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    
    timezone: str = "Europe/Kiev"
    log_level: str = "INFO"
    
    use_mock_data: bool = field(default_factory=lambda: os.getenv("USE_MOCK_DATA", "true").lower() == "true")
    
    candle_close_delay_seconds: int = 10
    
    cluster_leaders: List[str] = field(default_factory=lambda: [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "TONUSDT",
        "XRPUSDT", "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "DOTUSDT"
    ])
    
    cluster_recalc_hour: int = 0
    cluster_lookback_days: int = 30


config = AppConfig()
