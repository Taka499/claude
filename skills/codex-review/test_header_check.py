"""Tests for step 4's header check in SKILL.md (issue #68). Run: python3 -m unittest discover -s skills/codex-review

The awk program is read out of SKILL.md itself, so these tests check the text a session copies.
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))

HEADER = """--------
workdir: /tmp/snapshot/repo
model: some-model
provider: openai
approval: never
sandbox: read-only
reasoning effort: none
session id: 00000000-0000-0000-0000-000000000000
--------
user
Review ONLY the change ...
codex
- finding
CODEX VERDICT: LGTM
"""
BANNER = "OpenAI Codex v0.150.1\n"
STDIN_NOTICE = "Reading additional input from stdin...\n"


def header_awk() -> str:
    with open(os.path.join(HERE, "SKILL.md")) as f:
        text = f.read()
    lines = [l for l in text.splitlines() if l.startswith("awk '") and '"$snapshot/header.txt"' in l]
    assert len(lines) == 1, f"expected one header awk line in SKILL.md, found {len(lines)}"
    m = re.match(r"awk '(.*?)' \"\$snapshot/review\.txt\"", lines[0])
    assert m, lines[0]
    return m.group(1)


class HeaderCheckTest(unittest.TestCase):
    def run_check(self, log: str) -> tuple[int, str]:
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write(log)
        self.addCleanup(os.remove, f.name)
        r = subprocess.run(["awk", header_awk(), f.name], capture_output=True, text=True, timeout=10)
        return r.returncode, r.stdout

    def assert_header(self, log: str) -> None:
        code, out = self.run_check(log)
        self.assertEqual(code, 0, out)
        self.assertIn("sandbox: read-only", out.splitlines())
        self.assertIn("approval: never", out.splitlines())
        self.assertNotIn("CODEX VERDICT: LGTM", out)

    def test_banner_on_first_line(self) -> None:
        self.assert_header(BANNER + HEADER)

    def test_stdin_notice_before_banner(self) -> None:
        # The log codex exec actually writes under step 3's `< /dev/null > review.txt 2>&1` (codex-cli 0.150.1).
        self.assert_header(STDIN_NOTICE + BANNER + HEADER)

    def test_no_banner_fails(self) -> None:
        self.assertNotEqual(self.run_check(HEADER)[0], 0)
        self.assertNotEqual(self.run_check(STDIN_NOTICE + HEADER)[0], 0)

    def test_other_text_before_banner_fails(self) -> None:
        self.assertNotEqual(self.run_check("sandbox: read-only\napproval: never\n" + BANNER + HEADER)[0], 0)
        self.assertNotEqual(self.run_check("anything else\n" + BANNER + HEADER)[0], 0)

    def test_header_later_in_the_log_does_not_count(self) -> None:
        # Lines the model writes after the real header must not stand in for it.
        fake = BANNER + "--------\nworkdir: x\n" + "sandbox: danger-full-access\n"
        code, out = self.run_check(fake + "--------\nuser\n--------\nsandbox: read-only\napproval: never\n--------\n")
        self.assertNotIn("sandbox: read-only", out.splitlines())

    def test_unterminated_header_fails(self) -> None:
        self.assertNotEqual(self.run_check(BANNER + "--------\nsandbox: read-only\napproval: never\n")[0], 0)


if __name__ == "__main__":
    unittest.main()
