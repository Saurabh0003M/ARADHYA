"""PreToolUse hook: block shell commands that print secret-bearing env vars.

Reads the hook payload JSON from stdin. Exits 2 (block, message on stderr)
if the command would echo/print an environment variable whose name matches
(?i)(KEY|TOKEN|SECRET); exits 0 otherwise.

Deliberately conservative: assignments like `$env:GITHUB_TOKEN=$null` and
commands that merely pass such vars to a program (e.g. `gh pr list`) are
allowed. Only printing contexts are blocked.
"""
import json
import re
import sys

SECRET_NAME = r"[A-Za-z0-9_]*(?:KEY|TOKEN|SECRET)[A-Za-z0-9_]*"

BLOCK_PATTERNS = [
    # PowerShell: echo/Write-Host/Write-Output/Write-Error/Out-Host of $env:X
    # (not followed by '=' i.e. not an assignment, and not a substring/length access)
    rf"(?i)\b(?:echo|write-host|write-output|write-error|out-host|write-information)\b[^;\r\n|]*\$env:{SECRET_NAME}\b(?!\s*=|\.)",
    # POSIX: echo/printf of $X, ${X} or "$X"
    rf"(?i)\b(?:echo|printf)\b[^;\r\n|]*\$\{{?{SECRET_NAME}\}}?(?![A-Za-z0-9_])(?!\s*=)",
    # printenv X / env | grep X-style direct reads
    rf"(?i)\bprintenv\s+{SECRET_NAME}\b",
    # PowerShell: Get-Item/Get-ChildItem/Get-Content env:X (prints name+value)
    rf"(?i)\b(?:get-item|get-childitem|gci|get-content|cat|type)\s+env:{SECRET_NAME}\b",
    # PowerShell: a bare `$env:X` statement alone prints the value
    rf"(?i)(?:^|[;|(]|\bthen\s|\bdo\s)\s*\$env:{SECRET_NAME}\s*(?:$|[;)])",
]

# Length/existence checks are the sanctioned way to verify a var — allow them.
ALLOW_PATTERNS = [
    rf"(?i)\$env:{SECRET_NAME}[\"')]*\.Length",
    rf"(?i)\$\{{?#{SECRET_NAME}\}}?",  # bash ${#X}
]


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # malformed payload: never block on guard failure
    command = (payload.get("tool_input") or {}).get("command") or ""
    if not command:
        return 0

    stripped = command
    for pat in ALLOW_PATTERNS:
        stripped = re.sub(pat, "", stripped)

    for pat in BLOCK_PATTERNS:
        match = re.search(pat, stripped)
        if match:
            sys.stderr.write(
                "secret_guard: blocked — this command prints an env var whose "
                f"name matches KEY/TOKEN/SECRET ({match.group(0).strip()!r}). "
                "Never print secrets; to verify a var exists, print its "
                "length only (e.g. `$env:X.Length`).\n"
            )
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
