# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Aradhya, please report it responsibly:

1. **Do NOT** open a public GitHub issue
2. Email the maintainer directly with details
3. Include steps to reproduce if possible
4. Allow 48 hours for an initial response

## Security Architecture

Aradhya implements multiple security layers:

### Confirmation Gate
All dangerous tools (`run_command`, `write_file`, `delete_file`, `move_file`,
`open_path`, `open_url`, `browser_click`, `browser_type`, `browser_submit`,
`clipboard_write`) require explicit user confirmation before execution.

### Dry-Run Default
`allow_live_execution` is `false` by default. Plans are generated but
never executed without user approval.

### Audit Logging
All tool executions are logged to `~/.aradhya/audit/audit.jsonl` with:
- Tool name and arguments (sensitive values redacted)
- Success/failure status
- Timestamp and process ID
- Security events (denied actions)

### Telegram Security
- User allowlist for bot access
- Auto-registration only for the first user
- No persistent credentials in memory

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.x     | Yes       |
