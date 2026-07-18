import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from app.core.config import settings


class EmailService:
    """
    Service responsible for sending emails.
    """

    def __init__(self):
        self.host = settings.SMTP_HOST
        self.port = settings.SMTP_PORT
        self.username = settings.SMTP_USERNAME
        self.password = settings.SMTP_PASSWORD
        self.from_email = settings.SMTP_FROM_EMAIL
        self.from_name = settings.SMTP_FROM_NAME

    def send_otp_email(self, recipient_email: str, otp: str):
        """
        Send OTP email.
        """

        template_path = (
            Path(__file__).parent.parent
            / "templates"
            / "otp_email.html"
        )

        print("Template path:", template_path)
        print("Exists:", template_path.exists())
        with open(template_path, "r", encoding="utf-8") as file:
            html = file.read()

        html = html.replace("{{OTP}}", otp)

        message = MIMEMultipart("alternative")
        message["Subject"] = "Your CipherChat Verification Code"
        message["From"] = f"{self.from_name} <{self.from_email}>"
        message["To"] = recipient_email

        message.attach(MIMEText(html, "html"))

        with smtplib.SMTP(self.host, self.port) as server:
            server.starttls()
            server.login(self.username, self.password)
            server.sendmail(
                self.from_email,
                recipient_email,
                message.as_string(),
            )