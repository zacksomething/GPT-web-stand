# ChatGPT web operation

Use this reference with the current host's browser tool documentation. Page layouts, labels, and available controls change; derive interactions from observed UI, never from the sample's old numeric indices.

## Select a usable surface

Respect any browser or tab selected by the user and the host's browser-selection rules. Discover currently callable tools; a skill name or installed browser alone is not a working connection.

Prefer a browser tab controller where it is available. A documented computer-use controller operating the actual browser UI is also a valid automatic web route. In the validated macOS setup, `cua_repl` native Chrome accessibility control could reach logged-in ChatGPT while in-app navigation timed out. This is an environment observation, not a permanent default or a guarantee.

Initialize `cua_repl` using one documented discovery/selection call and read the returned API instructions. For native macOS Chrome, `cua.getApp("com.google.Chrome")` returns the available accessibility state. When using a tab API, select or create the tab using the documented host rules. Do not use shell scripts, remote debugging clients, cookies, or private endpoints to bypass missing UI capabilities.

If the initial route fails **before any send attempt**, automatically try another currently callable UI route when the user's browser choice and host rules permit it. Confirm the first route did not submit anything and preserve any draft. A switch must reach the same requested ChatGPT web model; it is not permission to change providers, use an API, or install a controller. After a send attempt or ambiguous submission, recover the original conversation instead of opening another chat and resending. If no permitted route works, report the concrete blocker.

Use a dedicated tab/chat for a new logical consultation. Keep unrelated chats and drafts intact. If the browser is already displaying a relevant existing consultation, resume it using the recorded identity. For a fresh tab in native Chrome, open through its visible New Tab control, then use the observed address field. Do not blindly send keyboard input to a changing window.

After an action, refresh the accessibility or DOM state before deciding the next action. If the host says the user changed the app, refresh once and reassess. If the user is actively taking control, preserve state and avoid fighting for focus.

## Preflight at the actual composer

Check the destination is ChatGPT, a usable composer exists, and login is valid. Stop site actions for login/MFA/CAPTCHA requiring user participation; do not request credentials in chat or extract an existing browser profile.

Observe the model selector showing `6 Pro` or `GPT-6 Pro`. If another model is selected, select the requested option using visible controls and verify the resulting selection. If the label differs and its equivalence is not established, report the uncertainty instead of silently substituting. Preserve any separately requested effort setting; do not confuse Pro subscription status with the selected model.

Prepare the full prompt locally before filling the composer. Inspect the resulting text. For attachments, read the host's upload documentation first, use only the specifically authorized files, and verify upload/processing is complete before sending. A successful file-picker action is not evidence that parsing completed. Prefer inline selected excerpts when they are sufficient and covered by authorization.

## Send once and bind the answer

Record pre-send evidence: selected model label, exact prompt snapshot, material readiness, browser surface, and chat identity available so far. Reserve `send_intent` in the local helper immediately before clicking the observed Send control once.

Then observe the submitted input and running state. Capture a persistent conversation URL as soon as the UI provides it. If the initial URL is visibly temporary, record it as provisional and update the observation once a stable URL appears. Do not invent a remote turn ID when the tool exposes none.

A new empty chat, exact submitted text, submission timestamp and corresponding assistant response can provide sufficient correlation when no stable turn ID is exposed. A request marker included in the frozen prompt can add evidence; its appearance alone does not prove authenticity.

If the send call throws or local confirmation fails, inspect the same chat before further mutation. Search the visible conversation for the exact submitted prompt/marker and its response. If it is present, resume collection; if absence remains ambiguous, stop sending and retain the unknown state. Never press Retry, Regenerate or Send solely because a local timer expired.

## Observe a long run

Use state deltas and narrowly relevant UI observations. A practical cadence is a short first check followed by progressively longer intervals up to 60 seconds, adjusted to the host. Do useful independent work between checks. Preserve communication responsiveness; avoid returning the complete growing transcript every few seconds.

Completion needs evidence from the correct response, stopped generation, and the final response controls/content. A Copy or rating control is useful but can belong to an older answer. A requested end marker is useful for detecting truncation but is not sufficient by itself. Streaming pauses, unchanging text length, or the absence of a spinner alone are insufficient.

If the UI offers “continue generating”, the answer may be incomplete. Continue the same answer when the visible action is unambiguous and in scope; otherwise preserve partial output and handle it as a concrete follow-up need. Capture refusal, rate-limit and error messages accurately. On rate limit, stop new submissions; retain the result/identity and any visible reset information.

## Preserve the result

Use the supported page text export, scoped visible text, or Copy workflow exposed by the current tools. Browser clipboard access may be available; native computer-use APIs may instead expose answer text in the accessibility tree. Save the original returned text, preserving wording, links, code and meaningful structure. Never manufacture a “verbatim” result from a summary.

For long answers, ensure the full bound response and any relevant attachments were obtained. If the control surface cannot collect the whole result, mark it partial rather than claiming full capture. Keep raw output separate from the short local summary.

Leave the consultation available for evidence and follow-up. For host-controlled tabs that are automatically cleaned up, use the documented deliverable/handoff marking when appropriate. Record the URL independently because turn-scoped tab marks do not guarantee future access.

## Recovery and stopping

When continuing an interrupted consultation, recover the latest request directory for the logical task from the prior task context or its saved output. Do not run `init` for the same question. Follow this sequence:

1. Run the helper's `status --task <directory>`. Read the frozen prompt and relevant observations, including the latest conversation URL, submission evidence, follow-up count and any cancellation request. Status summarizes caller observations; it is not a live server query.
2. If a complete answer was already captured, inspect that result and completion evidence before collecting anything again. Check `adoption.md` to find the unfinished local work. Resume verification/adoption when the saved evidence is sufficient; do not send again just to reproduce an existing answer.
3. Otherwise reopen the recorded conversation through the current permitted browser tools. Match the submitted prompt and corresponding answer against the saved evidence. If only a provisional URL was saved, recover the original tab or an observed matching conversation; never invent its persistent URL.
4. Record what the page now shows: still running, complete, explicitly failed/cancelled, or blocked/uncertain. For a complete answer, collect the full bound response and record completion separately from capture. For a running answer, continue waiting under the current task budget.
5. If the submission cannot be confirmed, preserve that uncertainty. Do not clear `send_intent`, create a replacement request, or use another chat to evade the send guard. If no send was attempted and no reservation exists, the normal preflight and first-send path remains available.
6. Run `verify-materials`, assess any changes, record adoption and continue the original task. Restoring a saved consultation requires an active Codex turn; no automatic wake-up or background worker is provided.

Keep local wait expiry, remote failure, user cancellation request, and observed cancellation separate. A confirmed late completion may arrive after cancellation was requested; report what actually happened.

The local helper protects one request from a repeated send reservation. It does not control the browser, guarantee server idempotency, serialize unrelated operators, or survive a closed host as an active worker. Keep one controller per consultation; cross-task parallel browser scheduling requires its own tested implementation.
