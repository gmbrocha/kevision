# Known limitations — delta_v2 denoise pipeline

Tracker for issues we deliberately ship past so we can come back later.
Each entry: what breaks, why, who's affected, mitigation idea.

---

## 1. Thin Δ base collinear with a long thin horizontal feature

**Source:** `run_denoise_bases_fixed.py` (thickness-aware horizontal mask).

**Failure mode:** A Δ marker whose base sits on the same horizontal scanline as
another long thin horizontal feature (e.g., a dimension line, a hatching tick
that happens to be exactly collinear, a thin grid line) will be wiped.

**Why:** The thickness-aware mask classifies each long horizontal run by
whether it contains *any* thick portion. Wall + Δ base = mixed (we keep the
base). But thin dimension line + Δ base = uniformly thin → entire run masked,
including the base.

**Who hits this:** Probably rare on real drawings — Δ markers are usually
placed near walls (which are thick), not near other thin annotations. But it
will eventually surface on plans with dense dimensioning.

**Mitigation ideas (when we revisit):**
1. Add a "digit-halo protect" pass on top: any pixel within ~80px of a
   pure-upright-numeric word bbox is exempt from masking entirely.
2. Localize the thickness rule per-segment instead of per-component: split
   each long run into segments and apply the mask on a per-segment basis,
   so a thin segment touching a wall in one place isn't penalized for being
   thin in another.
3. Prefer 2D shape priors: for any uniformly-thin long run, additionally
   check whether its midpoint is inside a candidate triangle outline (Δ
   base) before deciding to mask.
