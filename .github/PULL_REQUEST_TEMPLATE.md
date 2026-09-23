<!--
PR titles must be Conventional Commits (enforced by .github/workflows/pr-title.yml):
main is squash-merge only, so the title becomes the commit message release-please reads.
Mark a PR breaking (`!` + a `BREAKING CHANGE:` footer) if it changes render_key inputs,
the TTS plugin protocol or the project directory schema.
-->

## What changed

<!-- One or two sentences. Link the issue if there is one. -->

## Checklist

- [ ] Requirement IDs implemented or touched: <!-- e.g. DG-02, JB-05 -->
- [ ] Tests added or updated (unit / golden / integration)
- [ ] Docs updated (docs/**, or "n/a")
- [ ] No new dependency, or: license is on the allow list and NOTICE regenerated
- [ ] No change to render_key inputs / plugin protocol / project schema, or marked breaking
- [ ] Strings go through i18next and both en and pl catalogues are updated

## How it was verified

<!-- The command you ran, and anything a reviewer should look at closely. -->
