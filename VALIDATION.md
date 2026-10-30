# Validation scope

This file separates local record tests from browser and cloud execution evidence.
The Linux results below were obtained on 2026-10-30 (Asia/Taipei), starting from
repository commit `74cffac62d123349592a26d3e3e307a1fc47bb73` plus this change.
No private paths, prompts, credentials or real conversation identifiers are included.

## Three independent layers

| Layer | Evidence | What it does not establish |
|---|---|---|
| Local record helper on Linux | All 21 offline tests passed on Ubuntu 24.04.3 LTS, x86_64, Python 3.12.14, Linux kernel 6.18.57 | Browser control, remote completion, machine power-loss durability, or compatibility with every filesystem |
| Browser host restores the original conversation | Two historical macOS live text consultations; no host-exit/reopen recovery test | Preserved IDs and URLs do not prove that login, model selection, conversation binding or complete-answer collection can be restored |
| Cloud execution continues after the Mac is off | Not tested; no independent executor or background worker in this repository | This change made no ECS connection attempt and provides no evidence of cloud network reachability, scheduling, automatic wake-up or continued browser work |

## Local test coverage

The original 11 tests passed unchanged on Linux before adding new tests. Existing
coverage was retained rather than reimplemented. The added suites target actual
gaps: process death at publication boundaries and semantic corruption of stored
records.

| Scenario | Existing coverage | Added coverage |
|---|---|---|
| Duplicate sending | Sequential refusal and two concurrent send reservations | Kill after log replacement but before successful CLI response; a fresh process retains `submission_unknown`, identities and binding, and refuses another reservation |
| File locks | Concurrent reservations allow one winner | A real nonblocking `flock` probe proves contention; SIGKILL releases the holder's lock; six gated appenders preserve all events with contiguous sequence numbers |
| Atomic writes | Successful writes leave no temporary files | SIGKILL before/after `os.replace` for the log and result; old committed data or the complete new file remains; abandoned temporary files are ignored |
| Initialization | Empty prompt does not publish a task | Kill before final manifest publication; the incomplete directory cannot be used and is preserved |
| State after process restart | Ordinary CLI calls already use separate processes | Fresh CLI processes read committed request IDs, conversation metadata, execution/result states and append later observations after a killed process |
| Result capture | Exact bytes, idempotence, conflict protection, size checks, no execution | Kill before replacement leaves no result; kill after replacement permits identical replay and rejects conflicting bytes and another send reservation |
| Record corruption | A non-list log is preserved | Missing/truncated/invalid UTF-8 logs; wrong request IDs, duplicate/out-of-order/non-integer sequences, invalid evidence/binding/details; malformed manifests/UUID types. `status`, `record`, and `capture` fail without changing evidence |
| Materials and follow-ups | Frozen snapshots, changed/missing sources, distinct request IDs and follow-up counting, older records without `followup_index` | Existing tests continue to pass unchanged |

The corruption tests exposed two implementation gaps: persisted entries were not
validated against their request identity/sequence and observation field rules;
non-string UUIDs could raise an uncaught Python exception. The helper now reuses
observation validation when reading logs, validates sequence metadata, and returns
structured `invalid_record` / `invalid_task` errors while preserving files.

These checks are not an authenticated audit log. Structurally valid substitutions
or deletion of whole entries can remain undetectable. No automatic repair,
reservation reset, or replay of browser actions is provided.

## Reproduce and automate

From the repository root, without a network connection or ChatGPT account:

```sh
python3 -B -m unittest discover -s tests -p 'test_task_record*.py' -v
```

- `tests/test_task_record.py`: 11 existing behavior tests.
- `tests/test_task_record_corruption.py`: 3 tests, with multiple corruption cases
  exercised across read and write commands.
- `tests/test_task_record_recovery.py`: 7 POSIX locking/process-crash tests.

The crash tests use disposable subprocesses, real files/locks/replacements, pipe
handshakes, bounded timeouts and cleanup. Fault injection is confined to test
children; there are no production test hooks or browser operations. The
post-replacement checkpoint deliberately kills the process before it can return
success (and before directory `fsync`); it tests process failure on a running
kernel, not reboot or power failure. Filesystem/device failures, NFS and other
network filesystems, and Windows are outside this result.

`.github/workflows/local-records.yml` runs the same command on `ubuntu-latest`
with Python 3.9 and 3.13 on push, pull request and manual dispatch. It records the
actual runner/runtime, uses read-only repository permissions, and requires no
secrets or browser account. Configuration alone is not a passed Actions run;
consult the run associated with the reviewed commit for matrix results. The
local Python 3.12 result does not claim the matrix has already passed.

## Historical browser validation (2026-09-19)

The skill was validated in one macOS environment:

- The official Skill format validator accepted the metadata and structure.
- Eleven local behavior tests passed, including a rerun from a fresh temporary
  repository copy, independent of the original research folder.
- Two live text consultations completed in ChatGPT web using the visible 6 Pro
  selection and native Chrome accessibility through the host's `cua_repl` tools.
  One was a development run; one used the installed Skill in a later user turn.
  Both used one submission with no manual transfer and no follow-up.
- The bound answer, stopped generation and final answer controls supported
  completion. Complete visible text was saved, decisive implementation claims
  were checked, and local adoption was recorded.
- Three offline reasoning exercises covered uncertain submission, unavailable
  requested model, and exhausted follow-up budget with changed materials. These
  were not browser fault-injection tests.

The five installable files under `skills/web-stand-in/` remain self-contained;
the tests and CI configuration are repository maintenance files. The helper and
record documentation are updated in this change. The historical browser runs
have not been repeated against this revision.

## Not yet verified

- Real attachment upload/parsing, long-answer completeness and downloads.
- Actual disconnection after sending, login expiry, rate limits, cancellation,
  changed ChatGPT layouts, or host exit and reopen during a long task.
- Live follow-up execution, concurrent browser scheduling, Linux browser
  operation, or other host tool implementations.
- Cloud-to-ECS connectivity or execution continuity while the Mac is powered off.
- Trigger rate across unrelated tasks or new installations.
- Improved research coverage, reduced Codex usage, or lower total latency against
  a measured baseline.

Persisting a request identifier cannot guarantee remote exactly-once execution
or keep work active after the host closes.
