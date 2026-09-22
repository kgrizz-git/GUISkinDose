> **Status 2026-09-22** — Step 0 is decided: non-loopback is refused outright
> (see §4). §1.1 and the Summary describe the pre-decision state for the
> record; the current behavior is loopback-only (§4 + code references below).
> Code-path claims verified against the tree 2026-09-21, line references
> refreshed 2026-09-22.

# GUI Network-Exposure Hardening Assessment

Investigated: 2026-09-21

For `TO_DO.md` item *"GUI network-exposure hardening"* (Next Up): this
assessment evaluated opt-in LAN serving risk and recommended mitigations.
**Decided 2026-09-22 (see §4): non-loopback is refused outright** — there is
no network mode, and Packages A–C are moot as specified. What stands: the
loopback threat model (§2 Case A), the residual loopback risks (§4), and the
deferred Package D trigger. The pre-decision analysis below is kept for the
reasoning record.

## Summary

Off-host serving is refused by construction: the GUI always binds the literal
`127.0.0.1` (`_resolve_bind_host`, `src/guiskindose/gui/app.py:429`,
normalizes `localhost`, raises `non_loopback_gui_binding_refused` on anything
else), the `--host`/`--allow-network` CLI surface is removed, and regression
tests pin default/normalized/refused behavior. What remains is one often-missed
property of the loopback default: loopback is per-host, not per-user, and every
local browser shares one unauthenticated `AppState` singleton with full
privileges (see §1.2, still current).

**Pre-decision record (kept for the threat-model reasoning):** accidental
exposure was already closed by loopback-by-default plus the explicit-ack gate;
the open question was deliberate LAN serving. **Recommendation at the time:**
keep opt-in LAN serving with mitigations (A) network-mode banner + startup
banner + doc tweaks, (B) port randomization in network mode, (C) a spiked
token gate (proposed as single-use; shipped instead as a launch-lifetime
bearer — deliberately reusable so a cleared cookie or second profile doesn't
lock the operator out), explicitly deferring (D) per-client state / real auth.
Step 0 has since been decided as refusal — Packages A–C are moot as specified
(see §4 for what survives and the residual loopback risks).

---

## 1. What exists today

### 1.1 Loopback-only refusal (shipped 2026-09-22; gate history below)

- `_resolve_bind_host` (`src/guiskindose/gui/app.py:429`): only the literal
  `127.0.0.1` is accepted (`localhost` is normalized to it, never resolved);
  anything else — including IPv6 `::1` (fail-closed) — raises `ValueError`
  (`non_loopback_gui_binding_refused`). The `--host`/`--allow-network` CLI
  flags are removed; `run_gui` (`src/guiskindose/gui/app.py:447`) keeps a
  validated `host` knob for programmatic callers only.
- The single dispatch in `main.py:554` (mirrored in `__main__.py:60`) means
  browser and `--native` modes share the same refusal — native still binds
  `host:port` under the hood (`ui.run` at `src/guiskindose/gui/app.py:477`),
  so there is no native back door to network serving.
- README (`README.md` "Privacy / network") states the refusal plus the
  per-host-not-per-user consequence. Regression tests
  (`tests/gui/test_gui_security.py`) pin localhost-by-default, literal
  normalization, and parametrized refusal. Upload size caps ride in the same
  file (DoS bounding, orthogonal to network auth).

### 1.1b Loopback controls — token + Host/Origin (shipped 2026-09-22)

Refusal keeps remote machines away but is not an authentication boundary, so
browser mode additionally ships (`src/guiskindose/gui/loopback_security.py`,
wired in `run_gui` before `ui.run`):

- a **per-launch token**: random secret printed to the console as a launch
  URL (valid until restart, auto-opened when the port accepts connections);
  bootstraps an `HttpOnly; SameSite=Strict` session cookie required on HTTP
  and websocket traffic alike. Only the token hash is retained
  (constant-time compare); stale tabs die on restart.
- **strict Host validation** (loopback authority only — DNS rebinding
  rejected) and **Origin checks**: a present-but-foreign Origin is always
  rejected; sockets additionally need the session whenever tokens are on
  (an allowlisted Origin alone proves nothing against local processes,
  which can forge it). Native skips the session check, tolerating embedded
  webviews that omit Origin entirely (remote pages cannot omit it).
- Native mode keeps Host/Origin without the token (embedded window is the
  trusted client); another local user can still reach its port.

*Gate history (superseded, kept for the record):* before refusal, an unset
host bound `127.0.0.1` while a non-loopback `--host` required the explicit
`--allow-network` acknowledgement (`network_gui_binding_requires_explicit_acknowledgement`),
with a value-free warning on acknowledged LAN binds. The acknowledgement model
was retired because even admitted users shared one state with no isolation —
see §4.
### 1.2 Single shared process-global state (by design, load-bearing)

