thonimport logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Any

import requests
from dateutil import parser as dt_parser

from .utils_date import parse_twitter_timestamp

logger = logging.getLogger(__name__)

TWITTER_PROFILE_ENDPOINT = "https://cdn.syndication.twimg.com/timeline/profile"

@dataclass
class NormalizedUser:
    name: str
    followers_count: Optional[int]
    screen_name: str
    url: Optional[str]

@dataclass
class NormalizedTweet:
    bookmark_count: int
    created_at: str
    created_at_dt: datetime
    conversation_id_str: str
    entities: Optional[Dict[str, Any]]
    favorite_count: int
    full_text: str
    reply_count: int
    retweet_count: int
    views_count: Optional[int]
    user: NormalizedUser

def extract_screen_name_from_url(url: str) -> str:
    """
    Extract the screen name from a Twitter profile URL.
    Examples:
        https://twitter.com/elonmusk -> elonmusk
        https://x.com/elonmusk -> elonmusk
    """
    pattern = re.compile(r"https?://(?:www\.)?(?:twitter\.com|x\.com)/([^/?#]+)", re.IGNORECASE)
    match = pattern.match(url.strip())
    if not match:
        raise ValueError(f"Could not extract screen name from URL: {url}")
    screen_name = match.group(1)
    logger.debug("Extracted screen_name '%s' from URL '%s'", screen_name, url)
    return screen_name

def fetch_profile_tweets(screen_name: str, count: int = 200) -> Dict[str, Any]:
    """
    Fetch raw timeline data from Twitter's public profile syndication endpoint.

    This relies on a public JSON endpoint used by Twitter to embed timelines.
    It may change over time, so callers must be prepared for HTTP or parsing errors.
    """
    params = {"screen_name": screen_name, "count": str(count)}
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        )
    }

    logger.info("Fetching tweets for @%s", screen_name)
    resp = requests.get(TWITTER_PROFILE_ENDPOINT, params=params, headers=headers, timeout=15)
    resp.raise_for_status()

    try:
        data = resp.json()
    except ValueError as exc:
        logger.error("Failed to decode JSON for @%s: %s", screen_name, exc)
        raise

    return data

