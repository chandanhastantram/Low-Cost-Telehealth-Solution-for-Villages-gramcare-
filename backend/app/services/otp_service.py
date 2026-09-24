"""
GramCare – OTP delivery service

Cost-cutting choice: no paid SMS API (Twilio etc.) is wired in. In dev
(CONSOLE_OTP=true) the OTP is logged to the server console, which is enough
to develop and demo the whole flow without spending anything. When a real
deployment needs SMS delivery, plug a free/self-hosted gateway (e.g. an
Android-phone SMS gateway app, or a village-level IVR/USSD channel per the
paper's future-scope) into `_deliver` below.
"""

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


async def send_otp_sms(phone: str, otp: str) -> None:
    if settings.CONSOLE_OTP or settings.APP_ENV == "development":
        logger.info(f"[DEV] OTP for {phone}: {otp}")
        # Plain ASCII only: some consoles (e.g. Windows cp1252) raise
        # UnicodeEncodeError on emoji, which would otherwise crash the
        # request after the OTP was already stored.
        print(f"\n{'='*40}")
        print(f"  OTP for {phone}: {otp}")
        print(f"{'='*40}\n")
        return

    await _deliver(phone, otp)


async def _deliver(phone: str, otp: str) -> None:
    """Production delivery hook — intentionally a no-op until a free/self-hosted
    channel is wired in. Raising here (rather than silently succeeding) makes
    a misconfigured prod deployment fail loudly instead of pretending to send."""
    raise NotImplementedError(
        "No OTP delivery channel configured for production. "
        "Set CONSOLE_OTP=true for dev, or implement a gateway in _deliver()."
    )
