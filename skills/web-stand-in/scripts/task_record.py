#!/usr/bin/env python3
"""Local records for one ChatGPT web request; never operates a browser.

All observations are caller-supplied evidence, not independently verified facts.
send_intent reserves one attempt before clicking Send. Its successful return is
a duplicate-send guard, not authorization. After a crash, inspect the existing
conversation; do not reserve or send again with this request.
Requires Python 3.9+ on macOS/Linux (fcntl provides per-task process locking).
"""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import uuid


DEFAULT_MAX_RESULT_BYTES = 2_000_000
MAX_OBSERVATION_BYTES = 32_768
EVENT_STATES = {
    "send_intent": "submission_unknown",
    "submission_observed": "submitted",
    "running_observed": "running",
    "completion_observed": "completed",
    "failure_observed": "failed",
    "cancellation_observed": "cancelled",
}
EVENTS = set(EVENT_STATES) | {"blocked_observed", "cancel_requested", "note"}
OBSERVATION_FIELDS = {
    "event", "request_id", "evidence", "details", "conversation_url",
    "remote_turn_id", "model_observed",
}


class RecordError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def atomic_write(task, destination, data):
    """Destination is always chosen by this script, never by result content."""
    fd, temporary = tempfile.mkstemp(prefix=".write-", dir=task)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        directory = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_text_bytes(path, max_bytes=None):
    if not path.is_file():
        raise RecordError("not_a_file", "Expected a regular file: " + str(path))
    with path.open("rb") as stream:
        data = stream.read() if max_bytes is None else stream.read(max_bytes + 1)
    if max_bytes is not None and len(data) > max_bytes:
        raise RecordError("size_limit", "File exceeds the configured byte limit.")
    try:
        decoded = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise RecordError("invalid_utf8", "Expected UTF-8 text.") from error
    if not decoded.strip():
        raise RecordError("empty_text", "Text must contain non-whitespace content.")
    return data


def load_task(directory):
    task = Path(directory).expanduser().resolve()
    record = task / "task.json"
    if record.is_symlink():
        raise RecordError("invalid_task", "task.json must not be a symlink.")
    metadata = json.loads(record.read_text(encoding="utf-8"))
    if not isinstance(metadata, dict) or metadata.get("schema_version") != 1:
        raise RecordError("invalid_task", "Unsupported task record.")
    for field in ("task_id", "packet_id", "request_id"):
        uuid.UUID(metadata[field])
    if not isinstance(metadata.get("materials"), list):
        raise RecordError("invalid_task", "Invalid material manifest.")
    return task, metadata


@contextmanager
def task_lock(task):
    lock = task / ".record.lock"
    # Do not follow a substituted lock path outside the task directory.
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "a+b") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def read_observations(task):
    path = task / "observations.json"
    if path.is_symlink():
        raise RecordError("invalid_record", "Observation log must not be a symlink.")
    records = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, list) or any(
        not isinstance(item, dict)
        or not isinstance(item.get("observation"), dict)
        or item["observation"].get("event") not in EVENTS
        for item in records
    ):
        raise RecordError("invalid_record", "Invalid observation log; refusing to replace it.")
    return records


