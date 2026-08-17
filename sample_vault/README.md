# Sample Vault

This folder is a small, entirely synthetic research workspace. It contains no API keys, personal settings, scraped articles, or raw GDELT archives.

It is intended to show the files AI Research Lab keeps locally after several collections, a seven-day baseline, and a trend-analysis note. The examples use fictional sources and URLs so that they are safe to commit and share.

## Contents

- `vault/` contains machine-readable snapshots and a small tag dictionary.
- `markdown/` contains the Obsidian-facing baseline and analysis examples.

The data represents a fictional AI infrastructure topic across four collection dates, plus a small Semiconductors topic for cross-topic context. It is not real research and should not be used as evidence.

## Try it safely

Open the Markdown files in `markdown/` directly with Obsidian or a text editor. No API key is needed.

To inspect the time-series inputs from the application, copy the *contents* of `sample_vault/vault` into a separate, empty AI Research Lab data folder. Do not merge it into a vault that contains your own research data.

For a source checkout, the default target is `vault/`. For an installed app, the default target is `%LOCALAPPDATA%\AI Research Lab\vault`.

The sample deliberately does not include raw GDELT cache files. Those archives are large and are not needed to demonstrate local snapshot, baseline, tag, or analysis behavior.
