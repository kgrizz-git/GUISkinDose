# Example kerma-meter calibration file

`calibration_factors_example.csv` is a starting point for your own calibration file. Every unit
name and number in it is fictional. Copy it, replace the rows with your own measurements, and
select the copy in Settings, Kerma-meter correction, or pass it on the command line:

```text
guiskindose --kerma-meter-correction-file my_factors.csv --kerma-meter-calibration-date 1902-03-01 ...
```

## Columns

| Column | Meaning |
|---|---|
| `equipment` | The unit the factor belongs to. It must match the device serial number or the station name in your data, or the explicit equipment label you set. Matching ignores case and surrounding spaces. |
| `tube` | `single` (single-plane unit), `A`, or `B` (the two tubes of a biplane unit). `Single Plane`, `Plane A`, and `Plane B` are also accepted. |
| `correction_factor` | CF = (real measured dose) / (dose the unit reported). It must be a number greater than zero. Values near 1.0 are typical. |
| `valid_from`, `valid_to` | Optional ISO dates (`YYYY-MM-DD`). Either may be blank for an open end. Leave both blank for a factor that always applies. |

## Calibration periods

If a dose meter was recalibrated, give the same unit and tube one row per period. In the example,
`DEMO-ROOM-2` tube `A` has a factor for 1901 and a new one from 1902 onward (placeholder years). Periods for the
same unit and tube must not overlap, or the file is rejected.

GUISkinDose never reads dates from your exam data. In the GUI you pick the period for each exam in
the correction-factor dialog. On the command line, `--kerma-meter-calibration-date` picks the period
containing that date for every exam. Without it, the current period (the one with no `valid_to`) is
used.

## Not in this file

Do not put patient identifiers or real serial numbers in a file you plan to share. Unit names that
identify a site are treated as identifiers and are kept out of logs and per-event exports.
