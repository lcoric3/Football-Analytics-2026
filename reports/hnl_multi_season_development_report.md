# HNL Multi-Season Player Development Report (2024/2025 -> 2025/2026)


*Generated 2026-07-06 by `src/player_development.py`, from the season-suffixed CSVs already in `data/processed/` and `data/output/` - this report never calls the SportMonks API and never recomputes a per-season score.*

## 1. Summary

This report compares every player with scored, eligible-minutes data in **both** HNL 2024/2025 and HNL 2025/2026, matched by `player_id` (not name - see Section 9 for why that matters). It highlights who improved, who declined, who broke through as a young talent, and who kept improving after a transfer.

| Metric | Count |
|:---|:---|
| Scored players in 2024/2025 | 329 |
| Scored players in 2025/2026 | 332 |
| Players matched in both seasons (by player_id) | 169 |
| Players who changed team between seasons | 45 |
| Players with a higher overall_score in 2025/2026 | 54 |
| Players with a lower overall_score in 2025/2026 | 53 |

## 2. Biggest Improvers

Ranked by `overall_score_change` (this season's `overall_score` minus last season's) - the biggest gains in season-relative overall output.

| Player | Team | Position | Age | Overall 2024/2025 | Overall 2025/2026 | Change |
|:---|:---|:---|:---|:---|:---|:---|
| Iker Pozo | Gorica | Midfielder | 25.0 | 42.7 | 72.2 | 29.5 |
| Ante Orec | Rijeka | Defender | 24.0 | 37.9 | 63.5 | 25.6 |
| Mihail Caimacov | Slaven Koprivnica | Midfielder | 27.0 | 32.7 | 57.4 | 24.7 |
| Abdoulie Sanyang | Hajduk Split | Attacker | 27.0 | 39.7 | 64.2 | 24.5 |
| Luka Skaricic | Varaždin | Defender | 24.0 | 44.9 | 66.7 | 21.8 |
| Advan Kadusic | Istra 1961 | Defender | 28.0 | 36.3 | 56.9 | 20.6 |
| Salim Fago Lawal | Istra 1961 | Attacker | 23.0 | 31.3 | 51.2 | 19.8 |
| Marko Soldo | Dinamo Zagreb | Midfielder | 22.0 | 62.8 | 82.2 | 19.4 |
| Merveil Ndockyt | Rijeka | Midfielder | 27.0 | 34.5 | 53.4 | 18.9 |
| Bruno Bogojevic | Gorica | Attacker | 28.0 | 41.1 | 57.5 | 16.4 |

## 3. Biggest Decliners

The flip side of Section 2 - the biggest drops in `overall_score`. A decline here can mean genuine regression, but see the Limitations section: fewer minutes, a tougher team context, or a role change after a transfer can all pull a season-relative score down without the player getting any worse.

| Player | Team | Position | Age | Overall 2024/2025 | Overall 2025/2026 | Change |
|:---|:---|:---|:---|:---|:---|:---|
| Vinko Rozic | Istra 1961 | Attacker | 22.0 | 64.7 | 42.0 | -22.7 |
| Moris Valincic | Dinamo Zagreb | Defender | 23.0 | 68.2 | 47.0 | -21.2 |
| Oliver Zelenika | Varaždin | Goalkeeper | 33.0 | 66.2 | 46.2 | -20.0 |
| Emin Hasic | Osijek | Defender | 23.0 | 66.8 | 46.9 | -19.9 |
| Stjepan Loncar | Istra 1961 | Midfielder | 29.0 | 58.7 | 38.9 | -19.8 |
| Igor Lepinjica | Slaven Koprivnica | Attacker | 26.0 | 45.4 | 25.7 | -19.7 |
| Gabriel Rukavina | Rijeka | Attacker | 22.0 | 58.9 | 39.6 | -19.4 |
| Dušan Vuković | Lokomotiva Zagreb | Attacker | 23.0 | 55.2 | 36.3 | -18.9 |
| Jurica Prsir | Gorica | Midfielder | 26.0 | 72.8 | 54.3 | -18.5 |
| Antonio Bosec | Vukovar | Defender | 28.0 | 39.7 | 21.2 | -18.5 |

