# Phantom packs (optional clinical meshes)

A **phantom pack** is a zip of allow-listed clinical STL files plus a manifest. It is optional data, not a second application.

## Full vs Light

- **GUISkinDose Full** already ships the whole clinical phantom catalog inside the app bundle.
- **GUISkinDose Light** ships a starter set. Install a phantom pack zip, or use the Full download, to add the remaining clinical meshes.

Meshes resolve **shipped bundle first**, then your per-user library. A pack cannot replace or shadow a mesh that is already bundled.

## Install in the GUI

On **Settings → Phantom Settings**, the clinical catalog lists each mesh as **Installed** or **Not installed**. Use **Install phantom pack** to pick a `.zip` (browser upload or native file dialog). After a successful install, the list and mesh selector update without restarting.

## Install from the command line

```bash
guiskindose --install-phantom-pack phantom-pack.zip
```

This exits after install; it does not run a dose calculation. Pack install is not available together with `--mode gui`.

## Where files live

- **Preferences and equipment profiles:** `~/.guiskindose/` (window settings, profiles — not phantom STL files).
- **Extra clinical meshes:** a per-OS phantom library folder (macOS Application Support, Windows Local AppData, Linux XDG data home). Removing extra meshes means deleting that phantom directory; reinstalling the app does not remove it.
