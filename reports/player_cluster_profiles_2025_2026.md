# Player Cluster Profiles

KMeans groups players purely by *statistical shape* - each cluster below is a playing style, not a quality tier. An elite and a modest player can land in the same cluster if their per-90 rates have a similar shape, the same idea as the cosine-similarity search explained in the README. `quality_score` (`overall_score` for outfield players, `goalkeeper_score` for goalkeepers) is only used below to choose which players to show as examples - it has no influence on which cluster a player was assigned to.

**Cluster names describe playing style, not literal position.** Clustering looks only at per-90 stats, never at the `position` column, so an archetype name like "ball-playing defenders" can include a deep-lying midfielder whose tackle/pass profile matches that style - see each player's own `position` column for their actual role.

## Cluster 0: dribbling creators

- **Players in cluster:** 21
- **Average age:** 25.6
- **Average minutes:** 1797
- **Playing style:** `key_passes_per90` above average (+1.4σ); `assists_per90` above average (+1.4σ); `goal_contribution_per90` above average (+1.3σ)

**Top players in this cluster:**

| Player | Team | Position | Age | Minutes | Quality Score |
|:---|:---|:---|:---|:---|:---|
| Gabriel Vidovic | Dinamo Zagreb | Attacker | 22 | 1380 | 85.2 |
| Adriano Jagusic | Slaven Koprivnica | Midfielder | 20 | 1728 | 70.3 |
| Mateo Lisica | Dinamo Zagreb | Attacker | 22 | 1387 | 68.8 |
| Miha Zajc | Dinamo Zagreb | Midfielder | 32 | 1656 | 68.5 |
| Josip Mitrovic | Slaven Koprivnica | Attacker | 26 | 2346 | 65.9 |

## Cluster 1: progressive distributors

- **Players in cluster:** 17
- **Average age:** 28.6
- **Average minutes:** 1477
- **Playing style:** `accurate_crosses_per90` above average (+2.1σ); `crosses_per90` above average (+1.8σ); `key_passes_per90` above average (+1.2σ)

**Top players in this cluster:**

| Player | Team | Position | Age | Minutes | Quality Score |
|:---|:---|:---|:---|:---|:---|
| Ljuban Crepulja | Slaven Koprivnica | Midfielder | 32 | 1841 | 74.5 |
| Ismaël Bennacer | Dinamo Zagreb | Midfielder | 28 | 956 | 74.0 |
| Tiago Dantas | Rijeka | Midfielder | 25 | 2487 | 62.0 |
| Marijan Cabraja | Gorica | Defender | 29 | 2661 | 59.6 |
| Dario Melnjak | Hajduk Split | Defender | 33 | 907 | 57.5 |

## Cluster 2: progressive distributors (variant 2)

- **Players in cluster:** 24
- **Average age:** 26.7
- **Average minutes:** 1721
- **Playing style:** `long_balls_per90` above average (+1.6σ); `clearances_per90` above average (+1.5σ); `accurate_long_balls_per90` above average (+1.5σ)

**Top players in this cluster:**

| Player | Team | Position | Age | Minutes | Quality Score |
|:---|:---|:---|:---|:---|:---|
| Sergi Domínguez | Dinamo Zagreb | Defender | 21 | 2576 | 79.4 |
| Scott McKenna | Dinamo Zagreb | Defender | 29 | 2628 | 70.2 |
| Stjepan Radeljic | Rijeka | Defender | 28 | 1977 | 68.3 |
| Luka Skaricic | Varaždin | Defender | 24 | 1678 | 66.7 |
| Luka Jelenic | Osijek | Defender | 26 | 2363 | 65.9 |

## Cluster 3: balanced profile

- **Players in cluster:** 34
- **Average age:** 24.3
- **Average minutes:** 1101
- **Playing style:** `minutes_per_appearance` below average (-1.0σ); `passes_per90` below average (-0.9σ); `accurate_long_balls_per90` below average (-0.9σ)

**Top players in this cluster:**

| Player | Team | Position | Age | Minutes | Quality Score |
|:---|:---|:---|:---|:---|:---|
| Iuri Tavares | Varaždin | Attacker | 25 | 2065 | 61.9 |
| Fran Topic | Dinamo Zagreb | Attacker | 22 | 732 | 60.9 |
| Samuel Akere | Osijek | Attacker | 22 | 980 | 60.6 |
| Miloš Jovičić | Osijek | Attacker | 20 | 471 | 57.4 |
| Ivan Canjuga | Varaždin | Attacker | 20 | 800 | 55.4 |

## Cluster 4: balanced profile

- **Players in cluster:** 29
- **Average age:** 26.8
- **Average minutes:** 1481
- **Playing style:** `long_ball_accuracy` below average (-0.9σ); `tackles_per90` above average (+0.8σ); `crosses_per90` above average (+0.7σ)

**Top players in this cluster:**

