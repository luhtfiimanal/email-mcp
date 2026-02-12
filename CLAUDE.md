# Email MCP Server

## Project
MCP server (stdio) for reading and sending emails via IMAP/SMTP, built for Mailcow. Uses Python + `mcp` SDK + `python-dotenv`.

## Agent Instructions

### Morning Email Check
When the user asks to check their email (e.g., "check emailku", "ada email penting?", "morning briefing"):

1. **Fetch unread emails** — use `email_search(query="UNSEEN")` to get only unread emails.
2. **Categorize** each email into:
   - **Penting** — from colleagues, clients, or partners; about projects, meetings, deadlines, invoices, or action items.
   - **Promosi/Newsletter** — marketing emails, newsletters, automated notifications, social media updates.
3. **Summarize important emails** — for each important email, include: sender, subject, and a one-line summary of the content (use `email_read` if the subject alone is unclear).
4. **Check for meetings** — if any email mentions a meeting, call, or appointment for today, highlight it with the time and participants.
5. **Format the response** as:
   ```
   ## Email Penting (X)
   - **[Sender]** — Subject — short summary
   - ...

   ## Meeting Hari Ini
   - [Time] — [Topic] — [Participants]
   - (or: Tidak ada meeting hari ini)

   ## Promosi/Newsletter (X)
   - [Sender] — Subject
   - ...
   ```

### Sending Emails
- Always provide both `body` and `html` parameters.
- Keep HTML clean — use `<p>`, `<b>`, `<ul>`, `<ol>`, `<code>`, `<pre>` only.
- Do NOT add signatures or footers unless asked.
