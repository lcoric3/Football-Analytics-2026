"""
Stage 4: explainable scouting scores.

Football data science logic:
Per-90 metrics live on very different scales - a good goals_per90 is
~0.5, a good passes_per90 is ~50. You can't just average them together.

The simple, explainable fix used here is a *percentile rank*: for each
metric, every player gets a score from 0 to 100 for where they rank
compared to other players ("you are better than X% of HNL players in
this stat"). Percentiles are unitless and always on a 0-100 scale, so
they can be safely averaged into a composite score.

Position-aware percentiles:
attacking_score, creative_score, defensive_score and progressive_
midfielder_score are ranked *within each position group* (Defender vs.
Defender, Midfielder vs. Midfielder, ...) rather than against the whole
pool. Two reasons:
  1. A defender's attacking_score computed against the whole pool (which
     is mostly attackers/midfielders) is close to meaningless noise - it
     mostly measures "is this player not a defender". Ranked against other
     defenders, it instead answers "does this defender contribute more
     going forward than most defenders?", which is what a scout actually
     wants to know.
  2. It removes overall_score's old bias toward all-rounder midfielders:
     previously a specialist (pure striker, pure destroyer) always lost to
     a decent-at-everything midfielder, because the specialist's weak
     dimensions were judged against the whole pool including players whose
     whole job is that dimension. Judged against positional peers instead,
     a specialist can top out all three dimensions relative to what's
     normal for their role.
Dribbling/passing/duel-defending scores are deliberately kept pool-wide
(no position grouping) - they're meant to answer "who are the best
dribblers/passers/ball-winners in the league", the same kind of absolute
leaderboard as top_scorers/top_assists in analysis.py, not "best dribbler
for a defender".

Small-sample guard: per-90 rates are noisy for players with little playing
time (one substitute appearance with a lucky goal can produce an absurd
goals_per90). Players below MIN_MINUTES_FOR_SCORES are excluded from the
percentile calculation entirely and get a NaN score, rather than letting
them distort the ranking or occupy a false top spot.

Goalkeepers and overall_score:
attacking_score/creative_score/defensive_score are built from outfield
actions (goals, assists, tackles, passes...) that goalkeepers barely
produce. Even judged only against other goalkeepers (position-aware
percentiles), a goalkeeper's attacking_score is close to a coin flip -
nearly every keeper has ~0 goals/shots/conversion, so percentile-ranking
a field of ties just distributes essentially the same score to everyone,
and adding that into overall_score can let a keeper with clean passing
stats and a low card count outrank real outfield performers on "overall".
Goalkeeping is a different job that needs different inputs (saves, clean
sheets, goals conceded, penalties saved) - see goalkeeper_score below.
analysis.py excludes goalkeepers from best_overall/best_u23 and ranks
them separately as best_goalkeepers, by goalkeeper_score instead.

age_potential_score (Stage B1):
A young-player scouting lens on top of overall_score - see the formula's
own comment further down for the full breakdown. In short: it's
overall_score plus a small, capped bonus for being young (age_bonus) and
a small bonus for already earning real first-team minutes at that age
(reliability_bonus), so it stays additive and explainable rather than
another opaque percentile blend. Like overall_score, it inherits the
"outfield only" caveat - it's not a meaningful lens for goalkeepers.

Team-context scoring and underrated_score (Stage B2):
overall_score is computed against the whole HNL player pool, so it never
asks "compared to their own teammates". team_average_score (a team's own
mean overall_score, outfield eligible players only) and
score_above_team_average (a player's gap above/below that) add that
context. underrated_score then rewards two things on top of raw quality:
outperforming your own team, and playing for a squad whose average
outfield output sits below the league's average team - a reproducible
proxy for "good player, low visibility", replacing the old fixed
BIG_CLUBS exclusion list in report.py. See the formula's own comment
further down for the exact weights/caps. This is a statistical proxy, not
a market-value or "true team strength" model - see the report's
limitations section.
"""
import logging
import os

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

FEATURES_CSV_PATH = "data/processed/hnl_player_features_2025_2026.csv"
SCORED_CSV_PATH = "data/processed/hnl_player_scored_2025_2026.csv"

# ~5 full matches - below this, per-90 rates are considered too noisy to score.
MIN_MINUTES_FOR_SCORES = 450

# --- age_potential_score constants (Stage B1) -----------------------------
# Age below which a player counts as "young" for age_bonus - matches
# analysis.py's U23_AGE_LIMIT, the "young player" cutoff used everywhere
# else in this project.
AGE_POTENTIAL_AGE_CUTOFF = 23
# age_bonus grows by this many points for every year younger than the cutoff.
AGE_BONUS_PER_YEAR = 2.0
# ...but the bonus is capped at this many years below the cutoff, so a
# 15-year-old doesn't get an implausibly bigger bonus than a 17-year-old -
# both hit the same ceiling (age 17 and under all score the max bonus).
AGE_BONUS_CAP_YEARS = 6
# reliability_bonus - a percentile rank of minutes played, scaled down to
# at most this many points, so it can nudge age_potential_score without
# ever swamping the underlying overall_score.
RELIABILITY_BONUS_MAX = 8.0

