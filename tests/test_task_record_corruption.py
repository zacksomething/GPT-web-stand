"""Corruption must fail closed, preserving evidence for manual inspection."""

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid


SCRIPT = Path(__file__).resolve().parents[1] / "skills/web-stand-in/scripts/task_record.py"


class CorruptionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="web-stand-in-corruption-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        prompt = self.root / "prompt.txt"
        prompt.write_text("Inspect local evidence.\n", encoding="utf-8")
        task = self.cli("init", "--root", self.root / "tasks", "--prompt-file", prompt)
        self.task = Path(task["task"])
        self.observation = self.root / "observation.json"
        self.observation.write_text(json.dumps({
            "event": "send_intent", "request_id": task["request_id"],
            "evidence": "Synthetic local test; no browser submission.",
        }), encoding="utf-8")
        self.cli("record", "--task", self.task, "--observation-file", self.observation)
        self.source = self.root / "result-source.txt"
        self.source.write_text("Synthetic answer.\n", encoding="utf-8")

    def cli(self, *arguments, expected=0):
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), *map(str, arguments)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, expected, result.stderr or result.stdout)
        self.assertNotIn("Traceback", result.stderr)
        return json.loads(result.stdout if expected == 0 else result.stderr)

    def snapshot(self):
        # The empty advisory lock file may be created by a read operation.
        return {str(p.relative_to(self.task)): p.read_bytes()
                for p in self.task.rglob("*") if p.is_file() and p.name != ".record.lock"}

    def assert_blocked_and_preserved(self, error_code):
        before = self.snapshot()
        for command in (
            ("status", "--task", self.task),
            ("record", "--task", self.task, "--observation-file", self.observation),
            ("capture", "--task", self.task, "--result-file", self.source),
        ):
            with self.subTest(command=command[0]):
                error = self.cli(*command, expected=2)
                self.assertEqual(error["error"], error_code)
                self.assertEqual(self.snapshot(), before)

    def test_unreadable_or_truncated_log_never_becomes_an_empty_log(self):
        log = self.task / "observations.json"
        for content in (b"", b"[", b"\xff", None):
            with self.subTest(content=content):
                if content is None:
                    log.unlink()
                else:
                    log.write_bytes(content)
                self.assert_blocked_and_preserved("invalid_record")

    def test_semantically_damaged_log_cannot_be_read_appended_or_captured(self):
        log = self.task / "observations.json"
        original = json.loads(log.read_text(encoding="utf-8"))
        cases = {}
        for name, field, value in (
            ("wrong request", "request_id", str(uuid.uuid4())),
            ("missing request", "request_id", None),
            ("empty evidence", "evidence", "  "),
            ("unhashable event", "event", []),
            ("invalid binding", "conversation_url", 42),
            ("invalid details", "details", []),
        ):
            damaged = copy.deepcopy(original)
            damaged[0]["observation"][field] = value
            cases[name] = damaged
        for name, field, value in (
            ("out of order", "sequence", 2),
            ("boolean sequence", "sequence", True),
            ("missing timestamp", "recorded_at", None),
        ):
            damaged = copy.deepcopy(original)
            damaged[0][field] = value
            cases[name] = damaged
        cases["duplicate sequence"] = original + original
        cases["non object entry"] = [None]
        for name, damaged in cases.items():
            with self.subTest(damage=name):
                log.write_text(json.dumps(damaged), encoding="utf-8")
                self.assert_blocked_and_preserved("invalid_record")

    def test_damaged_task_identity_is_a_structured_error_and_preserves_files(self):
        manifest = self.task / "task.json"
        original = json.loads(manifest.read_text(encoding="utf-8"))
        cases = [b"{", b"\xff", b"[]"]
        for value in (None, 123, [], "not-a-uuid"):
            damaged = dict(original, request_id=value)
            cases.append(json.dumps(damaged).encode("utf-8"))
        missing = dict(original)
        del missing["request_id"]
        cases.append(json.dumps(missing).encode("utf-8"))
        for content in cases:
            with self.subTest(content=content[:80]):
                manifest.write_bytes(content)
                self.assert_blocked_and_preserved("invalid_task")


if __name__ == "__main__":
    unittest.main()
