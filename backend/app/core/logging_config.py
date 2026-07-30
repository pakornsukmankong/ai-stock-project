"""Log routing so that "error" in the log viewer means an actual error.

Railway — like most container log collectors — classifies a line by the stream
it arrived on, not by the level inside the text: stdout = info, stderr = error.
Python's `logging.basicConfig()` sends *everything* to stderr, so every INFO
line from httpx/apscheduler showed up red and filtering by error was useless.

The level therefore has to pick the stream: INFO/DEBUG to stdout, WARNING and
above to stderr.
"""
import logging
import sys
from datetime import datetime

import pytz

# Every log timestamp renders in this timezone. Business logic (APScheduler,
# market hours, DB cutoffs) still runs in UTC — only the *displayed* timestamp
# changes, so logs read in local time without a constant +7 conversion. Change
# this one constant to relocate all log timestamps.
LOG_TZ = pytz.timezone("Asia/Bangkok")

_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
# %Z renders the offset (e.g. "+07") so the timezone is never ambiguous.
_DATEFMT = "%Y-%m-%d %H:%M:%S %Z"

# Uvicorn owns these and points them at stderr with propagate=False.
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")

# Libraries that log one INFO line per operation, drowning our own signal.
# httpx logs every HTTP request ("GET .../chart/NVDA 200 OK") — ~50 lines per
# analysis cycle across Yahoo + Supabase calls. apscheduler logs every job as it
# runs and finishes. None of it is actionable at INFO; raise to WARNING so only
# genuine problems (a failed request, a missed job) still appear. Our own
# "Starting analysis cycle" / "BUY SIGNAL" / "[LINE] Sent" lines are untouched.
_NOISY_LOGGERS = ("httpx", "httpcore", "apscheduler.executors.default", "apscheduler.scheduler")


def local_now() -> datetime:
    """Timezone-aware 'now' in LOG_TZ, for print() lines that embed a timestamp."""
    return datetime.now(LOG_TZ)


class _LocalTimeFormatter(logging.Formatter):
    """Render %(asctime)s in LOG_TZ instead of the host's (UTC) local time."""

    def formatTime(self, record: logging.LogRecord, datefmt=None) -> str:
        dt = datetime.fromtimestamp(record.created, LOG_TZ)
        return dt.strftime(datefmt or "%Y-%m-%d %H:%M:%S")


class _BelowWarningFilter(logging.Filter):
    """Keep stdout to non-failures — WARNING and above belong on stderr."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno < logging.WARNING


def configure_logging(level: int = logging.INFO) -> None:
    """Route records to stdout/stderr by level. Replaces basicConfig()."""
    formatter = _LocalTimeFormatter(_FORMAT, datefmt=_DATEFMT)

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(level)
    stdout_handler.addFilter(_BelowWarningFilter())
    stdout_handler.setFormatter(formatter)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)
    stderr_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    # Replace rather than append: basicConfig or a re-run would otherwise leave
    # a stderr handler behind and every line would still be duplicated as error.
    root.handlers = [stdout_handler, stderr_handler]

    # Silence the per-request / per-job chatter, keeping their warnings+errors.
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


def adopt_uvicorn_loggers() -> None:
    """Hand uvicorn's loggers to the root logger so they split by level too.

    Uvicorn installs its own handlers (startup/error lines on stderr) with
    propagate=False, so "INFO: Started server process" is tagged as an error.
    Must run *after* uvicorn has configured logging — i.e. from the app lifespan.
    """
    for name in _UVICORN_LOGGERS:
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
