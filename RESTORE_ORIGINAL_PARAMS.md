# 🔧 ВОССТАНОВЛЕНИЕ ОРИГИНАЛЬНЫХ ПАРАМЕТРОВ

**Дата создания:** 2025-10-26  
**Цель:** Вернуть конфигурацию к оригинальным значениям после тестирования

---

## 📋 ОРИГИНАЛЬНЫЕ ПАРАМЕТРЫ (до смягчения для теста)

### В файле `config.py` изменить:

```python
# СТРАТЕГИЯ
sweep_min_atr: float = 0.20           # ULTRA-TEST: 0.01
wick_body_ratio: float = 2.0          # ULTRA-TEST: 0.0
liq_percentile_base: int = 95         # ULTRA-TEST: 10
liq_min_usd: float = 500_000          # ULTRA-TEST: 1000
oi_delta_min_percent: float = -1.5    # ULTRA-TEST: -0.01
volume_percentile: int = 90           # ULTRA-TEST: 10
```

---

## 🚀 ИНСТРУКЦИЯ ДЛЯ VPS

### 1. Откройте config.py:
```bash
nano /root/SWB/config.py
```

### 2. Найдите и измените (CTRL+W для поиска):

**Строка ~20:**
```python
sweep_min_atr: float = 0.20  # ULTRA-TEST: 0.01
```

**Строка ~23:**
```python
wick_body_ratio: float = 2.0  # ULTRA-TEST: 0.0
```

**Строка ~25:**
```python
liq_percentile_base: int = 95  # ULTRA-TEST: 10
```

**Строка ~27:**
```python
liq_min_usd: float = 500_000  # ULTRA-TEST: 1000
```

**Строка ~30:**
```python
oi_delta_min_percent: float = -1.5  # ULTRA-TEST: -0.01
```

**Строка ~34:**
```python
volume_percentile: int = 90  # ULTRA-TEST: 10
```

### 3. Сохраните:
- CTRL+O (Save)
- Enter
- CTRL+X (Exit)

### 4. Перезапустите бота:
```bash
sudo systemctl restart lsfp-bot
tail -20 /root/SWB/bot.log | grep "Bot started"
```

---

## ✅ ПРОВЕРКА

После восстановления:
```bash
grep -E "sweep_min_atr|wick_body_ratio|liq_percentile_base|liq_min_usd|oi_delta_min" /root/SWB/config.py
```

Должно показать ОРИГИНАЛЬНЫЕ значения (0.20, 2.0, 95, 500_000, -1.5).

---

## 📊 ЗАЧЕМ НУЖНО ВОССТАНОВИТЬ?

**Временные параметры (для теста):**
- ⬇️ Очень мягкие фильтры
- ✅ Пропускают почти все сигналы
- ❌ Низкое качество сигналов

**Оригинальные параметры (production):**
- ✅ Строгие фильтры
- ✅ Высокое качество сигналов
- 🎯 ~10 сигналов в час (при нормальной волатильности)

---

**ВАЖНО:** Не забудьте восстановить параметры после тестирования!