def init_task(args):
    root = Path(args.root).expanduser().resolve()
    parent = load_task(args.parent_task)[1] if args.parent_task else None
    prompt_source = Path(args.prompt_file).expanduser().resolve()
    prompt = read_text_bytes(prompt_source)
    material_sources = [Path(item).expanduser().resolve() for item in args.material]
    for source in material_sources:
        if not source.is_file():
            raise RecordError("not_a_file", "Expected a regular material file: " + str(source))
    root.mkdir(parents=True, exist_ok=True)
    task_id, packet_id, request_id = (str(uuid.uuid4()) for _ in range(3))
    task = root / task_id
    task.mkdir(mode=0o700)
    try:
        atomic_write(task, task / "prompt.txt", prompt)
        materials = []
        if material_sources:
            (task / "materials").mkdir(mode=0o700)
        for index, source in enumerate(material_sources, start=1):
            data = source.read_bytes()
            # The ordinal disambiguates identical basenames from different folders.
            relative = "materials/{:04d}-{}".format(index, source.name)
            atomic_write(task, task / relative, data)
            materials.append({"source_path": str(source), "frozen_path": relative,
                              "sha256": digest(data), "bytes": len(data)})
        metadata = {
            "schema_version": 1, "task_id": task_id, "packet_id": packet_id,
            "request_id": request_id, "created_at": now(),
            "logical_task_id": parent.get("logical_task_id", parent["task_id"]) if parent else task_id,
            "parent_task_id": parent["task_id"] if parent else None,
            "followup_index": parent.get("followup_index", 0) + 1 if parent else 0,
            "required_model": "GPT-6 Pro", "route": "chatgpt-web",
            "prompt": {"source_path": str(prompt_source), "frozen_path": "prompt.txt",
                       "sha256": digest(prompt), "bytes": len(prompt)},
            "materials": materials,
        }
        atomic_write(task, task / "observations.json", json_bytes([]))
        # Publish metadata last: no partially initialized task is usable.
        atomic_write(task, task / "task.json", json_bytes(metadata))
    except Exception:
        shutil.rmtree(task)
        raise
    return {"task": str(task), "task_id": task_id, "packet_id": packet_id,
            "request_id": request_id, "prompt_path": str(task / "prompt.txt"),
            "logical_task_id": metadata["logical_task_id"], "parent_task_id": metadata["parent_task_id"],
            "followup_index": metadata["followup_index"],
            "manifest_path": str(task / "task.json"),
            "observations_path": str(task / "observations.json"),
            "required_model": metadata["required_model"], "route": metadata["route"]}


def record_observation(args):
    task, metadata = load_task(args.task)
    raw = read_text_bytes(Path(args.observation_file).expanduser().resolve(), MAX_OBSERVATION_BYTES)
    observation = json.loads(raw)
    if not isinstance(observation, dict) or set(observation) - OBSERVATION_FIELDS:
        raise RecordError("invalid_observation", "Observation must be an object using documented fields.")
    event = observation.get("event")
    if event not in EVENTS:
        raise RecordError("invalid_observation", "Unknown observation event.")
    if observation.get("request_id") != metadata["request_id"]:
        raise RecordError("request_mismatch", "Observation does not belong to this request.")
    if not isinstance(observation.get("evidence"), str) or not observation["evidence"].strip():
        raise RecordError("invalid_observation", "A nonempty evidence description is required.")
    for field in ("conversation_url", "remote_turn_id", "model_observed"):
        if field in observation and not isinstance(observation[field], str):
            raise RecordError("invalid_observation", field + " must be a string.")
    if "details" in observation and not isinstance(observation["details"], dict):
        raise RecordError("invalid_observation", "details must be an object.")
    with task_lock(task):
        records = read_observations(task)
        prior_submission = any(item["observation"]["event"] in {
            "send_intent", "submission_observed", "running_observed", "completion_observed"
        } for item in records)
        if event == "send_intent" and (prior_submission or (task / "result.txt").exists()):
            raise RecordError("duplicate_send_intent", "Existing submission evidence or reservation: inspect the same conversation; do not send again.")
        sequence = len(records) + 1
        records.append({"sequence": sequence, "recorded_at": now(), "observation": observation})
        atomic_write(task, task / "observations.json", json_bytes(records))
    return {"task": str(task), "request_id": metadata["request_id"], "sequence": sequence,
            "recorded_event": event, "send_intent_created": event == "send_intent"}


def capture_result(args):
    if args.max_bytes <= 0:
        raise RecordError("invalid_limit", "max-bytes must be positive.")
    task, metadata = load_task(args.task)
    data = read_text_bytes(Path(args.result_file).expanduser().resolve(), args.max_bytes)
    destination = task / "result.txt"
    with task_lock(task):
        read_observations(task)  # Refuse to silently work around a damaged record.
        if destination.is_symlink():
            raise RecordError("invalid_result_path", "Stored result must not be a symlink.")
        existed = destination.exists()
        if existed and destination.read_bytes() != data:
            raise RecordError("result_conflict", "Different original text is already stored; it was not overwritten.")
        if not existed:
            atomic_write(task, destination, data)
    return {"task": str(task), "request_id": metadata["request_id"],
            "result_path": str(destination), "sha256": digest(data), "bytes": len(data),
            "already_captured": existed, "result_state": "captured"}


