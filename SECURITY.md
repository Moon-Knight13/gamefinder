# Security Policy

## Supported Use
This template is intended for secure-by-default project bootstrapping.

## Reporting a Vulnerability

**Do not open a public issue for a security vulnerability.**

- **In this template:** report privately via GitHub's
  [Private Vulnerability Reporting](https://docs.github.com/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
  — open the repository's **Security** tab and click **Report a vulnerability**.
  (Repo maintainers: enable this under *Settings → Security → Private vulnerability reporting*.)
  Low-severity findings (weak defaults, misconfiguration, documentation gaps) that are
  safe to discuss in the open may instead use the *Security Vulnerability* issue template.
- **In a project derived from this template:** report to that project's maintainer using
  their disclosure process.

Please include reproduction steps and an impact assessment. We aim to acknowledge reports
within a few business days.

## Secret Leak Response
1. Revoke and rotate exposed credentials immediately.
2. Remove secrets from code and git history.
3. Re-scan repository history with gitleaks.
4. Re-run CI secret and semgrep checks.
5. Document incident and remediation in project notes.

## Baseline Security Controls

Protecting the repository:
- Pre-commit hooks with gitleaks and semgrep.
- CI secret scan and semgrep workflows.
- Local bootstrap script to enforce branch protection and required checks.

Protecting the agent itself (see [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md)):
- `permissions.deny` rules in `.claude/settings.json` over credential and key
  material. Deny rules hold in every permission mode, including
  `bypassPermissions`, and no settings scope can remove one.
- Bash sandbox with credential deny entries for the mounted credential volumes.
- A `PreToolUse` guard over the files that govern the agent — `.claude/`,
  `.devcontainer/`, `CLAUDE.md`, the routing scripts, the gate configs — so a
  session cannot widen its own boundary in passing.
- A `PostToolUse` rail that labels issue and PR text as untrusted data, because
  the board gates cards on metadata while the agent acts on the body.
- gitleaks run as a file is written, not only at commit time.

Deny-by-default egress in the devcontainer firewall bounds **where** data can go.
It does not bound **whether** data leaves: the allowlist admits the whole GitHub
CIDR range, so `git push` is an accepted exfiltration path. The container is a
host-protection boundary, not a data-containment one.

## GameFinder Data Model

GameFinder stores the following in a SQLite database:

| Table | Contains | Sensitive? |
|-------|----------|------------|
| `guilds` | Server config (threshold, timezone, block hours) | No |
| `users` | Discord user ID, timezone preference | Low — user IDs are public in Discord |
| `availability` | User ID + date + block per guild | Low |
| `games` | Game metadata, creator ID, slot info | Low |
| `rsvps` | User RSVP status per game | Low |
| `campaigns` | Recurring game config | No |
| `campaign_roster` | Player membership in campaigns | Low |
| `sessions` | Individual session dates and status | No |

**Guild isolation guarantee:** Every query that reads or writes user data
includes `guild_id` in its WHERE clause. A query missing `guild_id` is a
security bug — it leaks another server's data.

**Bot token handling:** The Discord bot token lives in `.env` on the
deployment host only. It is never committed to the repository. The
`.env.example` file contains only placeholder values.

**Data deletion:**
- Users: `/data delete` removes all user data immediately.
- Guilds: data scheduled for deletion 30 days after bot removal.
- Stale availability: auto-purged daily for dates outside forecast window.

See [docs/PRIVACY_POLICY.md](docs/PRIVACY_POLICY.md) for the full privacy policy.

## Non-Goals

The threat model states these in full. In short: prompt injection is not solved,
only blast-radius-reduced; TLS is not inspected, so domain fronting is live;
egress policy is per-container, not per-binary; subagents share the parent
process and are not a security boundary; and in a single-maintainer repository,
required review is self-review.
