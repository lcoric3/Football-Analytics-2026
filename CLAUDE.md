I want to build this new project like my old football-machine-learning project:

https://github.com/lcoric3/football-machine-learning

First, inspect this current project. Then also inspect the old GitHub repo as inspiration. Do not copy blindly. Rebuild the idea in a cleaner and more professional way.

My old project had:

* football API data collection
* CSV datasets
* player statistics
* per-90 metrics
* HNL defender analysis
* HNL midfielder / Brighton-style analysis
* striker outputs
* First NL and Second NL outputs
* PyTorch goal prediction model
* train/test evaluation with MAE, RMSE, R2
* notebooks and charts

Now I want this new project to focus on SportMonks API and Croatian HNL / 1. HNL 2025/2026 player statistics.

Main goal:
Create a complete football data science and machine learning pipeline:
SportMonks API → raw data → cleaned data → feature engineering → scouting rankings → visualizations → ML-ready dataset → optional ML models.

Important rules:

* Do not hardcode API tokens.
* Read SportMonks token from environment variable SPORTMONKS_API_TOKEN.
* Keep main.py simple.
* Put most code inside src/.
* Explain each change before editing.
* Do not delete existing code without asking.
* I want to learn, so explain the football data science logic step by step.

Create this structure if missing:

Football-Analytics-2026/
├── main.py
├── requirements.txt
├── README.md
├── src/
│   ├── sportmonks_client.py
│   ├── fetch_data.py
│   ├── clean_data.py
│   ├── feature_engineering.py
│   ├── scouting_scores.py
│   ├── analysis.py
│   ├── visualization.py
│   └── ml_models.py
├── data/
│   ├── raw/
│   ├── processed/
│   └── output/
├── notebooks/
└── reports/
└── figures/

Step 1: API data collection

* Use SportMonks API.
* Fetch Croatian HNL / 1. HNL 2025/2026 player statistics.
* If league_id or season_id is needed, create helper functions to search/find them.
* Handle pagination, API errors, missing token, empty responses, and rate limits.
* Save raw JSON and CSV in data/raw/.

Step 2: Data cleaning
Create:
data/processed/hnl_player_stats_clean_2025_2026.csv

Useful columns:

* player_id
* player_name
* team_name
* position
* age
* nationality
* appearances
* minutes
* goals
* assists
* shots
* shots_on_target
* passes
* pass_accuracy
* tackles
* interceptions
* duels
* yellow_cards
* red_cards
* rating

Step 3: Feature engineering
Create per-90 metrics:

* goals_per90
* assists_per90
* shots_per90
* shots_on_target_per90
* passes_per90
* tackles_per90
* interceptions_per90
* cards_per90

Create additional ratios if data exists:

* shot_accuracy
* goal_conversion
* pass_accuracy_ratio
* duel_success_rate
* minutes_per_appearance
* goal_contribution_per90

Step 4: Scouting scores
Create explainable scores:

* attacking_score
* creative_score
* defensive_score
* discipline_score
* overall_score

Make the formulas simple and comment every formula.

Step 5: Analysis outputs
Create CSV rankings:

* top scorers
* top assists
* best U23 players if age exists
* best defenders
* best midfield creators
* best attackers
* best overall players
* best players by position

Save to:
data/output/top_players_hnl_2025_2026.csv

Step 6: Visualizations
Use matplotlib.
Create charts:

* top 10 goals per 90
* top 10 assists per 90
* top 10 overall scouting score
* best U23 players
  Save charts to reports/figures/.

Step 7: Machine learning
Create:
data/processed/hnl_ml_features_2025_2026.csv

Add simple ML ideas:

* player similarity with cosine similarity
* KMeans player clustering
* optional rating prediction if rating exists
* optional goals prediction only if enough data exists

If there is no good target variable yet, explain that this project is currently better for scouting/ranking and unsupervised ML than supervised prediction.

Step 8: README
Write a clear README explaining:

* what the project does
* how to set SPORTMONKS_API_TOKEN
* how to install requirements
* how to run main.py
* what files are generated
* what the scouting scores mean

Before editing, first give me a plan and list exactly which files you will create or modify.
