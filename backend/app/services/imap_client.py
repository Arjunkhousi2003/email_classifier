"""IMAP fallback for providers that are not connected through Gmail OAuth."""

import email
import imaplib
from datetime import datetime, timezone
from email.header import decode_header
from email.utils import parsedate_to_datetime

from app.services.errors import ProviderError

BODY_LIMIT = 20_000


def _decode_header(value: str | None) -> str:
    if not value:
        return ""
    parts = []
    for text, charset in decode_header(value):
        if isinstance(text, bytes):
            parts.append(text.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(text)
    return "".join(parts)


def _body(message: email.message.Message) -> str:
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition")):
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")[:BODY_LIMIT]
        return ""
    payload = message.get_payload(decode=True) or b""
    charset = message.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")[:BODY_LIMIT]


def fetch_messages(
    host: str,
    username: str,
    password: str,
    port: int = 993,
    use_ssl: bool = True,
    limit: int = 25,
) -> list[dict]:
    client: imaplib.IMAP4 | None = None
    try:
        client = imaplib.IMAP4_SSL(host, port) if use_ssl else imaplib.IMAP4(host, port)
        client.login(username, password)
        status, _ = client.select("INBOX", readonly=True)
        if status != "OK":
            raise ProviderError("Could not open INBOX")
        status, data = client.search(None, "ALL")
        if status != "OK" or not data or not data[0]:
            return []
        ids = data[0].split()[-max(1, min(limit, 100)) :]
        messages = []
        for msg_id in ids:
            status, fetched = client.fetch(msg_id, "(RFC822)")
            if status != "OK" or not fetched or not isinstance(fetched[0], tuple):
                continue
            raw = fetched[0][1]
            parsed = email.message_from_bytes(raw)
            subject = _decode_header(parsed.get("Subject"))
            sender = _decode_header(parsed.get("From"))
            body = _body(parsed)
            received = None
            if parsed.get("Date"):
                try:
                    received = parsedate_to_datetime(parsed.get("Date"))
                    if received.tzinfo is None:
                        received = received.replace(tzinfo=timezone.utc)
                except (TypeError, ValueError, IndexError):
                    received = None
            messages.append(
                {
                    "provider": "imap",
                    "provider_message_id": f"{host}:{msg_id.decode()}",
                    "thread_id": None,
                    "sender": sender[:500],
                    "recipients": _decode_header(parsed.get("To")),
                    "subject": subject,
                    "snippet": body[:180],
                    "body_text": body,
                    "received_at": received,
                    "headers": {
                        "from": sender,
                        "to": _decode_header(parsed.get("To")),
                        "subject": subject,
                        "date": parsed.get("Date") or "",
                    },
                }
            )
        return messages
    except imaplib.IMAP4.error as exc:
        raise ProviderError("IMAP login or fetch failed") from exc
    except OSError as exc:
        raise ProviderError("Could not reach the IMAP server") from exc
    finally:
        if client is not None:
            try:
                client.logout()
            except Exception:
                pass
