# AI Research Lab

AI Research Lab is a local-first, Windows research workspace for following a topic over time. It collects recent articles, keeps the collection history in a local vault, and writes readable Markdown notes for Obsidian or any ordinary folder.

Unlike a one-off search summary, the project is built to retain evidence over time: what changed, where material came from, how diverse the coverage is, and whether a claim has support from more than one source.

[Windows releases](https://github.com/EricLKIM/AI-Research-Lab/releases/latest)

## What it does

- Collects topic-focused news through Google News RSS, with an optional regional mix.
- Mixes in community material from Reddit, X, YouTube, Hacker News, and GDELT when those sources are enabled and configured.
- Stores collection snapshots locally for 7-, 30-, 90-, 180-, or 365-day trend analysis.
- Separates GPT-assisted findings into confirmed trends, emerging signals, and rumors.
- Adds a local data-quality summary: coverage, unique domains, duplication, unknown dates, platform mix, and region mix.
- Keeps a compact cross-topic tag index, so related analysis notes can provide limited supporting context without re-reading every Markdown file.
- Supports GDELT DOC API and GDELT dump-based backfill. A completed seven-day backfill can create a no-API baseline note.
- Saves human-readable notes outside the machine-data vault if you prefer.

The application treats rumors and community posts as signals to investigate, not as established facts.

## Quick start: Windows installer

Download the latest Windows installer from [Releases](https://github.com/EricLKIM/AI-Research-Lab/releases/latest), then run it.

On a first installation, Setup asks for:

- an OpenAI-compatible API key (optional until you run GPT-assisted work);
- an API base URL (optional; leave blank for the default OpenAI endpoint); and
- the folder where Obsidian-compatible Markdown notes should be written.

The installer language becomes the initial app and output language. API keys, app settings, and machine-readable collection data are stored per user, outside the application folder. Later installer updates preserve those settings; change them from the app when needed.

The installed app checks GitHub Releases in the background at startup. It shows an update button only when a newer release is available.

## A typical workflow

1. Add a topic in the desktop app and run **Topic Research**.
2. Let the app collect data on a schedule, or run it when you need an update.
3. For a new or incomplete topic, choose a backfill option to fill missing days.
4. Run **Trend Analysis** when you want a conclusion. It uses the current collection, saved time-series data, and a bounded amount of related cross-topic evidence.
5. Read the generated Markdown in Obsidian or your selected output folder.

The app does not run GPT trend analysis automatically. Scheduled collection is separate from manual analysis by design.

## Screens

### Topic Research

![Topic Research](assets/Topic_Search.gif)

### Trend Analysis

![Trend Analysis](assets/Analysis.gif)

## Installation

### Run from source

- Windows
- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/)
- An OpenAI-compatible API key for GPT-assisted summaries and analysis

Clone and install dependencies:

```powershell
git clone https://github.com/EricLKIM/AI-Research-Lab.git
cd AI-Research-Lab
uv sync
```

Create `.env` from `.env.example`, then set at least:

```env
OPENAI_API_KEY=your_api_key
OPENAI_API_BASE=https://api.openai.com/v1
```

`OPENAI_API_BASE` is optional. Leave it blank when using the default OpenAI endpoint.

Start the desktop app:

```powershell
run_app.bat
```

`diagnose_gui.bat` is available when the desktop app does not start. The repository also includes `run_topic_digest.bat` and `run_digest.bat` for the older command-line entry points.

### Windows release build

The release installer packages a folder of dedicated executables: the GUI plus the Topic Research, Backfill, Analysis, and scheduled-collection pipelines. Personal settings, API keys, and the vault are excluded.

```powershell
.\build_release.ps1
```

Then open `setup.iss` in Inno Setup and compile it. The installer is written to `installer\AI-Research-Lab-Setup-<version>.exe`; upload that `.exe` as the asset of a GitHub Release. Do not upload `setup.iss` itself as the downloadable application.

## Data and output locations

The app keeps machine-readable state separate from notes intended for reading.

| Content | Default location | Purpose |
|---|---|---|
| Snapshots, analysis state, tags, pending backfill work | Source checkout: `D:\ai-research-lab\vault`; installed app: `%LOCALAPPDATA%\AI Research Lab\vault` | Local machine data; not committed to Git |
| Markdown notes | Chosen in Settings, for example `C:\Users\<you>\Desktop\AI_research` | Obsidian or ordinary Markdown output |
| Optional raw GDELT dump cache | `vault\gdelt-cache` | Reusable local source archives |

The installed app keeps API keys, settings, favorites, and internal data under `%LOCALAPPDATA%\AI Research Lab`, outside the program folder. API keys are stored locally in `.env` as plain text, so use a device account you trust and do not share this folder.

The initialization helper clears only generated research data while preserving API keys, GUI settings, favorites, and `.obsidian` configuration:

```powershell
# Review the deletion plan
.venv\Scripts\python.exe scripts\initialize_research_data.py

# Apply it
.venv\Scripts\python.exe scripts\initialize_research_data.py --confirm
```

Run it only after closing the app.

## Sources and credentials

Google News RSS is the default latest-news source. GDELT is enabled by default for global news and backfill.

Community sources are optional and are configured in **Advanced Settings**.

| Source | Credential needed | Notes |
|---|---|---|
| Reddit | OAuth client ID, secret, and user agent | Uses Reddit's approved API path when configured |
| X | Bearer token | Availability and limits depend on the X API plan |
| YouTube | Data API key | Search consumes YouTube quota |
| Hacker News | None | Included only for AI and semiconductor topics |
| GDELT DOC | None | Public API; use conservatively because it can rate-limit |

GDELT dump downloads use HTTPS first. Some environments currently encounter a certificate hostname mismatch from the GDELT host. The app pauses and asks for explicit approval before using HTTP for that manual run. Scheduled collection never approves HTTP automatically. HTTP is less secure and should only be used when you accept that risk.

## Backfill and baselines

Backfill fills missing collection dates or, for a new topic, can build an initial baseline after you approve the prompt.

- **GDELT DOC API** works in time windows and uses response-aware waiting and retry behavior.
- **GDELT dump** downloads GKG blocks, filters them locally, and can keep or remove the raw archive cache.
- **Sample scan** uses balanced UTC windows for a faster, distributed sample. **Full scan** examines all listed blocks for the day.
- A seven-day backfill with enough material creates `*_7d_baseline.md`. It reports coverage and repeated signals; it is not a GPT conclusion.

The baseline is written to the Markdown output folder. Snapshots remain in the vault.

## Trend analysis

Trend Analysis is a single GPT call when its inputs have changed. Before calling the model, the app does local work to keep the request small:

- tags and source metadata are normalized locally;
- saved snapshots are aggregated over the selected period;
- up to five relevant cross-topic findings are used as supporting context;
- unchanged source input and unchanged context skip the GPT call.

The resulting note includes:

- confirmed trends, emerging signals, and rumors;
- time-series direction labels such as rising, falling, stable, or new;
- a data-quality section;
- any new alerts for high-confidence early signals, contradictions, rising signals, or weak coverage.

The Analysis tab also compares the most recent two non-cached runs. It lists new or disappeared signals, category changes, and large confidence changes.

### Custom tags

Advanced Settings includes a small tag dictionary editor. Add a canonical tag, comma-separated phrases to match, and optional parent tags. The editor stores its data in `vault\tag_dictionary.json` and applies it to future collections and later local re-aggregation of older snapshots.

## Scheduled collection

The app can register up to three Windows Task Scheduler collection times from Advanced Settings. The task starts when Windows becomes available and can recover missing snapshot dates on a later run.

Scheduled collection does not use HTTP fallback and does not run GPT Trend Analysis automatically.

## Limits and interpretation

This project helps organize evidence; it does not verify facts on its own.

- A source score or confidence score is an analytical aid, not a statement of truth.
- Reprints and copies of the same report are not independent confirmation.
- Emerging signals and rumors require primary-source checking before being used for decisions.
- Search results, API availability, quotas, and GDELT availability are controlled by external services.
- A sparse topic should be treated as an initial observation, even if the generated note looks polished.

For a useful first pass, aim for at least 20–30 unique articles from several domains. For a more stable seven-day trend, 30–50 unique articles across four or five collection dates is a reasonable starting point.

## Repository hygiene

The repository ignores API keys, GUI settings, the vault, GDELT cache, and local Obsidian configuration. Check `git status` before publishing changes and do not commit credentials or collected personal data.

## License

[MIT](LICENSE)
