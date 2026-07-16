import logging
from datetime import datetime, timezone
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from app.core.config import get_settings
from app.core.logging_config import configure_logging


# Routes by level: INFO/DEBUG -> stdout, WARNING+ -> stderr. basicConfig() put
# everything on stderr, which log collectors read as "error".
configure_logging()

logger = logging.getLogger("ai-stock-alert")


@dataclass
class ErrorEntry:
    timestamp: str
    source: str
    message: str
    details: Optional[str] = None


@dataclass
class HealthStatus:
    scheduler_running: bool = False
    last_analysis_at: Optional[str] = None
    last_error_at: Optional[str] = None
    consecutive_failures: int = 0
    total_errors_24h: int = 0


class ErrorMonitor:
    """Centralized error monitoring and health tracking.

    Tracks errors, scheduler health, and can send alerts
    when critical failures occur.
    """

    MAX_ERROR_HISTORY = 100
    CRITICAL_FAILURE_THRESHOLD = 3  # Alert after 3 consecutive failures

    def __init__(self) -> None:
        self.errors: deque[ErrorEntry] = deque(maxlen=self.MAX_ERROR_HISTORY)
        self.health = HealthStatus()
        self._consecutive_failures = 0

    def log_error(self, source: str, message: str, details: Optional[str] = None) -> None:
        """Log an error and track it."""
        entry = ErrorEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            source=source,
            message=message,
            details=details,
        )
        self.errors.append(entry)
        self.health.last_error_at = entry.timestamp
        self.health.total_errors_24h = self._count_recent_errors()

        logger.error(f"[{source}] {message}" + (f" | {details}" if details else ""))

    def log_scheduler_success(self) -> None:
        """Record successful scheduler run."""
        self.health.last_analysis_at = datetime.now(timezone.utc).isoformat()
        self._consecutive_failures = 0
        self.health.consecutive_failures = 0

    def log_scheduler_failure(self, error: str) -> None:
        """Record scheduler failure and check if critical."""
        self._consecutive_failures += 1
        self.health.consecutive_failures = self._consecutive_failures
        self.log_error("scheduler", f"Analysis cycle failed: {error}")

        if self._consecutive_failures >= self.CRITICAL_FAILURE_THRESHOLD:
            self._handle_critical_failure()

    def set_scheduler_running(self, is_running: bool) -> None:
        """Update scheduler running status."""
        self.health.scheduler_running = is_running

    def get_health(self) -> dict:
        """Get current health status."""
        return {
            "scheduler_running": self.health.scheduler_running,
            "last_analysis_at": self.health.last_analysis_at,
            "last_error_at": self.health.last_error_at,
            "consecutive_failures": self.health.consecutive_failures,
            "total_errors_24h": self._count_recent_errors(),
            "status": self._determine_status(),
        }

    def get_recent_errors(self, limit: int = 20) -> list[dict]:
        """Get recent error entries."""
        errors = list(self.errors)[-limit:]
        return [
            {
                "timestamp": e.timestamp,
                "source": e.source,
                "message": e.message,
                "details": e.details,
            }
            for e in reversed(errors)
        ]

    def _count_recent_errors(self) -> int:
        """Count errors in the last 24 hours."""
        now = datetime.now(timezone.utc)
        count = 0
        for entry in self.errors:
            entry_time = datetime.fromisoformat(entry.timestamp)
            if (now - entry_time).total_seconds() < 86400:
                count += 1
        return count

    def _determine_status(self) -> str:
        """Determine overall system health status."""
        if self._consecutive_failures >= self.CRITICAL_FAILURE_THRESHOLD:
            return "critical"
        if self._consecutive_failures > 0:
            return "degraded"
        if not self.health.scheduler_running:
            return "offline"
        return "healthy"

    def _handle_critical_failure(self) -> None:
        """Handle critical failure - log prominently."""
        logger.critical(
            f"CRITICAL: Scheduler has failed {self._consecutive_failures} times consecutively!"
        )


# Global monitor instance
monitor = ErrorMonitor()
