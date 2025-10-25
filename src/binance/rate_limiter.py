import asyncio
import time
import logging
from typing import Dict, Optional
from dataclasses import dataclass, field
from config import BinanceConfig

logger = logging.getLogger(__name__)


@dataclass
class RateLimitWindow:
    window_start: float
    weight_used: int = 0
    requests_count: int = 0


class BinanceRateLimiter:
    
    def __init__(self, config: BinanceConfig):
        self.config = config
        self.max_weight = config.rate_limit_weight_per_minute
        self.pause_threshold = int(self.max_weight * config.rate_limit_pause_threshold)
        
        self.current_window = RateLimitWindow(window_start=time.time())
        self.is_paused = False
        self.pause_until = 0
        
        self._lock = asyncio.Lock()
        
        logger.info(f"Rate limiter initialized: max_weight={self.max_weight}/min, pause_threshold={self.pause_threshold}")
    
    async def acquire(self, weight: int = 1) -> bool:
        async with self._lock:
            current_time = time.time()
            
            if self._should_reset_window(current_time):
                self._reset_window(current_time)
            
            if self.is_paused:
                if current_time < self.pause_until:
                    wait_time = self.pause_until - current_time
                    logger.warning(f"Rate limit paused, waiting {wait_time:.2f}s")
                    await asyncio.sleep(wait_time)
                    current_time = time.time()
                    self._reset_window(current_time)
                    self.is_paused = False
                else:
                    self._reset_window(current_time)
                    self.is_paused = False
            
            if self.current_window.weight_used + weight > self.pause_threshold:
                time_until_reset = 60 - (current_time - self.current_window.window_start)
                if time_until_reset > 0:
                    self.is_paused = True
                    self.pause_until = current_time + time_until_reset + self.config.rate_limit_resume_buffer
                    logger.warning(
                        f"Approaching rate limit ({self.current_window.weight_used}/{self.max_weight}), "
                        f"pausing for {time_until_reset + self.config.rate_limit_resume_buffer:.2f}s"
                    )
                    await asyncio.sleep(time_until_reset + self.config.rate_limit_resume_buffer)
                    current_time = time.time()
                    self._reset_window(current_time)
                    self.is_paused = False
            
            self.current_window.weight_used += weight
            self.current_window.requests_count += 1
            
            return True
    
    def update_from_headers(self, headers: Dict[str, str]):
        if 'X-MBX-USED-WEIGHT-1M' in headers:
            try:
                used_weight = int(headers['X-MBX-USED-WEIGHT-1M'])
                self.current_window.weight_used = used_weight
                
                if used_weight > self.pause_threshold:
                    logger.warning(f"High weight usage detected from headers: {used_weight}/{self.max_weight}")
            except ValueError:
                pass
    
    def _should_reset_window(self, current_time: float) -> bool:
        return (current_time - self.current_window.window_start) >= 60
    
    def _reset_window(self, current_time: float):
        if self.current_window.weight_used > 0:
            logger.debug(
                f"Window reset: used {self.current_window.weight_used}/{self.max_weight} weight, "
                f"{self.current_window.requests_count} requests"
            )
        self.current_window = RateLimitWindow(window_start=current_time)
    
    def get_status(self) -> Dict:
        current_time = time.time()
        window_age = current_time - self.current_window.window_start
        return {
            'weight_used': self.current_window.weight_used,
            'max_weight': self.max_weight,
            'usage_percent': (self.current_window.weight_used / self.max_weight) * 100,
            'requests_count': self.current_window.requests_count,
            'is_paused': self.is_paused,
            'window_age_seconds': window_age,
            'seconds_until_reset': max(0, 60 - window_age)
        }
