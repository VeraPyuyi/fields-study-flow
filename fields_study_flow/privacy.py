"""Shared private-path detection for public reports, not source locators."""
import re

# A URL's slash is not a filesystem root. Relative bundle paths stay portable.
PRIVATE_PATH_RE = re.compile(
    r"(?:file://[^\s)\]}\"'<]+"
    r"|(?<![A-Za-z0-9])[A-Za-z]:[\\/][^)\]}\"'<\r\n]+"
    r"|\\\\[A-Za-z0-9._$-]+[\\/][A-Za-z0-9._$ -]+(?:[\\/][^)\]}\"'<\r\n]+)?"
    r"|(?<![A-Za-z0-9:/.])/(?:Users|home|tmp|opt|mnt|srv|var|data|workspace|private|root|usr|media|Volumes)/[^)\]}\"'<\r\n]+"
    r"|(?<![A-Za-z0-9:/.])/(?:[\w.-]+/)+[^\s/()\]}\"'<]+\.(?:pdf|py|ipynb|md|tex|json|yaml|yml|csv|txt)\b)"
)
