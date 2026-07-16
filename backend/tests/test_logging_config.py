"""Log routing tests.

Railway classifies a log line by the stream it arrived on — stdout = info,
stderr = error — not by the level in the text. So the level must decide the
stream, or "filter by error" surfaces every INFO line and hides nothing.
"""
import logging
import sys

from app.core.logging_config import adopt_uvicorn_loggers, configure_logging


def _streams_of_root_handlers():
    root = logging.getLogger()
    return {h.stream: h for h in root.handlers}


def test_info_goes_to_stdout_and_errors_to_stderr(capsys):
    configure_logging()
    log = logging.getLogger("test.routing")

    log.info("routine request")
    log.warning("degraded")
    log.error("broken")

    captured = capsys.readouterr()

    # INFO must not reach stderr, or it gets reported as an error.
    assert "routine request" in captured.out
    assert "routine request" not in captured.err

    # WARNING/ERROR must not reach stdout, or real failures hide as info.
    assert "degraded" in captured.err
    assert "broken" in captured.err
    assert "degraded" not in captured.out
    assert "broken" not in captured.out


def test_configure_is_idempotent():
    # Re-running must replace handlers, not stack them — otherwise every line
    # is emitted twice and INFO lands on a leftover stderr handler.
    configure_logging()
    first = len(logging.getLogger().handlers)
    configure_logging()

    assert len(logging.getLogger().handlers) == first == 2
    streams = _streams_of_root_handlers()
    assert sys.stdout in streams and sys.stderr in streams


def test_adopt_uvicorn_loggers_hands_them_to_root():
    # Uvicorn ships its own stderr handlers with propagate=False, so its INFO
    # lines are tagged as errors until they are routed through root.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = [logging.StreamHandler(sys.stderr)]
        lg.propagate = False

    adopt_uvicorn_loggers()

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        assert lg.handlers == []
        assert lg.propagate is True
