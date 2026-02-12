import imaplib
import smtplib
import email
import email.utils
import os
import time
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from dotenv import load_dotenv
from mcp.server import FastMCP

load_dotenv()

IMAP_HOST = os.environ["IMAP_HOST"]
IMAP_PORT = int(os.environ.get("IMAP_PORT", "993"))
SMTP_HOST = os.environ["SMTP_HOST"]
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
EMAIL_USER = os.environ["EMAIL_USER"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]

mcp = FastMCP(
    "Email",
    instructions="""MCP server for reading and sending emails via IMAP/SMTP (Mailcow).

Available folders: INBOX, Sent, Drafts, Trash, Junk, Archive.
To read sent emails, use email_list(folder="Sent") and email_read(uid="...", folder="Sent").

When sending or replying to emails, ALWAYS provide both `body` (plain text) and `html` parameters.
The `body` is the plain text fallback, and `html` should contain a well-formatted HTML version.
Use proper HTML email best practices: inline styles, table-based layout if needed, and keep it clean and professional.
Do NOT add any signature or footer unless the user explicitly asks for one.

HTML formatting rules:
- Use basic tags: <p>, <br>, <ul>, <ol>, <li>, <b>, <i>, <a>, <code>, <pre>.
- For inline code, use: <code style="background:#f3f4f6; padding:2px 6px; border-radius:4px; font-size:13px;">code here</code>
- For code blocks, use:
  <pre style="background:#f3f4f6; padding:12px 16px; border-radius:6px; font-size:13px; overflow-x:auto; font-family:monospace;"><code>code here</code></pre>
- NEVER use markdown syntax (```, **, _, etc.) inside the html parameter. Always convert to proper HTML tags.
- Keep the overall look clean and professional — like a normal email, not a marketing newsletter.
""",
)


def _decode_header_value(value: str) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded)


def _get_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))
            if content_type == "text/plain" and "attachment" not in disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
        # Fallback to text/html if no plain text found
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))
            if content_type == "text/html" and "attachment" not in disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
    return ""


def _get_attachments(msg: email.message.Message) -> list[dict]:
    attachments = []
    if msg.is_multipart():
        for part in msg.walk():
            disposition = str(part.get("Content-Disposition", ""))
            if "attachment" in disposition:
                filename = part.get_filename()
                if filename:
                    filename = _decode_header_value(filename)
                    attachments.append({
                        "filename": filename,
                        "content_type": part.get_content_type(),
                        "size": len(part.get_payload(decode=True) or b""),
                    })
    return attachments


def _imap_connect() -> imaplib.IMAP4_SSL:
    conn = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    conn.login(EMAIL_USER, EMAIL_PASSWORD)
    return conn


def _save_to_sent(msg_bytes: bytes) -> None:
    conn = _imap_connect()
    try:
        date_time = imaplib.Time2Internaldate(time.time())
        conn.append("Sent", "(\\Seen)", date_time, msg_bytes)
    finally:
        conn.logout()


def _format_email_summary(uid: bytes, msg: email.message.Message) -> dict:
    return {
        "uid": uid.decode(),
        "from": _decode_header_value(msg.get("From", "")),
        "to": _decode_header_value(msg.get("To", "")),
        "subject": _decode_header_value(msg.get("Subject", "")),
        "date": msg.get("Date", ""),
    }


@mcp.tool()
def email_folders() -> str:
    """List all email folders/mailboxes."""
    conn = _imap_connect()
    try:
        status, folders = conn.list()
        if status != "OK":
            return "Failed to list folders"
        result = []
        for f in folders:
            decoded = f.decode()
            # Extract folder name from IMAP LIST response
            # Format: (\\flags) "delimiter" "name"
            parts = decoded.split(' "')
            if len(parts) >= 2:
                name = parts[-1].strip('"')
            else:
                name = decoded
            result.append(name)
        return "\n".join(result)
    finally:
        conn.logout()


