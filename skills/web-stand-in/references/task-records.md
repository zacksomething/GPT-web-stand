# Local records and helper

`scripts/task_record.py` uses the Python 3.9+ standard library on macOS/Linux. It does not contact ChatGPT or operate a browser. Resolve the script from the skill's actual installation path, not a hardcoded personal directory. Runtime records belong in the current task's output directory.

## Freeze one request

Prepare a UTF-8 prompt and choose explicit files. Optional files are copied locally for versioning; `--material` does not upload them.

```sh
python3 /path/to/web-stand-in/scripts/task_record.py init \
  --root /path/to/project/.web-stand-in \
  --prompt-file /path/to/prepared-prompt.md \
  --material /path/to/selected-evidence.txt
```

Omit `--material` when all needed evidence is inline. The JSON response gives the new task directory, request/packet/task IDs and snapshot paths. Keep those exact returned identities. Avoid putting credentials, authentication directories, unrelated data or large unselected trees in a packet.

For a justified follow-up, run `init` with a new delta prompt and `--parent-task <previous-request-directory>`. It creates a new request directory and carries `logical_task_id` and `parent_task_id`; `followup_index` starts at 0 and increases by one from its parent. Link each follow-up to the most recent request and check the task's budget before sending. Each request has its own prompt, send reservation and raw result. Continue the existing ChatGPT chat. Never use this option to replace an uncertain submission.

## Record observed facts

Write a small JSON file locally and pass it with `--observation-file`. Example before sending:

```json
{
  "event": "send_intent",
  "request_id": "ID returned by init",
  "evidence": "Composer matches the frozen prompt; no pending attachments; model selector shows 6 Pro.",
  "model_observed": "6 Pro",
  "conversation_url": "https://chatgpt.com/"
}
```

```sh
python3 /path/to/web-stand-in/scripts/task_record.py record \
  --task /path/to/request-directory --observation-file /path/to/observation.json
```

Only the first successful `send_intent` returns `send_intent_created: true`. Subsequent attempts return an error, including concurrent attempts. This is a local duplicate-send guard, not authorization or a remote exactly-once guarantee. If a crash occurs after the reservation but before the click, preserve ambiguity and inspect the chat; do not erase the reservation to retry.

Other events are `submission_observed`, `running_observed`, `completion_observed`, `failure_observed`, `cancellation_observed`, `blocked_observed`, `cancel_requested`, and `note`. Each requires the request ID and nonempty evidence. Use optional `details` for compact facts, and `conversation_url`, `remote_turn_id`, or `model_observed` only when actually observed. The helper stores caller reports; it does not independently prove them. Never record an event solely to reach a desired status.

## Capture and inspect

Save the collected original answer to a local UTF-8 file, then:

```sh
python3 /path/to/web-stand-in/scripts/task_record.py capture \
  --task /path/to/request-directory --result-file /path/to/collected-answer.txt
python3 /path/to/web-stand-in/scripts/task_record.py status \
  --task /path/to/request-directory
python3 /path/to/web-stand-in/scripts/task_record.py verify-materials \
  --task /path/to/request-directory
```

`capture` rejects empty or oversized data. Its default cap is 2,000,000 bytes; use `--max-bytes` when the task justifies a different limit. Re-capturing identical content is idempotent; different content cannot overwrite the original. `capture` means bytes were stored, not that the remote response completed or passed review. Store partial extracts separately and capture the final original once completeness is established.

`verify-materials` detects changed or missing source files; exit code 1 means review the change before adoption. Normal commands use exit 0; invalid operations use exit 2. A corruption error must be inspected, not bypassed by deleting evidence.

Keep `adoption.md` beside the request record with: accepted/rejected/deferred conclusions and reasons, decisive sources checked, material-version changes, actual local test results, actions taken, and unresolved limits. Store a concise `summary.md` when the answer is long. These are local judgments and remain separate from the raw answer and browser observations.

Task directories contain local paths and potentially private materials. They are not automatically suitable to upload or publish. Do not upload the manifest or diagnostic output merely because it exists.
