# modules/gemini_rate_limiter.py

"""
Rate limiter for Gemini API calls based on free tier limits.

Free Tier Limits:
- Gemini 2.5 Flash: RPM: 10, TPM: 250,000, RPD: 250
- Gemini 2.0 Flash-Lite: RPM: 30, TPM: 1,000,000, RPD: 200
"""

import time
import threading
from collections import deque
from typing import Dict, Optional
import logging

from . import config

logger = logging.getLogger(__name__)


class GeminiRateLimiter:
    """
    Thread-safe rate limiter for Gemini API calls.
    
    Tracks requests per minute (RPM), tokens per minute (TPM), and requests per day (RPD).
    """
    
    def __init__(self):
        self.lock = threading.Lock()
        self.model_limits = config.GEMINI_RATE_LIMITS
        self.safety_margin = config.GEMINI_RATE_LIMIT_SAFETY_MARGIN
        self.enabled = config.GEMINI_ENABLE_RATE_LIMITING
        
        # Track requests per model: {model_name: deque of timestamps}
        self.request_timestamps: Dict[str, deque] = {}
        
        # Track tokens per model: {model_name: deque of (timestamp, token_count)}
        self.token_usage: Dict[str, deque] = {}
        
        # Track daily requests: {model_name: {date: count}}
        self.daily_counts: Dict[str, Dict[str, int]] = {}
        
        # Initialize tracking for each model
        for model_name in self.model_limits.keys():
            self.request_timestamps[model_name] = deque(maxlen=1000)
            self.token_usage[model_name] = deque(maxlen=1000)
            self.daily_counts[model_name] = {}
    
    def _get_current_date(self) -> str:
        """Get current date as YYYY-MM-DD string."""
        return time.strftime("%Y-%m-%d")
    
    def _cleanup_old_entries(self, model_name: str):
        """Remove entries older than 1 minute from tracking."""
        now = time.time()
        one_minute_ago = now - 60
        
        # Clean RPM tracking
        while self.request_timestamps[model_name] and self.request_timestamps[model_name][0] < one_minute_ago:
            self.request_timestamps[model_name].popleft()
        
        # Clean TPM tracking
        while self.token_usage[model_name] and self.token_usage[model_name][0][0] < one_minute_ago:
            self.token_usage[model_name].popleft()
    
    def _check_rpm_limit(self, model_name: str) -> bool:
        """Check if we can make a request within RPM limit."""
        if not self.enabled:
            return True
        
        limits = self.model_limits.get(model_name, {})
        max_rpm = int(limits.get("rpm", 100) * self.safety_margin)
        
        self._cleanup_old_entries(model_name)
        current_rpm = len(self.request_timestamps[model_name])
        
        return current_rpm < max_rpm
    
    def _check_tpm_limit(self, model_name: str, estimated_tokens: int) -> bool:
        """Check if estimated tokens fit within TPM limit."""
        if not self.enabled:
            return True
        
        limits = self.model_limits.get(model_name, {})
        max_tpm = int(limits.get("tpm", 1000000) * self.safety_margin)
        
        self._cleanup_old_entries(model_name)
        
        # Calculate total tokens used in last minute
        now = time.time()
        one_minute_ago = now - 60
        
        total_tokens = sum(
            tokens for timestamp, tokens in self.token_usage[model_name]
            if timestamp >= one_minute_ago
        )
        
        return (total_tokens + estimated_tokens) <= max_tpm
    
    def _check_rpd_limit(self, model_name: str) -> bool:
        """Check if we can make a request within RPD limit."""
        if not self.enabled:
            return True
        
        limits = self.model_limits.get(model_name, {})
        max_rpd = int(limits.get("rpd", 1000) * self.safety_margin)
        
        today = self._get_current_date()
        today_count = self.daily_counts[model_name].get(today, 0)
        
        return today_count < max_rpd
    
    def wait_if_needed(self, model_name: str, estimated_tokens: int = 0):
        """
        Wait if necessary to respect rate limits.
        
        Args:
            model_name: Name of the model (e.g., "gemini-2.5-flash")
            estimated_tokens: Estimated token count for this request (default: 0)
        """
        if not self.enabled:
            return
        
        with self.lock:
            # Check RPM limit
            if not self._check_rpm_limit(model_name):
                # Wait until oldest request is more than 1 minute old
                if self.request_timestamps[model_name]:
                    oldest = self.request_timestamps[model_name][0]
                    wait_time = max(0, 60 - (time.time() - oldest) + 1)
                    if wait_time > 0:
                        logger.warning(f"RPM limit reached for {model_name}, waiting {wait_time:.1f}s")
                        time.sleep(wait_time)
                        self._cleanup_old_entries(model_name)
            
            # Check TPM limit
            if estimated_tokens > 0 and not self._check_tpm_limit(model_name, estimated_tokens):
                # Wait until tokens free up
                if self.token_usage[model_name]:
                    oldest = self.token_usage[model_name][0][0]
                    wait_time = max(0, 60 - (time.time() - oldest) + 1)
                    if wait_time > 0:
                        logger.warning(
                            f"TPM limit reached for {model_name} (estimated {estimated_tokens} tokens), "
                            f"waiting {wait_time:.1f}s"
                        )
                        time.sleep(wait_time)
                        self._cleanup_old_entries(model_name)
            
            # Check RPD limit
            if not self._check_rpd_limit(model_name):
                raise RuntimeError(
                    f"Daily request limit ({self.model_limits[model_name]['rpd']}) "
                    f"reached for {model_name}. Please try again tomorrow."
                )
            
            # Record this request
            now = time.time()
            self.request_timestamps[model_name].append(now)
            
            if estimated_tokens > 0:
                self.token_usage[model_name].append((now, estimated_tokens))
            
            today = self._get_current_date()
            self.daily_counts[model_name][today] = self.daily_counts[model_name].get(today, 0) + 1
    
    def get_status(self, model_name: str) -> Dict[str, any]:
        """Get current rate limit status for a model."""
        with self.lock:
            self._cleanup_old_entries(model_name)
            
            limits = self.model_limits.get(model_name, {})
            today = self._get_current_date()
            
            # Calculate current usage
            current_rpm = len(self.request_timestamps[model_name])
            current_tpm = sum(tokens for _, tokens in self.token_usage[model_name])
            current_rpd = self.daily_counts[model_name].get(today, 0)
            
            return {
                "model": model_name,
                "rpm": {
                    "current": current_rpm,
                    "limit": int(limits.get("rpm", 100) * self.safety_margin),
                    "max": limits.get("rpm", 100),
                },
                "tpm": {
                    "current": current_tpm,
                    "limit": int(limits.get("tpm", 1000000) * self.safety_margin),
                    "max": limits.get("tpm", 1000000),
                },
                "rpd": {
                    "current": current_rpd,
                    "limit": int(limits.get("rpd", 1000) * self.safety_margin),
                    "max": limits.get("rpd", 1000),
                },
            }


# Global rate limiter instance
_rate_limiter = None


def get_rate_limiter() -> GeminiRateLimiter:
    """Get or create the global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = GeminiRateLimiter()
    return _rate_limiter

