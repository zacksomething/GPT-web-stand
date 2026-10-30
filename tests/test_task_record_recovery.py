"""POSIX process-crash tests for local records, never browser recovery.

Child-process checkpoints surround real flock/replace operations. Each test
kills or releases a child only after a pipe handshake, so no scheduling sleeps
or production fault-injection hooks are needed. SIGKILL tests process failure,
not a machine power loss or filesystem/device durability guarantee.
"""

import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "skills/web-stand-in/scripts/task_record.py"
TIMEOUT = 15

# Patching happens only inside the disposable test child. The script still
# uses real files, real flock locks and real atomic replacements.
CHILD = r'''
import importlib.util
from pathlib import Path
import sys

script, mode, filename, *arguments = sys.argv[1:]
spec = importlib.util.spec_from_file_location("task_record", script)
recorder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recorder)

def checkpoint(label):
    print(label, flush=True)
    if sys.stdin.buffer.read(1) != b"x":
        raise RuntimeError("Test controller closed the checkpoint pipe")

if mode == "hold_lock":
    with recorder.task_lock(Path(arguments[0])):
        checkpoint("locked")
    sys.exit(0)

if mode in {"before_replace", "after_replace"}:
    original_replace = recorder.os.replace
    def replace(source, destination):
        selected = Path(destination).name == filename
        if selected and mode == "before_replace":
            checkpoint("before_replace")
        original_replace(source, destination)
        if selected and mode == "after_replace":
            checkpoint("after_replace")
    recorder.os.replace = replace

if mode in {"contended_lock", "lock_gate"}:
    original_flock = recorder.fcntl.flock
    def flock(fd, operation):
        if operation == recorder.fcntl.LOCK_EX:
            if mode == "lock_gate":
                checkpoint("lock_gate")
            else:
                try:
                    original_flock(fd, operation | recorder.fcntl.LOCK_NB)
                except BlockingIOError:
                    print("blocked", flush=True)
                else:
                    print("unexpectedly_uncontended", flush=True)
        return original_flock(fd, operation)
    recorder.fcntl.flock = flock

sys.argv = [script, *arguments]
sys.exit(recorder.main())
'''


