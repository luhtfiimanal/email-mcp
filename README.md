# Email MCP

MCP server that connects to any IMAP/SMTP email server (built for Mailcow, works with others). Gives [Claude Code](https://claude.com/claude-code) the ability to read, search, send, reply, and delete emails.

## Tools

| Tool | Description |
|------|-------------|
| `email_folders` | List all mailbox folders |
| `email_list` | List recent emails in a folder |
| `email_read` | Read a specific email by UID |
| `email_search` | Search emails using IMAP search criteria |
| `email_send` | Send an email (plain text + HTML) |
| `email_reply` | Reply to an email by UID |
| `email_delete` | Delete an email (moves to Trash) |

## Setup

### 1. Clone and install dependencies

```bash
git clone https://github.com/luhtfiimanal/email-mcp.git
cd email-mcp
uv sync
```

### 2. Configure credentials

Copy and edit the `.env` file:

```bash
cp .env.example .env
```

```env
IMAP_HOST=mail.example.com
IMAP_PORT=993
SMTP_HOST=mail.example.com
SMTP_PORT=587
EMAIL_USER=you@example.com
EMAIL_PASSWORD=your-password
```

### 3. Register with Claude Code

Add as a global MCP server (available in all projects):

```bash
claude mcp add --transport stdio email --scope user -- \
  uv run --directory /path/to/email-mcp python server.py
```

Or add to a specific project only:

```bash
claude mcp add --transport stdio email --scope project -- \
  uv run --directory /path/to/email-mcp python server.py
```

### 4. Restart Claude Code

The `email_*` tools should now be available. Verify with `/mcp`.

## Usage examples

Once registered, you can ask Claude Code things like:

- "Check my inbox"
- "Read the latest email from john@example.com"
- "Search for emails about the quarterly report"
- "Send an email to alice@example.com about the meeting tomorrow"
- "Reply to that email and cc bob"
- "Delete that spam email"
- "Show my sent emails"

## Search syntax

The `email_search` tool uses IMAP search criteria:

```
FROM "sender@example.com"
SUBJECT "meeting"
SINCE "01-Jan-2025"
UNSEEN
OR FROM "alice" FROM "bob"
SUBJECT "report" SINCE "01-Dec-2024"
```

## How it works

- Uses `imaplib` for reading emails (IMAP over SSL)
- Uses `smtplib` for sending emails (SMTP with STARTTLS)
- Sent emails are automatically saved to the Sent folder
- Supports HTML email with plain text fallback
- Runs as a stdio MCP server via the [Python MCP SDK](https://github.com/modelcontextprotocol/python-sdk)

## License

MIT
