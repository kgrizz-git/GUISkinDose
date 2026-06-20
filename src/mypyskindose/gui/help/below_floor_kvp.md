# Below-floor kVp handling

The half-value-layer (HVL) table that drives the backscatter (`k_bs`) and medium
(`k_med`) corrections is tabulated down to a **floor of 25 kV**. Events recorded
below that floor have no tabulated beam quality.

Pick how MyPySkinDose should handle such events:

- **Snap to grid edge (default)** — leave the kVp as-is. The HVL lookup clamps the
  event to the lowest tabulated kVp (25 kV) and flags it as `clamped`. This
  preserves historical behavior; results never change silently.
- **Skip (drop the events)** — remove the below-floor events entirely so they
  contribute no dose. Use when sub-floor events are spurious (e.g. test exposures).
- **Substitute a manual kVp** — replace every below-floor kVp with a value you
  enter. Use when you know the true technique factor.
- **Substitute the exam-average kVp** — replace every below-floor kVp with the
  mean kVp of that exam's in-floor events. Computed per exam, so multi-exam runs do
  not cross-contaminate. If an exam has *no* in-floor event, it falls back to snap.

Whatever you pick is applied **before** the HVL lookup, and every affected event is
reported in the post-calculation warnings. When below-floor events are detected,
you are also prompted at calculation time to confirm the policy for that run.