- `state = AppState()` (`src/guiskindose/gui/state.py:137`) is a module-level
  singleton holding everything: loaded RDSR frames, filenames, per-exam
  metadata, settings mirrors, results, and figures (`state.py:19`).
- The `busy` flag (`src/guiskindose/gui/state.py:127`) is process-global, not
  per-client: it crudely serializes concurrent operations but isolates
  nothing. Every connected browser sees and mutates the same patients,
  settings, and results — there are no sessions, no users, no read-only
  viewers.
- Fixed port `8765` with no `--port` flag (`src/guiskindose/gui/app.py:483`;
  `cli_args.py` has no port option): predictable for drive-by local pages.
  `reload=False` and a 30 s client-reconnect window
  (`src/guiskindose/gui/app.py:482`, `:486`) are sane; neither substitutes
  for access control — any local browser pointed at the URL, new or
  reattached, is a full-privilege client.

### 1.3 Partially shipped neighbours

- Privacy-plan Phase 9 (`dev-docs/plans/PRIVACY_HARDENING_PLAN.md:324`):
  items 1 (onboarding notice) and 3 (loopback default) shipped; item 4
  (`--allow-network` gate) shipped then **retired 2026-09-22** by outright
  refusal (see §1.1). The first-run onboarding dialog
  (`src/guiskindose/gui/app.py:104`, dismissable) already carries
  network-aware copy. Item 5 (explain no-auth/shared-state) exists in
  README/CLI/docstring/onboarding, but there is **no persistent or
  mode-aware in-GUI surface** (nothing reflects actual LAN serving, and the
  dialog can be permanently dismissed). Item 6 (refuse non-loopback until
  per-client state + auth) is **decided 2026-09-22** (refusal shipped; see
  §1.1/§4). Item 7 (registry entries) has the onboarding privacy line (`dev-docs/ui_copy.json:49`,
  which does include network wording) but no dedicated network-mode banner
  or help page.
- In-app help (`docs/source/gui_help/`) has no network-mode page; the only
  network-adjacent copy is the export-destination caution.

## 2. Threat model

### Case A — localhost default

- **Single-user workstation**: exposure surface is local processes only.
  Residual risk is low but nonzero (malware / other local users aside, the
  operator is the threat boundary they already manage).
- **Shared / multi-user workstation** (wards, reading rooms, teaching
  machines): **any user on the machine can open `localhost:8765` and get
  full access to loaded PHI and shared settings.** Loopback is per-host, not
  per-user. README's "reachable only from the machine it runs on"
  (`README.md:88`) is accurate but easy to misread as "only by me" — worth
  one clarifying sentence (Package A).

### Case B — opt-in LAN (`--host 0.0.0.0 --allow-network`)

> Rejected alternative (refused 2026-09-22, see §4) — retained for the
> threat-model reasoning that motivated refusal.

Anyone on the routable network, with no credentials, can:

1. **Read** all loaded exams, Data Table contents, results, and dose maps
   (PHI-derived values rendered in the browser).
2. **Write** new PHI into the shared state via uploads: LAN upload access
   permits unauthenticated creation of PHI-bearing server-side files within
   the size cap. Temp dirs/files are `0700`/`0600`, uploads persist until
   explicit removal, clear, or clean shutdown, crash leftovers may remain up
   to 24 hours, and deletion is plain unlink with no secure erase.
3. **Mutate** settings, offsets, and coordinate toggles, changing what every
   other viewer sees and what the next calculation produces — including
   cross-talk between different operators' patients.
4. **Compute**: trigger dose calculations (CPU-heavy on human meshes) and
   exports — availability and integrity impact, not just confidentiality.
   Lifetime note: in browser mode the server shuts down only after the
   *last* client disconnects (`src/guiskindose/gui/app.py:375`), so a
   connected LAN viewer keeps the process — and the loaded PHI plus temp
   files — alive after the operator closes their own window.

Fixed port 8765 makes the service trivially discoverable; the 30-second
client-side reconnect window covers socket reattachment after a dropped
connection — it is not a privilege lifetime. While the server remains
reachable, stale tabs can reload and new clients can connect with full
privileges. None of this is accidental —
the operator opted in — but the blast radius of that opt-in currently has no
in-app reminder and no technical bound beyond the network perimeter the
operator was told to provide themselves.

### What is explicitly NOT claimed

