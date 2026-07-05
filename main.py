"""
Football-Analytics-2026 pipeline orchestrator.

Runs the full HNL 2025/2026 pipeline in order:
SportMonks API -> raw data -> cleaned data -> feature engineering
-> scouting scores -> analysis rankings -> visualizations -> ML dataset
-> Markdown report

Each stage lives in its own src/ module and reads the previous stage's
output file, so this file just calls them in sequence.
"""
import os
import sys

from dotenv import load_dotenv

from src import fetch_data
from src import clean_data
from src import feature_engineering
from src import scouting_scores
from src import analysis
from src import visualization
from src import ml_models
from src import report


def main():
    load_dotenv()

    if not os.getenv("SPORTMONKS_API_TOKEN"):
        print(
            "ERROR: SPORTMONKS_API_TOKEN is not set.\n"
            "Set it as an environment variable or put it in a .env file:\n"
            "  SPORTMONKS_API_TOKEN=your_token_here"
        )
        sys.exit(1)

    print("Step 1/8: Fetching player statistics from SportMonks API...")
    fetch_data.run()

    print("Step 2/8: Cleaning raw data...")
    clean_data.run()

    print("Step 3/8: Engineering per-90 and ratio features...")
    feature_engineering.run()

    print("Step 4/8: Computing scouting scores...")
    scouting_scores.run()

    print("Step 5/8: Building ranking analysis...")
    analysis.run()

    print("Step 6/8: Generating charts...")
    visualization.run()

    print("Step 7/8: Building ML-ready dataset and running ML models...")
    ml_models.run()

    print("Step 8/8: Writing the Markdown scouting report...")
    report.run()

    print("Pipeline complete.")


if __name__ == "__main__":
    main()