def _iter_raw_tweets(raw: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    """
    Attempt to iterate over tweet-like objects in the raw response.

    Different Twitter endpoints produce different shapes; this function
    tries a few known patterns and yields any tweet-like dicts it finds.
    """
    if not isinstance(raw, dict):
        return []

    # Pattern 1: legacy API-like structure { "globalObjects": { "tweets": { id: {...} } } }
    global_objects = raw.get("globalObjects")
    if isinstance(global_objects, dict):
        tweets_obj = global_objects.get("tweets")
        if isinstance(tweets_obj, dict):
            for tweet in tweets_obj.values():
                if isinstance(tweet, dict):
                    yield tweet

    # Pattern 2: simple list at "tweets"
    tweets_list = raw.get("tweets")
    if isinstance(tweets_list, list):
        for tweet in tweets_list:
            if isinstance(tweet, dict):
                yield tweet

    # Pattern 3: embedded "timeline" format often used in widgets
    timeline = raw.get("timeline")
    if isinstance(timeline, dict):
        instructions = timeline.get("instructions") or []
        for inst in instructions:
            if not isinstance(inst, dict):
                continue
            entries = inst.get("addEntries", {}).get("entries") or inst.get("entries")
            if not entries:
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                content = entry.get("content") or {}
                item = content.get("item") or {}
                tweet_results = item.get("tweet_results")
                if isinstance(tweet_results, dict):
                    result = tweet_results.get("result")
                    if isinstance(result, dict):
                        legacy = result.get("legacy")
                        if isinstance(legacy, dict):
                            yield legacy

def _normalize_user(tweet_obj: Dict[str, Any], user_obj: Optional[Dict[str, Any]] = None) -> NormalizedUser:
    u = user_obj or tweet_obj.get("user", {})

    name = u.get("name") or ""
    followers_count = u.get("followers_count")
    screen_name = u.get("screen_name") or ""
    url = u.get("url")

    # Sometimes extended user data lives under "entities"
    if not url and isinstance(u.get("entities"), dict):
        url_entities = u["entities"].get("url", {}).get("urls")
        if isinstance(url_entities, list) and url_entities:
            url = url_entities[0].get("expanded_url") or url_entities[0].get("url")

    return NormalizedUser(
        name=name,
        followers_count=followers_count if isinstance(followers_count, int) else None,
        screen_name=screen_name,
        url=url,
    )

def _normalize_tweet(tweet_obj: Dict[str, Any], user_obj: Optional[Dict[str, Any]] = None) -> Optional[NormalizedTweet]:
    created_at_str = tweet_obj.get("created_at")
    if not created_at_str:
        # Some GraphQL/modern APIs use "legacy" blocks; this should be handled by caller.
        return None

    dt = parse_twitter_timestamp(created_at_str)
    if dt is None:
        logger.debug("Could not parse created_at '%s'", created_at_str)
        return None

    conversation_id = tweet_obj.get("conversation_id_str") or str(tweet_obj.get("id_str") or tweet_obj.get("id") or "")
    full_text = tweet_obj.get("full_text") or tweet_obj.get("text") or ""

    entities = tweet_obj.get("entities") or {}

    bookmark_count = tweet_obj.get("bookmark_count") or 0
    favorite_count = tweet_obj.get("favorite_count") or tweet_obj.get("favorite_count", 0)
    reply_count = tweet_obj.get("reply_count") or tweet_obj.get("reply_count", 0)
    retweet_count = tweet_obj.get("retweet_count") or tweet_obj.get("retweet_count", 0)

    # Various keys for views/impressions
    views_count = None
    for key in ("views_count", "view_count", "impression_count", "impressions"):
        value = tweet_obj.get(key)
        if isinstance(value, int):
            views_count = value
            break
        if isinstance(value, str) and value.isdigit():
            views_count = int(value)
            break

    normalized_user = _normalize_user(tweet_obj, user_obj)

    return NormalizedTweet(
        bookmark_count=int(bookmark_count or 0),
        created_at=created_at_str,
        created_at_dt=dt,
        conversation_id_str=conversation_id,
        entities=entities,
        favorite_count=int(favorite_count or 0),
        full_text=str(full_text),
        reply_count=int(reply_count or 0),
        retweet_count=int(retweet_count or 0),
        views_count=views_count,
        user=normalized_user,
    )

def _flatten_normalized_tweet(t: NormalizedTweet) -> Dict[str, Any]:
    return {
        "bookmark_count": t.bookmark_count,
        "created_at": t.created_at,
        "conversation_id_str": t.conversation_id_str,
        "entities": t.entities,
        "favorite_count": t.favorite_count,
        "full_text": t.full_text,
        "reply_count": t.reply_count,
        "retweet_count": t.retweet_count,
        "views_count": t.views_count,
        "user": {
            "name": t.user.name,
            "followers_count": t.user.followers_count,
            "screen_name": t.user.screen_name,
            "url": t.user.url,
        },
    }

def normalize_and_filter_tweets(
    raw: Dict[str, Any],
    since_dt: datetime,
) -> List[Dict[str, Any]]:
    normalized: List[NormalizedTweet] = []

    # Some payloads contain a "users" collection keyed by id
    users_map = {}
    global_objects = raw.get("globalObjects")
    if isinstance(global_objects, dict):
        users_map = global_objects.get("users") or {}
        if not isinstance(users_map, dict):
            users_map = {}

    for tweet_obj in _iter_raw_tweets(raw):
        user_obj: Optional[Dict[str, Any]] = None
        user_id = tweet_obj.get("user_id") or tweet_obj.get("user_id_str")
        if user_id and isinstance(users_map, dict):
            user_obj = users_map.get(str(user_id))

        normalized_tweet = _normalize_tweet(tweet_obj, user_obj)
        if not normalized_tweet:
            continue

        if normalized_tweet.created_at_dt >= since_dt:
            normalized.append(normalized_tweet)

    normalized.sort(key=lambda t: t.created_at_dt, reverse=True)
    logger.debug("Normalized %d tweet(s) after filtering by since_dt=%s", len(normalized), since_dt)

    return [_flatten_normalized_tweet(t) for t in normalized]

def scrape_tweets_for_urls(urls: List[str], since_dt: datetime) -> List[Dict[str, Any]]:
    all_tweets: List[Dict[str, Any]] = []

    for url in urls:
        try:
            screen_name = extract_screen_name_from_url(url)
        except ValueError as exc:
            logger.error("Skipping URL '%s': %s", url, exc)
            continue

        try:
            raw = fetch_profile_tweets(screen_name)
        except requests.RequestException as exc:
            logger.error("Failed to fetch tweets for @%s: %s", screen_name, exc)
            continue
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected error while fetching @%s: %s", screen_name, exc)
            continue

        try:
            normalized = normalize_and_filter_tweets(raw, since_dt)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Failed to normalize tweets for @%s: %s", screen_name, exc)
            continue

        for tweet in normalized:
            tweet["_source_profile"] = screen_name

        all_tweets.extend(normalized)

    # Final global sorting by created_at (reverse chronological)
    def sort_key(obj: Dict[str, Any]) -> datetime:
        created_at = obj.get("created_at")
        if isinstance(created_at, str):
            try:
                return dt_parser.parse(created_at)
            except Exception:
                return datetime.min
        return datetime.min

    all_tweets.sort(key=sort_key, reverse=True)
    logger.info("Aggregated %d tweet(s) across all URLs.", len(all_tweets))
    return all_tweets