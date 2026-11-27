# Privacy Policy — GameFinder Bot

**Effective date:** 2026-11-27

## What data we collect

GameFinder stores the minimum data needed for scheduling:

| Data | Purpose | Storage |
|------|---------|---------|
| Discord user ID | Identify you across sessions | SQLite |
| Timezone (optional) | Display times in your timezone | SQLite |
| Availability blocks | Aggregate scheduling insights | SQLite |
| RSVP status | Track game attendance | SQLite |
| Guild (server) ID | Isolate data between servers | SQLite |

We do **not** collect: message content, usernames, email addresses, IP addresses,
or any data beyond what is listed above.

## Why we collect it

Scheduling functionality. Availability data powers the `/windows` insights.
RSVP data tracks game attendance. Timezone data localizes time display.

## Data retention

- **Availability:** Auto-purged when it falls outside the forecast window
  (configurable per server, default 3 weeks).
- **On request:** Run `/data delete` to immediately delete all your data.
- **Server removal:** When the bot is removed from a server, all that
  server's data is deleted within 30 days.
- **Games:** Completed and cancelled games are retained for stats. No
  personal data beyond Discord user IDs is stored.

## Data sharing

We do **not** share data with any third party. All data remains in the bot's
SQLite database on our server.

## Guild isolation

Data from one Discord server is never accessible to another. Every database
query is scoped by guild ID.

## Your rights

You may:
- View your data via bot commands (`/available`, `/games`)
- Delete all your data via `/data delete`
- Request data export by contacting the bot operator

Under GDPR or similar regulations, you have the right to access, rectify,
and erase your personal data. Contact the server operator or bot maintainer
for requests.

## Security

- Bot token stored only on the deployment host, never in the repository
- SQLite database file permissions restricted to the bot process
- All queries scoped by guild ID to prevent cross-server data leakage
- See [SECURITY.md](../SECURITY.md) for vulnerability reporting

## Contact

For privacy concerns or data requests, open an issue on the
[GitHub repository](https://github.com/Moon-Knight13/gamefinder) or contact
the bot operator in your Discord server.
