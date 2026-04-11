# Tax Pack Country Template

This directory is a starter pack for onboarding a new country or new tax-domain pack.

It is a scaffold, not a publishable skill as-is.

## How To Use

1. Copy this directory to `skills/tax-pack-<country>-<domain>/`.
2. Replace the placeholder values:
   - `tax-pack-xx-einvoice`
   - `XX`
   - `xx-example-profile`
   - URLs, hints, and authority names
3. Adjust the overlay or switch to a different family parser if EN16931/UBL does not fit.
4. Add a real fixture PDF and generate a trusted baseline.
5. Run the pack through `test` and `quality-gate`.

## Files To Edit First

- `pack.json`
- `profiles/registry.json`
- `profiles/overlays/country_overlay.py`
- `sources/official_sources.yaml`

## Expected Destination Layout

After copying, your real pack should live next to `skills/tax-parser-core`, for example:

```text
skills/
  tax-parser-core/
  tax-pack-pl-einvoice/
```

That sibling layout is required because `scripts/pack_cli.py` resolves the core skill relative to the installed pack directory.
