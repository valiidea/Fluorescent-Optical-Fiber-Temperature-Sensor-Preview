#!/usr/bin/env python3
"""Fail on unexpected publishable files, unsafe assets, and broken local links.

This guard supplements manual disclosure review; it cannot prove that arbitrary
new text contains no proprietary information. Review every allowlist change.
"""
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = set("""
.gitignore
.github/ISSUE_TEMPLATE/config.yml
.github/ISSUE_TEMPLATE/consultation.yml
.github/workflows/preview-check.yml
LICENSE
README.md
README.en.md
assets/system-overview.svg
docs/system-overview.md
docs/engineering-notes.md
docs/integration-guide.md
docs/measurement-guide.md
docs/preview-boundary.md
docs/purchase.md
docs/faq.md
tools/check_public_surface.py
""".split())
PATTERNS = {
    "local user path": r"/(?:Users|home)/[^/\s]+",
    "serial device path": r"/dev/(?:cu\.|tty)",
    "GitHub token": r"gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}",
    "private key": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "private repository link": r"github\.com/valiidea/Fluorescent-Optical-Fiber-Temperature-Sensor(?=[/\s)#?]|$)",
}


def main():
    result = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                            cwd=ROOT, check=True, capture_output=True)
    files = set(result.stdout.decode().strip("\0").split("\0"))
    errors = []
    for name in sorted(files - ALLOWED):
        errors.append(f"Unexpected publishable file: {name}")
    for name in sorted(ALLOWED - files):
        errors.append(f"Missing public file: {name}")
    for name in sorted(files & ALLOWED):
        path = ROOT / name
        if path.is_symlink() or not path.is_file():
            errors.append(f"Not a regular file: {name}")
            continue
        if path.stat().st_size > 200_000:
            errors.append(f"Oversized public asset: {name}")
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            errors.append(f"Non-text payload: {name}")
            continue
        for label, pattern in PATTERNS.items():
            if re.search(pattern, content):
                errors.append(f"Possible {label}: {name}")
        if path.suffix == ".md":
            for target in re.findall(r"\]\(([^\s)]+)\)", content):
                link = urlsplit(target)
                if link.scheme or link.netloc or not link.path:
                    continue
                destination = (path.parent / unquote(link.path)).resolve()
                if ROOT not in destination.parents or not destination.is_file():
                    errors.append(f"Broken or escaping link in {name}: {target}")
        if path.suffix == ".svg":
            try:
                tree = ET.fromstring(content)
                for element in tree.iter():
                    tag = element.tag.rsplit("}", 1)[-1]
                    if tag in ("script", "foreignObject", "image"):
                        errors.append(f"Active or embedded SVG content: {name}")
                    for attr, value in element.attrib.items():
                        local = attr.rsplit("}", 1)[-1]
                        if local.startswith("on") or (local == "href" and not value.startswith("#")):
                            errors.append(f"External or active SVG attribute: {name}")
            except ET.ParseError:
                errors.append(f"Invalid SVG: {name}")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Public surface OK: {len(files)} allowlisted files; links and text scan passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
