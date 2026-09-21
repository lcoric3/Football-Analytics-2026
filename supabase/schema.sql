-- =============================================================================
-- Football-Analytics-2026 - private scouting database (Supabase / PostgreSQL)
--
-- Run this whole file once in the Supabase SQL Editor (see SCOUTING_SETUP.md).
-- It is safe to re-run: tables/indexes use IF NOT EXISTS and triggers are
-- dropped and re-created.
--
-- What lives here: only the human scouting layer - scout reports and
-- shortlists. Player statistics are NOT stored in the database; they stay in
-- the read-only CSV files the analytics pipeline already produces, and are
-- joined to these tables in the app via (league_code, player_id,
-- season_suffix).
--
-- ACCESS MODEL (single-user private version):
--   * Row Level Security is ENABLED on every table and NO policies are
--     created. With RLS on and no policy, the `anon` and `authenticated`
--     roles (the ones behind the public/anon API key) can read and write
--     nothing at all.
--   * The private Streamlit app connects server-side with a Supabase SECRET
--     key (sb_secret_...). Secret keys use the built-in `service_role`
--     Postgres role, which bypasses RLS. That key must live only in
--     Streamlit Secrets or a local .env - never in client-side code and
--     never in Git.
--   * The REVOKE statements below are a second, independent lock on top of
--     RLS, in case a policy is ever added by mistake.
--
-- The lists of allowed values (recommendation, status) are mirrored in
-- src/scout_validation.py - a test fails if the two ever drift apart.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Shared trigger function: keep updated_at current on every UPDATE.
-- `set search_path = ''` is the Supabase-recommended hardening for functions.
-- -----------------------------------------------------------------------------
create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    new.updated_at := now();
    return new;
end;
$$;


-- -----------------------------------------------------------------------------
-- scouting_reports: one row per scout observation of one player.
-- -----------------------------------------------------------------------------
create table if not exists public.scouting_reports (
    id                  uuid primary key default gen_random_uuid(),

    -- Which player/season this report is about. There is deliberately no
    -- foreign key: player data lives in CSV files, not in this database.
    -- league_code keeps the structure ready for leagues other than HNL.
    league_code         text        not null default 'hnl',
    player_id           bigint      not null,
    season_suffix       text        not null,

    observation_date    date        not null,
    opponent            text,
    observed_position   text        not null,

    -- Ratings are whole numbers 1-10 (converted to a 0-100 scale in the app).
    technical_rating    smallint    not null,
    tactical_rating     smallint    not null,
    physical_rating     smallint    not null,
    mental_rating       smallint    not null,
    potential_rating    smallint    not null,

    strengths           text,
    weaknesses          text,
    notes               text,
    recommendation      text        not null,

    created_at          timestamptz not null default now(),
    updated_at          timestamptz not null default now(),

    constraint scouting_reports_league_code_format
        check (league_code ~ '^[a-z0-9_]{1,32}$'),
    constraint scouting_reports_season_suffix_format
        check (season_suffix ~ '^[0-9]{4}_[0-9]{4}$'),
    constraint scouting_reports_opponent_length
        check (opponent is null or char_length(opponent) between 1 and 100),
    constraint scouting_reports_position_length
        check (char_length(observed_position) between 1 and 50),
    constraint scouting_reports_technical_range
        check (technical_rating between 1 and 10),
    constraint scouting_reports_tactical_range
        check (tactical_rating between 1 and 10),
    constraint scouting_reports_physical_range
        check (physical_rating between 1 and 10),
    constraint scouting_reports_mental_range
        check (mental_rating between 1 and 10),
    constraint scouting_reports_potential_range
        check (potential_rating between 1 and 10),
    constraint scouting_reports_strengths_length
        check (strengths is null or char_length(strengths) <= 2000),
    constraint scouting_reports_weaknesses_length
        check (weaknesses is null or char_length(weaknesses) <= 2000),
    constraint scouting_reports_notes_length
        check (notes is null or char_length(notes) <= 5000),
    constraint scouting_reports_recommendation_values
        check (recommendation in (
            'Preporučeno',
            'Nastaviti pratiti',
            'Potrebno ponovno gledati',
            'Ne preporučuje se'
        ))
);

