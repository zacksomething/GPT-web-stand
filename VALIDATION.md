# Validation scope

As of 2026-09-19, the skill has been validated in one macOS environment. This file summarizes results without including private paths, prompts or conversation identifiers.

## Completed

- The official Skill format validator accepted the skill metadata and structure.
- Eleven local behavior tests passed. They cover snapshots and version changes, duplicate/concurrent send reservations, request identity, result preservation and conflicts, damaged records, separate completion/capture states, and follow-up linkage/counting.
- Two live text consultations completed in ChatGPT web using the visible 6 Pro selection and native Chrome accessibility through the host's `cua_repl` tools. One was a development run; one used the installed Skill in a later user turn. Both used one submission with no manual transfer and no follow-up.
- The bound answer, stopped generation and final answer controls supported completion. Complete visible text was saved, decisive implementation claims were checked, and local adoption was recorded.
- Three independent offline behavior exercises covered uncertain submission, unavailable requested model, and exhausted follow-up budget with changed materials. These were reasoning exercises, not browser fault injection.

## Portability and packaging

The five files under `skills/web-stand-in/` are unchanged copies of the reviewed skill. They contain no author-specific absolute paths and require no files in the source research workspace. The test script uses a repository-relative path to the packaged helper.

Before publication, the packaged repository was copied into a fresh temporary directory, and the eleven tests were rerun from that directory. This verifies local test/helper independence from the research folder on the tested machine. It does not establish compatibility with another operating system, Python version, browser, account or host tool implementation.

## Not yet verified

- Real attachment upload/parsing, long-answer completeness and attachment downloads.
- Actual disconnection after sending, login expiry, rate limits, cancellation, and changed ChatGPT layouts.
- Long-task recovery after exiting and reopening the host.
- Live follow-up execution, concurrent browser scheduling, and other operating systems.
- Trigger rate across unrelated tasks or new installations.
- Improved research coverage, reduced Codex usage, or lower total latency against a measured baseline.

There is no independent browser executor or background worker in this repository. Persisting a request identifier cannot guarantee remote exactly-once execution or keep work active after the host closes.
