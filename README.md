# Football-Analytics-2026

A football data science and machine learning pipeline for Croatian HNL (1. HNL)
2025/2026 player statistics, built on the [SportMonks](https://www.sportmonks.com/)
Football API.

## What it does

The pipeline turns raw SportMonks player statistics into scouting-ready
rankings, charts, and an ML-ready dataset:

```
SportMonks API -> raw data -> cleaned data -> feature engineering
-> scouting scores -> analysis rankings -> visualizations -> ML dataset
```

## Setup

### 1. Get a SportMonks API token

Sign up at SportMonks and copy your API token. **Never hardcode the token
in code** - it is always read from the environment variable
`SPORTMONKS_API_TOKEN`.

Set it for your current PowerShell session:

```powershell
$env:SPORTMONKS_API_TOKEN = "your_token_here"
```

Or create a `.env` file in the project root (already covered by
`.gitignore`, never commit it):

```
SPORTMONKS_API_TOKEN=your_token_here
```

### 2. (Optional) override league/season lookup

`fetch_data.py` automatically searches SportMonks for the "HNL" league and
its "2025/2026" season. If your subscription names them differently (or
the search returns more than one candidate), skip the lookup by setting:

```
HNL_LEAGUE_ID=<id>
HNL_SEASON_ID=<id>
```

### 3. Install requirements

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 4. Run the pipeline

```powershell
python main.py
```

## Project structure

```
Football-Analytics-2026/
├── main.py                  # Orchestrator - runs each pipeline stage in order
├── requirements.txt
├── src/
│   ├── sportmonks_client.py # API client: auth, pagination, retries, rate limits
│   ├── fetch_data.py        # Finds HNL league/season, fetches player stats
│   ├── clean_data.py        # Raw JSON/CSV -> clean flat schema
│   ├── feature_engineering.py # Per-90 metrics and ratios
│   ├── scouting_scores.py   # Attacking/creative/defensive/discipline/overall scores
│   ├── analysis.py          # Ranking tables (top scorers, best defenders, etc.)
│   ├── visualization.py     # matplotlib charts
│   └── ml_models.py         # Similarity, clustering, optional regression
├── data/
│   ├── raw/                 # Raw SportMonks JSON + CSV
│   ├── processed/           # Cleaned + feature-engineered CSVs
│   └── output/               # Final ranking CSVs
├── notebooks/                # Exploratory analysis
└── reports/figures/          # Generated charts
```

## Generated files

| File | Produced by | Description |
|---|---|---|
| `data/raw/hnl_player_stats_raw_2025_2026.json` / `.csv` | `fetch_data.py` | Raw SportMonks API response |
| `data/processed/hnl_player_stats_clean_2025_2026.csv` | `clean_data.py` | Cleaned, flat player statistics |
| `data/processed/hnl_player_features_2025_2026.csv` | `feature_engineering.py` | Adds per-90 metrics and ratios |
| `data/processed/hnl_player_scored_2025_2026.csv` | `scouting_scores.py` | Adds scouting scores |
| `data/output/top_players_hnl_2025_2026.csv` | `analysis.py` | Ranking tables (top scorers, defenders, etc.) |
| `reports/figures/*.png` | `visualization.py` | Charts |
| `data/processed/hnl_ml_features_2025_2026.csv` | `ml_models.py` | ML-ready dataset |

## Scouting scores

Raw per-90 metrics live on very different scales (a good `goals_per90` is
~0.5, a good `passes_per90` is ~50), so they can't be averaged directly.
Every score below is built from **percentile ranks**: each metric is
converted to "this player is better than X% of HNL players in this stat"
(0-100), which puts everything on the same scale before combining it.

Scores are only computed for players with at least 450 minutes played
(~5 full matches) - below that, per-90 rates are too noisy (a single
lucky goal in 30 minutes would look like a superstar rate) and the score
is left blank (`NaN`) instead of being misleading.

| Score | Built from (percentile of...) |
|---|---|
| `attacking_score` | `goals_per90`, `shots_on_target_per90`, `goal_conversion` |
| `creative_score` | `assists_per90`, `passes_per90`, `pass_accuracy_ratio` |
| `defensive_score` | `tackles_per90`, `interceptions_per90`, `duel_success_rate` |
| `discipline_score` | 100 minus percentile of `cards_per90` (fewer cards = higher score) |
| `overall_score` | `0.3 * attacking + 0.3 * creative + 0.3 * defensive + 0.1 * discipline` |

These percentiles are computed across the *whole* player pool, not per
position - a centre-back will rarely have a high `attacking_score`, which
is expected. `analysis.py` handles position-aware rankings (e.g. "best
defenders") by filtering to a position group first, then sorting by the
relevant score within that group.

## Machine learning notes

`ml_models.py` builds `data/processed/hnl_ml_features_2025_2026.csv` from
players who cleared the same 450-minute eligibility bar, using only
per-90/ratio features (never raw totals, so playing time doesn't bias
the comparison). Three things are done with it:

- **Player similarity (cosine similarity):** standardizes each feature,
  then measures the angle between two players' stat vectors. Close to
  1.0 means "similar statistical profile", independent of team or league
  position.
- **KMeans clustering:** groups players into 4 clusters purely by
  statistical similarity, with no notion of position or team - useful for
  discovering play-style archetypes (e.g. a "destroyer" cluster with high
  tackles/interceptions and low pass volume vs. a "deep playmaker"
  cluster with the opposite profile).
- **Optional supervised prediction (rating, goals):** both are skipped
  automatically, with an explanation logged, if there are fewer than 30
  eligible players. Even when they run, treat the results cautiously:
  - `rating` is itself partly derived from the same match events as our
    features, so a good R2 mostly confirms the features are sensible
    rather than predicting something genuinely new.
  - `goals` prediction deliberately excludes any feature derived from
    goals (`goals_per90`, `goal_conversion`, etc.) to avoid leaking the
    answer into the input - it predicts from raw shot/pass/defensive
    volume instead.

**Bottom line:** with one HNL season (a few hundred players), this
project is currently a stronger fit for scouting/ranking and unsupervised
ML (similarity, clustering) than for supervised prediction. Multiple
seasons of history would give a regression model enough rows and a
clearer signal to be worth trusting.
