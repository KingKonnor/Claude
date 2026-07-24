#!/usr/bin/env python3
"""Fetch recent X posts for tracked accounts and keyword searches, score
them for viral potential, and merge the results into docs/results.json.

Reads config.json for the account/keyword lists and scoring weights.
Requires the X_BEARER_TOKEN environment variable (X API v2 bearer token).
"""

import json
import math
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config.json"
RESULTS_PATH = REPO_ROOT / "docs" / "results.json"

SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"
TWEET_FIELDS = "created_at,public_metrics,author_id"
USER_FIELDS = "username,name,public_metrics"
EXPANSIONS = "author_id"
MAX_RESULTS = 100

DEFAULT_WEIGHTS = {"velocity": 0.5, "engagement_ratio": 0.3, "controversy": 0.2}


def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def load_existing_posts():
    if RESULTS_PATH.exists():
        with open(RESULTS_PATH) as f:
            data = json.load(f)
        return {post["id"]: post for post in data.get("posts", [])}
    return {}


def bearer_token():
    token = os.environ.get("X_BEARER_TOKEN")
    if not token:
        print("ERROR: X_BEARER_TOKEN environment variable is not set.", file=sys.stderr)
        sys.exit(1)
    return token


def parse_created_at(created_at_str):
    fmt = "%Y-%m-%dT%H:%M:%S.%fZ" if "." in created_at_str else "%Y-%m-%dT%H:%M:%SZ"
    return datetime.strptime(created_at_str, fmt).replace(tzinfo=timezone.utc)


def hours_since(created_at_str):
    delta = datetime.now(timezone.utc) - parse_created_at(created_at_str)
    return max(delta.total_seconds() / 3600.0, 0.25)


def search_recent(query, token):
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "query": query,
        "max_results": MAX_RESULTS,
        "tweet.fields": TWEET_FIELDS,
        "expansions": EXPANSIONS,
        "user.fields": USER_FIELDS,
    }
    resp = requests.get(SEARCH_URL, headers=headers, params=params, timeout=30)
    if resp.status_code == 429:
        print(f"WARNING: rate limited on query {query!r}, skipping this run.", file=sys.stderr)
        return [], {}
    resp.raise_for_status()
    body = resp.json()
    tweets = body.get("data", [])
    users = {u["id"]: u for u in body.get("includes", {}).get("users", [])}
    return tweets, users


def build_account_query(accounts):
    from_clause = " OR ".join(f"from:{a}" for a in accounts)
    return f"({from_clause}) -is:retweet"


def score_post(likes, retweets, replies, quotes, followers, hours, weights):
    """Combine three signals into a 0-100 viral score.

    Each raw signal is unbounded, so it's squashed with log1p / a cap before
    weighting so no single viral outlier blows the scale past 100.
    """
    total_engagement = likes + retweets + replies + quotes

    velocity_raw = total_engagement / hours
    velocity_score = min(100.0, math.log1p(velocity_raw) * 12.0)

    ratio_raw = total_engagement / max(followers, 1)
    engagement_ratio_score = min(100.0, ratio_raw * 500.0)

    controversy_raw = replies / max(likes, 1)
    controversy_score = min(100.0, controversy_raw * 40.0)

    overall = (
        weights.get("velocity", DEFAULT_WEIGHTS["velocity"]) * velocity_score
        + weights.get("engagement_ratio", DEFAULT_WEIGHTS["engagement_ratio"]) * engagement_ratio_score
        + weights.get("controversy", DEFAULT_WEIGHTS["controversy"]) * controversy_score
    )

    return {
        "velocity_raw": round(velocity_raw, 3),
        "velocity_score": round(velocity_score, 2),
        "engagement_ratio_raw": round(ratio_raw, 5),
        "engagement_ratio_score": round(engagement_ratio_score, 2),
        "controversy_raw": round(controversy_raw, 3),
        "controversy_score": round(controversy_score, 2),
        "overall": round(min(100.0, overall), 2),
    }


def build_post_record(tweet, users, source_type, matched_keyword, weights):
    author = users.get(tweet["author_id"], {})
    metrics = tweet.get("public_metrics", {})
    likes = metrics.get("like_count", 0)
    retweets = metrics.get("retweet_count", 0)
    replies = metrics.get("reply_count", 0)
    quotes = metrics.get("quote_count", 0)
    followers = author.get("public_metrics", {}).get("followers_count", 0)
    hours = hours_since(tweet["created_at"])
    username = author.get("username", "unknown")

    record = {
        "id": tweet["id"],
        "source_type": source_type,
        "author": {
            "username": username,
            "name": author.get("name", username),
            "followers_count": followers,
        },
        "text": tweet.get("text", ""),
        "created_at": tweet["created_at"],
        "url": f"https://x.com/{username}/status/{tweet['id']}",
        "metrics": {
            "likes": likes,
            "retweets": retweets,
            "replies": replies,
            "quotes": quotes,
        },
        "score": score_post(likes, retweets, replies, quotes, followers, hours, weights),
    }
    if matched_keyword:
        record["matched_keyword"] = matched_keyword
    return record


def main():
    config = load_config()
    token = bearer_token()
    weights = config.get("score_weights", DEFAULT_WEIGHTS)
    lookback_days = config.get("lookback_days", 7)

    posts_by_id = load_existing_posts()

    accounts = config.get("tracked_accounts", [])
    if accounts:
        tweets, users = search_recent(build_account_query(accounts), token)
        for tweet in tweets:
            record = build_post_record(tweet, users, "tracked_account", None, weights)
            posts_by_id[record["id"]] = record
        print(f"Fetched {len(tweets)} posts from {len(accounts)} tracked accounts.")

    keywords = config.get("keywords", [])
    for keyword in keywords:
        query = f'"{keyword}" -is:retweet'
        tweets, users = search_recent(query, token)
        for tweet in tweets:
            record = build_post_record(tweet, users, "keyword_search", keyword, weights)
            # A tracked-account post takes priority over a keyword match for the same tweet.
            if record["id"] not in posts_by_id or posts_by_id[record["id"]]["source_type"] != "tracked_account":
                posts_by_id[record["id"]] = record
        print(f"Fetched {len(tweets)} posts for keyword {keyword!r}.")
        time.sleep(1)

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    posts = [p for p in posts_by_id.values() if parse_created_at(p["created_at"]) >= cutoff]
    posts.sort(key=lambda p: p["score"]["overall"], reverse=True)

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_PATH, "w") as f:
        json.dump(
            {
                "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "posts": posts,
            },
            f,
            indent=2,
        )
        f.write("\n")
    print(f"Wrote {len(posts)} posts to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
