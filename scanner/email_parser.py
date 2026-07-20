import email
import email.message
import logging
from email.header import decode_header
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def _decode_mime_header(value: str) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    decoded = []
    for content, charset in parts:
        if isinstance(content, bytes):
            try:
                decoded.append(content.decode(charset or "utf-8", errors="replace"))
            except (LookupError, ValueError):
                decoded.append(content.decode("utf-8", errors="replace"))
        else:
            decoded.append(content)
    return " ".join(decoded)


def _get_text_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    for a_tag in soup.find_all("a"):
        href = a_tag.get("href", "")
        text = a_tag.get_text(strip=True)
        if href and text:
            a_tag.insert_after(f" ({href}) ")
    return soup.get_text(separator="\n", strip=True)


def _get_email_body(msg: email.message.Message) -> Optional[str]:
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    html = payload.decode(charset, errors="replace")
                    return _get_text_from_html(html)
        return None
    else:
        payload = msg.get_payload(decode=True)
        if payload is None:
            return None
        charset = msg.get_content_charset() or "utf-8"
        text = payload.decode(charset, errors="replace")
        content_type = msg.get_content_type()
        if content_type == "text/html":
            return _get_text_from_html(text)
        return text

def parse_eml(filepath: str) -> dict:
    path = Path(filepath)
    raw = path.read_bytes()
    msg = email.message_from_bytes(raw)
    subject = _decode_mime_header(msg.get("Subject", ""))
    from_ = _decode_mime_header(msg.get("From", ""))
    date = msg.get("Date", "")
    body = _get_email_body(msg) or ""
    message_id = msg.get("Message-Id", "")
    return {"subject": subject, "from": from_, "date": date, "body": body, "message_id": message_id}
