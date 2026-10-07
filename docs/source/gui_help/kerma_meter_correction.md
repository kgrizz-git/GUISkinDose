# Kerma-meter correction factors

Apply a calibration factor so dose uses laboratory-traceable air kerma instead of
the unit's uncorrected reported `K_IRP`.

**Definition:** `CF = (real measured dose) / (unit reported dose)`.

## Lookup keys

CF is resolved per **individual unit × tube** (Plane A / Plane B / Single Plane):

1. Explicit equipment label (optional override for the whole run)
2. Device serial number (DICOM)
3. Station name (DICOM)
4. Tabular unit/room column when DICOM identity is absent

## Vendor column roles

- **Radimetrics:** `Equipment` is the room/unit (CF key); `Device` is the model.
- **DoseTrack:** `Equipment Name` is often the **model**, not a unique room. Sites with
  multiple rooms of the same model should set an explicit label or supply a custom
  station column.

## Calibration file columns and periods

**Start from the example.** The Corrections tab, Kerma-meter correction, has a *Download example
calibration file* button. The example (`calibration_factors_example.csv`, with a README
beside it) uses fictional unit names, and shows one unit and tube with two calibration
periods. It is also installed with the package under `example_data/kerma_meter/`
(`guiskindose.get_path_to_example_kerma_meter_file()` returns its path). Replace its rows with
your own measurements, then pass your copy with `--kerma-meter-correction-file` on the
command line or select it in the Corrections tab.

The calibration file has the columns `equipment`, `tube`, and `correction_factor`. It may also
have `valid_from` and `valid_to` (ISO dates, `YYYY-MM-DD`; either may be blank for an open end).
Use them when a dose meter was recalibrated and the same unit and tube has different factors
over time. Rows without dates behave as before. Two periods for the same unit and tube must not
overlap, and a file that does is rejected when it loads.

GUISkinDose never reads dates from your exam data. You choose the period for each exam yourself
(see the dialog below), or on the command line with `--kerma-meter-calibration-date YYYY-MM-DD`,
which picks the period containing that date for every exam. Without it, the period with no
`valid_to` (the current one), otherwise the most recent, is used, and a warning with the count
of affected pairs is logged.

## Fail-soft behavior

When equipment or tube cannot be resolved, or the `(equipment, tube)` pair is missing
from the table, CF falls back to the configured default factor (usually `1.0`).

Reported `K_IRP` in the Data table stays uncorrected. Corrected kerma is stored per event
as `kerma_corrected` and included in exports as `air_kerma_corrected`. The GUI Results tab
currently shows uncorrected `K_IRP` only.

## Missing-factor dialog

When correction is enabled, GUISkinDose lists every detected unit and tube as soon as events
load. If any pair has no factor yet, a dialog opens. Each row is pre-filled in this order:

1. a value you entered earlier for that exam (`entered manually`), or the previous exam's value (`↳ follows Exam N`),
2. the value from the calibration file (`from file`),
3. the default factor (`default: review`). Please check these rows.

Rows are grouped by exam, because a recalibrated meter can need a different factor in a later
exam. Exam 2 and later start from the value the same unit and tube has in the previous exam and
say **follows Exam N** until you change that row. Editing an earlier exam updates the exams that
still follow it, and never the ones you edited. Only values you enter are stored, so a row that follows an earlier exam keeps following it after you confirm and reopen the dialog. The list scrolls. A tube shown as **unknown**
cannot be looked up, so the default factor applies to it.

**Calibration period.** When the file has dated rows for a unit and tube of an exam, that exam
gets a *Calibration period* selector listing the file's periods, for example
`1901-01-01 → 1901-12-31`. Exam 1 starts on the most recent period and later exams follow the
previous exam's choice until you pick one. The chosen period selects that exam's file factor.
The choice is saved with the run configuration only when identifiers are included.

When the file has dated rows, the dialog opens at load even if every factor is already covered, so the period is chosen on purpose instead of silently defaulting to the latest one.

Confirming changes to factors, units, or periods clears earlier calculation results. Rerun the calculation before reading or exporting results.

**Exams with no equipment identity.** If an exam carries no serial number or station name, the
dialog asks which unit it was acquired on. Pick a detected unit or a unit from the file, or type
a new name. The exam's factors are then looked up for that unit. The chooser stays available afterwards (and when you reopen the dialog from the Corrections tab) so you can change the unit or clear it. The choice is stored per exam
and saved with the run configuration only when identifiers are included.

**Confirm** is blocked until every factor is a number greater than zero; a blank field is an error, not a kept value. If the loaded data changes while the dialog is open, your entries are discarded with a notice.

A row you confirm at the default factor without changing it is remembered as answered, so the dialog does not ask again. It is not stored as a factor, so a calibration file row added later still applies.

**Cancel** never blocks the run. It keeps file values and your earlier entries, and every
unanswered pair uses the default factor. Calculate re-opens the dialog once if pairs are still
unanswered.

**Reviewing later.** The Corrections tab has a *Review correction factors…* button that opens the dialog at any time with every detected pair, so confirmed factors can be edited. The dialog also reopens when you select or clear the calibration file or sheet, or turn asking back on.

**Turning it off.** Clear *Ask for missing correction factors* in the Corrections tab, or tick *Don't ask
again until the loaded data changes* in the dialog. Loading, removing, or re-parsing events
resets that choice. Command-line runs never open a dialog.
