# Phantom packs (optional clinical meshes)

A **phantom pack** is a zip of allow-listed clinical STL files plus a manifest. It is optional data, not a second application.

## Full vs Light

- **GUISkinDose Full** already ships the whole clinical phantom catalog inside the app bundle.
- **GUISkinDose Light** ships a starter set. Install a phantom pack zip, or use the Full download, to add the remaining clinical meshes.

Meshes resolve **shipped bundle first**, then your per-user library. A pack cannot replace or shadow a mesh that is already bundled.

## Install in the GUI

On **Settings → Phantom Settings**, the clinical catalog lists each mesh as **Installed** or **Not installed**. Use **Install phantom pack** to pick a `.zip` (browser upload or native file dialog). After a successful install, the list, mesh selector, and phantom preview update without restarting.

**Download phantom pack** fetches the pack published for this GUISkinDose version from GitHub. It is offered only when clinical meshes are missing. The download shows progress and can be cancelled or retried; a cancelled or failed download leaves the library unchanged. If the catalog is already complete, both download and local-zip actions are hidden.

The download contacts only the fixed GitHub release URL for this version. It sends no exam data, file names, or machine identifiers. TLS is always verified, and redirects are limited to GitHub's release hosts. The SHA-256 manifest pin in the app rejects a substituted or tampered pack. That pin proves integrity, not authenticity: the app and pack share the GitHub release, so a compromised release could replace both. Use the Full download or a separately authenticated channel if you need a stronger authenticity boundary. The published `.zip.sha256` file is a convenience, not a signature.

With no network, installed meshes and **Install phantom pack** keep working. A blocked `github.com` or asset host is an offline failure; there are no mirrors.

Pack zips must stay under **80 MiB**. The browser upload control sets that limit client-side. The Settings handler stops streaming once the cumulative body exceeds 80 MiB even if a client bypasses the widget cap, and the GUI HTTP server rejects oversized upload POST bodies (80 MiB plus a small multipart overhead) before they reach the handler.

## Install from the command line

```bash
guiskindose --install-phantom-pack phantom-pack.zip
guiskindose --download-phantom-pack
```

Both exit after install; they do not run a dose calculation. The download uses the same pinned release URL and verification as the GUI. Pack install or download is not available together with `--mode gui`, and the two pack flags are mutually exclusive.

## Where files live

- **Preferences and equipment profiles:** `~/.guiskindose/` (window settings, profiles — not phantom STL files).
- **Extra clinical meshes:** a per-OS phantom library folder (macOS Application Support, Windows Local AppData, Linux XDG data home). Removing extra meshes means deleting that phantom directory; reinstalling the app does not remove it.
