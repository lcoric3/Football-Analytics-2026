# Player Cluster Profiles

KMeans groups players purely by *statistical shape* - each cluster below is a playing style, not a quality tier. An elite and a modest player can land in the same cluster if their per-90 rates have a similar shape, the same idea as the cosine-similarity search explained in the README. `quality_score` (`overall_score` for outfield players, `goalkeeper_score` for goalkeepers) is only used below to choose which players to show as examples - it has no influence on which cluster a player was assigned to.

**Cluster names describe playing style, not literal position.** Clustering looks only at per-90 stats, never at the `position` column, so an archetype name like "ball-playing defenders" can include a deep-lying midfielder whose tackle/pass profile matches that style - see each player's own `position` column for their actual role.

## Cluster 0: balanced profile

- **Players in cluster:** 33
- **Average age:** 25.1
- **Average minutes:** 1466
- **Playing style:** `successful_dribbles_per90` above average (+0.9σ); `long_balls_per90` below average (-0.8σ); `clearances_per90` below average (-0.8σ)

**Top players in this cluster:**

| Player | Team | Position | Age | Minutes | Quality Score |
|:---|:---|:---|:---|:---|:---|
| Arijan Ademi | Dinamo Zagreb | Midfielder | 35 | 837 | 72.5 |
| Dario Spikic | Dinamo Zagreb | Attacker | 27 | 624 | 67.7 |
| Ivan Laća | Šibenik | Attacker | 23 | 1545 | 63.8 |
| Marko Soldo | Osijek | Midfielder | 22 | 2357 | 62.8 |
| Adriano Jagusic | Slaven Koprivnica | Midfielder | 20 | 1526 | 61.8 |

## Cluster 1: ball-playing defenders

- **Players in cluster:** 27
- **Average age:** 28.7
- **Average minutes:** 1474
- **Playing style:** `clearances_per90` above average (+1.5σ); `dribble_success_rate` above average (+1.3σ); `duel_success_rate` above average (+1.1σ)

**Top players in this cluster:**

| Player | Team | Position | Age | Minutes | Quality Score |
|:---|:---|:---|:---|:---|:---|
| Luka Jelenic | Osijek | Defender | 26 | 2532 | 71.8 |
| Dominik Kovacic | Slaven Koprivnica | Defender | 32 | 2484 | 62.2 |
| Mateo Les | Gorica | Defender | 26 | 2360 | 56.7 |
| Ivan Nekic | Varaždin | Defender | 25 | 1596 | 55.9 |
| Stephane Keller | Istra 1961 | Defender | 24 | 694 | 55.6 |

## Cluster 2: balanced profile

- **Players in cluster:** 16
- **Average age:** 28.6
- **Average minutes:** 1570
- **Playing style:** `crosses_per90` above average (+1.6σ); `accurate_crosses_per90` above average (+1.5σ); `key_passes_per90` above average (+0.8σ)

**Top players in this cluster:**

| Player | Team | Position | Age | Minutes | Quality Score |
|:---|:---|:---|:---|:---|:---|
| Jurica Prsir | Gorica | Midfielder | 26 | 1511 | 72.8 |
| Ivan Cvijanovic | Osijek | Defender | 22 | 888 | 65.4 |
| Šime Gržan | Šibenik | Attacker | 32 | 2116 | 61.5 |
| Ivan Rakitić | Hajduk Split | Midfielder | 38 | 3065 | 60.6 |
| Simun Mikolcic | Osijek | Midfielder | 22 | 622 | 56.1 |

## Cluster 3: high-volume finishers

- **Players in cluster:** 23
- **Average age:** 26.5
- **Average minutes:** 1516
- **Playing style:** `goal_contribution_per90` above average (+1.9σ); `assists_per90` above average (+1.7σ); `key_passes_per90` above average (+1.6σ)

**Top players in this cluster:**

| Player | Team | Position | Age | Minutes | Quality Score |
|:---|:---|:---|:---|:---|:---|
| Nathanaël Mbuku | Dinamo Zagreb | Attacker | 24 | 496 | 84.2 |
| Luka Stojkovic | Dinamo Zagreb | Midfielder | 22 | 1542 | 73.0 |
| Lukas Kacavenda | Dinamo Zagreb | Midfielder | 23 | 733 | 71.9 |
| Marko Pjaca | Dinamo Zagreb | Attacker | 31 | 2384 | 71.7 |
| Arbër Hoxha | Dinamo Zagreb | Attacker | 27 | 1254 | 69.6 |

## Cluster 4: high-volume finishers (variant 2)

- **Players in cluster:** 23
- **Average age:** 26.3
- **Average minutes:** 1318
- **Playing style:** `shots_on_target_per90` above average (+1.3σ); `duel_success_rate` below average (-1.2σ); `pass_accuracy_ratio` below average (-1.2σ)

**Top players in this cluster:**

