---
name: tax-law-parser
description: Single user-facing entry point for uploaded tax-law PDFs. Try installed country packs first, parse with the best matching profile, and internally route to onboarding, repair, or publish-back workflows based on parser state instead of requiring the user to ask for those workflows explicitly.
---

## What I do

- Accept an uploaded tax or eInvoice PDF as the primary user input.
- Try existing installed packs and profiles first.
- Return parsed output when the current system already knows how to handle the document.
- Internally route to onboarding, repair, or publish-back workflows when parsing state requires it.

## When to use me

- The user uploads or references a tax-law PDF and wants it parsed.
- The user does not know which country pack or profile should be used.
- The user only expresses the business goal: parse the document.

## Frontdoor rule

Do not require the user to ask:

- how to onboard a new country
- how to repair a drifting parser
- how to publish a local fix back to GitHub

Those are backend workflows, not user-facing entry points.

## Default runtime path

1. Identify whether the PDF matches an existing installed pack/profile.
2. If yes, run the known parser path first.
3. If parsing succeeds and validation is acceptable, return the output.
4. If no profile matches, enter onboarding workflow.
5. If a profile matches but the result drifts or gate fails, enter repair workflow.
6. If a local fix passes validation and should become upstream truth, enter publish-back workflow.

## State-based routing

### `parse_success`

Conditions:

- profile matched
- parser ran successfully
- validation passed
- stable profiles also pass gate

Action:

- return the result to the user

### `parse_no_match`

Condition:

- no existing profile can reasonably parse the PDF

Action:

- switch to the new-country or new-document-family onboarding workflow
- use [$tax-pack-onboarding](/Users/xueyunsong/Documents/GitHub/gec-ai/skills/tax-pack-onboarding/SKILL.md)

### `parse_drift_detected`

Condition:

- profile matched, but output compare or gate indicates drift

Action:

- repair the existing pack first
- prefer pack-local fixes over `core` changes

### `local_fix_validated`

Condition:

- local fix now passes `test` and `quality-gate`

Action:

- if the fix should become upstream truth, use [$tax-pack-publish-back](/Users/xueyunsong/Documents/GitHub/gec-ai/skills/tax-pack-publish-back/SKILL.md)

## Hard rules

- Treat this skill as the only user-facing entry for parsing PDFs.
- Do not expose onboarding or publish-back as the first thing the user must decide.
- Prefer installed country packs over ad hoc one-off parser changes.
- Prefer pack-local repair before changing shared `tax-parser-core`.
- Do not treat a local installed-skill edit as upstream truth until publish-back is complete.

## Expected behavior

The user experience should stay simple:

- user gives PDF
- system tries known parser
- system handles engineering branching internally

The engineering complexity belongs behind this frontdoor, not in the user's prompt.
