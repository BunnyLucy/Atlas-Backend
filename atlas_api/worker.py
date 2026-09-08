import asyncio
import io
import smtplib
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

import structlog
from PIL import Image
from qcloud_cos import CosConfig, CosS3Client
from sqlalchemy import select

from .config import get_settings
from .db import SessionLocal
from .models import AssetVersion, OutboxEvent

log = structlog.get_logger()
settings = get_settings()


def send_email(payload: dict, subject: str, purpose: str) -> None:
    if settings.env != "production" and not settings.smtp_host:
        log.info("development_email", to=payload.get("email"), subject=subject, purpose=purpose, token=payload.get("token"))
        return
    if not all((settings.smtp_host, settings.smtp_username, settings.smtp_password, settings.email_from)):
        raise RuntimeError("SMTP is not fully configured")
    message = EmailMessage()
    message["From"], message["To"], message["Subject"] = settings.email_from, payload["email"], subject
    message.set_content(f"Atlas {purpose} token: {payload['token']}\n\n此链接或验证码仅供你本人使用。")
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        smtp.starttls(); smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value()); smtp.send_message(message)


def generate_thumbnail(payload: dict) -> str:
    if not all((settings.cos_secret_id, settings.cos_secret_key, settings.cos_region, settings.cos_bucket)):
        raise RuntimeError("COS is not fully configured")
    client = CosS3Client(CosConfig(Region=settings.cos_region, SecretId=settings.cos_secret_id, SecretKey=settings.cos_secret_key.get_secret_value(), Scheme="https"))
    response = client.get_object(Bucket=settings.cos_bucket, Key=payload["objectKey"])
    source = response["Body"].get_raw_stream().read()
    image = Image.open(io.BytesIO(source)); image.thumbnail((640, 640))
    output = io.BytesIO(); image.convert("RGB").save(output, format="JPEG", quality=84, optimize=True); output.seek(0)
    key = f"thumbnails/{payload['assetID']}/{payload['version']}.jpg"
    client.put_object(Bucket=settings.cos_bucket, Key=key, Body=output, ContentType="image/jpeg")
    return key


async def dispatch(event: OutboxEvent) -> None:
    if event.kind == "email.verify":
        await asyncio.to_thread(send_email, event.payload, "验证你的 Atlas 邮箱", "email verification")
    elif event.kind == "email.reset-password":
        await asyncio.to_thread(send_email, event.payload, "重置你的 Atlas 密码", "password reset")
    elif event.kind == "asset.thumbnail":
        key = await asyncio.to_thread(generate_thumbnail, event.payload)
        async with SessionLocal() as session:
            version = await session.get(AssetVersion, (event.payload["assetID"], event.payload["version"]))
            if version:
                version.thumbnail_key = key
                await session.commit()
    else:
        raise RuntimeError(f"Unsupported outbox event: {event.kind}")


async def process_one() -> bool:
    async with SessionLocal() as session:
        now = datetime.now(UTC)
        event = await session.scalar(select(OutboxEvent).where(OutboxEvent.processed_at.is_(None), OutboxEvent.available_at <= now).order_by(OutboxEvent.created_at).with_for_update(skip_locked=True).limit(1))
        if not event:
            return False
        try:
            await dispatch(event)
            event.processed_at, event.last_error = now, None
        except Exception as exc:
            event.attempts += 1
            event.last_error = str(exc)[:2000]
            event.available_at = now + timedelta(seconds=min(3600, 2 ** min(event.attempts, 10)))
            log.error("outbox_failed", event_id=str(event.id), kind=event.kind, error=str(exc))
        await session.commit()
        return True


async def run() -> None:
    log.info("worker_started")
    while True:
        if not await process_one():
            await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(run())