- No evidence of remote code execution, traversal, or injection via the
  network path was sought in this assessment; the findings are
  authentication/authorization-absence plus shared-state design, consistent
  with the plan's own framing (`PRIVACY_HARDENING_PLAN.md:335`).
- Upload size caps already bound the cheapest DoS vector; this assessment
  does not re-litigate them.

## 3. Gaps (ordered by leverage)

| # | Gap | Status |
|---|---|---|
| 1 | No in-GUI network-mode indication | **Moot** — refused 2026-09-22; there is no network mode to indicate |
| 2 | Fixed predictable port 8765, no randomization or override | Open, modest (residual: known-port probing; see §4 follow-ups) |
| 3 | No token/auth layer | **Done in browser mode** (per-launch token + session cookie, 2026-09-22); Host/Origin checks in both modes; no per-user isolation (see gap 4) |
| 4 | No read-only view mode; no per-client state (singleton `AppState`) | Deferred (Package D trigger: demonstrated clinical-LAN need; not scheduled) |
| 5 | README loopback wording undersells the multi-user-machine case | **Done** — README "Privacy / network" now states per-host-not-per-user |
| 6 | Refuse-vs-serve policy decision (plan item 6) | **Decided 2026-09-22** — refuse (see §4) |
| 7 | Server lifetime follows the last connected client | **Moot as LAN risk** — loopback-only; local-process lifetime semantics unchanged |

## 4. Recommendations

### Step 0 — Decision (maintainer, before any code)

**Decided 2026-09-22: refuse non-loopback entirely.** The unauthenticated,
shared-state GUI always binds the literal `127.0.0.1` and raises on any other
host; the `--host` / `--allow-network` CLI surface is removed. Rationale: the
ward-display / tableside-tablet workflows that argued for serve-with-mitigations
do not outweigh the shared-state + no-auth combination — even a token gate
would admit mutually-visible operators with no isolation between them
(Package D remains the only true multi-user answer, still deferred). The
accidental-exposure typo the gate was built for stays closed by construction:
there is no longer any flag combination that serves off-host.

Packages A–C below are therefore **moot as specified** (no network mode exists
to banner, randomize, or gate). What survives from them:

- Package A item 3 (README one-liner: loopback is per-host, not per-user) —
  still applies and is now in `README.md`.
- The `gui_help` loopback-scope page (covering the malicious-webpage angle)
  is **required**, not optional: the only in-GUI notice is the one-time,
  dismissable onboarding dialog, so the help page is the durable in-app
  reminder. Register it in `help_registry.json` with the follow-up PR.

Residual loopback risks (after the 2026-09-22 controls): browser mode now
requires a per-launch token (console URL bootstraps a `HttpOnly;
SameSite=Strict` session cookie; stale tabs die on restart) and enforces
strict Host/Origin checks, closing the DNS-rebinding and cross-site drive-by
paths in both modes (native: Host/Origin without the token). What remains:
anyone on the machine with the launch URL or an active session shares the
full-privilege singleton state (no per-user isolation); token hygiene is the
operator's (console output, browser history on shared profiles). Possible
follow-ups, none scheduled: randomized loopback port (modest), per-client
state + real auth (Package D). Record the trigger, do not schedule the work.

Original Step-0 analysis (kept for the record): refusal is the strongest
control and the smallest diff, but it kills legitimate workflows (ward display
screens, tablet at tableside, teaching demos on lab LANs). Serve-with-mitigations
(Packages A→C) would have kept localhost UX byte-for-byte unchanged.

### Package A — Say it where it happens (cheap, do regardless)

*Moot as specified (no network mode); line refs are investigation-time.*

1. One persistent banner in the shared page shell (`ui.header` at
   `src/guiskindose/gui/app.py:164`) whenever the bound host is non-loopback:
   no-auth + shared-state + operator-acknowledged wording — not tab-local
   banners per tab. Back it with an immutable resolved-network-mode
   configuration set before `ui.run()` (test seam: set it before
   `user.open("/")` in NiceGUI user-simulation tests, which never call
   `run_gui()`), and assert banner-visible on LAN / banner-absent on
   loopback in `tests/gui/test_gui_security.py`. This complements (not
   duplicates) the one-time onboarding notice. Register copy in
   `ui_copy.json` / `help_registry.json` (plan item 7) and add a `gui_help`
   network-mode page.
2. Startup stderr banner in network mode restating the same (value-free,
   same convention as the existing coded warning).
3. README one-liner: loopback is per-host, not per-user — shared machines
   need their own access story.

### Package B — Unpredictable port in network mode (small, verify first)

*Moot as specified (no network mode); line refs are investigation-time.*

