import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger("app.services.email")


class EmailService:
    """
    Service responsible for sending emails.

    Sending runs in a background thread via `asyncio.to_thread`
    so a slow SMTP server never blocks the HTTP request loop.
    A failed send is retried up to `retries` times with
    exponential backoff before the error propagates.
    """

    def __init__(
        self,
        retries: int = 3,
        base_delay_seconds: float = 0.5,
    ):
        self.host = settings.SMTP_HOST
        self.port = settings.SMTP_PORT
        self.username = settings.SMTP_USERNAME
        self.password = settings.SMTP_PASSWORD
        self.from_email = settings.SMTP_FROM_EMAIL
        self.from_name = settings.SMTP_FROM_NAME
        self.retries = retries
        self.base_delay_seconds = base_delay_seconds

    def _template_path(self) -> Path:
        return (
            Path(__file__).parent.parent
            / "templates"
            / "otp_email.html"
        )

    async def send_otp_email(
        self,
        recipient_email: str,
        otp: str,
    ):
        """
        Send the OTP email, retrying transient SMTP failures.
        """

        html = await asyncio.to_thread(
            self._render_otp_template,
            otp,
        )

        message = MIMEMultipart("alternative")
        message["Subject"] = "Your CipherChat Verification Code"
        message["From"] = f"{self.from_name} <{self.from_email}>"
        message["To"] = recipient_email

        message.attach(MIMEText(html, "html"))

        last_error: Exception | None = None

        for attempt in range(1, self.retries + 1):

            try:

                await asyncio.to_thread(
                    self._send_sync,
                    recipient_email,
                    message,
                )

                logger.info(
                    "OTP email sent to %s",
                    recipient_email,
                )

                return

            except Exception as exc:

                last_error = exc

                logger.warning(
                    "SMTP attempt %d/%d failed for %s: %s",
                    attempt,
                    self.retries,
                    recipient_email,
                    exc,
                )

                if attempt < self.retries:

                    await asyncio.sleep(
                        self.base_delay_seconds * (2 ** (attempt - 1))
                    )

        raise last_error

    def _render_otp_template(self, otp: str) -> str:
        template_path = self._template_path()

        with open(template_path, "r", encoding="utf-8") as file:
            html = file.read()

        return html.replace("{{OTP}}", otp)

    def _send_sync(
        self,
        recipient_email: str,
        message: MIMEMultipart,
    ):
        with smtplib.SMTP(
            self.host,
            self.port,
            timeout=15,
        ) as server:
            server.starttls()
            server.login(self.username, self.password)
            server.sendmail(
                self.from_email,
                recipient_email,
                message.as_string(),
            )