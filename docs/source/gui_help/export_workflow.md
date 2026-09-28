# Export

## Privacy

Exports are de-identified by default and use filenames that do not derive from the source exam. Enabling **Include
source filenames (may contain PHI)** is a separate, intentional action and can make the export an identified clinical
record. Store every export in an approved destination, apply the appropriate retention policy, and avoid repository
or shared-network locations unless they are specifically approved for clinical data.

## Intended use

Every export carries an intended-use notice. The rich report (XLSX, PDF, HTML, DOCX) states it in its header, the JSON
results include an `intended_use` field, and exported dose-map images show a short version in the corner. GUISkinDose
is not FDA-cleared, and qualified medical physicists and physicians are responsible for reviewing its results.

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