# --- underrated_score constants (Stage B2) --------------------------------
# Caps (in overall_score points, before weighting) on how large a single
# team-context gap is allowed to grow before its bonus stops increasing.
STANDOUT_BONUS_CAP = 30
WEAK_TEAM_BONUS_CAP = 30
# Both bonuses are weighted equally - neither "outperforms their own team"
# nor "plays for a weaker team" alone should be worth more than the other.
STANDOUT_BONUS_WEIGHT = 0.5
WEAK_TEAM_BONUS_WEIGHT = 0.5


def _percentile(series, eligible, group=None):
    """Rank a metric from 0 (worst) to 100 (best), computed only among
    `eligible` players; ineligible players get NaN instead of a score.

    If `group` is given (e.g. the position column), the percentile is
    computed separately within each group value, so a player is only ever
    compared to peers in the same group - see the module docstring for why
    this matters for cross-position fairness."""
    result = pd.Series(np.nan, index=series.index)
    if group is None:
        result.loc[eligible] = series.loc[eligible].rank(pct=True, method="average") * 100
    else:
        eligible_values = series.loc[eligible]
        eligible_groups = group.loc[eligible]
        result.loc[eligible] = eligible_values.groupby(eligible_groups).rank(
            pct=True, method="average"
        ) * 100
    return result


