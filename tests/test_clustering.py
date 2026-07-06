"""
Tests for src/ml_models.py's player clustering (Stage B5) - cluster_players,
build_cluster_profiles_report, and save_cluster_outputs.
"""
import pandas as pd

from src import ml_models


def test_cluster_players_assigns_cluster_id_and_name(scored_df):
    ml_df = ml_models.build_ml_dataset(scored_df)

    clustered = ml_models.cluster_players(ml_df, n_outfield_clusters=2, n_goalkeeper_clusters=2)

    assert "cluster_id" in clustered.columns
    assert "cluster_name" in clustered.columns
    assert clustered["cluster_id"].notna().all()


def test_no_empty_cluster_names(scored_df):
    ml_df = ml_models.build_ml_dataset(scored_df)

    clustered = ml_models.cluster_players(ml_df, n_outfield_clusters=2, n_goalkeeper_clusters=2)

    assert clustered["cluster_name"].notna().all()
    assert (clustered["cluster_name"].str.strip() != "").all()


def test_too_few_players_falls_back_to_neutral_label(scored_df):
    """With the default N_OUTFIELD_CLUSTERS (8), the tiny synthetic fixture
    (6 eligible outfield players) doesn't have enough rows to cluster
    meaningfully - those rows should get a neutral "not enough" label
    instead of a forced KMeans grouping."""
    ml_df = ml_models.build_ml_dataset(scored_df)

    clustered = ml_models.cluster_players(ml_df)

    outfield = clustered[clustered["position"] != "Goalkeeper"]
    assert (outfield["cluster_name"] == "Not enough players to cluster").all()
    assert outfield["cluster_id"].isna().all()


def test_player_clusters_csv_and_report_can_be_created_from_synthetic_data(
    scored_df, tmp_path, monkeypatch,
):
    """save_cluster_outputs() should write a real CSV (with the expected
    columns) and a real Markdown report, using only synthetic data - no
    API/.env involved."""
    ml_df = ml_models.build_ml_dataset(scored_df)
    clustered = ml_models.cluster_players(ml_df, n_outfield_clusters=2, n_goalkeeper_clusters=2)

    csv_path = tmp_path / "player_clusters.csv"
    report_path = tmp_path / "player_cluster_profiles.md"
    monkeypatch.setattr(ml_models, "CLUSTERS_OUTPUT_CSV_PATH", str(csv_path))
    monkeypatch.setattr(ml_models, "CLUSTER_PROFILES_REPORT_PATH", str(report_path))

    ml_models.save_cluster_outputs(clustered)

    assert csv_path.exists()
    saved = pd.read_csv(csv_path)
    assert list(saved.columns) == ml_models.CLUSTER_CSV_COLUMNS
    assert saved["cluster_id"].notna().all()
    assert (saved["cluster_name"].str.strip() != "").all()

    assert report_path.exists()
    report_text = report_path.read_text(encoding="utf-8")
    assert report_text.startswith("# Player Cluster Profiles")
