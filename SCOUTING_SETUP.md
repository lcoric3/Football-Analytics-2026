# Privatni skautski sustav - upute za postavljanje

`scout_app.py` je **privatna** Streamlit aplikacija za skautske izvještaje,
shortliste i usporedbu igrača. Analitičke ocjene čita iz postojećih CSV-ova
(samo za čitanje), a skautske bilješke sprema u **Supabase** (PostgreSQL).
Nikada ne poziva SportMonks API i ne sprema bilješke u lokalne datoteke.

> ## ⚠️ Ova aplikacija se NE SMIJE postaviti kao javna
>
> Aplikacija se na bazu spaja **secret ključem** (`sb_secret_...`), koji
> **zaobilazi sve sigurnosne politike baze** (Row Level Security). Tko god
> može otvoriti pokrenutu aplikaciju, može **čitati, mijenjati i brisati sve
> vaše skautske bilješke**. Zato imate **dva neovisna sloja zaštite, i oba su
> obavezna**:
>
> 1. **Streamlit pristup:** postavka *Only specific people can view this app*
>    (korak 7);
> 2. **Zaporka aplikacije:** `SCOUT_APP_PASSWORD` (korak 5). Bez nje je
>    aplikacija zaključana.
>
> Zaporka je **dodatna zaštita i ne zamjenjuje** postavku *Only specific
> people*.
>
> Također:
>
> - `scout_app.py` nikad ne objavljujte kao javnu aplikaciju;
> - ključ i zaporku nikad ne stavljajte u kod, u Git ni u klijentski (browser)
>   kod;
> - slijedite korake 6 i 7 **točno ovim redoslijedom** (privatnost se
>   uključuje *prije* nego što aplikacija dobije ključ i zaporku).
>
> Postojeći javni dashboard (`app.py`) je zasebna aplikacija: ne koristi
> Supabase, ne zna za ove tajne i na njega ova postavka ne utječe.

## Sadržaj

