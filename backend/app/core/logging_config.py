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

_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"

# Uvicorn owns these and points them at stderr with propagate=False.
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


class _BelowWarningFilter(logging.Filter):
    """Keep stdout to non-failures — WARNING and above belong on stderr."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno < logging.WARNING


def configure_logging(level: int = logging.INFO) -> None:
    """Route records to stdout/stderr by level. Replaces basicConfig()."""
    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)

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