-- Main access path: "all reports for this player in this season".
create index if not exists scouting_reports_player_season_idx
    on public.scouting_reports (league_code, player_id, season_suffix);

-- "Most recent observations first" listings.
create index if not exists scouting_reports_observation_date_idx
    on public.scouting_reports (observation_date desc);

drop trigger if exists scouting_reports_set_updated_at on public.scouting_reports;
create trigger scouting_reports_set_updated_at
    before update on public.scouting_reports
    for each row execute function public.set_updated_at();


-- -----------------------------------------------------------------------------
-- shortlists: a named list of players the scout wants to track.
-- -----------------------------------------------------------------------------
create table if not exists public.shortlists (
    id           uuid primary key default gen_random_uuid(),
    name         text        not null,
    description  text,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now(),

    constraint shortlists_name_length
        check (char_length(name) between 1 and 100),
    constraint shortlists_description_length
        check (description is null or char_length(description) <= 1000)
);

-- Two shortlists with the same name (ignoring case) would be confusing.
create unique index if not exists shortlists_name_unique_idx
    on public.shortlists (lower(name));

drop trigger if exists shortlists_set_updated_at on public.shortlists;
create trigger shortlists_set_updated_at
    before update on public.shortlists
    for each row execute function public.set_updated_at();


-- -----------------------------------------------------------------------------
-- shortlist_players: membership of a player on a shortlist.
-- -----------------------------------------------------------------------------
create table if not exists public.shortlist_players (
    id             uuid primary key default gen_random_uuid(),

    -- Deleting a shortlist removes its membership rows too.
    shortlist_id   uuid        not null
                       references public.shortlists (id) on delete cascade,

    league_code    text        not null default 'hnl',
    player_id      bigint      not null,
    -- The season whose statistics were on screen when the player was added.
    season_suffix  text        not null,

    status         text        not null default 'Praćenje',
    -- 1 = highest priority ... 5 = lowest priority.
    priority       smallint    not null default 3,
    note           text,

    added_at       timestamptz not null default now(),
    updated_at     timestamptz not null default now(),

    constraint shortlist_players_league_code_format
        check (league_code ~ '^[a-z0-9_]{1,32}$'),
    constraint shortlist_players_season_suffix_format
        check (season_suffix ~ '^[0-9]{4}_[0-9]{4}$'),
    constraint shortlist_players_status_values
        check (status in (
            'Praćenje',
            'Potrebno skautirati',
            'Prioritet',
            'Odbijen'
        )),
    constraint shortlist_players_priority_range
        check (priority between 1 and 5),
    constraint shortlist_players_note_length
        check (note is null or char_length(note) <= 1000),

    -- A player can only be on a given shortlist once. SportMonks player ids
    -- are globally unique, so (shortlist, player) is enough even when more
    -- leagues are added later.
    constraint shortlist_players_unique_player_per_shortlist
        unique (shortlist_id, player_id)
);

create index if not exists shortlist_players_shortlist_idx
    on public.shortlist_players (shortlist_id);

create index if not exists shortlist_players_player_idx
    on public.shortlist_players (league_code, player_id, season_suffix);

drop trigger if exists shortlist_players_set_updated_at on public.shortlist_players;
create trigger shortlist_players_set_updated_at
    before update on public.shortlist_players
    for each row execute function public.set_updated_at();


-- -----------------------------------------------------------------------------
-- Row Level Security: ON, with no policies (see ACCESS MODEL at the top).
-- -----------------------------------------------------------------------------
alter table public.scouting_reports  enable row level security;
alter table public.shortlists        enable row level security;
alter table public.shortlist_players enable row level security;

-- Second lock: the anon / authenticated API roles get no table privileges.
revoke all on table public.scouting_reports  from anon, authenticated;
revoke all on table public.shortlists        from anon, authenticated;
revoke all on table public.shortlist_players from anon, authenticated;

-- The server-side secret key (which runs as the `service_role` Postgres role)
-- is the only intended client.
grant all on table public.scouting_reports  to service_role;
grant all on table public.shortlists        to service_role;
grant all on table public.shortlist_players to service_role;