@mcp.tool()
def email_list(folder: str = "INBOX", count: int = 20) -> list[dict]:
    """List recent emails in a folder.

    Args:
        folder: Folder name (default: INBOX)
        count: Number of recent emails to return (default: 20)
    """
    conn = _imap_connect()
    try:
        status, _ = conn.select(folder, readonly=True)
        if status != "OK":
            return [{"error": f"Cannot select folder: {folder}"}]

        status, data = conn.uid("search", None, "ALL")
        if status != "OK":
            return [{"error": "Search failed"}]

        uids = data[0].split()
        if not uids:
            return []

        recent_uids = uids[-count:]
        recent_uids.reverse()

        results = []
        for uid in recent_uids:
            status, msg_data = conn.uid("fetch", uid, "(BODY.PEEK[HEADER] FLAGS)")
            if status != "OK" or not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1] if isinstance(msg_data[0], tuple) else msg_data[0]
            msg = email.message_from_bytes(raw)
            summary = _format_email_summary(uid, msg)

            # Parse flags
            flags_data = msg_data[0][0] if isinstance(msg_data[0], tuple) else b""
            flags_str = flags_data.decode(errors="replace")
            summary["seen"] = "\\Seen" in flags_str

            results.append(summary)
        return results
    finally:
        conn.logout()


@mcp.tool()
def email_read(uid: str, folder: str = "INBOX") -> dict:
    """Read a specific email by UID.

    Args:
        uid: Email UID
        folder: Folder name (default: INBOX)
    """
    conn = _imap_connect()
    try:
        status, _ = conn.select(folder)
        if status != "OK":
            return {"error": f"Cannot select folder: {folder}"}

        status, msg_data = conn.uid("fetch", uid.encode(), "(RFC822)")
        if status != "OK" or not msg_data or not msg_data[0]:
            return {"error": f"Email UID {uid} not found"}

        raw = msg_data[0][1]
        msg = email.message_from_bytes(raw)

        return {
            "uid": uid,
            "from": _decode_header_value(msg.get("From", "")),
            "to": _decode_header_value(msg.get("To", "")),
            "cc": _decode_header_value(msg.get("Cc", "")),
            "subject": _decode_header_value(msg.get("Subject", "")),
            "date": msg.get("Date", ""),
            "message_id": msg.get("Message-ID", ""),
            "body": _get_body(msg),
            "attachments": _get_attachments(msg),
        }
    finally:
        conn.logout()


@mcp.tool()
def email_search(query: str, folder: str = "INBOX", count: int = 20) -> list[dict]:
    """Search emails using IMAP search criteria.

    Args:
        query: Search query. Examples:
            - FROM "sender@example.com"
            - SUBJECT "meeting"
            - SINCE "01-Jan-2025"
            - UNSEEN
            - OR FROM "alice" FROM "bob"
            - SUBJECT "report" SINCE "01-Dec-2024"
        folder: Folder name (default: INBOX)
        count: Max results to return (default: 20)
    """
    conn = _imap_connect()
    try:
        status, _ = conn.select(folder, readonly=True)
        if status != "OK":
            return [{"error": f"Cannot select folder: {folder}"}]

        status, data = conn.uid("search", None, query)
        if status != "OK":
            return [{"error": f"Search failed: {query}"}]

        uids = data[0].split()
        if not uids:
            return []

        recent_uids = uids[-count:]
        recent_uids.reverse()

        results = []
        for uid in recent_uids:
            status, msg_data = conn.uid("fetch", uid, "(BODY.PEEK[HEADER] FLAGS)")
            if status != "OK" or not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1] if isinstance(msg_data[0], tuple) else msg_data[0]
            msg = email.message_from_bytes(raw)
            results.append(_format_email_summary(uid, msg))
        return results
    finally:
        conn.logout()