def add_scores(df):
    df = df.copy()
    eligible = df["minutes"] >= MIN_MINUTES_FOR_SCORES
    position = df["position"]

    # attacking_score: how much of a goal threat is this player *relative to
    # others in the same position*? (goal output, shot volume on target,
    # finishing quality). Position-aware so a defender's attacking_score
    # reflects "does more going forward than most defenders", not "barely
    # registers next to a striker".
    df["attacking_score"] = (
        _percentile(df["goals_per90"], eligible, group=position)
        + _percentile(df["shots_on_target_per90"], eligible, group=position)
        + _percentile(df["goal_conversion"], eligible, group=position)
    ) / 3

    # creative_score: how much does this player create/build play, relative
    # to positional peers? (assists, passing volume, passing quality)
    df["creative_score"] = (
        _percentile(df["assists_per90"], eligible, group=position)
        + _percentile(df["passes_per90"], eligible, group=position)
        + _percentile(df["pass_accuracy_ratio"], eligible, group=position)
    ) / 3

    # defensive_score: how much defensive work does this player do, and win,
    # relative to positional peers? (tackles, interceptions, duel success)
    df["defensive_score"] = (
        _percentile(df["tackles_per90"], eligible, group=position)
        + _percentile(df["interceptions_per90"], eligible, group=position)
        + _percentile(df["duel_success_rate"], eligible, group=position)
    ) / 3

    # discipline_score: fewer cards per 90 = higher score (100 - percentile
    # of cards_per90, so a player with the most cards scores near 0). Kept
    # pool-wide (not position-aware) - card discipline isn't a role skill.
    df["discipline_score"] = 100 - _percentile(df["cards_per90"], eligible)

    # dribbling_score: beats defenders and keeps the ball, judged league-wide
    # (this is meant to answer "who are the best dribblers in HNL", not
    # "best dribbler for a centre-back"). Combines volume (successful
    # dribbles per90), quality (% of attempts that succeed - so a player who
    # tries 10 to land 2 doesn't outscore one who tries 3 to land 2), and
    # fouls drawn per90 as a proxy for "hard to stop legally".
    df["dribbling_score"] = (
        _percentile(df["successful_dribbles_per90"], eligible)
        + _percentile(df["dribble_success_rate"], eligible)
        + _percentile(df["fouls_drawn_per90"], eligible)
    ) / 3

    # passing_score: distribution quality *and* volume, league-wide. Pass
    # accuracy is deliberately only one of five equally-weighted ingredients
    # here - a center-back playing safe five-yard passes all game can hit
    # 95% accuracy without creating anything, so key passes (passes that
    # lead to a shot), accurate long balls (range/risk), and accurate
    # crosses (final-third delivery) are weighted the same as accuracy.
    df["passing_score"] = (
        _percentile(df["passes_per90"], eligible)
        + _percentile(df["key_passes_per90"], eligible)
        + _percentile(df["accurate_crosses_per90"], eligible)
        + _percentile(df["accurate_long_balls_per90"], eligible)
        + _percentile(df["pass_accuracy_ratio"], eligible)
    ) / 5

    # duel_defending_score: pure ball-winning ability, league-wide (tackles,
    # interceptions, aerials won, and duel success rate cover ground duels,
    # aerial duels, and anticipation together). Cards are penalized lightly
    # (5% weight) - persistent fouling/carding to win duels should cost a
    # little, not dominate an otherwise elite defensive score.
    df["duel_defending_score"] = (
        _percentile(df["tackles_per90"], eligible)
        + _percentile(df["interceptions_per90"], eligible)
        + _percentile(df["duel_success_rate"], eligible)
        + _percentile(df["aerials_won_per90"], eligible)
        + _percentile(df["clearances_per90"], eligible)
    ) / 5 - 0.05 * _percentile(df["cards_per90"], eligible)

    # progressive_midfielder_score: SportMonks doesn't expose true
    # "progressive passes/carries into the final third" for this plan, so
    # this is a proxy built from what is available: key passes (passing
    # that directly creates chances), long balls (moving the ball forward
    # in bulk), successful dribbles (progressing the ball by foot), and
    # assists (the end product of progression). Position-aware, so it's
    # judged against a player's own position group - meant to be read for
    # midfielders (analysis.py filters to position="Midfielder" for the
    # "best progressive midfielders" ranking).
    df["progressive_midfielder_score"] = (
        _percentile(df["key_passes_per90"], eligible, group=position)
        + _percentile(df["long_balls_per90"], eligible, group=position)
        + _percentile(df["successful_dribbles_per90"], eligible, group=position)
        + _percentile(df["assists_per90"], eligible, group=position)
    ) / 4

    # passer_defender_score (a.k.a. ball-playing defender score): half
    # passing quality, half proven defensive reliability. The passing half
    # is computed within-position (a defender's passing volume compared to
    # other defenders, not to central midfielders who naturally pass far
    # more often) using passes per90, pass accuracy, accurate long balls,
    # and key passes. The defensive half simply reuses defensive_score
    # (already computed above), so this score rewards defenders who
    # combine reliable defending with genuine ball-playing range - not just
    # any decent passer. Meant to be read for defenders (analysis.py
    # filters to position="Defender" for the ranking).
    passer_defender_passing = (
        _percentile(df["passes_per90"], eligible, group=position)
        + _percentile(df["pass_accuracy_ratio"], eligible, group=position)
        + _percentile(df["accurate_long_balls_per90"], eligible, group=position)
        + _percentile(df["key_passes_per90"], eligible, group=position)
    ) / 4
    df["passer_defender_score"] = 0.5 * passer_defender_passing + 0.5 * df["defensive_score"]

    # goalkeeper_score: a separate model for a different job. Computed only
    # among goalkeepers (the eligible+Goalkeeper mask below), from stats
    # that actually measure goalkeeping: shot-stopping volume (saves per90),
    # match outcomes while playing (clean sheet rate), goals conceded per90
    # (inverted - fewer conceded is better), penalties saved, and passing
    # accuracy as a simple proxy for distribution quality. Not used in
    # overall_score and not compared to outfield players - see the module
    # docstring for why.
    goalkeeper_eligible = eligible & (position == "Goalkeeper")
    df["goalkeeper_score"] = (
        _percentile(df["saves_per90"], goalkeeper_eligible)
        + _percentile(df["clean_sheet_rate"], goalkeeper_eligible)
        + (100 - _percentile(df["goals_conceded_per90"], goalkeeper_eligible))
        + _percentile(df["penalties_saved"], goalkeeper_eligible)
        + _percentile(df["pass_accuracy_ratio"], goalkeeper_eligible)
    ) / 5

    # overall_score: weighted blend of the four core scores above.
    # Attacking/creative/defensive are weighted equally (0.3 each) since a
    # scouting view should value all three roles similarly; discipline is
    # a smaller factor (0.1) - it matters, but shouldn't dominate the
    # ranking of an otherwise excellent player. Because the three role
    # scores are now position-aware, this composite no longer structurally
    # favors all-rounder midfielders over positional specialists.
    df["overall_score"] = (
        0.3 * df["attacking_score"]
        + 0.3 * df["creative_score"]
        + 0.3 * df["defensive_score"]
        + 0.1 * df["discipline_score"]
    )

    # age_potential_score (Stage B1): a young-player scouting lens.
    # overall_score alone treats a promising 19-year-old the same as a
    # 30-year-old journeyman posting an identical score today - it says
    # nothing about future upside. Rather than build yet another opaque
    # percentile blend, age_potential_score stays a simple, fully traceable
    # sum of three explainable ingredients:
    #
    #   age_potential_score = overall_score + age_bonus + reliability_bonus
    #
    # age_bonus: rewards being younger than AGE_POTENTIAL_AGE_CUTOFF (23),
    # tapering linearly and capped at AGE_BONUS_CAP_YEARS years below the
    # cutoff (see the constants above) - e.g. with the defaults, a 20-year-old
    # gets +6, a 17-year-old (or younger) gets the capped max of +12, and a
    # 23-year-old or older gets +0.
    years_below_cutoff = (AGE_POTENTIAL_AGE_CUTOFF - df["age"]).clip(
        lower=0, upper=AGE_BONUS_CAP_YEARS
    )
    df["age_bonus"] = years_below_cutoff * AGE_BONUS_PER_YEAR

    # reliability_bonus: a young player who already plays regular first-team
    # minutes is a safer scouting bet than one with the same rates from only
    # a handful of cameos - rewarded as a percentile rank of `minutes` among
    # all scoring-eligible players (pool-wide - playing-time trust isn't a
    # positional skill), scaled down to at most RELIABILITY_BONUS_MAX points.
    minutes_percentile = _percentile(df["minutes"], eligible)
    df["reliability_bonus"] = minutes_percentile / 100 * RELIABILITY_BONUS_MAX

    df["age_potential_score"] = df["overall_score"] + df["age_bonus"] + df["reliability_bonus"]

    # --- team-context scoring: team_average_score, score_above_team_average,
    # --- underrated_score (Stage B2) ---------------------------------------
    # overall_score alone says nothing about context: the same score means
    # more from a player carrying a weak side than from a player surrounded
    # by a stacked XI. This block adds three plain, comment-explained
    # columns - never a hidden model of "true" team strength or market
    # value (see the report's caveat for that limitation).
    #
    # team_average_score: the mean overall_score of a team's own eligible
    # *outfield* players (goalkeepers excluded - same reasoning as
    # best_overall/best_u23 in analysis.py: overall_score isn't a meaningful
    # measure of goalkeeping quality, so mixing keepers in would distort a
    # team's average for no good reason). This is a simple proxy for "how
    # strong is this squad's individual outfield output" - not a form table,
    # not a results-based measure.
    outfield_eligible = eligible & (position != "Goalkeeper")
    team_average_score = (
        df.loc[outfield_eligible].groupby("team_name")["overall_score"].mean()
    )
    df["team_average_score"] = df["team_name"].map(team_average_score)

    # score_above_team_average: how far this player's own overall_score sits
    # above (or below) their team's average - a literal gap, not a
    # percentile. Positive means "outperforms their own teammates".
    df["score_above_team_average"] = df["overall_score"] - df["team_average_score"]

    # underrated_score = overall_score + standout_bonus + weak_team_bonus.
    # Two capped, equally-weighted bonuses on top of raw quality - a genuine
    # "hidden gem" still has to be a good player first (overall_score), not
    # merely someone who happens to play for a weak team:
    #
    # standout_bonus: only the *positive* part of score_above_team_average
    # counts (underperforming your own team isn't "underrated"), capped at
    # STANDOUT_BONUS_CAP points before weighting so one extreme gap can't
    # dominate the score by itself.
    standout_gap = df["score_above_team_average"].clip(lower=0, upper=STANDOUT_BONUS_CAP)
    df["standout_bonus"] = standout_gap * STANDOUT_BONUS_WEIGHT

    # weak_team_bonus: rewards playing for a squad whose average outfield
    # output sits below the *league's* average team (computed here, per
    # team, then averaged across teams so one big squad with many
    # just-eligible players can't outweigh a small squad with a few elite
    # ones) - a reproducible, data-driven stand-in for "surrounded by less
    # individual talent", instead of a fixed list of "big clubs".
    league_average_team_score = team_average_score.mean()
    weak_team_gap = (league_average_team_score - df["team_average_score"]).clip(
        lower=0, upper=WEAK_TEAM_BONUS_CAP
    )
    df["weak_team_bonus"] = weak_team_gap * WEAK_TEAM_BONUS_WEIGHT

    df["underrated_score"] = df["overall_score"] + df["standout_bonus"] + df["weak_team_bonus"]

    return df


def run():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if not os.path.exists(FEATURES_CSV_PATH):
        raise FileNotFoundError(f"{FEATURES_CSV_PATH} not found. Run feature_engineering.run() first.")

    df = pd.read_csv(FEATURES_CSV_PATH)
    df = add_scores(df)

    os.makedirs(os.path.dirname(SCORED_CSV_PATH), exist_ok=True)
    df.to_csv(SCORED_CSV_PATH, index=False)
    logger.info("Saved %d rows with scouting scores to %s", len(df), SCORED_CSV_PATH)
    return df


if __name__ == "__main__":
    run()
