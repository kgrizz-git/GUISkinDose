# Export

Use the Export tab after a calculation completes to save result artifacts.

Available exports:

- JSON with the full result dictionary and metadata.
- Interactive HTML dose map.
- PNG dose-map image.
- Rich report in XLSX, PDF, HTML, or DOCX format.

The rich report collects the calculation output, effective settings, input provenance, correction summaries, warnings, discarded-event notes, and dose-map images. It is intended as an audit-friendly review artifact, not as a replacement for source RDSR data.

In browser mode, exports download through the browser. In native mode, the app can ask for a save path and then offer open-file or open-folder actions when supported by the platform.

If an export fails because a backend dependency is missing, the app shows the package needed to restore that format. JSON and basic dose-map exports should remain available as fallback artifacts when report-specific backends fail.

For export scope and remaining polish items, see [Rich Export Plan](../../../dev-docs/plans/RICH_EXPORT_PLAN.md).
