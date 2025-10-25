"""
ОРИГИНАЛЬНЫЕ ПАРАМЕТРЫ КОНФИГУРАЦИИ
Создано: 2025-10-26
Цель: Бекап оригинальных значений перед тестированием с смягченными параметрами

ЭТИ ПАРАМЕТРЫ НУЖНО ВОССТАНОВИТЬ ПОСЛЕ ТЕСТИРОВАНИЯ!
"""

# ===== ОРИГИНАЛЬНЫЕ ЗНАЧЕНИЯ СТРАТЕГИИ =====

# Sweep detection (пробой ликвидности)
sweep_min_atr_ORIGINAL = 0.20  # Минимум 20% ATR для sweep (сейчас: 0.05)
sweep_min_atr_strict_ORIGINAL = 0.30  # Строгий порог 30% ATR

# Wick/body ratio (фитиль/тело свечи)
wick_body_ratio_ORIGINAL = 2.0  # Фитиль >= 200% тела (сейчас: 0.0 - отключено)

# Liquidation filter (фильтр ликвидаций)
liq_percentile_base_ORIGINAL = 95  # 95-й перцентиль ликвидаций (сейчас: 50)
liq_percentile_strict_ORIGINAL = 97  # 97-й перцентиль для строгих условий
liq_min_usd_ORIGINAL = 500_000  # Минимум $500k ликвидаций (сейчас: $100k)
liq_window_minutes_ORIGINAL = 4  # Окно 4 минуты

# Open Interest delta (изменение открытого интереса)
oi_delta_min_percent_ORIGINAL = -1.5  # Минимум -1.5% падения OI (сейчас: -0.5)
oi_delta_max_percent_ORIGINAL = -3.0  # Максимум -3.0% падения OI
oi_delta_strict_percent_ORIGINAL = -2.5  # Строгий порог -2.5%

# Volume (объем торгов)
volume_percentile_ORIGINAL = 90  # 90-й перцентиль объема
volume_lookback_bars_ORIGINAL = 50  # Оглядываться на 50 баров назад

# ATR limits (диапазон волатильности)
atr_min_percent_ORIGINAL = 1.2  # Минимум 1.2% ATR
atr_max_percent_ORIGINAL = 5.5  # Максимум 5.5% ATR
atr_period_ORIGINAL = 14  # Период ATR 14 баров


# ===== КОМАНДА ДЛЯ ВОССТАНОВЛЕНИЯ =====
"""
В config.py вернуть:

sweep_min_atr: float = 0.20
wick_body_ratio: float = 2.0
liq_percentile_base: int = 95
liq_min_usd: float = 500_000
oi_delta_min_percent: float = -1.5
"""