## 4. Young Improvers (age <= 23 in 2025/2026)

Players age 23 or under this season who also improved their `overall_score` - the clearest "still improving, still young" signal this dataset can produce.

| Player | Team | Position | Age | Overall Change |
|:---|:---|:---|:---|:---|
| Salim Fago Lawal | Istra 1961 | Attacker | 23.0 | 19.8 |
| Marko Soldo | Dinamo Zagreb | Midfielder | 22.0 | 19.4 |
| Vito Caic | Vukovar | Midfielder | 21.0 | 12.6 |
| Rokas Pukstas | Hajduk Split | Midfielder | 21.0 | 12.3 |
| Mateo Lisica | Dinamo Zagreb | Attacker | 22.0 | 11.8 |
| Anton Matkovic | Osijek | Attacker | 20.0 | 9.9 |
| Ante Kavelj | Gorica | Midfielder | 20.0 | 9.4 |
| Adriano Jagusic | Slaven Koprivnica | Midfielder | 20.0 | 8.6 |
| Filip Cuic | Gorica | Attacker | 23.0 | 8.1 |
| Styopa Mkrtchyan | Osijek | Defender | 23.0 | 5.8 |

## 5. Increased Playing Time

Ranked by raw `minutes_change` - not a quality signal by itself, but useful alongside the other tables: a player whose scores improved *and* whose minutes grew is a much more reliable signal than one whose scores improved on a small, noisy sample (see the Limitations section).

| Player | Team | Minutes 2024/2025 | Minutes 2025/2026 | Change |
|:---|:---|:---|:---|:---|
| Franko Kolic | Istra 1961 | 39.0 | 3150.0 | 3111.0 |
| Josip Posavec | Lokomotiva Zagreb | 90.0 | 2970.0 | 2880.0 |
| Marijan Cabraja | Gorica | 127.0 | 2661.0 | 2534.0 |
| Blaz Boskovic | Lokomotiva Zagreb | 223.0 | 2459.0 | 2236.0 |
| Matija Subotic | Lokomotiva Zagreb | 10.0 | 2055.0 | 2045.0 |
| Ante Orec | Rijeka | 464.0 | 2338.0 | 1874.0 |
| Toni Silic | Hajduk Split | 90.0 | 1890.0 | 1800.0 |
| Filip Kruselj | Slaven Koprivnica | 441.0 | 2226.0 | 1785.0 |
| Stjepan Loncar | Istra 1961 | 1043.0 | 2784.0 | 1741.0 |
| Zvonimir Sarlija | Hajduk Split | 537.0 | 2211.0 | 1674.0 |

## 6. Improved After Changing Team

Players who moved clubs between seasons *and* still improved their `overall_score` - a signal the improvement survived a change in teammates/system, not just one team's context (see Limitations).

| Player | Team 2024/2025 | Team 2025/2026 | Overall Change |
|:---|:---|:---|:---|
| Iker Pozo | Šibenik | Gorica | 29.5 |
| Marko Soldo | Osijek | Dinamo Zagreb | 19.4 |
| Merveil Ndockyt | Gorica | Rijeka | 18.9 |
| Bruno Bogojevic | Rijeka | Gorica | 16.4 |
| Tiago Dantas | Osijek | Rijeka | 16.4 |
| Vito Caic | Gorica | Vukovar | 12.6 |
| Gregor Sikosek | Gorica | Varaždin | 12.1 |
| Mateo Lisica | Istra 1961 | Dinamo Zagreb | 11.8 |
| Ante Kavelj | Šibenik | Gorica | 9.4 |
| Filip Cuic | Lokomotiva Zagreb | Gorica | 8.1 |

## 7. Specialist Score Improvers

Ranked by each player's single biggest specialist-score gain (`dribbling_score`, `passing_score`, `duel_defending_score`, `progressive_midfielder_score`, or `passer_defender_score` - see scouting_scores.py) - a player can be a modest all-rounder but a big riser in one specific skill, which `overall_score_change` alone would hide.

