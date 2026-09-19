"""Behavior tests for the local task recorder; no browser or network access."""

import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid


SCRIPT = Path(__file__).resolve().parents[1] / "skills/web-stand-in/scripts/task_record.py"


class TaskRecordTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="web-stand-in-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.prompt = self.root / "问题.txt"
        self.prompt.write_text("Review the supplied evidence.\n", encoding="utf-8")

    def cli(self, *arguments, expected=0):
        completed = subprocess.run([sys.executable, str(SCRIPT), *map(str, arguments)],
                                   text=True, capture_output=True, check=False)
        self.assertEqual(completed.returncode, expected, completed.stderr or completed.stdout)
        return json.loads(completed.stdout if expected in (0, 1) else completed.stderr)

    def create(self, *materials):
        args = ["init", "--root", self.root / "tasks", "--prompt-file", self.prompt]
        for material in materials:
            args.extend(["--material", material])
        return self.cli(*args)

    def observation(self, task, event="send_intent", name="observation.json", **extra):
        path = self.root / name
        path.write_text(json.dumps({"event": event, "request_id": task["request_id"],
                                    "evidence": "Observed in the selected conversation.", **extra}),
                        encoding="utf-8")
        return path

    def test_snapshots_distinguish_same_names_and_detect_source_change(self):
        left, right = self.root / "a", self.root / "b"
        left.mkdir()
        right.mkdir()
        first, second = left / "材料 same.bin", right / "材料 same.bin"
        first.write_bytes(b"\x00first")
        second.write_bytes(b"second")
        task = self.create(first, second)
        directory = Path(task["task"])
        metadata = json.loads((directory / "task.json").read_text())
        ids = [task[key] for key in ("task_id", "packet_id", "request_id")]
        self.assertEqual(len(set(ids)), 3)
        for identifier in ids:
            uuid.UUID(identifier)
        self.assertEqual(metadata["required_model"], "GPT-6 Pro")
        self.assertEqual(metadata["route"], "chatgpt-web")
        self.assertEqual((directory / "prompt.txt").read_bytes(), self.prompt.read_bytes())
        snapshots = metadata["materials"]
        self.assertNotEqual(snapshots[0]["frozen_path"], snapshots[1]["frozen_path"])
        self.cli("verify-materials", "--task", directory)
        first.write_bytes(b"changed")
        second.unlink()
        verification = self.cli("verify-materials", "--task", directory, expected=1)
        self.assertEqual([item["source_status"] for item in verification["files"]],
                         ["unchanged", "changed", "missing"])
        self.assertTrue(all(item["frozen_status"] == "unchanged" for item in verification["files"]))
        self.assertEqual((directory / snapshots[0]["frozen_path"]).read_bytes(), b"\x00first")

    def test_empty_prompt_does_not_publish_a_task(self):
        self.prompt.write_text(" \n\t", encoding="utf-8")
        self.cli("init", "--root", self.root / "tasks", "--prompt-file", self.prompt, expected=2)
        self.assertFalse((self.root / "tasks").exists())

    def test_repeated_send_intent_is_rejected_and_log_is_not_overwritten(self):
        task = self.create()
        observation = self.observation(task)
        first = self.cli("record", "--task", task["task"], "--observation-file", observation)
        self.assertTrue(first["send_intent_created"])
        before = (Path(task["task"]) / "observations.json").read_bytes()
        error = self.cli("record", "--task", task["task"], "--observation-file", observation, expected=2)
        self.assertEqual(error["error"], "duplicate_send_intent")
        self.assertEqual((Path(task["task"]) / "observations.json").read_bytes(), before)
        state = self.cli("status", "--task", task["task"])
        self.assertEqual(state["execution_state"], "submission_unknown")

    def test_concurrent_send_reservations_allow_exactly_one_attempt(self):
        task = self.create()
        observation = self.observation(task)
        command = [sys.executable, str(SCRIPT), "record", "--task", task["task"],
                   "--observation-file", str(observation)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            calls = [pool.submit(subprocess.run, command, text=True, capture_output=True) for _ in range(2)]
            results = [call.result() for call in calls]
        self.assertEqual(sorted(item.returncode for item in results), [0, 2])
        log = json.loads((Path(task["task"]) / "observations.json").read_text())
        self.assertEqual(len(log), 1)

    def test_wrong_request_and_unknown_event_cannot_change_record(self):
        task = self.create()
        wrong = self.observation(task, request_id=str(uuid.uuid4()))
        error = self.cli("record", "--task", task["task"], "--observation-file", wrong, expected=2)
        self.assertEqual(error["error"], "request_mismatch")
        unsupported = self.observation(task, event="validated")
        self.cli("record", "--task", task["task"], "--observation-file", unsupported, expected=2)
        self.assertEqual(self.cli("status", "--task", task["task"])["observation_count"], 0)

    def test_capture_is_exact_idempotent_conflict_safe_and_does_not_execute(self):
        task = self.create()
        source = self.root / "returned.txt"
        unexpected = self.root / "must-not-exist"
        original = ('{"destination": "' + str(unexpected) + '", "command": "touch ' + str(unexpected) + '"}\n').encode()
        source.write_bytes(original)
        captured = self.cli("capture", "--task", task["task"], "--result-file", source)
        self.assertFalse(captured["already_captured"])
        self.assertEqual(Path(captured["result_path"]).read_bytes(), original)
        self.assertEqual(captured["sha256"], hashlib.sha256(original).hexdigest())
        self.assertFalse(unexpected.exists())
        self.assertTrue(self.cli("capture", "--task", task["task"], "--result-file", source)["already_captured"])
        source.write_text("different text", encoding="utf-8")
        error = self.cli("capture", "--task", task["task"], "--result-file", source, expected=2)
        self.assertEqual(error["error"], "result_conflict")
        self.assertEqual(Path(captured["result_path"]).read_bytes(), original)
        state = self.cli("status", "--task", task["task"])
        self.assertEqual(state["execution_state"], "prepared")
        self.assertEqual(state["result_state"], "captured")
        self.assertNotIn("validated", state.values())
        intent = self.observation(task)
        self.cli("record", "--task", task["task"], "--observation-file", intent, expected=2)

    def test_empty_and_oversized_result_are_not_saved(self):
        task = self.create()
        source = self.root / "returned.txt"
        for content, expected_error in ((b" \n", "empty_text"), (b"12345", "size_limit")):
            source.write_bytes(content)
            error = self.cli("capture", "--task", task["task"], "--result-file", source,
                             "--max-bytes", 4, expected=2)
            self.assertEqual(error["error"], expected_error)
            self.assertFalse((Path(task["task"]) / "result.txt").exists())
        source.write_bytes(b"1234")
        self.cli("capture", "--task", task["task"], "--result-file", source, "--max-bytes", 4)

    def test_observations_append_and_capture_does_not_imply_completion(self):
        task = self.create()
        directory = Path(task["task"])
        for event in ("send_intent", "submission_observed", "running_observed"):
            observation = self.observation(task, event=event)
            self.cli("record", "--task", directory, "--observation-file", observation)
        source = self.root / "partial.txt"
        source.write_text("Partial response", encoding="utf-8")
        self.cli("capture", "--task", directory, "--result-file", source)
        self.assertEqual(self.cli("status", "--task", directory)["execution_state"], "running")
        completion = self.observation(task, event="completion_observed", conversation_url="https://chatgpt.com/c/example")
        self.cli("record", "--task", directory, "--observation-file", completion)
        log = json.loads((directory / "observations.json").read_text())
        self.assertEqual([item["sequence"] for item in log], [1, 2, 3, 4])
        self.assertEqual(self.cli("status", "--task", directory)["execution_state"], "completed")
        self.assertEqual(self.cli("status", "--task", directory)["conversation_url"],
                         "https://chatgpt.com/c/example")
        self.assertEqual(list(directory.glob(".write-*")), [])

    def test_follow_up_links_logical_task_but_has_separate_request_and_result(self):
        parent = self.create()
        parent_prompt = Path(parent["prompt_path"]).read_bytes()
        self.prompt.write_text("Check one remaining assumption.\n", encoding="utf-8")
        child = self.cli("init", "--root", self.root / "tasks", "--prompt-file", self.prompt,
                         "--parent-task", parent["task"])
        self.assertEqual(parent["logical_task_id"], parent["task_id"])
        self.assertEqual(parent["followup_index"], 0)
        self.assertEqual(child["logical_task_id"], parent["logical_task_id"])
        self.assertEqual(child["parent_task_id"], parent["task_id"])
        self.assertEqual(child["followup_index"], 1)
        self.assertNotEqual(child["task_id"], parent["task_id"])
        self.assertNotEqual(child["packet_id"], parent["packet_id"])
        self.assertNotEqual(child["request_id"], parent["request_id"])
        self.assertEqual(Path(parent["prompt_path"]).read_bytes(), parent_prompt)
        grandchild = self.cli("init", "--root", self.root / "tasks", "--prompt-file", self.prompt,
                              "--parent-task", child["task"])
        self.assertEqual(grandchild["logical_task_id"], parent["task_id"])
        self.assertEqual(grandchild["followup_index"], 2)
        self.assertEqual(self.cli("status", "--task", grandchild["task"])["followup_index"], 2)
        metadata = json.loads(Path(grandchild["manifest_path"]).read_text())
        self.assertEqual(metadata["followup_index"], 2)
        self.assertEqual(self.cli("status", "--task", child["task"])["observation_count"], 0)

    def test_older_record_without_followup_index_defaults_to_zero(self):
        parent = self.create()
        manifest = Path(parent["manifest_path"])
        metadata = json.loads(manifest.read_text())
        metadata.pop("followup_index")
        manifest.write_text(json.dumps(metadata), encoding="utf-8")
        self.assertEqual(self.cli("status", "--task", parent["task"])["followup_index"], 0)
        child = self.cli("init", "--root", self.root / "tasks", "--prompt-file", self.prompt,
                         "--parent-task", parent["task"])
        self.assertEqual(child["followup_index"], 1)
        self.assertEqual(child["logical_task_id"], parent["task_id"])

    def test_damaged_log_is_preserved(self):
        task = self.create()
        log = Path(task["task"]) / "observations.json"
        damaged = b'{"not": "a log"}'
        log.write_bytes(damaged)
        observation = self.observation(task)
        self.cli("record", "--task", task["task"], "--observation-file", observation, expected=2)
        self.assertEqual(log.read_bytes(), damaged)


if __name__ == "__main__":
    unittest.main()
