# Loopback Scope And Local Access

The GUI is a **local-only application**. It always binds to `127.0.0.1`
(localhost) and refuses any other host — there is no LAN or remote mode. Do
not try to expose it with a proxy; move the computation to the machine where
the data may reside instead.

## Loopback is per-host, not per-user

Loopback binding is **not** an authentication boundary:

- Anyone logged into this machine who opens the GUI port sees the same
  shared state — patient data, settings, results. OS accounts alone do not
  protect it, so shared workstations need their own access story (one
  operator at a time, or per-operator machines).
- In browser mode, access additionally needs the console launch URL (it
  bootstraps your session and stays valid until restart) or an active
  session. Anyone with either sees everything.
- Native mode has no launch token: any local user who reaches the port gets
  the same full access.

## Browser-origin traffic

A hostile webpage open in the operator's browser cannot drive the GUI:
strict Host validation rejects DNS-rebinding tricks, Origin checks reject
cross-site requests and socket handshakes, and every browser-mode request
and socket needs the session. Still, avoid untrusted browsing on the
operating machine while the GUI runs — the guarantees above assume a
non-compromised browser.

## Sessions end on restart

Sessions, launch URLs, and cookies are per-launch: restarting the GUI
invalidates all of them. Stale tabs stop working — relaunch and use the new
console URL. There are no user accounts, no roles, and no audit trail of who
did what; treat the running GUI as a single-operator instrument.