Randomize the bound port when (and only when) serving non-loopback; keep
`8765` for loopback so bookmarks, docs, and muscle memory survive. This is
currently underspecified against the single `ui.run(... port=8765 ...)`
call (`src/guiskindose/gui/app.py:454`): passing port `0` delegates selection
to the server, but the effective port must then be recovered and advertised
as a usable client URL (printing `0.0.0.0:<port>` is not one), and
preselecting a free port has a bind race. Verify NiceGUI exposes the
effective post-bind port; if it does not, add an explicit `--port` option
and recommend a user-selected high port instead. Frame random ports as
scan-noise reduction only — never as access control.

### Package C — Token-bootstrapped session gate (moderate, spike first)

*Shipped 2026-09-22 in loopback-adapted form (no spike needed — no network
mode): per-launch token printed to the console bootstraps an `HttpOnly;
SameSite=Strict` session cookie in browser mode (required on HTTP and
websocket traffic alike); strict Host validation and Origin checks apply in
both modes with the native session exemption above. The Google-font
query-token caveat below is moot — the font has been vendored and served
locally since 2026-09-22 — and line refs are investigation-time.*

*Reviewed alternatives (declined with rationale):* a POST-body/fragment
bootstrap handoff instead of the query token — rejected. The query token does
appear once in uvicorn access logs, but per-launch rotation bounds that
exposure to the current run (the token dies on restart). A fragment design
would additionally keep the token out of access logs and browser history, but
the console print (needed for manual open) remains in both designs, and it
would need a custom JS bootstrap page plus a new token-gated endpoint —
complexity in the most sensitive flow for a modest narrowing. Non-ASCII
token bytes are rejected on the 403 path: raw non-ASCII fails the query
decode guard, and percent-decoded Unicode is refused before hashing
(`test_percent_encoded_unicode_token_rejected`).

Print a random token to the server console at startup in network mode;
consume it once in a bootstrap exchange that issues an `HttpOnly`,
`SameSite=Strict` session cookie (single-use was the proposal; the shipped
loopback gate above keeps the token valid until restart instead), then
require that cookie on HTTP routes, websocket upgrades, static assets,
downloads, and reconnects; localhost exempt. Do **not** require a query token on every request: query strings leak
through browser history and `Referer` headers — and, at the time of writing,
the app loaded an external Google stylesheet (`src/guiskindose/gui/app.py:160`
then), so a query token would have been disclosed to a third party on every
page load. (That request is gone: the font has been vendored and served
locally since 2026-09-22.) Either set a restrictive `Referrer-Policy` or
remove/self-host the font before any token-in-URL design — the latter is now
already the case.
**Spike before committing**: NiceGUI page + websocket + static-asset paths
must all pass the gate without breaking reconnect, `ui.download()` exports,
or the native path. Explicit stop conditions: token leakage via URL
persistence, cookie-less websocket authentication proving infeasible, or
incomplete route coverage. If the spike hits any of them, stop and
re-evaluate rather than shipping a half-gate that teaches false confidence.

### Package D — Deferred (large, only on demonstrated need)

Per-client state (replacing the `AppState` singleton) + real authentication,
and/or a read-only shared-view mode. This is a state-management rewrite with
PHI-isolation testing obligations. Pursue only if B/C prove insufficient or
a clinical LAN deployment requires named users. Record the trigger, do not
schedule the work.

### Suggested sequencing note

Superseded by the §4 refusal: no packages ship. Residual follow-ups (separate
PR, per TO_DO): loopback-scope help note, Host/Origin validation, randomized
loopback port; Package D only on trigger.

---

## Files examined

(Current code refs: `app.py:429` `_resolve_bind_host`, `app.py:447` `run_gui`,
`app.py:477` `ui.run`, `app.py:482-486` port/reload/reconnect, `main.py:554`
/ `__main__.py:60` dispatch, `state.py:127` `busy` / `:137` singleton. The
pre-refusal refs below — `app.py:411-467`, `cli_args.py:202-226`,
`main.py:552`, `__main__.py:63` — are the investigation-time locations, kept
so the history reads against the right tree.)

- `src/guiskindose/gui/app.py` (esp. lines 411-467)
- `src/guiskindose/gui/state.py` (esp. lines 18-137)
- `src/guiskindose/cli_args.py` (esp. lines 202-226)
- `src/guiskindose/main.py:552`
- `src/guiskindose/__main__.py:63`
- `tests/gui/test_gui_security.py`
- `README.md:87`
- `dev-docs/TO_DO.md` ("GUI network-exposure hardening" item)
- `dev-docs/plans/PRIVACY_HARDENING_PLAN.md:324`
- `dev-docs/ui_copy.json:49`
