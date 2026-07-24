# Drama Radar

Twice-daily X (Twitter) story-sourcing and viral-rating tool. Pulls recent
posts from a list of tracked accounts plus a set of keyword searches, scores
each post for viral potential, and shows a ranked, mobile-friendly list.

## How it works

1. `.github/workflows/fetch-and-score.yml` runs on a cron schedule (twice a
   day, ~12 hours apart) and on manual trigger.
2. It runs `scripts/fetch_and_score.py`, which:
   - Calls the X API v2 recent-search endpoint once for all `tracked_accounts`
     (combined as `from:a OR from:b OR ...`), and once per entry in
     `keywords`.
   - Scores every post (see below) and merges the results into
     `docs/results.json`, keeping only posts from the last `lookback_days`
     (default 7).
3. The workflow commits `docs/results.json` back to the repo.
4. `docs/index.html` (static HTML/JS, no build step) fetches `results.json`
   and renders a ranked, filterable list. Deploy `docs/` with GitHub Pages
   and it's reachable from your phone.

## Setup

### 1. X API access

You need an X API v2 **bearer token** with access to the recent-search
endpoint (`GET /2/tweets/search/recent`) — this requires at least the Basic
tier of the API (the free tier doesn't include search). Generate one in the
[X Developer Portal](https://developer.x.com/).

Add it as a repo secret:

- Repo **Settings → Secrets and variables → Actions → New repository secret**
- Name: `X_BEARER_TOKEN`
- Value: your bearer token

### 2. Enable GitHub Pages

- Repo **Settings → Pages**
- Source: **Deploy from a branch**
- Branch: your default branch, folder **`/docs`**

Once merged to the default branch, your dashboard will be live at
`https://<user>.github.io/<repo>/`.

Note: GitHub Actions `schedule` triggers only fire on the **default branch**,
so the twice-daily cron won't run until this is merged there. You can test it
early with **Actions → Fetch and score X posts → Run workflow** (this works
on any branch via `workflow_dispatch`).

### 3. Edit your config

`config.json` at the repo root — no code changes needed:

```json
{
  "tracked_accounts": ["someuser", "anotheruser"],
  "keywords": ["some search phrase", "another term"],
  "score_weights": { "velocity": 0.5, "engagement_ratio": 0.3, "controversy": 0.2 },
  "lookback_days": 7
}
```

The placeholder accounts/keywords in this repo are guesses and should be
verified/replaced with real handles before relying on this tool.

## Viral score

For each post, three raw signals are computed then squashed into 0-100
sub-scores (so no single viral outlier blows past 100) and combined with the
weights from `config.json`:

| Signal | Raw formula | What it captures |
|---|---|---|
| **Velocity** | `(likes + retweets + replies + quotes) / hours_since_posted` | How fast engagement is accumulating |
| **Engagement ratio** | `total_engagement / follower_count` | Punching above the author's normal reach |
| **Controversy** | `replies / likes` | Disproportionate reply activity — a proxy for drama/debate |

`overall = w_velocity * velocity_score + w_ratio * ratio_score + w_controversy * controversy_score`,
capped at 100. All raw values and sub-scores are stored per-post in
`docs/results.json` so you can see why something scored the way it did.

## Local testing

```bash
pip install -r scripts/requirements.txt
export X_BEARER_TOKEN=your_token_here
python scripts/fetch_and_score.py
# then open docs/index.html with a local static server, e.g.:
python -m http.server --directory docs 8080
```

## Repo layout

```
config.json                       tracked accounts, keywords, score weights
scripts/fetch_and_score.py        fetch + score + write docs/results.json
scripts/requirements.txt
docs/index.html, style.css, app.js  frontend (GitHub Pages source)
docs/results.json                 generated data (committed by the workflow)
.github/workflows/fetch-and-score.yml
```
