"""Multi-signal digest formatting — BUY and SELL grouped into sections."""
from datetime import datetime, timezone

from app.schemas.stock import AIAnalysisResult
from app.services.line_notification import LineNotificationService


def _item(symbol, action):
    return {
        "symbol": symbol,
        "price": 100.0,
        "analysis": AIAnalysisResult(
            symbol=symbol,
            action=action,
            summary=f"{action} {symbol}",
            confidence="High",
            reasons=["r1", "r2"],
            analyzed_at=datetime.now(timezone.utc),
        ),
    }


def test_single_item_uses_action_label():
    svc = LineNotificationService()
    msg = svc.format_digest([_item("AMZN", "SELL")])
    assert "SELL SIGNAL: AMZN" in msg


def test_mixed_digest_groups_buy_and_sell_sections():
    svc = LineNotificationService()
    msg = svc.format_digest(
        [_item("AMZN", "BUY"), _item("LLY", "SELL"), _item("NVDA", "BUY")]
    )
    assert "🚀 BUY SIGNALS (2)" in msg
    assert "🔴 SELL SIGNALS (1)" in msg
    # BUY section comes before SELL section.
    assert msg.index("BUY SIGNALS") < msg.index("SELL SIGNALS")
    for sym in ("AMZN", "LLY", "NVDA"):
        assert sym in msg