| Player | Position | Best-Improved Metric | Change |
|:---|:---|:---|:---|
| Domagoj Antolic | Midfielder | dribbling_score | 62.3 |
| Matej Vuk | Attacker | dribbling_score | 44.7 |
| Advan Kadusic | Defender | duel_defending_score | 36.3 |
| Mihail Caimacov | Midfielder | duel_defending_score | 34.8 |
| Oliver Zelenika | Goalkeeper | dribbling_score | 33.6 |
| Ivan Nevistic | Goalkeeper | dribbling_score | 33.3 |
| Iker Pozo | Midfielder | progressive_midfielder_score | 32.6 |
| Jon Mersinaj | Defender | passer_defender_score | 32.1 |
| Marko Soldo | Midfielder | passer_defender_score | 31.6 |
| Styopa Mkrtchyan | Defender | progressive_midfielder_score | 25.9 |

## 8. Hidden Gems Who Improved

Players tagged `hidden_gems` in 2024/2025 (outperforming their own team *and* playing at a squad below the league average - see that season's own scouting report) who then also improved their `overall_score` in 2025/2026 - a signal that last season's under-the-radar standout kept getting better, not just a one-season blip.

| Player | Team 2024/2025 | Team 2025/2026 | Overall Change |
|:---|:---|:---|:---|
| Michele Sego | Varaždin | Hajduk Split | 2.6 |
| Niko Sigur | Hajduk Split | Hajduk Split | 0.6 |

## 9. Methodology

- **Matching**: players are matched by `player_id`, not `player_name` - SportMonks IDs are stable per player, while name strings can differ in accents/transliteration between API pulls, or collide between two different players who share a name. A player who didn't play in one of the two seasons (transferred out of the league, injured all season, etc.) is not in this comparison - only the 169 players scored in *both* seasons are.
- **Score changes**: every `*_score_change` column is simply `<score>_2025_2026 - <score>_2024_2025`; positive means improved relative to that season's own player pool (see Limitations).
- **Flags**: `changed_team`/`same_position` compare the raw `team`/`position` strings between seasons; `minutes_increased`, `improved_overall`, and `improved_specialist_score` are simple `> 0` checks on the corresponding change column(s).
- **Rankings**: `biggest_improvers`/`biggest_decliners` sort by `overall_score_change`; `young_improvers` additionally requires age <= 23 in 2025/2026; `changed_team_improvers` requires `changed_team` and `improved_overall`; `specialist_improvers` sorts by each player's single biggest specialist-score gain; `hidden_gems_who_improved` starts from 2024/2025's `hidden_gems` list and keeps only the ones who also improved.


## 10. Limitations

- **Scores are season-relative, not absolute.** Every score here (`overall_score`, `attacking_score`, ...) is a percentile rank against that season's own player pool (see scouting_scores.py). A positive `overall_score_change` means "improved relative to their own season's peers", not "objectively became a better footballer" - the league's overall talent level can shift between seasons independent of any one player.
- **Team context changes between seasons.** `underrated_score`'s team-context bonuses (see scouting_scores.py) are relative to that season's own team-strength distribution - a team's average squad quality can rise or fall between seasons for reasons that have nothing to do with any individual player.
- **Minutes changes affect reliability, not just opportunity.** A player with a big `overall_score_change` on a small `minutes` sample (either season) is a noisier signal than the same change on a full season's minutes - cross-check `minutes_change` and each season's raw minutes before treating a jump as a real trend.
- **A player changing team may change role entirely.** `changed_team` only compares club names - it says nothing about whether the player's tactical role, position share, or set-piece duties changed along with the move, any of which can move scores independent of underlying skill.
- **SportMonks stat availability may differ between seasons.** If a stat type wasn't mapped or wasn't returned for a given season (see clean_data.py's `STAT_TYPE_MAP` and its "unmapped statistic type ids" warning), the score(s) built from it may be missing for that season - this module skips (not crashes on) any comparison column that isn't present in both seasons, but a missing column also means that particular comparison silently isn't possible this run.
- **This is a scouting signal, not a final evaluation.** Like every other ranking in this project, it says nothing about video-scouted technique, tactical fit, injury history, or transfer feasibility - treat it as a reproducible starting point for a human scout, not a conclusion.