| Player | Team | Position | Age | Minutes | Quality Score |
|:---|:---|:---|:---|:---|:---|
| Ante Orec | Rijeka | Defender | 24 | 2338 | 63.5 |
| Marcel Heister | Istra 1961 | Defender | 33 | 2107 | 62.1 |
| David Puclin | Varaždin | Midfielder | 34 | 758 | 61.4 |
| Filip Kruselj | Slaven Koprivnica | Defender | 21 | 2226 | 58.7 |
| Kerim Çalhanoğlu | Vukovar | Defender | 23 | 1350 | 58.4 |

## Cluster 5: high-volume finishers

- **Players in cluster:** 20
- **Average age:** 26.3
- **Average minutes:** 1705
- **Playing style:** `goals_per90` above average (+2.0σ); `shots_on_target_per90` above average (+1.9σ); `goal_contribution_per90` above average (+1.7σ)

**Top players in this cluster:**

| Player | Team | Position | Age | Minutes | Quality Score |
|:---|:---|:---|:---|:---|:---|
| Michele Sego | Hajduk Split | Attacker | 25 | 2051 | 64.2 |
| Dion Beljo | Dinamo Zagreb | Attacker | 24 | 2619 | 63.0 |
| Monsef Bakrar | Dinamo Zagreb | Attacker | 25 | 1511 | 61.7 |
| Sandro Kulenovic | Dinamo Zagreb | Attacker | 26 | 505 | 59.4 |
| Bruno Bogojevic | Gorica | Attacker | 28 | 1255 | 57.5 |

## Cluster 6: ball-playing defenders

- **Players in cluster:** 30
- **Average age:** 24.9
- **Average minutes:** 1318
- **Playing style:** `clearances_per90` above average (+1.2σ); `shot_accuracy` below average (-1.1σ); `duel_success_rate` above average (+1.0σ)

**Top players in this cluster:**

| Player | Team | Position | Age | Minutes | Quality Score |
|:---|:---|:---|:---|:---|:---|
| Niko Galesic | Dinamo Zagreb | Defender | 25 | 1405 | 60.9 |
| Zvonimir Sarlija | Hajduk Split | Defender | 29 | 2211 | 60.3 |
| Roko Jurisic | Osijek | Defender | 24 | 1229 | 59.3 |
| Bruno Goda | Dinamo Zagreb | Defender | 28 | 1587 | 58.3 |
| Dominik Kovacic | Slaven Koprivnica | Defender | 32 | 2968 | 56.4 |

## Cluster 7: defensive distributors

- **Players in cluster:** 26
- **Average age:** 23.9
- **Average minutes:** 1531
- **Playing style:** `long_ball_accuracy` above average (+0.9σ); `tackles_per90` above average (+0.8σ); `cards_per90` above average (+0.8σ)

**Top players in this cluster:**

| Player | Team | Position | Age | Minutes | Quality Score |
|:---|:---|:---|:---|:---|:---|
| Marko Soldo | Dinamo Zagreb | Midfielder | 22 | 689 | 82.2 |
| Iker Pozo | Gorica | Midfielder | 25 | 2716 | 72.2 |
| Josip Misic | Dinamo Zagreb | Midfielder | 32 | 2658 | 66.2 |
| Niko Sigur | Hajduk Split | Midfielder | 22 | 2224 | 64.6 |
| Mihail Caimacov | Slaven Koprivnica | Midfielder | 27 | 887 | 57.4 |

## Cluster 8: goalkeeper distributors

- **Players in cluster:** 7
- **Average age:** 28.7
- **Average minutes:** 1736
- **Playing style:** `clean_sheet_rate` above average (+1.0σ); `goals_conceded_per90` below average (-0.9σ); `pass_accuracy_ratio` above average (+0.8σ)

**Top players in this cluster:**

| Player | Team | Position | Age | Minutes | Quality Score |
|:---|:---|:---|:---|:---|:---|
| Dominik Livakovic | Dinamo Zagreb | Goalkeeper | 31 | 1260 | 65.9 |
| Ivan Filipovic | Dinamo Zagreb | Goalkeeper | 31 | 810 | 65.9 |
| Toni Silic | Hajduk Split | Goalkeeper | 22 | 1890 | 61.2 |
| Martin Zlomislic | Rijeka | Goalkeeper | 27 | 2970 | 60.6 |
| Marko Malenica | Osijek | Goalkeeper | 32 | 2700 | 60.0 |

## Cluster 9: balanced profile

- **Players in cluster:** 10
- **Average age:** 28.0
- **Average minutes:** 1908
- **Playing style:** `clean_sheet_rate` below average (-0.7σ); `goals_conceded_per90` above average (+0.6σ); `pass_accuracy_ratio` below average (-0.6σ)

**Top players in this cluster:**

| Player | Team | Position | Age | Minutes | Quality Score |
|:---|:---|:---|:---|:---|:---|
| Oliver Zelenika | Varaždin | Goalkeeper | 33 | 2880 | 64.1 |
| Mateusz Stolarski | Slaven Koprivnica | Goalkeeper | 35 | 696 | 54.7 |
| Josip Posavec | Lokomotiva Zagreb | Goalkeeper | 30 | 2970 | 54.7 |
| Franko Kolic | Istra 1961 | Goalkeeper | 23 | 3150 | 53.5 |
| Davor Matijas | Gorica | Goalkeeper | 26 | 3240 | 49.4 |

