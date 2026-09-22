> **NEEDS REVIEW** — This assessment has not yet been reviewed by a domain
> expert, and its Step-0 refuse-vs-serve recommendation is a maintainer
> decision, not a decided outcome. Code-path claims are verified against the
> tree.

# GUI Network-Exposure Hardening Assessment

Investigated: 2026-09-21

For `TO_DO.md` item *"GUI network-exposure hardening"* (Next Up): evaluate
the residual risk of opt-in LAN serving (fixed port 8765, no authentication,
single shared process-global state) and adopt proportional mitigations,
threat-modelling the hospital-workstation / shared-network case first while
keeping localhost UX unchanged.

## Summary

Accidental exposure is already closed: loopback-by-default is enforced in
code (`src/guiskindose/gui/app.py:411`), a non-loopback `--host` without
`--allow-network` raises instead of serving, and regression tests pin both
behaviors. What remains is **deliberate** exposure plus one often-missed
property of the default: loopback is per-host, not per-user, and every
connected browser — local or LAN — shares one unauthenticated `AppState`
singleton with full privileges.

**Recommendation:** keep opt-in LAN serving (refusal would kill legitimate
workflows; the typo-risk the gate was built for is already closed), but bound
it: (A) in-GUI network-mode banner + startup banner + doc tweaks, (B) port
randomization in network mode, (C) a spiked single-use token gate, and
explicitly defer (D) per-client state / real auth. Step 0 is a maintainer
decision — see §4.

---

## 1. What exists today

### 1.1 Loopback default + explicit-acknowledgement gate (shipped)

- `_resolve_bind_host` (`src/guiskindose/gui/app.py:411`): unset host binds
  `127.0.0.1`; anything outside `127.0.0.1`/`localhost` without
  `allow_network` raises `ValueError`
  (`network_gui_binding_requires_explicit_acknowledgement`), otherwise logs a
  value-free warning. IPv6 `::1` is conservatively treated as network (not in
  the exempt tuple) — correct behavior, no change needed.
- `run_gui` docstring (`src/guiskindose/gui/app.py:424`) states no-auth,
  shared-state, and trusted-network-only framing; the single dispatch in
  `main.py:552` (mirrored in `__main__.py:63`) means browser and `--native`
  modes share the same gate — native still binds `host:port` under the hood
  (`ui.run` at `src/guiskindose/gui/app.py:454`), so `--native --host
  0.0.0.0` without the flag is refused too.
- CLI help (`src/guiskindose/cli_args.py:202`, flag at `:217`) and README
  (`README.md:87`) both warn: no authentication, PHI-derived data, trusted
  network + own access controls. README enumerates LAN consequences plainly
  (`README.md:98`): anyone reaching the port can view loaded patient data,
  trigger exports, and mutate shared settings.
- Regression tests (`tests/gui/test_gui_security.py:27`, `:35`, `:43`) pin
  localhost-by-default, acknowledged-LAN passthrough, and unacknowledged
  refusal. Upload size caps ride in the same file (DoS bounding, orthogonal
  to network auth).
### 1.2 Single shared process-global state (by design, load-bearing)

- `state = AppState()` (`src/guiskindose/gui/state.py:137`) is a module-level
  singleton holding everything: loaded RDSR frames, filenames, per-exam
  metadata, settings mirrors, results, and figures (`state.py:19`).
- The `busy` flag (`src/guiskindose/gui/state.py:127`) is process-global, not
  per-client: it crudely serializes concurrent operations but isolates
  nothing. Every connected browser sees and mutates the same patients,
  settings, and results — there are no sessions, no users, no read-only
  viewers.
- Fixed port `8765` with no `--port` flag (`src/guiskindose/gui/app.py:460`;
  `cli_args.py` has no port option): predictable and scannable on any host
  that can route to the machine. `reload=False` and a 30 s client-reconnect
  window (`src/guiskindose/gui/app.py:459`, `:463`) are sane; neither
  substitutes for access control — any browser pointed at the URL, new or
  reattached, is a full-privilege client.

### 1.3 Partially shipped neighbours

- Privacy-plan Phase 9 (`dev-docs/plans/PRIVACY_HARDENING_PLAN.md:324`):
  items 1 (onboarding notice) and 3–4 (loopback default, `--allow-network`
  gate) shipped — the first-run onboarding dialog
  (`src/guiskindose/gui/app.py:104`, dismissable) already carries
  network-aware copy. Item 5 (explain no-auth/shared-state) exists in
  README/CLI/docstring/onboarding, but there is **no persistent or
  mode-aware in-GUI surface** (nothing reflects actual LAN serving, and the
  dialog can be permanently dismissed). Item 6 (refuse non-loopback until
  per-client state + auth) is an open policy decision. Item 7 (registry
  entries) has the onboarding privacy line (`dev-docs/ui_copy.json:49`,
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
| 1 | No in-GUI network-mode indication — all warnings live in CLI/README/logs, invisible to someone viewing the served GUI | Open |
| 2 | Fixed predictable port 8765, no randomization or override | Open |
| 3 | No token/auth layer (NiceGUI `>=2.0.0` per `pyproject.toml:38` brings none; needs custom middleware covering page + websocket + static paths) | Open, needs spike |
| 4 | No read-only view mode; no per-client state (singleton `AppState`) | Open, large |
| 5 | README loopback wording undersells the multi-user-machine case | Open, one sentence |
| 6 | Refuse-vs-serve policy decision (plan item 6) | Open, maintainer call |
| 7 | Server lifetime follows the last connected client — a lingering LAN viewer keeps loaded PHI resident after the operator leaves | Open; surface in Package A scope (e.g. visible session/client indicator), no new package |

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
- The `gui_help` network-mode page idea becomes a short loopback-scope note
  if a help page is wanted; not required.

Residual loopback risks (documented, not fixed by refusal): any local account
can reach the port (no login); a malicious webpage in the operator's own
browser could attempt requests at the fixed `127.0.0.1:8765` origin
(DNS-rebinding/CSRF shape — no auth, predictable port). Possible follow-ups,
none scheduled: Host/Origin header validation on the server (cheap,
uvicorn/NiceGUI-level — rejects cross-origin browser traffic but not local
processes), a randomized loopback port per launch (raises the bar for
drive-by web pages, costs bookmark stability), per-client state + real auth
(Package D). Record the trigger, do not schedule the work.

Original Step-0 analysis (kept for the record): refusal is the strongest
control and the smallest diff, but it kills legitimate workflows (ward display
screens, tablet at tableside, teaching demos on lab LANs). Serve-with-mitigations
(Packages A→C) would have kept localhost UX byte-for-byte unchanged.

### Package A — Say it where it happens (cheap, do regardless)

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

Print a random token to the server console at startup in network mode;
consume it once in a bootstrap exchange that issues an `HttpOnly`,
`SameSite=Strict` session cookie, then require that cookie on HTTP routes,
websocket upgrades, static assets, downloads, and reconnects; localhost
exempt. Do **not** require a query token on every request: query strings leak
through browser history and `Referer` headers — and the app currently loads
an external Google stylesheet (`src/guiskindose/gui/app.py:160`), so a query
token would be disclosed to a third party on every page load. Either set a
restrictive `Referrer-Policy` or remove/self-host the font before any
token-in-URL design.
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

Step 0 decision → Package A (one PR) → Package B (one PR) → Package C spike
(go/no-go) → D only on trigger. Each package extends `test_gui_security.py`;
localhost behavior must stay pinned unchanged throughout.

---

## Files examined

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