@unittest.skipUnless(os.name == "posix", "The recorder requires POSIX flock")
class TaskRecordRecoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="web-stand-in-recovery-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.prompt = self.root / "问题.txt"
        self.prompt.write_text("Review this synthetic test input.\n", encoding="utf-8")

    def cli(self, *arguments, expected=0):
        completed = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *map(str, arguments)],
            text=True, capture_output=True, timeout=TIMEOUT, check=False,
        )
        self.assertEqual(completed.returncode, expected, completed.stderr or completed.stdout)
        return json.loads(completed.stdout if expected == 0 else completed.stderr)

    def create(self):
        return self.cli("init", "--root", self.root / "tasks", "--prompt-file", self.prompt)

    def observation(self, task, event="send_intent", name="observation.json", **extra):
        path = self.root / name
        path.write_text(json.dumps({
            "event": event, "request_id": task["request_id"],
            "evidence": "Synthetic local test evidence.", **extra,
        }), encoding="utf-8")
        return path

    def child(self, mode, filename, *arguments):
        process = subprocess.Popen(
            [sys.executable, "-B", "-u", "-c", CHILD, str(SCRIPT), mode, filename,
             *map(str, arguments)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.addCleanup(self.reap, process)
        return process

    @staticmethod
    def reap(process):
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=TIMEOUT)

    def handshake(self, process, expected):
        # Read one byte at a time: TextIO buffering could otherwise hide a later
        # line from select(), particularly when the child reports an error.
        line = bytearray()
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while not line.endswith(b"\n"):
                self.assertTrue(selector.select(TIMEOUT), "Child checkpoint timed out")
                chunk = os.read(process.stdout.fileno(), 1)
                self.assertTrue(chunk, "Child exited before checkpoint: " + repr(bytes(line)))
                line.extend(chunk)
        self.assertEqual(line.decode().strip(), expected)

    def kill_at_checkpoint(self, process, expected):
        self.handshake(process, expected)
        process.kill()
        stdout, stderr = process.communicate(timeout=TIMEOUT)
        self.assertEqual(process.returncode, -signal.SIGKILL, stderr.decode())
        # The helper never acknowledged success to its caller before death.
        self.assertEqual(stdout, b"")
        self.assertEqual(stderr, b"")

    def test_flock_blocks_writer_and_is_released_when_holder_is_killed(self):
        task = self.create()
        directory = Path(task["task"])
        holder = self.child("hold_lock", "", directory)
        self.handshake(holder, "locked")
        writer = self.child("contended_lock", "", "record", "--task", directory,
                            "--observation-file", self.observation(task))
        # A real LOCK_NB probe proves contention before entering blocking flock.
        self.handshake(writer, "blocked")
        self.assertEqual(json.loads((directory / "observations.json").read_text()), [])
        holder.kill()
        holder.communicate(timeout=TIMEOUT)
        self.assertEqual(holder.returncode, -signal.SIGKILL)
        stdout, stderr = writer.communicate(timeout=TIMEOUT)
        self.assertEqual(writer.returncode, 0, stderr.decode())
        self.assertTrue(json.loads(stdout)["send_intent_created"])
        self.assertEqual(self.cli("status", "--task", directory)["observation_count"], 1)

    def test_concurrent_appenders_keep_all_events_and_contiguous_sequences(self):
        task = self.create()
        writers = []
        for index in range(6):
            observation = self.observation(
                task, event="note", name="note-{}.json".format(index),
                evidence="Writer {}".format(index),
            )
            process = self.child("lock_gate", "", "record", "--task", task["task"],
                                 "--observation-file", observation)
            self.handshake(process, "lock_gate")
            writers.append(process)
        for process in writers:
            process.stdin.write(b"x")
            process.stdin.flush()
        for process in writers:
            stdout, stderr = process.communicate(timeout=TIMEOUT)
            self.assertEqual(process.returncode, 0, stderr.decode())
            self.assertEqual(json.loads(stdout)["recorded_event"], "note")
        records = json.loads((Path(task["task"]) / "observations.json").read_text())
        self.assertEqual([entry["sequence"] for entry in records], list(range(1, 7)))
        self.assertEqual({entry["observation"]["evidence"] for entry in records},
                         {"Writer {}".format(index) for index in range(6)})

    def test_kill_before_send_log_replace_preserves_old_log_and_ignores_temporary(self):
        task = self.create()
        directory = Path(task["task"])
        log = directory / "observations.json"
        before = log.read_bytes()
        observation = self.observation(task)
        writer = self.child("before_replace", "observations.json", "record", "--task", directory,
                            "--observation-file", observation)
        self.kill_at_checkpoint(writer, "before_replace")
        self.assertEqual(log.read_bytes(), before)
        self.assertEqual(len(list(directory.glob(".write-*"))), 1)
        state = self.cli("status", "--task", directory)
        self.assertEqual(state["execution_state"], "prepared")
        self.assertEqual(state["request_id"], task["request_id"])
        self.assertEqual(state["observation_count"], 0)
        # No reservation was committed or acknowledged; stale temp bytes are
        # never interpreted as records. The restarted helper can reserve once.
        result = self.cli("record", "--task", directory, "--observation-file", observation)
        self.assertTrue(result["send_intent_created"])

    def test_kill_after_send_log_replace_restores_binding_and_rejects_resend(self):
        task = self.create()
        directory = Path(task["task"])
        binding = {"conversation_url": "https://chatgpt.com/c/synthetic-test",
                   "remote_turn_id": "synthetic-turn", "model_observed": "6 Pro"}
        observation = self.observation(task, **binding)
        writer = self.child("after_replace", "observations.json", "record", "--task", directory,
                            "--observation-file", observation)
        self.kill_at_checkpoint(writer, "after_replace")
        log = directory / "observations.json"
        before = log.read_bytes()
        self.assertEqual(len(json.loads(before)), 1)
        state = self.cli("status", "--task", directory)
        self.assertEqual(state["execution_state"], "submission_unknown")
        self.assertEqual(state["observation_count"], 1)
        for field in ("task_id", "packet_id", "request_id", "logical_task_id"):
            self.assertEqual(state[field], task[field])
        for field, value in binding.items():
            self.assertEqual(state[field], value)
        error = self.cli("record", "--task", directory, "--observation-file", observation, expected=2)
        self.assertEqual(error["error"], "duplicate_send_intent")
        self.assertEqual(log.read_bytes(), before)
        # A fresh process can append later caller evidence without erasing the
        # ambiguous reservation or inventing remote completion.
        later = self.observation(task, event="running_observed")
        self.cli("record", "--task", directory, "--observation-file", later)
        self.assertEqual(self.cli("status", "--task", directory)["execution_state"], "running")

    def test_kill_before_result_replace_leaves_no_partial_result(self):
        task = self.create()
        directory = Path(task["task"])
        source = self.root / "answer.txt"
        original = ("完整的离线测试结果\n" * 4096).encode("utf-8")
        source.write_bytes(original)
        writer = self.child("before_replace", "result.txt", "capture", "--task", directory,
                            "--result-file", source)
        self.kill_at_checkpoint(writer, "before_replace")
        self.assertFalse((directory / "result.txt").exists())
        self.assertEqual(len(list(directory.glob(".write-*"))), 1)
        self.assertEqual(self.cli("status", "--task", directory)["result_state"], "absent")
        result = self.cli("capture", "--task", directory, "--result-file", source)
        self.assertFalse(result["already_captured"])
        self.assertEqual((directory / "result.txt").read_bytes(), original)

    def test_kill_after_result_replace_allows_identical_replay_and_rejects_conflict(self):
        task = self.create()
        directory = Path(task["task"])
        source = self.root / "answer.txt"
        original = ("Complete synthetic response.\n" * 4096).encode("utf-8")
        source.write_bytes(original)
        writer = self.child("after_replace", "result.txt", "capture", "--task", directory,
                            "--result-file", source)
        self.kill_at_checkpoint(writer, "after_replace")
        destination = directory / "result.txt"
        self.assertEqual(destination.read_bytes(), original)
        state = self.cli("status", "--task", directory)
        self.assertEqual(state["execution_state"], "prepared")
        self.assertEqual(state["result_state"], "captured")
        self.assertTrue(self.cli("capture", "--task", directory,
                                 "--result-file", source)["already_captured"])
        source.write_text("A conflicting response", encoding="utf-8")
        error = self.cli("capture", "--task", directory, "--result-file", source, expected=2)
        self.assertEqual(error["error"], "result_conflict")
        self.assertEqual(destination.read_bytes(), original)
        error = self.cli("record", "--task", directory,
                         "--observation-file", self.observation(task), expected=2)
        self.assertEqual(error["error"], "duplicate_send_intent")

    def test_init_killed_before_manifest_publication_is_not_a_usable_task(self):
        tasks = self.root / "tasks"
        writer = self.child("before_replace", "task.json", "init", "--root", tasks,
                            "--prompt-file", self.prompt)
        self.kill_at_checkpoint(writer, "before_replace")
        directories = list(tasks.iterdir())
        self.assertEqual(len(directories), 1)
        interrupted = directories[0]
        self.assertFalse((interrupted / "task.json").exists())
        self.cli("status", "--task", interrupted, expected=2)
        error = self.cli("record", "--task", interrupted,
                         "--observation-file", self.prompt, expected=2)
        self.assertIn("error", error)
        # Initialization is not resumed from uncommitted metadata. An explicit
        # fresh init leaves the interrupted directory intact for inspection.
        task = self.create()
        self.assertNotEqual(Path(task["task"]), interrupted)
        self.assertTrue(interrupted.exists())
        self.assertEqual(self.cli("status", "--task", task["task"])["execution_state"], "prepared")


if __name__ == "__main__":
    unittest.main()