def file_match(path, expected):
    try:
        return "unchanged" if digest(path.read_bytes()) == expected else "changed"
    except FileNotFoundError:
        return "missing"
    except OSError:
        return "unreadable"


def verify_materials(args):
    task, metadata = load_task(args.task)
    results = []
    for entry in [metadata["prompt"]] + metadata["materials"]:
        relative = Path(entry["frozen_path"])
        frozen = task / relative
        if relative.is_absolute() or ".." in relative.parts or frozen.is_symlink():
            raise RecordError("invalid_manifest", "Frozen paths must stay inside the task.")
        if not frozen.resolve().is_relative_to(task):
            raise RecordError("invalid_manifest", "Frozen paths must stay inside the task.")
        results.append({"source_path": entry["source_path"], "frozen_path": str(frozen),
                        "source_status": file_match(Path(entry["source_path"]), entry["sha256"]),
                        "frozen_status": file_match(frozen, entry["sha256"])})
    unchanged = all(item["source_status"] == "unchanged" and item["frozen_status"] == "unchanged"
                    for item in results)
    return {"task": str(task), "all_unchanged": unchanged, "files": results}


def status(args):
    task, metadata = load_task(args.task)
    with task_lock(task):
        records = read_observations(task)
        state = "prepared"
        for entry in records:
            state = EVENT_STATES.get(entry["observation"]["event"], state)
        result = task / "result.txt"
        if result.is_symlink():
            raise RecordError("invalid_result_path", "Stored result must not be a symlink.")
        captured = result.is_file()
        last_event = records[-1]["observation"]["event"] if records else None
        binding = {}
        for entry in records:
            for field in ("conversation_url", "remote_turn_id", "model_observed"):
                if field in entry["observation"]:
                    binding[field] = entry["observation"][field]
    return {"task": str(task), "task_id": metadata["task_id"],
            "packet_id": metadata["packet_id"], "request_id": metadata["request_id"],
            "logical_task_id": metadata.get("logical_task_id", metadata["task_id"]),
            "parent_task_id": metadata.get("parent_task_id"),
            "followup_index": metadata.get("followup_index", 0),
            "required_model": metadata["required_model"], "route": metadata["route"],
            "execution_state": state, "state_basis": "caller_recorded_observations",
            "result_state": "captured" if captured else "absent",
            "result_path": str(result) if captured else None,
            "manifest_path": str(task / "task.json"), "observation_count": len(records),
            "observations_path": str(task / "observations.json"),
            "last_event": last_event, **binding}


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Freeze a prompt and explicit material files.")
    init.add_argument("--root", required=True)
    init.add_argument("--prompt-file", required=True)
    init.add_argument("--material", action="append", default=[])
    init.add_argument("--parent-task", help="Link an intentional follow-up; metadata only, never permission to resend.")
    init.set_defaults(handler=init_task)
    record = commands.add_parser("record", help="Append one caller-supplied observation.")
    record.add_argument("--task", required=True)
    record.add_argument("--observation-file", required=True)
    record.set_defaults(handler=record_observation)
    capture = commands.add_parser("capture", help="Preserve raw UTF-8 result text, without executing it.")
    capture.add_argument("--task", required=True)
    capture.add_argument("--result-file", required=True)
    capture.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_RESULT_BYTES)
    capture.set_defaults(handler=capture_result)
    for name, handler in (("verify-materials", verify_materials), ("status", status)):
        command = commands.add_parser(name)
        command.add_argument("--task", required=True)
        command.set_defaults(handler=handler)
    return result


def main():
    args = parser().parse_args()
    try:
        output = args.handler(args)
    except (RecordError, OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"error": getattr(error, "code", "invalid_input"),
                          "message": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=False))
    return 1 if output.get("all_unchanged") is False else 0


if __name__ == "__main__":
    sys.exit(main())