1. [Supabase račun i projekt](#1-supabase-račun-i-projekt)
2. [Pokretanje `supabase/schema.sql`](#2-pokretanje-supabaseschemasql)
3. [Gdje su Project URL i ključ](#3-gdje-su-project-url-i-ključ)
4. [Lokalno spremanje u `.env`](#4-lokalno-spremanje-u-env)
5. [Streamlit Secrets i zaporka aplikacije](#5-streamlit-secrets-i-zaporka-aplikacije)
6. [Druga Streamlit aplikacija iz istog repozitorija](#6-druga-streamlit-aplikacija-iz-istog-repozitorija)
7. [Kako aplikacija ostaje privatna](#7-kako-aplikacija-ostaje-privatna)
8. [Provjera veze i prvi izvještaj](#8-provjera-veze-i-prvi-izvještaj)
9. [Rješavanje problema](#rješavanje-problema)
10. [Kako se računaju ocjene](#kako-se-računaju-ocjene)
11. [Sigurnosni model](#sigurnosni-model)

---

## 1. Supabase račun i projekt

1. Otvorite <https://supabase.com> i kliknite **Start your project** /
   **Sign in** (prijava GitHub računom je najjednostavnija).
2. Napravite **organizaciju** ako vas pita (osobna je u redu).
3. Kliknite **New project** i unesite:
   - **Name:** npr. `football-scouting`
   - **Database password:** generirajte jaku lozinku i spremite je u
     upravitelj lozinki (za ovu aplikaciju nije potrebna, ali je trebate
     imati za administraciju baze)
   - **Region:** najbliža vama (npr. Frankfurt)
4. Pričekajte nekoliko minuta dok se projekt ne stvori.

> Besplatni Supabase projekti mogu biti automatski **pauzirani** nakon
> razdoblja neaktivnosti. Ako aplikacija odjednom ne može doći do baze,
> otvorite Supabase nadzornu ploču i vratite (*Restore*) projekt. Točne
> uvjete provjerite u Supabase dokumentaciji za vaš plan.

## 2. Pokretanje `supabase/schema.sql`

Shema stvara tablice `scouting_reports`, `shortlists` i `shortlist_players`,
s ograničenjima (CHECK), indeksima, vezama (foreign key), automatskim
`updated_at` i **uključenim Row Level Securityjem bez ijedne politike** (vidi
[Sigurnosni model](#sigurnosni-model)).

1. U Supabase projektu otvorite **SQL Editor** (lijevi izbornik).
2. Kliknite **New query**.
3. Otvorite datoteku [`supabase/schema.sql`](supabase/schema.sql) iz ovog
   repozitorija, kopirajte **cijeli** sadržaj i zalijepite ga u editor.
4. Kliknite **Run**. Očekivani rezultat: `Success. No rows returned`.
5. Provjera: otvorite **Table Editor**. Trebali biste vidjeti tri tablice
   (`scouting_reports`, `shortlists`, `shortlist_players`) i oznaku da je
   RLS uključen.

Datoteku možete sigurno pokrenuti i više puta (koristi `IF NOT EXISTS`).
Napomena: ponovno pokretanje **ne mijenja** postojeće tablice - ako kasnije
mijenjate shemu, radite to zasebnim SQL naredbama (`ALTER TABLE ...`).

## 3. Gdje su Project URL i ključ

U Supabase projektu otvorite **Settings → API Keys** (isti podaci vide se i u
dijalogu **Connect**). Trebate dvije vrijednosti:

| Što | Gdje | Primjer oblika | Naziv varijable |
|---|---|---|---|
| **Project URL** | Connect dijalog / Settings → API | `https://abcdefgh.supabase.co` | `SUPABASE_URL` |
| **Secret ključ** (server-side) | Settings → API Keys | `sb_secret_...` | `SUPABASE_SECRET_KEY` |

Koristite **isključivo novi *Secret key*** (`sb_secret_...`). Ova aplikacija
je nova i **ne podržava** stare (legacy) `service_role` JWT ključeve, pa ih
ne upisujte. **Nemojte** koristiti ni `anon` / *publishable* ključ - on ima
minimalna prava, pa zbog uključenog RLS-a aplikacija neće moći ništa čitati
ni pisati.

> **Secret ključ zaobilazi RLS.** Tretirajte ga kao lozinku za cijelu bazu.
> Nemojte ga slati e-poštom, lijepiti u chat, spremati u Git ni prikazivati na
> ekranu (aplikacija ga nikad ne prikazuje, ni cijelog ni djelomično). Ako ga
> slučajno otkrijete, odmah ga zamijenite (rotirajte) u Settings → API Keys.

## 4. Lokalno spremanje u `.env`

Za pokretanje na vlastitom računalu (`streamlit run scout_app.py`):

```powershell
copy .env.example .env
```

Otvorite `.env` i popunite **samo** ove tri linije:

```
SUPABASE_URL=https://vas-projekt.supabase.co
SUPABASE_SECRET_KEY=sb_secret_vas_kljuc
SCOUT_APP_PASSWORD=vasa_duga_nasumicna_zaporka
```

(Kako napraviti jaku zaporku: korak 5.)

Bez navodnika i bez razmaka oko `=`. `.env` je već u `.gitignore`, pa se
nikad ne commita. Provjerite:

```powershell
git check-ignore -v .env
```

Naredba treba ispisati redak iz `.gitignore` (znači da je datoteka
ignorirana). Ako ne ispiše ništa, **nemojte** commitati dok to ne ispravite.

Alternativa: umjesto `.env` možete koristiti `.streamlit/secrets.toml`
(također ignoriran) u formatu iz koraka 5.

Aplikacija konfiguraciju čita ovim redoslijedom: **1.** `st.secrets`,
**2.** varijable okruženja (uključujući `.env`).

## 5. Streamlit Secrets i zaporka aplikacije

Na Streamlit Community Cloudu tajne se ne stavljaju u repozitorij nego u
postavke **privatne** Streamlit aplikacije. Format je TOML, s ključevima na
vrhu razine:

```toml
SUPABASE_URL = "https://vas-projekt.supabase.co"
SUPABASE_SECRET_KEY = "sb_secret_vas_kljuc"
SCOUT_APP_PASSWORD = "vasa_duga_nasumicna_zaporka"
```

**Ne radite ovo još** - tajne se dodaju tek u koraku 7, *nakon* što je
aplikacija postavljena kao privatna.

### Zaporka aplikacije (`SCOUT_APP_PASSWORD`)

Zaporka je **drugi sloj zaštite** cijele aplikacije. Vrijedi za sve stranice
i provjerava se **prije** nego što se učitaju podaci ili stvori veza sa
Supabaseom.

**Kako napraviti jaku zaporku:** neka bude **duga (barem 20 znakova),
nasumična i jedinstvena** (ne koristite je nigdje drugdje). Najlakše je
generirati je u upravitelju lozinki ili ovako:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(24))"
```

Spremite je u upravitelj lozinki, a u Secrets (i lokalni `.env`) samo
zalijepite. Ne stavljajte razmake na početak ni kraj.

**Kako se ponaša:**

- **Bez postavljene zaporke aplikacija ostaje zaključana** i prikazuje samo
  poruku s poveznicom na ove upute. Ne postoji „otvoreni" način rada.
- Zaporku upisujete u polju na početnom zaslonu. Nakon uspješne prijave
  aplikacija pamti samo to da ste prijavljeni (jednu logičku oznaku u sessionu),
  **nikad samu zaporku**. Zaporka se ne prikazuje i ne upisuje u logove ni
  poruke o greškama.
- Gumb **Odjava** (bočna traka) briše oznaku prijave i ponovno zaključava
  aplikaciju.
- Nakon **3 uzastopne pogrešne zaporke** prikazuje se upozorenje, a nakon
  **5** se prijava privremeno blokira (30 sekundi, svaka sljedeća blokada
  traje dvostruko dulje, do 15 minuta). Tijekom blokade se ni točna zaporka ne
  prihvaća. Blokada vrijedi za cijelu aplikaciju, pa je ne poništava otvaranje
  novog taba; istječe sama, a poništava je i ponovno pokretanje aplikacije.
  Uspješna prijava (nakon što blokada istekne) briše brojač pogrešaka.
- Ako kasnije **uklonite** zaporku iz Secrets, i već otvorene sesije se
  zaključavaju. Ako je **promijenite**, već prijavljene sesije ostaju
  prijavljene dok se ne odjave ili ponovno učitaju - nakon promjene zaporke
  ponovno pokrenite aplikaciju (*Reboot app*).

> **Zaporka je dodatna zaštita, a ne zamjena za postavku *Only specific
> people can view this app*.** Obje postavite. Zaporka štiti od pogreške u
> postavkama (npr. aplikacija koja je slučajno ostala javna), ali ne štiti od
> curenja samog ključa iz drugih izvora.

## 6. Druga Streamlit aplikacija iz istog repozitorija

Isti repozitorij može pokretati dvije aplikacije: postojeći javni dashboard i
ovu privatnu. Postojeća aplikacija se ne dira.

1. Provjerite da su `scout_app.py`, `src/` i `requirements.txt` pushani na
   granu `main` na GitHubu.
2. Otvorite <https://share.streamlit.io> i prijavite se GitHub računom.
3. Kliknite **Create app** → **Deploy a public app from GitHub**
   (naziv opcije je isti i za privatne aplikacije - privatnost se postavlja
   u sljedećem koraku).
4. Ispunite:
   - **Repository:** `lcoric3/Football-Analytics-2026`
   - **Branch:** `main`
   - **Main file path:** `scout_app.py`
   - **App URL:** neka poddomena različita od javne aplikacije
5. Otvorite **Advanced settings** → **Python version: 3.12**.
6. ⚠️ **Polje Secrets OSTAVITE PRAZNO.**
7. Kliknite **Deploy**.

Zašto bez tajni: zadana vidljivost aplikacije ovisi o repozitoriju. Prema
Streamlit dokumentaciji su aplikacije iz **javnog** GitHub repozitorija
**po zadanom javne**, a iz **privatnog** repozitorija po zadanom vidljive samo
vama i članovima radnog prostora (uz ograničenje od jedne privatne aplikacije
odjednom). Provjerite vidljivost svog repozitorija na GitHubu; ako je javan,
svatko s poveznicom može otvoriti aplikaciju dok ne uključite privatnost
(korak 7). Bez tajni je to bezopasno: aplikacija je zaključana i ne prikazuje
nikakve podatke.

## 7. Kako aplikacija ostaje privatna

Napravite ovo **odmah nakon prvog deploya, prije dodavanja tajni**. To vrijedi
i za javni i za privatni repozitorij - ne oslanjajte se na zadanu vidljivost:

1. Otvorite aplikaciju na Community Cloudu → **⋮ / Settings → Sharing**
   (ili gumb **Share** u gornjem desnom kutu).
2. Odaberite **Only specific people can view this app** (ne „public").
3. Dodajte **svoju e-adresu** (i samo adrese osoba kojima vjerujete).
4. **Provjerite:** otvorite URL aplikacije u anonimnom/privatnom prozoru
   preglednika (ili odjavljeni). Morate dobiti zahtjev za prijavu, **ne**
   samu aplikaciju. Ako vidite aplikaciju, privatnost nije uključena -
   **ne dodavajte tajne**.
5. Tek sad: **Settings → Secrets**, zalijepite TOML iz koraka 5 (sve **tri**
   vrijednosti: `SUPABASE_URL`, `SUPABASE_SECRET_KEY` i `SCOUT_APP_PASSWORD`)
   i spremite. Aplikacija će se ponovno pokrenuti.

Dodatne mjere:

- Streamlit dokumentacija navodi da je dopuštena samo **jedna privatna
  aplikacija odjednom** (pravilo je opisano uz aplikacije iz privatnih
  repozitorija) - uvjete za svoj račun provjerite prije deploya. Ako ne
  možete uključiti privatnost, **ne postavljajte aplikaciju na Cloud** -
  pokrećite je samo lokalno (`streamlit run scout_app.py`), što je
  najsigurnija opcija.
- Ako ikad posumnjate da je aplikacija bila javna dok je imala ključ:
  rotirajte ključ u Supabaseu (Settings → API Keys), promijenite
  `SCOUT_APP_PASSWORD` i ažurirajte Secrets.
- Ne dijelite snimke zaslona *Postavki veze* bez provjere - aplikacija
  ne prikazuje URL ni ključ, ali prikazuje nazive tablica i greške baze.

## 8. Provjera veze i prvi izvještaj

1. Otvorite privatnu aplikaciju (lokalno ili na Cloudu, prijavljeni na
   Streamlit). Vidjet ćete zaslon s poljem **Zaporka**: upišite
   `SCOUT_APP_PASSWORD` i kliknite **Prijava**. (Ako umjesto polja vidite
   poruku „Aplikacija je zaključana", zaporka nije postavljena - korak 5.)
2. U bočnoj traci odaberite **Postavke veze**. U tablici „Konfiguracija"
   oba retka moraju imati izvor (*Streamlit Secrets* ili *varijabla
   okruženja*), a ne „NEDOSTAJE". Vrijednosti se nikad ne prikazuju.
3. Kliknite **Provjeri vezu s bazom**. Očekujete tri zelena retka:
   `scouting_reports: OK`, `shortlists: OK`, `shortlist_players: OK`.
4. Odaberite **Skautska procjena**, odaberite sezonu, upišite ime igrača i
   odaberite ga.
5. U kartici **Novi izvještaj** ispunite obavezna polja (označena s `*`):
   datum promatranja, promatrana pozicija, pet ocjena (1-10) i preporuka.
   Kliknite **Spremi izvještaj**.
6. Trebate vidjeti „Izvještaj je spremljen", a iznad tablice skautsku i
   kombiniranu ocjenu igrača.
7. Provjera u bazi: Supabase **Table Editor → `scouting_reports`** - redak
   mora biti tamo.

## Rješavanje problema

| Poruka / simptom | Uzrok i rješenje |
|---|---|
| „Aplikacija je zaključana. Zaštita zaporkom nije postavljena" | `SCOUT_APP_PASSWORD` nije postavljen (ili je prazan). Lokalno: `.env` (korak 4). Na Cloudu: Settings → Secrets (korak 7). Nakon promjene ponovno pokrenite aplikaciju. |
| „Pogrešna zaporka" | Zaporka se ne podudara (razlikuju se velika i mala slova). Kopirajte je iz upravitelja lozinki. |
| „Previše neuspjelih pokušaja. Pokušajte ponovno za N s" | Privremena blokada nakon 5 pogrešnih zaporki. Pričekajte da istekne (ili ponovno pokrenite aplikaciju). Točna zaporka se tijekom blokade ne prihvaća. |
| „Baza nije povezana. Nedostaje konfiguracija: ..." | `SUPABASE_URL` / `SUPABASE_SECRET_KEY` nisu postavljeni. Lokalno: provjerite `.env` (korak 4). Na Cloudu: Settings → Secrets (korak 7). Nakon promjene ponovno pokrenite aplikaciju. |
| `SUPABASE_URL mora počinjati s https://` | URL je prekratak/pogrešan. Kopirajte cijeli Project URL. |
| `42P01` / „relation ... does not exist" | Shema nije pokrenuta. Ponovite korak 2. |
| `42501` / „permission denied" | Vjerojatno ste u `SUPABASE_SECRET_KEY` upisali `anon`/*publishable* ključ. Upišite *Secret key* (`sb_secret_...`). |
| „Invalid API key" / `Supabase klijent nije inicijaliziran` | Ključ je pogrešno kopiran (razmak, navodnici, skraćen) ili je rotiran. Kopirajte *Secret key* (`sb_secret_...`) ponovno. Stari `service_role` JWT ključevi nisu podržani. |
| Veza pada nakon dužeg mirovanja | Besplatni projekt je možda pauziran - vratite ga (*Restore*) u Supabaseu. |
| `23505` pri dodavanju igrača | Igrač je već na toj shortlisti (očekivano; aplikacija to prikazuje kao upozorenje). |
| Aplikacija ne pronalazi igrače | Nedostaju CSV-ovi u `data/processed/`. Ovaj repozitorij ih već sadrži; lokalno pokrenite `python main.py` samo ako ih trebate regenerirati. |

## Kako se računaju ocjene

Sve ocjene su na ljestvici 0-100 i zaokružene na **jednu decimalu**
(zaokružuje se tek na kraju računa). Formule su u
[`src/scout_ratings.py`](src/scout_ratings.py), a težine su imenovane
konstante pokrivene testovima.

**1. Pretvorba ocjene 1-10 u 0-100:**

```
(ocjena - 1) / 9 * 100
```

Ocjena 1 daje 0, ocjena 10 daje 100.

**2. Skautska ocjena jednog izvještaja** (težinski zbroj pretvorenih ocjena):

```
0.30 * tehnička + 0.30 * taktička + 0.20 * fizička + 0.20 * mentalna
```

Ocjena potencijala **nije** dio skautske ocjene (procjena budućnosti, ne
onoga što je skaut vidio) - prikazuje se zasebno kao prosjek.

**3. Više izvještaja** za istog igrača i sezonu: skautska ocjena je
**prosjek** ocjena pojedinih izvještaja; prikazuje se i broj izvještaja.

**4. Kombinirana ocjena:**

```
0.65 * analytical_score + 0.35 * scout_score
```

`analytical_score` je postojeći `overall_score` iz analitičkog pipelinea
(ne mijenja se). **Kombinirana ocjena postoji samo kad postoje obje
ocjene.** Igrač bez skautskog izvještaja prikazuje samo analitičku ocjenu -
kombinirana vrijednost se nikad ne izmišlja.

Napomene:

- Kombinirana ocjena računa se iz *nezaokružene* skautske ocjene, pa se
  može razlikovati za 0,1 od ručnog računa nad zaokruženim brojevima na
  ekranu.
- `overall_score` gradi se iz akcija igrača u polju, pa za **golmane** nije
  smislena mjera (aplikacija to ističe uz golmane).
- Ocjene su relativne prema HNL sezoni iz koje dolaze - to su pomoć za
  odlučivanje, ne konačna procjena igrača.

## Sigurnosni model

Ovo je **jednokorisnička privatna verzija**.

- **Row Level Security je uključen** na sve tri tablice i **ne postoji
  nijedna politika**. To znači da uloge `anon` i `authenticated` (iza
  „javnog" ključa) ne mogu čitati ni pisati ništa. Dodatno, `schema.sql`
  radi `REVOKE` privilegija tim ulogama kao drugu, neovisnu bravu.
- Aplikacija pristupa bazi **isključivo server-side** secret ključem
  (`sb_secret_...`, varijabla `SUPABASE_SECRET_KEY`) spremljenim u **Streamlit
  Secrets** (ili lokalnom `.env`). Taj ključ zaobilazi RLS - upravo zato je
  aplikacija dizajnirana da bude privatna. Stari `service_role` JWT ključevi
  nisu podržani.
- Ključ se **ne koristi u klijentskom kodu**, **ne sprema** u session state,
  bazu ni Git, **ne prikazuje** na ekranu (ni djelomično) i **ne ispisuje u
  logove ni poruke o greškama** (greške se svode na naziv operacije i
  tip/šifru greške).
- **Dva neovisna sloja pristupa:** (1) Streamlit *Only specific people can
  view this app* i (2) zaporka `SCOUT_APP_PASSWORD`. Zaporka se provjerava
  **prije** učitavanja podataka i **prije** stvaranja Supabase klijenta, uspoređuje
  se u konstantnom vremenu (`hmac.compare_digest`), nikad se ne sprema (u
  session state ide samo logička oznaka prijave), ne prikazuje i ne logira.
  Ponovljeni pogrešni pokušaji privremeno blokiraju prijavu. Bez postavljene
  zaporke aplikacija ostaje zaključana.
- Javni dashboard `app.py` ne uvozi ništa od ovoga i ne zna ni za jednu od ovih
  tajni (pokriveno testom).
- Svi upiti idu preko službenog Supabase klijenta, koji vrijednosti šalje kao
  parametre - SQL se nikad ne slaže spajanjem tekstova.
- Brisanja (izvještaja, igrača sa shortliste, shortliste) zahtijevaju
  potvrdu u sučelju **i** dodatno u sloju baze.

Ako ikad budete htjeli više korisnika ili javni pristup, to nije dovoljno:
tada treba ukloniti secret ključ iz aplikacije i uvesti prijavu korisnika
(Supabase Auth) uz RLS politike po korisniku. Zajednička zaporka nije
prijava korisnika.