| Player | Team | Position | Age | Minutes | Quality Score |
|:---|:---|:---|:---|:---|:---|
| Sandro Kulenovic | Dinamo Zagreb | Attacker | 26 | 1910 | 60.7 |
| Matej Sakota | Slaven Koprivnica | Attacker | 21 | 592 | 54.4 |
| Robert Mudrazija | Lokomotiva Zagreb | Midfielder | 29 | 2600 | 53.3 |
| Lovre Kulusic | Šibenik | Midfielder | 19 | 890 | 52.6 |
| Bruno Durdov | Hajduk Split | Attacker | 18 | 979 | 51.6 |

## Cluster 5: balanced profile

- **Players in cluster:** 40
- **Average age:** 27.9
- **Average minutes:** 1702
- **Playing style:** `tackles_per90` above average (+0.8σ); `shots_on_target_per90` below average (-0.7σ); `shot_accuracy` below average (-0.6σ)

**Top players in this cluster:**

| Player | Team | Position | Age | Minutes | Quality Score |
|:---|:---|:---|:---|:---|:---|
| Niko Sigur | Hajduk Split | Midfielder | 22 | 1612 | 64.0 |
| Filip Krovinovic | Hajduk Split | Midfielder | 30 | 2240 | 63.4 |
| Ronaël Pierre-Gabriel | Dinamo Zagreb | Defender | 28 | 2288 | 63.0 |
| Ivan Smolcic | Rijeka | Defender | 25 | 1564 | 61.1 |
| Josip Radosevic | Istra 1961 | Midfielder | 32 | 1230 | 57.1 |

## Cluster 6: progressive distributors

- **Players in cluster:** 25
- **Average age:** 28.0
- **Average minutes:** 2060
- **Playing style:** `accurate_long_balls_per90` above average (+1.3σ); `passes_per90` above average (+1.3σ); `long_balls_per90` above average (+1.2σ)

**Top players in this cluster:**

| Player | Team | Position | Age | Minutes | Quality Score |
|:---|:---|:---|:---|:---|:---|
| Raúl Torrente | Dinamo Zagreb | Defender | 24 | 1650 | 75.6 |
| Moris Valincic | Istra 1961 | Defender | 23 | 2619 | 68.2 |
| Niko Galesic | Rijeka | Defender | 25 | 1338 | 67.1 |
| Emin Hasic | Osijek | Defender | 23 | 1320 | 66.8 |
| Hrvoje Babec | Osijek | Midfielder | 26 | 1522 | 66.5 |

## Cluster 7: safe passers

- **Players in cluster:** 1
- **Average age:** 27.0
- **Average minutes:** 606
- **Playing style:** `goal_conversion` above average (+8.7σ); `shot_accuracy` above average (+4.4σ); `clearances_per90` above average (+3.2σ)

**Top players in this cluster:**

| Player | Team | Position | Age | Minutes | Quality Score |
|:---|:---|:---|:---|:---|:---|
| Jon Mersinaj | Lokomotiva Zagreb | Defender | 27 | 606 | 46.3 |

## Cluster 8: balanced profile

- **Players in cluster:** 8
- **Average age:** 30.5
- **Average minutes:** 1914
- **Playing style:** `clean_sheet_rate` below average (-0.7σ); `goals_conceded_per90` above average (+0.6σ); `saves_per90` above average (+0.6σ)

**Top players in this cluster:**

| Player | Team | Position | Age | Minutes | Quality Score |
|:---|:---|:---|:---|:---|:---|
| Ivan Sušak | Slaven Koprivnica | Goalkeeper | 28 | 2880 | 69.3 |
| Ivan Banic | Gorica | Goalkeeper | 31 | 2430 | 64.3 |
| Marko Malenica | Osijek | Goalkeeper | 32 | 2880 | 48.6 |
| Zvonimir Subaric | Lokomotiva Zagreb | Goalkeeper | 29 | 2970 | 45.7 |
| Ivan Filipovic | Dinamo Zagreb | Goalkeeper | 31 | 1260 | 40.0 |

## Cluster 9: goalkeeper distributors

- **Players in cluster:** 6
- **Average age:** 30.5
- **Average minutes:** 2358
- **Playing style:** `clean_sheet_rate` above average (+0.9σ); `goals_conceded_per90` below average (-0.8σ); `saves_per90` below average (-0.8σ)

**Top players in this cluster:**

| Player | Team | Position | Age | Minutes | Quality Score |
|:---|:---|:---|:---|:---|:---|
| Oliver Zelenika | Varaždin | Goalkeeper | 33 | 2880 | 67.9 |
| Ivan Lucic | Hajduk Split | Goalkeeper | 31 | 2496 | 66.4 |
| Lovro Majkic | Istra 1961 | Goalkeeper | 26 | 2751 | 61.4 |
| Martin Zlomislic | Rijeka | Goalkeeper | 27 | 3054 | 56.4 |
| Danijel Zagorac | Dinamo Zagreb | Goalkeeper | 39 | 810 | 56.4 |