@mcp.tool()
def email_send(
    to: str,
    subject: str,
    body: str,
    html: str = "",
    cc: str = "",
    bcc: str = "",
) -> str:
    """Send an email.

    Args:
        to: Recipient email address(es), comma-separated
        subject: Email subject
        body: Email body (plain text)
        html: Email body (HTML). If provided, email is sent as multipart with both plain text and HTML.
        cc: CC recipients, comma-separated (optional)
        bcc: BCC recipients, comma-separated (optional)
    """
    if html:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(body, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))
    else:
        msg = MIMEText(body, "plain", "utf-8")
    msg["From"] = EMAIL_USER
    msg["To"] = to
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = cc

    recipients = [addr.strip() for addr in to.split(",")]
    if cc:
        recipients += [addr.strip() for addr in cc.split(",")]
    if bcc:
        recipients += [addr.strip() for addr in bcc.split(",")]

    msg_str = msg.as_string()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(EMAIL_USER, EMAIL_PASSWORD)
        smtp.sendmail(EMAIL_USER, recipients, msg_str)

    _save_to_sent(msg_str.encode())

    return f"Email sent to {to}"


@mcp.tool()
def email_reply(
    uid: str,
    body: str,
    html: str = "",
    reply_all: bool = False,
    folder: str = "INBOX",
) -> str:
    """Reply to an email by UID.

    Args:
        uid: UID of the email to reply to
        body: Reply body (plain text)
        html: Reply body (HTML). If provided, reply is sent as multipart with both plain text and HTML.
        reply_all: If True, reply to all recipients (default: False)
        folder: Folder containing the email (default: INBOX)
    """
    conn = _imap_connect()
    try:
        status, _ = conn.select(folder, readonly=True)
        if status != "OK":
            return f"Cannot select folder: {folder}"

        status, msg_data = conn.uid("fetch", uid.encode(), "(RFC822)")
        if status != "OK" or not msg_data or not msg_data[0]:
            return f"Email UID {uid} not found"

        raw = msg_data[0][1]
        original = email.message_from_bytes(raw)
    finally:
        conn.logout()

    original_from = original.get("From", "")
    original_subject = original.get("Subject", "")
    original_message_id = original.get("Message-ID", "")

    subject = original_subject
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    if html:
        reply = MIMEMultipart("alternative")
        reply.attach(MIMEText(body, "plain", "utf-8"))
        reply.attach(MIMEText(html, "html", "utf-8"))
    else:
        reply = MIMEText(body, "plain", "utf-8")
    reply["From"] = EMAIL_USER
    reply["Subject"] = subject
    reply["In-Reply-To"] = original_message_id
    reply["References"] = original_message_id

    recipients = [email.utils.parseaddr(original_from)[1]]

    if reply_all:
        original_to = original.get("To", "")
        original_cc = original.get("Cc", "")
        all_addrs = []
        for field in [original_to, original_cc]:
            if field:
                for _, addr in email.utils.getaddresses([field]):
                    if addr and addr.lower() != EMAIL_USER.lower():
                        all_addrs.append(addr)
        if all_addrs:
            reply["Cc"] = ", ".join(all_addrs)
            recipients += all_addrs

    reply["To"] = email.utils.parseaddr(original_from)[1]

    reply_str = reply.as_string()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(EMAIL_USER, EMAIL_PASSWORD)
        smtp.sendmail(EMAIL_USER, recipients, reply_str)

    _save_to_sent(reply_str.encode())

    return f"Reply sent to {reply['To']}"


@mcp.tool()
def email_delete(uid: str, folder: str = "INBOX") -> str:
    """Delete an email by UID (moves to Trash).

    Args:
        uid: UID of the email to delete
        folder: Folder containing the email (default: INBOX)
    """
    conn = _imap_connect()
    try:
        status, _ = conn.select(folder)
        if status != "OK":
            return f"Cannot select folder: {folder}"

        # Try to move to Trash folder (common names)
        trash_names = ["Trash", "INBOX.Trash", "Deleted Items", "Deleted"]
        moved = False
        for trash in trash_names:
            status, _ = conn.uid("copy", uid.encode(), trash)
            if status == "OK":
                conn.uid("store", uid.encode(), "+FLAGS", "(\\Deleted)")
                conn.expunge()
                moved = True
                break

        if not moved:
            # Fallback: just mark as deleted
            conn.uid("store", uid.encode(), "+FLAGS", "(\\Deleted)")
            conn.expunge()

        return f"Email UID {uid} deleted"
    finally:
        conn.logout()


if __name__ == "__main__":
    mcp.run(transport="stdio")
