"""
╔══════════════════════════════════════════════════════╗
║  VELTRA MUSIC BOT — VIDEOMATE SEARCH (FIXED & FAST)  ║
║  VideoMate Search → Invidious Stream · Cobalt Direct  ║
║  All Bugs Fixed · Kurdish Mode Enhanced · Faster      ║
╚══════════════════════════════════════════════════════╝
"""

import discord
from discord.ext import commands
import asyncio
import os
import time
import math
import random
import sqlite3
import aiohttp
import logging
import traceback
import re
import json
import shutil
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    print("[FATAL] No DISCORD_TOKEN in environment")
    raise SystemExit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("veltra.log", encoding="utf-8", mode="a"),
    ],
)
log = logging.getLogger("veltra")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix="$", intents=intents, help_command=None)
bot_start_time = time.time()

C_LUNA   = 0xB5179E
C_GREEN  = 0x57F287
C_RED    = 0xED4245
C_YELLOW = 0xFEE75C

# ── yt-dlp binary (primary audio extractor for YouTube) ──
YTDLP_BIN = (
    shutil.which("yt-dlp")
    or os.path.expanduser("~/.local/bin/yt-dlp")
    or "/home/user/.local/bin/yt-dlp"
)
if not os.path.isfile(YTDLP_BIN or ""):
    YTDLP_BIN = None

# All URLs must include https:// prefix — BUG FIX: many were missing https://
INVIDIOUS_STREAM = [
    "https://inv.nadeko.net",
    "https://invidious.fdn.fr",
    "https://iv.ggtyler.dev",
    "https://invidious.protokolla.fi",
    "https://yt.artemislena.eu",
    "https://invidious.privacydev.net",
    "https://invidious.nerdvpn.de",
]

INVIDIOUS_SEARCH = [
    "https://inv.nadeko.net",
    "https://invidious.fdn.fr",
    "https://iv.ggtyler.dev",
    "https://invidious.protokolla.fi",
    "https://yt.artemislena.eu",
    "https://invidious.perennialte.ch",
    "https://invidious.privacydev.net",
    "https://invidious.nerdvpn.de",
    "https://vid.puffyan.us",
]

PIPED_SEARCH = [
    "https://pipedapi.kavin.rocks",
    "https://pipedapi.adminforge.de",
    "https://pipedapi.in.projectsegfau.lt",
    "https://piped-api.garudalinux.org",
]

# ═══════════════════════════════════════
#  DATABASE
# ═══════════════════════════════════════
DB_FILE = "veltra.db"


def _db():
    return sqlite3.connect(DB_FILE, timeout=10)


def init_db():
    try:
        conn = _db()
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id     INTEGER PRIMARY KEY,
                dj_role_id   INTEGER DEFAULT NULL,
                volume       INTEGER DEFAULT 100,
                loop_mode    TEXT    DEFAULT 'off',
                tfs          INTEGER DEFAULT 0,
                autoplay     INTEGER DEFAULT 0,
                kurdish_mode INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS history (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id   INTEGER,
                title      TEXT,
                url        TEXT,
                duration   TEXT,
                requester  TEXT,
                platform   TEXT    DEFAULT 'unknown',
                played_at  TEXT    DEFAULT (datetime('now'))
            );
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        log.error(f"DB init error: {e}")


init_db()


def get_settings(gid):
    try:
        conn = _db()
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM guild_settings WHERE guild_id=?", (gid,)
        ).fetchone()
        if not row:
            conn.execute(
                "INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)", (gid,)
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM guild_settings WHERE guild_id=?", (gid,)
            ).fetchone()
        conn.close()
        if row:
            return dict(row)
    except Exception as e:
        log.error(f"get_settings error: {e}")
    return {
        "dj_role_id": None,
        "volume": 100,
        "loop_mode": "off",
        "tfs": 0,
        "autoplay": 0,
        "kurdish_mode": 1,
    }


def save_settings(gid, **kw):
    try:
        get_settings(gid)
        sets = ", ".join(f"{k}=?" for k in kw)
        conn = _db()
        conn.execute(
            f"UPDATE guild_settings SET {sets} WHERE guild_id=?",
            [*kw.values(), gid],
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log.error(f"save_settings error: {e}")


def push_history(gid, title, url, dur, req, plat="unknown"):
    try:
        conn = _db()
        conn.execute(
            "INSERT INTO history (guild_id,title,url,duration,requester,platform) VALUES (?,?,?,?,?,?)",
            (gid, title, url, dur, req, plat),
        )
        conn.execute(
            "DELETE FROM history WHERE guild_id=? AND id NOT IN "
            "(SELECT id FROM history WHERE guild_id=? ORDER BY id DESC LIMIT 50)",
            (gid, gid),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


# ═══════════════════════════════════════
#  FILTERS
# ═══════════════════════════════════════
FILTERS = {
    "none":       {"label": "🎵 None",       "af": ""},
    "bassboost":  {"label": "🔊 Bass Boost",  "af": "bass=g=10,dynaudnorm=f=200"},
    "nightcore":  {"label": "🌙 Nightcore",   "af": "asetrate=44100*1.25,aresample=44100"},
    "vaporwave":  {"label": "🌊 Vaporwave",   "af": "asetrate=44100*0.8,aresample=44100"},
    "8d":         {"label": "🎧 8D Audio",    "af": "apulsator=hz=0.08"},
    "karaoke":    {"label": "🎤 Karaoke",     "af": "stereotools=mlev=0.03125"},
    "tremolo":    {"label": "〰️ Tremolo",    "af": "tremolo=f=4:d=0.9"},
    "vibrato":    {"label": "🎸 Vibrato",     "af": "vibrato=f=6.5:d=0.9"},
    "superbass":  {"label": "💥 Super Bass",  "af": "bass=g=20,dynaudnorm=f=200"},
    "soft":       {"label": "🕊️ Soft",       "af": "lowpass=f=300,volume=1.5"},
    "earrape":    {"label": "📢 Ear Rape",    "af": "acrusher=level_in=8:level_out=18:bits=8:mode=log:aa=1"},
    "pitch":      {"label": "🎵 Pitch Up",    "af": "asetrate=44100*1.15,aresample=44100"},
}

# ═══════════════════════════════════════
#  PLATFORM DETECTION
# ═══════════════════════════════════════
def detect_platform(url):
    if not url:
        return "unknown"
    lower_url = url.lower()
    if "spotify.com" in lower_url:
        return "spotify"
    if "music.apple.com" in lower_url:
        return "apple_music"
    if "soundcloud.com" in lower_url:
        return "soundcloud"
    if "deezer.com" in lower_url:
        return "deezer"
    if "anghami.com" in lower_url:
        return "anghami"
    if "facebook.com" in lower_url or "fb.watch" in lower_url:
        return "facebook"
    if "twitch.tv" in lower_url:
        return "twitch"
    if "vimeo.com" in lower_url:
        return "vimeo"
    if "videomate.com" in lower_url:
        return "videomate"
    if "youtube.com" in lower_url or "youtu.be" in lower_url:
        return "youtube"
    if any(lower_url.endswith(ext) for ext in (".mp3", ".mp4", ".m4a", ".ogg", ".wav", ".flac", ".webm")):
        return "direct"
    return "unknown"


PLATFORM_EMOJIS = {
    "spotify":     "🎵",
    "apple_music": "🍎",
    "soundcloud":  "☁️",
    "deezer":      "🎶",
    "anghami":     "🌙",
    "facebook":    "👤",
    "twitch":      "📺",
    "vimeo":       "📹",
    "videomate":   "🔍",
    "youtube":     "▶️",
    "direct":      "📎",
    "unknown":     "🔍",
}

PLATFORM_LABELS = {
    "spotify":     "Spotify",
    "apple_music": "Apple Music",
    "soundcloud":  "SoundCloud",
    "deezer":      "Deezer",
    "anghami":     "Anghami",
    "facebook":    "Facebook",
    "twitch":      "Twitch",
    "vimeo":       "Vimeo",
    "videomate":   "VideoMate",
    "youtube":     "YouTube",
    "direct":      "Direct Link",
    "unknown":     "Unknown",
}

# ═══════════════════════════════════════
#  KURDISH DETECTION — ENHANCED
# ═══════════════════════════════════════
KURDISH_KEYWORDS = [
    # Language identifiers
    "kurdish", "kurdi", "كوردي", "كوردیی", "kurdî", "کوردی", "کوردیی",
    # Genres / terms
    "stran", "gorani", "muzik kurdi", "kurdish song", "kurdish music",
    "muzika kurdi", "awaza", "dengbej",
    # Regions
    "kurdistan", "hawler", "slemani", "erbil", "duhok", "sulaymaniyah",
    "halabja", "kerkuk", "mahabad", "qamishli",
    # Artists (famous Kurdish musicians)
    "shivan perwer", "nasir razazi", "xoshnaw", "dilgesh", "dilnoza",
    "mihemed şexo", "zagros", "choni", "soran", "hasan zirak",
    "ayten arsen", "govend", "koma", "birhat",
    # Additional terms
    "sorani", "badini", "kurmanji", "zazaki",
]

KURDISH_CHAR_RANGES = [
    ('\u0600', '\u06FF'),   # Arabic/Persian/Kurdish block
    ('\u0750', '\u077F'),   # Arabic supplement
    ('\uFB50', '\uFDFF'),   # Arabic presentation forms A
    ('\uFE70', '\uFEFF'),   # Arabic presentation forms B
]


def is_kurdish(title):
    if not title:
        return False
    for char in title:
        for start, end in KURDISH_CHAR_RANGES:
            if start <= char <= end:
                return True
    lower_title = title.lower()
    for kw in KURDISH_KEYWORDS:
        if kw in lower_title:
            return True
    return False


def get_kurdish_queries(query):
    """Generate multiple Kurdish search query variants for maximum coverage."""
    if is_kurdish(query):
        return [
            query,
            f"{query} stran",
            f"{query} gorani",
        ]
    return [
        f"{query} kurdish song کوردی",
        f"{query} کوردی gorani",
        f"{query} stran kurdî",
        f"{query} kurdish cover",
        f"{query} muzik kurdi",
        f"{query} سۆرانی",
        f"{query} کرمانجی",
        query,
    ]


# ═══════════════════════════════════════
#  ★ VIDEOMATE SEARCH ENGINE ★
# ═══════════════════════════════════════
async def _scrape_videomate(session, query):
    """
    Scrape VideoMate search page for YouTube video IDs.
    VideoMate is a YouTube frontend — IDs are real YouTube video IDs.
    We get titles/thumbnails from Invidious JSON API in parallel.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        async with session.get(
            "https://www.videomate.com/search",
            params={"q": query},
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=8),
            ssl=False,
        ) as response:
            if response.status != 200:
                log.debug(f"VideoMate HTTP {response.status}")
                return None

            html = await response.text()

            if len(html) < 500:
                log.debug("VideoMate page too short (Captcha/Block?)")
                return None

            # Method 1: /watch/VIDEO_ID patterns
            video_ids = re.findall(r'href=["\']?/watch/([a-zA-Z0-9_-]{11})', html)

            if not video_ids:
                # Method 2: youtube.com/watch?v=VIDEO_ID
                video_ids = re.findall(r'youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})', html)

            if not video_ids:
                # Method 3: data-id or data-videoid attributes
                video_ids = re.findall(r'data-(?:video)?id=["\']([a-zA-Z0-9_-]{11})["\']', html)

            if not video_ids:
                log.debug("No video IDs found on VideoMate")
                return None

            # Deduplicate preserving order
            seen = set()
            unique_ids = []
            for vid in video_ids:
                if vid not in seen:
                    seen.add(vid)
                    unique_ids.append(vid)

            if not unique_ids:
                return None

            # Get details from Invidious for the first 6 IDs in parallel
            tasks = [_get_inv_details(session, vid) for vid in unique_ids[:6]]
            done = await asyncio.gather(*tasks, return_exceptions=True)

            results = [r for r in done if isinstance(r, dict) and r]
            if results:
                log.info(f"VideoMate: {len(results)} results for '{query[:40]}'")
                return results

    except Exception as e:
        log.debug(f"VideoMate error: {e}")

    return None


async def _get_inv_details(session, video_id):
    """Get video details from Invidious API for a YouTube ID."""
    # Try multiple Invidious instances for reliability
    for base in INVIDIOUS_SEARCH[:3]:
        try:
            async with session.get(
                f"{base}/api/v1/videos/{video_id}",
                params={"fields": "title,lengthSeconds,author,videoThumbnails"},
                timeout=aiohttp.ClientTimeout(total=5),
                ssl=False,
            ) as r:
                if r.status != 200:
                    continue
                data = await r.json()

                thumbs = data.get("videoThumbnails") or []
                thumb_url = ""
                for t in reversed(thumbs):
                    url_val = t.get("url", "")
                    if url_val.startswith("http"):
                        thumb_url = url_val
                        break

                return {
                    "id": video_id,
                    "title": data.get("title") or f"Video {video_id}",
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "webpage_url": f"https://www.youtube.com/watch?v={video_id}",
                    "duration": int(data.get("lengthSeconds") or 0),
                    "thumbnail": thumb_url or f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg",
                    "uploader": data.get("author") or "Unknown",
                    "channel": data.get("author") or "Unknown",
                }
        except Exception:
            continue

    # Fallback: return minimal info without Invidious metadata
    return {
        "id": video_id,
        "title": f"Video {video_id}",
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "webpage_url": f"https://www.youtube.com/watch?v={video_id}",
        "duration": 0,
        "thumbnail": f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg",
        "uploader": "Unknown",
        "channel": "Unknown",
    }


async def _fetch_invidious_search(session, base_url, query):
    """Invidious search fallback."""
    try:
        async with session.get(
            f"{base_url}/api/v1/search",
            params={"q": query, "type": "video", "sort_by": "relevance"},
            timeout=aiohttp.ClientTimeout(total=5),
            ssl=False,
        ) as r:
            if r.status != 200:
                return None
            data = await r.json()
            if not isinstance(data, list):
                return None
            results = []
            for item in data:
                if len(results) >= 5:
                    break
                if item.get("type") != "video":
                    continue
                vid = item.get("videoId")
                if not vid:
                    continue
                results.append({
                    "id": vid,
                    "title": item.get("title", "Unknown"),
                    "url": f"https://www.youtube.com/watch?v={vid}",
                    "webpage_url": f"https://www.youtube.com/watch?v={vid}",
                    "duration": int(item.get("lengthSeconds") or 0),
                    "thumbnail": f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
                    "uploader": item.get("author", "Unknown"),
                    "channel": item.get("author", "Unknown"),
                })
            if results:
                return results
    except Exception:
        pass

    return None


async def _fetch_piped_search(session, base_url, query):
    """Piped search fallback."""
    try:
        async with session.get(
            f"{base_url}/search",
            params={"q": query, "filter": "videos"},
            timeout=aiohttp.ClientTimeout(total=5),
            ssl=False,
        ) as r:
            if r.status != 200:
                return None
            data = await r.json()
            items = data.get("items") or []
            if not items:
                return None
            results = []
            for item in items:
                if len(results) >= 5:
                    break
                item_url = item.get("url", "")
                vid = ""
                if "v=" in item_url:
                    vid = item_url.split("v=")[1].split("&")[0]
                if not vid:
                    continue
                thumb = item.get("thumbnail", "") or f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg"
                results.append({
                    "id": vid,
                    "title": item.get("title", "Unknown"),
                    "url": f"https://www.youtube.com/watch?v={vid}",
                    "webpage_url": f"https://www.youtube.com/watch?v={vid}",
                    "duration": int(item.get("duration") or 0),
                    "thumbnail": thumb,
                    "uploader": item.get("uploaderName", "Unknown"),
                    "channel": item.get("uploaderName", "Unknown"),
                })
            if results:
                return results
    except Exception:
        pass

    return None


async def _scrape_youtube_search(session, query):
    """
    Scrape YouTube search results directly as an additional fallback.
    Extracts video IDs from YouTube search page HTML.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        async with session.get(
            "https://www.youtube.com/results",
            params={"search_query": query},
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=8),
            ssl=False,
        ) as r:
            if r.status != 200:
                return None
            html = await r.text()
            # Extract video IDs from YouTube search results
            video_ids = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})"', html)
            if not video_ids:
                return None
            # Deduplicate
            seen = set()
            unique_ids = []
            for vid in video_ids:
                if vid not in seen:
                    seen.add(vid)
                    unique_ids.append(vid)
            if not unique_ids:
                return None
            # Build minimal results from IDs (faster, no API call needed)
            # Try to extract titles from JSON in page
            titles = {}
            title_matches = re.findall(r'"videoId":"([a-zA-Z0-9_-]{11})".*?"text":"([^"]{3,100})"', html)
            for vid, title in title_matches:
                if vid not in titles:
                    titles[vid] = title
            results = []
            for vid in unique_ids[:6]:
                results.append({
                    "id": vid,
                    "title": titles.get(vid, f"Video {vid}"),
                    "url": f"https://www.youtube.com/watch?v={vid}",
                    "webpage_url": f"https://www.youtube.com/watch?v={vid}",
                    "duration": 0,
                    "thumbnail": f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
                    "uploader": "Unknown",
                    "channel": "Unknown",
                })
            return results if results else None
    except Exception as e:
        log.debug(f"YouTube scrape error: {e}")
    return None


async def instant_search(query):
    """
    PARALLEL SEARCH: Fires to VideoMate + YouTube + all Invidious + all Piped AT THE SAME TIME.
    Returns the very first result that replies. Sub-second speed.
    """
    async with aiohttp.ClientSession() as session:
        tasks = []

        # Priority 1: VideoMate (best for Kurdish)
        tasks.append(_scrape_videomate(session, query))

        # Priority 2: YouTube direct scrape
        tasks.append(_scrape_youtube_search(session, query))

        # Priority 3: All Invidious instances (parallel)
        for base in INVIDIOUS_SEARCH:
            tasks.append(_fetch_invidious_search(session, base, query))

        # Priority 4: All Piped instances (parallel)
        for base in PIPED_SEARCH:
            tasks.append(_fetch_piped_search(session, base, query))

        # Return VERY FIRST successful result
        for future in asyncio.as_completed(tasks):
            try:
                result = await future
                if result:
                    return result
            except Exception:
                continue

    return []


async def search_songs(query, kurdish_mode=True, force_kurdish=False):
    """Search songs with Kurdish mode support and broad fallback."""
    if force_kurdish:
        queries = get_kurdish_queries(query)
    elif kurdish_mode and not is_kurdish(query):
        queries = [f"{query} kurdish kurdi کوردی", f"{query} stran gorani", query]
    else:
        queries = [query]

    all_results = []
    seen_ids = set()

    for current_query in queries:
        results = await instant_search(current_query)
        if not results:
            continue

        if force_kurdish or (kurdish_mode and not is_kurdish(query)):
            kurdish_results = [r for r in results if is_kurdish(r.get("title", ""))]
            if kurdish_results:
                for r in kurdish_results:
                    vid = r.get("id")
                    if vid and vid not in seen_ids:
                        seen_ids.add(vid)
                        all_results.append(r)
                if len(all_results) >= 5:
                    break
                continue
            # No Kurdish results from this query — try the non-Kurdish results as last resort
            for r in results:
                vid = r.get("id")
                if vid and vid not in seen_ids:
                    seen_ids.add(vid)
                    all_results.append(r)
        else:
            for r in results:
                vid = r.get("id")
                if vid and vid not in seen_ids:
                    seen_ids.add(vid)
                    all_results.append(r)
            if len(all_results) >= 5:
                break

    # Final fallback: if force_kurdish found nothing, return any result for the query
    if not all_results:
        results = await instant_search(query)
        for r in results:
            vid = r.get("id")
            if vid and vid not in seen_ids:
                seen_ids.add(vid)
                all_results.append(r)

    return all_results[:5]


# ═══════════════════════════════════════
#  STREAM EXTRACTION
# ═══════════════════════════════════════
async def _ytdlp_extract(url: str) -> dict | None:
    """
    Primary audio extractor — uses yt-dlp subprocess.
    Works for YouTube, VideoMate, and most other platforms.
    This is the most reliable method — returns a direct playable stream URL.
    """
    if not YTDLP_BIN:
        log.warning("yt-dlp binary not found — skipping")
        return None

    try:
        proc = await asyncio.create_subprocess_exec(
            YTDLP_BIN,
            "-f", "bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio/best",
            "--no-playlist",
            "-j",                    # JSON output with all metadata
            "--no-warnings",
            "--quiet",
            "--no-check-certificate",
            url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=25)
        except asyncio.TimeoutError:
            proc.kill()
            log.warning(f"yt-dlp timed out for: {url[:60]}")
            return None

        if proc.returncode != 0 or not stdout:
            err_msg = stderr.decode(errors="ignore")[:200] if stderr else "no output"
            log.debug(f"yt-dlp failed (rc={proc.returncode}): {err_msg}")
            return None

        data = json.loads(stdout.decode(errors="ignore"))

        stream_url = data.get("url") or data.get("manifest_url")
        if not stream_url:
            log.debug("yt-dlp returned no stream URL")
            return None

        # HTTP headers yt-dlp says are required for this stream
        http_headers = data.get("http_headers") or {}

        return {
            "url":         stream_url,
            "webpage_url": data.get("webpage_url") or url,
            "title":       data.get("title") or "Unknown",
            "duration":    int(data.get("duration") or 0),
            "thumbnail":   data.get("thumbnail") or "",
            "uploader":    data.get("uploader") or data.get("channel") or "Unknown",
            "http_headers": http_headers,
        }

    except json.JSONDecodeError as e:
        log.debug(f"yt-dlp JSON parse error: {e}")
        return None
    except Exception as e:
        log.debug(f"yt-dlp error: {e}")
        return None


async def _get_cobalt_stream(session, url):
    """
    Cobalt API extracts direct audio from:
    Spotify, Apple Music, SoundCloud, Deezer, Facebook, Twitch, Vimeo, Direct MP3s
    """
    COBALT_INSTANCES = [
        "https://api.cobalt.tools/",
        "https://co.wuk.sh/",
    ]
    for cobalt_url in COBALT_INSTANCES:
        try:
            async with session.post(
                cobalt_url,
                json={
                    "url": url,
                    "videoQuality": "360",
                    "audioFormat": "mp3",
                    "isAudioOnly": True,
                },
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=10),
                ssl=False,
            ) as r:
                if r.status != 200:
                    continue
                data = await r.json()
                stream_url = data.get("url")
                if stream_url:
                    return {
                        "url": stream_url,
                        "title": data.get("title") or "Unknown",
                        "duration": data.get("duration") or 0,
                        "thumbnail": data.get("thumbnail") or "",
                        "uploader": data.get("author") or "Unknown",
                    }
        except Exception as e:
            log.debug(f"Cobalt {cobalt_url} failed: {e}")

    return None


async def _get_inv_stream(session, base_url, video_id):
    """Get audio stream URL from Invidious (for YouTube/VideoMate IDs)."""
    try:
        async with session.get(
            f"{base_url}/api/v1/videos/{video_id}",
            params={"fields": "adaptiveFormats,formatStreams"},
            timeout=aiohttp.ClientTimeout(total=5),
            ssl=False,
        ) as r:
            if r.status != 200:
                return None
            data = await r.json()

            # Try pure audio formats first (best quality, no video)
            best_audio = None
            best_bitrate = 0
            for fmt in data.get("adaptiveFormats", []):
                mime = fmt.get("mimeType") or ""
                if "audio" in mime and fmt.get("url"):
                    bitrate = int(fmt.get("bitrate") or 0)
                    if bitrate > best_bitrate:
                        best_bitrate = bitrate
                        best_audio = fmt["url"]

            if best_audio:
                return {"url": best_audio}

            # Fallback to combined streams (audio+video, FFmpeg will strip video)
            for fmt in data.get("formatStreams", []):
                if fmt.get("url"):
                    return {"url": fmt["url"]}
    except Exception:
        pass

    return None


async def instant_extract(url):
    """
    Extract a playable audio stream URL from any supported link.

    Priority order:
      1. yt-dlp        — YouTube / VideoMate (most reliable, gives real CDN URL)
      2. Cobalt API    — Spotify, Apple Music, SoundCloud, Deezer, Facebook, etc.
      3. Invidious     — YouTube fallback if yt-dlp is unavailable
    """
    platform = detect_platform(url)

    # ── NON-YOUTUBE PLATFORMS → Cobalt ──────────────────────────────────────
    if platform in ("spotify", "apple_music", "soundcloud", "deezer",
                    "anghami", "facebook", "twitch", "vimeo", "direct"):
        async with aiohttp.ClientSession() as session:
            result = await _get_cobalt_stream(session, url)
            if result:
                log.info(f"Extracted via Cobalt from {platform}")
                return result
        # Cobalt failed — nothing else can handle these platforms
        return None

    # ── YOUTUBE / VIDEOMATE → yt-dlp first, Invidious fallback ──────────────
    # yt-dlp is the gold standard: handles age-gated, live, signed URLs, etc.
    if YTDLP_BIN:
        result = await _ytdlp_extract(url)
        if result:
            log.info(f"Extracted via yt-dlp: {result.get('title','?')[:50]}")
            return result
        log.warning("yt-dlp extraction failed — trying Invidious fallback")

    # ── INVIDIOUS FALLBACK (parallel race) ──────────────────────────────────
    video_id = None
    if "youtu.be/" in url:
        video_id = url.split("youtu.be/")[1].split("?")[0]
    elif "v=" in url:
        video_id = url.split("v=")[1].split("&")[0]
    elif "/watch/" in url:
        video_id = url.split("/watch/")[1].split("?")[0]
        video_id = re.sub(r'[^a-zA-Z0-9_-]', '', video_id)

    if video_id and len(video_id) >= 11:
        video_id = video_id[:11]
        async with aiohttp.ClientSession() as session:
            tasks = [_get_inv_stream(session, base, video_id) for base in INVIDIOUS_STREAM]
            for future in asyncio.as_completed(tasks):
                try:
                    result = await future
                    if result:
                        log.info("Extracted stream via Invidious fallback")
                        return result
                except Exception:
                    continue

    log.error(f"All extraction methods failed for: {url[:80]}")
    return None


# ═══════════════════════════════════════
#  AUDIO SOURCE CREATION
# ═══════════════════════════════════════
# Default User-Agent that YouTube CDN / most stream hosts accept
_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

# Headers that FFmpeg must NOT receive — they break chunked / gzip negotiation
_SKIP_HEADERS = frozenset({"transfer-encoding", "content-length", "accept-encoding"})


def _build_ffmpeg_headers(http_headers: dict) -> str:
    """
    Convert a yt-dlp http_headers dict into FFmpeg's -headers string format.

    FFmpeg expects:   "Key1: Val1\\r\\nKey2: Val2\\r\\n"
    (literal backslash-r-backslash-n as the CRLF separator — NOT actual \\r\\n bytes)

    Returns an empty string when there are no usable headers.
    """
    merged = {}

    # Ensure we always have a User-Agent
    has_ua = any(k.lower() == "user-agent" for k in (http_headers or {}))
    if not has_ua:
        merged["User-Agent"] = _DEFAULT_UA

    for k, v in (http_headers or {}).items():
        if k.lower() not in _SKIP_HEADERS:
            merged[k] = v

    if not merged:
        return ""

    parts = [f"{k}: {v}" for k, v in merged.items()]
    # Join with literal \r\n that FFmpeg interprets as CRLF header separators
    return "\\r\\n".join(parts) + "\\r\\n"


def create_ffmpeg_source(stream_url, volume, filter_name, http_headers: dict = None):
    """
    Create a discord audio source from a direct stream URL.

    http_headers: dict of headers yt-dlp says are required for this stream.
                  Passed in full to FFmpeg via -headers so CDN 403s are avoided.
                  Falls back to a default User-Agent when None / empty.
    """
    if not stream_url:
        return None

    af = FILTERS.get(filter_name, FILTERS["none"])["af"]

    # ── Build full header block for FFmpeg ───────────────────────────────────
    headers_str = _build_ffmpeg_headers(http_headers)

    # ── Build before_options ─────────────────────────────────────────────────
    # -reconnect* flags make FFmpeg retry when the YouTube CDN drops mid-stream.
    # -headers passes the full yt-dlp header set so CDN servers don't 403.
    before_opts = (
        "-reconnect 1 "
        "-reconnect_streamed 1 "
        "-reconnect_delay_max 5 "
        "-reconnect_on_network_error 1"
    )
    if headers_str:
        # shlex.split (used by discord.py) handles quoted strings correctly
        before_opts += f' -headers "{headers_str}"'

    # ── Audio-only output, optional DSP filter chain ─────────────────────────
    options = "-vn"          # strip video track (important for combined streams)
    if af:
        options += f" -af {af}"

    try:
        pcm = discord.FFmpegPCMAudio(
            stream_url,
            before_options=before_opts,
            options=options,
        )
        return discord.PCMVolumeTransformer(pcm, volume=volume)
    except Exception as e:
        log.error(f"FFmpeg source creation error: {e}")
        return None


# ═══════════════════════════════════════
#  SONG & PLAYER
# ═══════════════════════════════════════
class Song:
    __slots__ = (
        "title", "url", "stream_url", "duration", "thumbnail",
        "uploader", "requester", "platform", "is_kurdish", "http_headers",
    )

    def __init__(self, data, requester, platform="unknown"):
        self.title      = str(data.get("title") or "Unknown")
        # webpage_url = the original platform/YouTube URL (for display & re-extraction)
        # stream_url  = the direct playable audio URL (set once extraction succeeds)
        self.url        = str(data.get("webpage_url") or "")
        self.stream_url = str(data.get("stream_url") or data.get("url") or "")
        if not self.url:
            self.url = self.stream_url
        self.duration    = data.get("duration") or 0
        self.thumbnail   = str(data.get("thumbnail") or "")
        self.uploader    = str(data.get("uploader") or data.get("channel") or "Unknown")
        self.requester   = requester
        self.platform    = platform
        self.is_kurdish  = is_kurdish(self.title)
        # HTTP headers required by yt-dlp for this stream (e.g. User-Agent, Referer)
        self.http_headers: dict = data.get("http_headers") or {}

    @property
    def dur_str(self):
        if not self.duration or self.duration <= 0:
            return "🔴 LIVE"
        total_secs = int(self.duration)
        mins, secs = divmod(total_secs, 60)
        hours, mins = divmod(mins, 60)
        if hours:
            return f"{hours}:{mins:02d}:{secs:02d}"
        return f"{mins}:{secs:02d}"

    def progress_bar(self, elapsed, length=13):
        if not self.duration or self.duration <= 0:
            return "─" * length + " 🔴"
        pct  = min(max(elapsed / self.duration, 0.0), 1.0)
        fill = int(pct * length)
        return "▬" * fill + "🔘" + "▬" * (length - fill)


class MusicPlayer:
    def __init__(self, guild_id):
        self.guild_id      = guild_id
        self.queue         = []
        self.current       = None
        self.history       = []
        self.loop          = "off"
        self.volume        = 1.0
        self.filter_name   = "none"
        self.skip_votes    = set()
        self.tfs           = False
        self.autoplay      = False
        self.kurdish_mode  = True
        self._start        = None
        self._paused_at    = None
        self._elapsed_pre  = 0.0
        self.np_msg        = None
        self._lock         = asyncio.Lock()
        self._playing      = False

    def elapsed(self):
        if self._start is None:
            return self._elapsed_pre
        if self._paused_at is not None:
            return self._elapsed_pre
        return self._elapsed_pre + (time.time() - self._start)

    def reset_timer(self):
        self._start       = time.time()
        self._paused_at   = None
        self._elapsed_pre = 0.0


_players: dict[int, MusicPlayer] = {}


def get_player(guild_id: int) -> MusicPlayer:
    if guild_id not in _players:
        p = MusicPlayer(guild_id)
        s = get_settings(guild_id)
        # BUG FIX: was missing a closing ) — caused SyntaxError
        p.volume      = max(0.0, min(2.0, (s.get("volume") or 100) / 100.0))
        p.loop        = s.get("loop_mode") or "off"
        p.tfs         = bool(s.get("tfs"))
        p.autoplay    = bool(s.get("autoplay"))
        p.kurdish_mode = bool(s.get("kurdish_mode", 1))
        _players[guild_id] = p
    return _players[guild_id]


def destroy_player(guild_id: int):
    p = _players.pop(guild_id, None)
    if p:
        p.queue.clear()
        p.history.clear()
        p.current = None


# ═══════════════════════════════════════
#  EMBED HELPERS
# ═══════════════════════════════════════
def make_embed(color: int, desc: str = "") -> discord.Embed:
    return discord.Embed(color=color, description=desc)


def ok_embed(desc: str) -> discord.Embed:
    return make_embed(C_GREEN, f"✅ {desc}")


def err_embed(desc: str) -> discord.Embed:
    return make_embed(C_RED, f"❌ {desc}")


def format_time(seconds) -> str:
    if not seconds or seconds < 0:
        return "0:00"
    total = int(seconds)
    mins, secs = divmod(total, 60)
    hours, mins = divmod(mins, 60)
    if hours:
        return f"{hours}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"


# ═══════════════════════════════════════
#  NOW PLAYING
# ═══════════════════════════════════════
def build_np_embed(player: MusicPlayer, vc: discord.VoiceClient) -> discord.Embed:
    song = player.current
    if not song:
        return make_embed(C_LUNA, "Nothing playing")

    elapsed   = player.elapsed()
    is_paused = vc.is_paused() if vc else False

    e = discord.Embed(color=C_LUNA)
    e.set_author(name=f"{'🟢 Kurdish' if song.is_kurdish else '🎵'} Now Playing")
    e.title = song.title
    if song.url.startswith("http"):
        e.url = song.url

    e.description = f"`{format_time(elapsed)}` {song.progress_bar(elapsed)} `{song.dur_str}`"

    loop_modes  = {"off": "➡️ Off", "track": "🔂 Track", "queue": "🔁 Queue"}
    vol_icon    = "🔇" if player.volume <= 0 else ("🔉" if player.volume < 0.5 else "🔊")
    filter_label = FILTERS.get(player.filter_name, FILTERS["none"])["label"]
    plat_emoji  = PLATFORM_EMOJIS.get(song.platform, "🔍")
    plat_label  = PLATFORM_LABELS.get(song.platform, "Unknown")

    e.add_field(name=f"{plat_emoji} Platform", value=plat_label, inline=True)
    e.add_field(name="🎙️ Artist",  value=song.uploader[:50], inline=True)
    e.add_field(name="⏱️ Length",  value=song.dur_str, inline=True)
    e.add_field(name=f"{vol_icon} Vol", value=f"{int(player.volume * 100)}%", inline=True)
    e.add_field(name="🔁 Loop",    value=loop_modes.get(player.loop, "➡️ Off"), inline=True)
    e.add_field(name="🎛️ Filter", value=filter_label, inline=True)
    e.add_field(name="📋 Queue",   value=str(len(player.queue)), inline=True)
    e.add_field(name="👤 By",      value=song.requester.mention, inline=False)

    if song.thumbnail and song.thumbnail.startswith("http"):
        e.set_thumbnail(url=song.thumbnail)

    status = "⏸ Paused" if is_paused else "▶️ Playing"
    e.set_footer(text=f"Veltra Music • {status}")
    return e


class NowPlayingView(discord.ui.View):
    def __init__(self, player: MusicPlayer, vc: discord.VoiceClient):
        super().__init__(timeout=None)
        self.player = player
        self.vc     = vc
        is_paused   = vc.is_paused() if vc else False

        buttons = [
            ("⏮️", "prev",    discord.ButtonStyle.secondary, 0),
            ("▶️" if is_paused else "⏸️", "pause", discord.ButtonStyle.primary, 0),
            ("⏭️", "skip",    discord.ButtonStyle.secondary, 0),
            ("⏹️", "stop",    discord.ButtonStyle.danger,    0),
            (
                "🔂" if player.loop == "track"
                else "🔁" if player.loop == "queue"
                else "➡️",
                "loop", discord.ButtonStyle.secondary, 1,
            ),
            ("🔀", "shuffle", discord.ButtonStyle.secondary, 1),
            ("❤️", "grab",    discord.ButtonStyle.secondary, 1),
            ("📋", "queue",   discord.ButtonStyle.secondary, 1),
        ]

        for emoji, action, style, row in buttons:
            self.add_item(_NPButton(emoji, action, style, row))


class _NPButton(discord.ui.Button):
    def __init__(self, emoji: str, action: str, style: discord.ButtonStyle, row: int):
        custom_id = f"vnp_{action}_{random.randint(0, 9999999)}"
        super().__init__(emoji=emoji, style=style, custom_id=custom_id, row=row)
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=False)
        except Exception:
            return

        if not interaction.guild or not interaction.guild.voice_client:
            return

        vc     = interaction.guild.voice_client
        player = get_player(interaction.guild.id)

        if not player.current:
            return

        try:
            handled = await self._handle(interaction, vc, player)

            if not handled and player.current and vc.is_connected():
                try:
                    if player.np_msg:
                        await player.np_msg.edit(
                            embed=build_np_embed(player, vc),
                            view=NowPlayingView(player, vc),
                        )
                except Exception:
                    pass
        except Exception as e:
            log.error(f"NPButton {self.action} error: {e}")

    async def _handle(
        self,
        interaction: discord.Interaction,
        vc: discord.VoiceClient,
        player: MusicPlayer,
    ) -> bool:
        if self.action == "pause":
            if vc.is_paused():
                player._elapsed_pre = player.elapsed()
                player._start       = time.time()
                player._paused_at   = None
                vc.resume()
            else:
                player._elapsed_pre = player.elapsed()
                player._paused_at   = time.time()
                vc.pause()

        elif self.action == "skip":
            player.skip_votes.clear()
            vc.stop()

        elif self.action == "stop":
            player.queue.clear()
            player.loop = "off"
            vc.stop()
            try:
                await interaction.followup.send(embed=ok_embed("Stopped!"), ephemeral=True)
            except Exception:
                pass
            return True

        elif self.action == "loop":
            modes = ["off", "track", "queue"]
            player.loop = modes[(modes.index(player.loop) + 1) % 3]
            save_settings(interaction.guild.id, loop_mode=player.loop)

        elif self.action == "shuffle":
            if len(player.queue) >= 2:
                random.shuffle(player.queue)
            try:
                await interaction.followup.send(embed=ok_embed("🔀 Shuffled!"), ephemeral=True)
            except Exception:
                pass
            return True

        elif self.action == "grab":
            song = player.current
            e = discord.Embed(
                color=C_LUNA,
                title="❤️ Saved!",
                description=f"**[{song.title}]({song.url})**",
            )
            e.add_field(name="Duration", value=song.dur_str, inline=True)
            if song.is_kurdish:
                e.add_field(name="Type", value="🟢 Kurdish", inline=True)
            if song.thumbnail and song.thumbnail.startswith("http"):
                e.set_thumbnail(url=song.thumbnail)
            try:
                await interaction.user.send(embed=e)
                await interaction.followup.send(embed=ok_embed("Sent to DMs!"), ephemeral=True)
            except discord.Forbidden:
                await interaction.followup.send(embed=err_embed("Can't DM you."), ephemeral=True)
            except Exception:
                pass
            return True

        elif self.action == "queue":
            q = player.queue
            if not q:
                await interaction.followup.send(
                    embed=make_embed(C_LUNA, "📋 Queue is empty."), ephemeral=True
                )
            else:
                lines = []
                for i, s in enumerate(q[:10]):
                    k_flag = " 🟢" if s.is_kurdish else ""
                    lines.append(f"`{i+1}.` [{s.title}]({s.url}) `{s.dur_str}`{k_flag}")
                extra = f"\n*+{len(q)-10} more...*" if len(q) > 10 else ""
                # BUG FIX: discord.Embed has no .set_description() — use description attribute
                em = make_embed(C_LUNA, "\n".join(lines) + extra)
                em.title = f"📋 {len(q)} songs in queue"
                await interaction.followup.send(embed=em, ephemeral=True)
            return True

        elif self.action == "prev":
            if player.history:
                prev_song = player.history.pop()
                if player.current:
                    player.queue.insert(0, player.current)
                player.queue.insert(0, prev_song)
                vc.stop()
            else:
                try:
                    await interaction.followup.send(
                        embed=err_embed("No previous song!"), ephemeral=True
                    )
                except Exception:
                    pass
            return True

        return False


# ═══════════════════════════════════════
#  PLAYBACK ENGINE
# ═══════════════════════════════════════
async def play_next(guild_id: int, text_channel, vc: discord.VoiceClient):
    player = get_player(guild_id)

    if player._lock.locked():
        return

    async with player._lock:
        if not vc or not vc.is_connected():
            return

        song = None

        if player.loop == "track" and player.current:
            song = player.current
        elif player.loop == "queue" and player.current:
            player.queue.append(player.current)
            song = player.queue.pop(0) if player.queue else None
        else:
            song = player.queue.pop(0) if player.queue else None

        if not song:
            if player.current:
                push_history(
                    guild_id,
                    player.current.title,
                    player.current.url,
                    player.current.dur_str,
                    str(player.current.requester),
                    player.current.platform,
                )
            player.current  = None
            player._playing = False

            # Autoplay: find related Kurdish music
            if player.autoplay:
                last_title = (
                    player.history[-1].title
                    if player.history
                    else "kurdish music"
                )
                try:
                    res = await search_songs(
                        f"{last_title} kurdish song",
                        kurdish_mode=True,
                        force_kurdish=True,
                    )
                    if not res:
                        res = await search_songs(
                            "kurdish music 2024",
                            kurdish_mode=True,
                            force_kurdish=True,
                        )
                    if res:
                        player.queue.append(Song(res[0], bot.user, "youtube"))
                        await play_next(guild_id, text_channel, vc)
                        return
                except Exception as e:
                    log.error(f"Autoplay error: {e}")

            # 24/7 idle check — disconnect after 5 minutes if empty & not in 24/7 mode
            if not player.tfs:
                try:
                    await asyncio.sleep(300)
                except asyncio.CancelledError:
                    return

                p2 = get_player(guild_id)
                if not p2.current and not p2.queue and vc.is_connected():
                    non_bots = [m for m in vc.channel.members if not m.bot]
                    if not non_bots:
                        try:
                            vc.stop()
                            await vc.disconnect()
                        except Exception:
                            pass
                        destroy_player(guild_id)
                        if text_channel:
                            try:
                                await text_channel.send(
                                    embed=make_embed(C_LUNA, "👋 Left (idle 5 minutes).")
                                )
                            except Exception:
                                pass
            return

        # Push previous song to history
        if player.current and player.current is not song:
            push_history(
                guild_id,
                player.current.title,
                player.current.url,
                player.current.dur_str,
                str(player.current.requester),
                player.current.platform,
            )
            player.history.append(player.current)
            if len(player.history) > 20:
                player.history.pop(0)

        player.current    = song
        player.skip_votes.clear()

        # ── GET STREAM URL ──
        if not song.stream_url:
            data = await instant_extract(song.url)

            if not data or not data.get("url"):
                if text_channel:
                    try:
                        await text_channel.send(
                            embed=err_embed(f"Skipping **{song.title[:50]}** — stream unavailable.")
                        )
                    except Exception:
                        pass
                player._playing = False
                await play_next(guild_id, text_channel, vc)
                return

            song.stream_url   = data["url"]
            song.http_headers = data.get("http_headers") or {}
            if data.get("title") and data["title"] != "Unknown":
                song.title = data["title"]
            if data.get("duration"):
                song.duration = data["duration"]
            if data.get("thumbnail") and data["thumbnail"].startswith("http"):
                song.thumbnail = data["thumbnail"]
            if data.get("uploader") and data["uploader"] != "Unknown":
                song.uploader = data["uploader"]

        # ── CREATE AUDIO SOURCE ──
        source = create_ffmpeg_source(
            song.stream_url, player.volume, player.filter_name, song.http_headers
        )

        if not source:
            if text_channel:
                try:
                    await text_channel.send(
                        embed=err_embed(f"Skipping **{song.title[:50]}** — audio error.")
                    )
                except Exception:
                    pass
            player._playing = False
            await play_next(guild_id, text_channel, vc)
            return

        # ── START PLAYBACK ──
        player.reset_timer()
        player._playing = True

        def after_callback(error):
            if error:
                log.error(f"Playback error: {error}")
            future = asyncio.run_coroutine_threadsafe(
                play_next(guild_id, text_channel, vc), bot.loop
            )
            future.add_done_callback(
                lambda f: f.exception() if f.exception() else None
            )

        try:
            vc.play(source, after=after_callback)
        except Exception as e:
            log.error(f"vc.play failed: {e}")
            player._playing = False
            return

        # ── NOW PLAYING MESSAGE ──
        if text_channel:
            try:
                np_embed = build_np_embed(player, vc)
                np_view  = NowPlayingView(player, vc)

                # BUG FIX: Message has no .is_deleted() method — use try/except edit
                edited = False
                if player.np_msg:
                    try:
                        await player.np_msg.edit(embed=np_embed, view=np_view)
                        edited = True
                    except Exception:
                        edited = False

                if not edited:
                    player.np_msg = await text_channel.send(embed=np_embed, view=np_view)
            except Exception:
                pass


async def start_playback(ctx: commands.Context):
    vc = ctx.voice_client
    if not vc:
        return
    player = get_player(ctx.guild.id)
    if not player._playing:
        await play_next(ctx.guild.id, ctx.channel, vc)


# ═══════════════════════════════════════
#  VOICE HELPERS
# ═══════════════════════════════════════
async def ensure_voice(ctx: commands.Context):
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send(embed=err_embed("Join a voice channel first!"))
        return None

    target = ctx.author.voice.channel

    if not target.permissions_for(ctx.me).connect:
        await ctx.send(embed=err_embed("I don't have permission to connect!"))
        return None

    if not target.permissions_for(ctx.me).speak:
        await ctx.send(embed=err_embed("I don't have permission to speak!"))
        return None

    vc = ctx.voice_client

    try:
        if not vc:
            vc = await target.connect(timeout=15)
        elif vc.channel != target:
            await vc.move_to(target)
        return vc
    except asyncio.TimeoutError:
        await ctx.send(embed=err_embed("Connection timed out. Try again."))
        return None
    except Exception as e:
        log.error(f"Voice connect error: {e}")
        # BUG FIX: was extra ) causing SyntaxError
        await ctx.send(embed=err_embed("Failed to connect to voice channel."))
        return None


async def check_dj(ctx: commands.Context) -> bool:
    if ctx.author.guild_permissions.manage_guild:
        return True

    settings = get_settings(ctx.guild.id)
    dj_id    = settings.get("dj_role_id")

    if dj_id:
        role = ctx.guild.get_role(int(dj_id))
        if role and role in ctx.author.roles:
            return True
        role_name = role.name if role else str(dj_id)
        await ctx.send(embed=err_embed(f"You need the **{role_name}** DJ role!"))
        return False

    return True


# ═══════════════════════════════════════
#  COMMANDS
# ═══════════════════════════════════════
@bot.command(aliases=["j"])
async def join(ctx: commands.Context):
    vc = await ensure_voice(ctx)
    if vc:
        await ctx.send(embed=ok_embed(f"Joined **{vc.channel.name}**!"))


@bot.command(aliases=["dc", "leave"])
async def disconnect(ctx: commands.Context):
    if not ctx.voice_client:
        return await ctx.send(embed=err_embed("Not in a voice channel!"))

    if not await check_dj(ctx):
        return

    vc = ctx.voice_client
    get_player(ctx.guild.id).queue.clear()

    try:
        vc.stop()
    except Exception:
        pass

    try:
        await vc.disconnect()
    except Exception:
        pass

    destroy_player(ctx.guild.id)
    await ctx.send(embed=ok_embed("Disconnected! 👋"))


@bot.command(aliases=["p"])
async def play(ctx: commands.Context, *, query: str):
    if not query or not query.strip():
        return await ctx.send(embed=err_embed("Provide a song name or URL!"))

    vc = await ensure_voice(ctx)
    if not vc:
        return

    player     = get_player(ctx.guild.id)
    platform   = detect_platform(query)
    plat_emoji = PLATFORM_EMOJIS.get(platform, "🔍")

    msg = await ctx.send(
        embed=make_embed(C_LUNA, f"{plat_emoji} Searching **{query[:80]}**...")
    )

    is_url = query.strip().startswith(("http://", "https://"))

    try:
        if is_url:
            data = await instant_extract(query)

            if not data or not data.get("url"):
                return await msg.edit(
                    embed=err_embed("Couldn't extract audio. Check the link and try again.")
                )

            # Preserve the original user-provided URL as the shareable webpage_url.
            # instant_extract() returns {"url": <stream>} — without "webpage_url" —
            # so we inject it here to avoid Song treating the stream URL as the page URL.
            if not data.get("webpage_url"):
                data = dict(data)
                data["webpage_url"] = query
            # Move raw "url" to "stream_url" so Song.__init__ stores it correctly.
            if not data.get("stream_url") and data.get("url"):
                data = dict(data)
                data["stream_url"] = data["url"]

            song = Song(data, ctx.author, platform)
            player.queue.append(song)

        else:
            results = await search_songs(query, kurdish_mode=player.kurdish_mode)

            if not results:
                return await msg.edit(embed=err_embed("No results found! Try different words."))

            song = Song(results[0], ctx.author, "youtube")
            player.queue.append(song)

        if vc.is_playing() or vc.is_paused():
            em = make_embed(C_LUNA)
            em.title       = f"{plat_emoji} Added to Queue"
            em.description = f"**[{song.title}]({song.url})**"
            em.add_field(name="Duration", value=song.dur_str, inline=True)
            em.add_field(name="Position", value=f"#{len(player.queue)}", inline=True)
            if song.is_kurdish:
                em.add_field(name="Type", value="🟢 Kurdish", inline=True)
            if song.thumbnail and song.thumbnail.startswith("http"):
                em.set_thumbnail(url=song.thumbnail)
            await msg.edit(embed=em)
        else:
            try:
                await msg.delete()
            except Exception:
                pass

    except Exception as e:
        log.error(f"Play error: {e}\n{traceback.format_exc()}")
        try:
            await msg.edit(embed=err_embed(f"Error: {str(e)[:150]}"))
        except Exception:
            pass
        return

    await start_playback(ctx)


@bot.command(aliases=["kurdish", "ku"])
async def kurdishplay(ctx: commands.Context, *, query: str):
    if not query or not query.strip():
        return await ctx.send(embed=err_embed("Provide a song name!"))

    vc = await ensure_voice(ctx)
    if not vc:
        return

    msg = await ctx.send(embed=make_embed(C_LUNA, f"🟢 Finding Kurdish: **{query[:80]}**..."))

    try:
        results = await search_songs(query, kurdish_mode=True, force_kurdish=True)

        if not results:
            return await msg.edit(embed=err_embed("No Kurdish version found. Try different words."))

        song = Song(results[0], ctx.author, "youtube")
        get_player(ctx.guild.id).queue.append(song)

        em = make_embed(C_LUNA)
        em.title       = "🟢 Kurdish Song Found!"
        em.description = f"**[{song.title}]({song.url})**"
        em.add_field(name="Duration", value=song.dur_str, inline=True)
        em.add_field(name="Channel",  value=song.uploader[:50], inline=True)
        if song.thumbnail and song.thumbnail.startswith("http"):
            em.set_thumbnail(url=song.thumbnail)
        await msg.edit(embed=em)

    except Exception as e:
        log.error(f"kurdishplay error: {e}")
        return await msg.edit(embed=err_embed(str(e)[:150]))

    await start_playback(ctx)


@bot.command(aliases=["pa"])
async def pause(ctx: commands.Context):
    vc = ctx.voice_client
    if not vc or not vc.is_playing():
        return await ctx.send(embed=err_embed("Nothing is playing!"))

    if not await check_dj(ctx):
        return

    player = get_player(ctx.guild.id)
    player._elapsed_pre = player.elapsed()
    player._paused_at   = time.time()
    vc.pause()
    await ctx.send(embed=ok_embed("Paused ⏸️"))


@bot.command(aliases=["res"])
async def resume(ctx: commands.Context):
    vc = ctx.voice_client
    if not vc or not vc.is_paused():
        return await ctx.send(embed=err_embed("Nothing is paused!"))

    if not await check_dj(ctx):
        return

    player = get_player(ctx.guild.id)
    player._elapsed_pre = player.elapsed()
    player._start       = time.time()
    player._paused_at   = None
    vc.resume()
    await ctx.send(embed=ok_embed("Resumed ▶️"))


@bot.command(aliases=["s"])
async def skip(ctx: commands.Context):
    vc = ctx.voice_client
    if not vc or (not vc.is_playing() and not vc.is_paused()):
        return await ctx.send(embed=err_embed("Nothing is playing!"))

    player    = get_player(ctx.guild.id)
    is_dj     = ctx.author.guild_permissions.manage_guild

    # BUG FIX: was calling get_player() instead of get_settings() — MusicPlayer has no .get()
    settings  = get_settings(ctx.guild.id)
    dj_id     = settings.get("dj_role_id")
    has_dj    = False

    if dj_id:
        dj_role = ctx.guild.get_role(int(dj_id))
        if dj_role and dj_role in ctx.author.roles:
            has_dj = True

    if is_dj or has_dj:
        player.skip_votes.clear()
        vc.stop()
        return await ctx.send(embed=ok_embed("⏭️ Skipped!"))

    members = [m for m in vc.channel.members if not m.bot]

    if not members:
        player.skip_votes.clear()
        vc.stop()
        return await ctx.send(embed=ok_embed("⏭️ Skipped!"))

    needed = max(1, math.ceil(len(members) * 0.5))
    player.skip_votes.add(ctx.author.id)
    votes = len(player.skip_votes)

    if votes >= needed:
        # BUG FIX: was always sending "need X more" even when threshold reached
        player.skip_votes.clear()
        vc.stop()
        await ctx.send(embed=ok_embed(f"🗳️ Vote skip passed ({votes}/{needed}) — Skipped!"))
    else:
        await ctx.send(
            embed=make_embed(
                C_YELLOW,
                f"🗳️ Skip vote: **{votes}/{needed}** — need {needed - votes} more.",
            )
        )


@bot.command(aliases=["vs"])
async def voteskip(ctx: commands.Context):
    await ctx.invoke(skip)


@bot.command()
async def stop(ctx: commands.Context):
    if not await check_dj(ctx):
        return

    vc = ctx.voice_client
    if not vc:
        return await ctx.send(embed=err_embed("Not in a voice channel!"))

    player = get_player(ctx.guild.id)
    player.queue.clear()
    player.loop = "off"
    vc.stop()
    await ctx.send(embed=ok_embed("⏹️ Stopped and queue cleared!"))


@bot.command(aliases=["np"])
async def nowplaying(ctx: commands.Context):
    vc = ctx.voice_client
    if not vc:
        return await ctx.send(embed=err_embed("Not in a voice channel!"))

    player = get_player(ctx.guild.id)
    if not player.current:
        return await ctx.send(embed=err_embed("Nothing is playing!"))

    try:
        player.np_msg = await ctx.send(
            embed=build_np_embed(player, vc), view=NowPlayingView(player, vc)
        )
    except Exception:
        pass


@bot.command(aliases=["replay", "restart"])
async def again(ctx: commands.Context):
    vc = ctx.voice_client
    if not vc or (not vc.is_playing() and not vc.is_paused()):
        return await ctx.send(embed=err_embed("Nothing is playing!"))

    if not await check_dj(ctx):
        return

    player = get_player(ctx.guild.id)
    if not player.current:
        return await ctx.send(embed=err_embed("Nothing is playing!"))

    player.queue.insert(0, player.current)
    vc.stop()
    await ctx.send(embed=ok_embed("🔁 Replaying current song!"))


@bot.command(aliases=["q"])
async def queue(ctx: commands.Context, page: int = 1):
    player = get_player(ctx.guild.id)

    if not player.current and not player.queue:
        return await ctx.send(embed=make_embed(C_LUNA, "📋 Queue is empty. Use `$play`!"))

    per_page = 10
    total    = len(player.queue)
    pages    = max(1, math.ceil(total / per_page))
    page     = max(1, min(page, pages))
    start    = (page - 1) * per_page
    chunk    = player.queue[start : start + per_page]

    desc = ""
    if player.current:
        k_flag = " 🟢" if player.current.is_kurdish else ""
        desc += (
            f"**▶️ Now:** [{player.current.title}]({player.current.url}) "
            f"`{player.current.dur_str}` — {player.current.requester.mention}{k_flag}\n\n"
        )

    if chunk:
        desc += "**📋 Up Next:**\n"
        for i, s in enumerate(chunk, start=start + 1):
            k_flag = " 🟢" if s.is_kurdish else ""
            desc += (
                f"`{i}.` [{s.title}]({s.url}) `{s.dur_str}` "
                f"— {s.requester.mention}{k_flag}\n"
            )

    total_dur  = sum(s.duration or 0 for s in player.queue)
    loop_modes = {"off": "➡️ Off", "track": "🔂 Track", "queue": "🔁 Queue"}

    em = make_embed(C_LUNA, desc)
    em.title = f"📋 Queue — {total} song(s)"
    em.set_footer(
        text=(
            f"Page {page}/{pages} • {format_time(total_dur)} total • "
            f"Loop: {loop_modes.get(player.loop, '➡️ Off')} • 🟢 = Kurdish"
        )
    )
    await ctx.send(embed=em)


@bot.command(aliases=["rm"])
async def remove(ctx: commands.Context, index: int):
    if not await check_dj(ctx):
        return

    player = get_player(ctx.guild.id)
    if index < 1 or index > len(player.queue):
        return await ctx.send(
            embed=err_embed(f"Invalid index! Queue has {len(player.queue)} songs.")
        )

    removed = player.queue.pop(index - 1)
    await ctx.send(embed=ok_embed(f"Removed **{removed.title[:50]}**"))


@bot.command()
async def clear(ctx: commands.Context):
    if not await check_dj(ctx):
        return

    get_player(ctx.guild.id).queue.clear()
    await ctx.send(embed=ok_embed("Queue cleared!"))


@bot.command(aliases=["sh"])
async def shuffle(ctx: commands.Context):
    if not await check_dj(ctx):
        return

    player = get_player(ctx.guild.id)
    if len(player.queue) < 2:
        return await ctx.send(embed=err_embed("Need at least 2 songs in the queue."))

    random.shuffle(player.queue)
    await ctx.send(embed=ok_embed("🔀 Queue shuffled!"))


@bot.command()
async def skipto(ctx: commands.Context, index: int):
    if not await check_dj(ctx):
        return

    vc = ctx.voice_client
    if not vc:
        return await ctx.send(embed=err_embed("Nothing is playing!"))

    player = get_player(ctx.guild.id)
    if index < 1 or index > len(player.queue):
        return await ctx.send(
            embed=err_embed(f"Invalid index! Queue has {len(player.queue)} songs.")
        )

    player.queue = player.queue[index - 1:]
    vc.stop()
    await ctx.send(embed=ok_embed(f"⏭️ Jumped to position **{index}**!"))


@bot.command(aliases=["vol"])
async def volume(ctx: commands.Context, vol: int):
    if not await check_dj(ctx):
        return

    if not 0 <= vol <= 200:
        return await ctx.send(embed=err_embed("Volume must be between 0 and 200."))

    player = get_player(ctx.guild.id)
    player.volume = vol / 100.0
    save_settings(ctx.guild.id, volume=vol)

    vc = ctx.voice_client
    if vc and vc.source:
        try:
            vc.source.volume = player.volume
        except Exception:
            pass

    icon = "🔇" if vol == 0 else ("🔉" if vol < 50 else "🔊")
    await ctx.send(embed=ok_embed(f"{icon} Volume set to **{vol}%**"))


@bot.command()
async def loop(ctx: commands.Context, mode: str = None):
    if not await check_dj(ctx):
        return

    player = get_player(ctx.guild.id)
    modes  = ["off", "track", "queue"]

    if mode is None:
        mode = modes[(modes.index(player.loop) + 1) % 3]
    else:
        mode = mode.lower()

    if mode not in modes:
        return await ctx.send(embed=err_embed("Mode must be: `off` / `track` / `queue`"))

    player.loop = mode
    save_settings(ctx.guild.id, loop_mode=mode)
    icons = {"off": "➡️", "track": "🔂", "queue": "🔁"}
    await ctx.send(embed=ok_embed(f"{icons[mode]} Loop set to **{mode.title()}**"))


@bot.command(aliases=["filter"])
async def setfilter(ctx: commands.Context, name: str = None):
    if not await check_dj(ctx):
        return

    if name is None:
        lines = [f"`{k}` — {v['label']}" for k, v in FILTERS.items()]
        em = make_embed(C_LUNA, "\n".join(lines))
        em.title = "🎛️ Audio Filters"
        em.set_footer(text="Usage: $filter <name>  |  $filter none to reset")
        return await ctx.send(embed=em)

    name = name.lower()

    if name not in FILTERS:
        valid = ", ".join(f"`{k}`" for k in FILTERS)
        return await ctx.send(embed=err_embed(f"Unknown filter! Valid: {valid}"))

    player     = get_player(ctx.guild.id)
    old_filter = player.filter_name
    player.filter_name = name
    vc = ctx.voice_client

    if vc and (vc.is_playing() or vc.is_paused()) and player.current:
        was_paused = vc.is_paused()
        paused_pos = player.elapsed()

        try:
            vc.stop()
        except Exception:
            pass

        await asyncio.sleep(0.6)

        data = await instant_extract(player.current.url)

        if data and data.get("url"):
            player.current.stream_url   = data["url"]
            player.current.http_headers = data.get("http_headers") or {}
            source = create_ffmpeg_source(
                player.current.stream_url, player.volume, name, player.current.http_headers
            )

            if source:
                player.reset_timer()
                player._playing = True

                def after_cb(err):
                    if err:
                        log.error(f"Filter after: {err}")
                    fut = asyncio.run_coroutine_threadsafe(
                        play_next(ctx.guild.id, ctx.channel, vc), bot.loop
                    )
                    fut.add_done_callback(
                        lambda f: f.exception() if f.exception() else None
                    )

                try:
                    vc.play(source, after=after_cb)
                    if was_paused:
                        vc.pause()
                        player._elapsed_pre = paused_pos
                        player._paused_at   = time.time()
                except Exception as e:
                    player.filter_name = old_filter
                    await ctx.send(embed=err_embed(f"Failed to apply filter: {e}"))
                    return
            else:
                player.filter_name = old_filter
                await ctx.send(embed=err_embed("Failed to create audio source."))
                return
        else:
            player.filter_name = old_filter
            await ctx.send(embed=err_embed("Stream extraction failed."))
            return

    await ctx.send(embed=ok_embed(f"🎛️ Filter set to **{FILTERS[name]['label']}**"))


@bot.command(aliases=["filters"])
async def listfilters(ctx: commands.Context):
    lines = [f"`{k}` — {v['label']}" for k, v in FILTERS.items()]
    em = make_embed(C_LUNA, "\n".join(lines))
    em.title = "🎛️ Available Filters"
    em.set_footer(text="$filter <name> to apply  |  $filter none to reset")
    await ctx.send(embed=em)


@bot.command(name="247")
async def tfs_cmd(ctx: commands.Context):
    if not await check_dj(ctx):
        return

    player     = get_player(ctx.guild.id)
    player.tfs = not player.tfs
    save_settings(ctx.guild.id, tfs=int(player.tfs))
    state = "enabled 🟢" if player.tfs else "disabled 🔴"
    await ctx.send(embed=ok_embed(f"24/7 mode {state}"))


@bot.command()
async def autoplay(ctx: commands.Context):
    if not await check_dj(ctx):
        return

    player          = get_player(ctx.guild.id)
    player.autoplay = not player.autoplay
    save_settings(ctx.guild.id, autoplay=int(player.autoplay))
    state = "enabled 🟢" if player.autoplay else "disabled 🔴"
    await ctx.send(embed=ok_embed(f"Autoplay {state}"))


@bot.command()
async def kurdishmode(ctx: commands.Context):
    player             = get_player(ctx.guild.id)
    player.kurdish_mode = not player.kurdish_mode
    save_settings(ctx.guild.id, kurdish_mode=int(player.kurdish_mode))
    state = "enabled 🟢" if player.kurdish_mode else "disabled 🔴"
    desc  = (
        "Will find Kurdish versions of songs"
        if player.kurdish_mode
        else "Normal search mode"
    )
    await ctx.send(embed=ok_embed(f"Kurdish mode {state} — {desc}"))


@bot.command(aliases=["setdj"])
@commands.has_permissions(manage_guild=True)
async def djrole(ctx: commands.Context, role: discord.Role = None):
    if not role:
        save_settings(ctx.guild.id, dj_role_id=None)
        return await ctx.send(embed=ok_embed("DJ role removed."))

    save_settings(ctx.guild.id, dj_role_id=role.id)
    await ctx.send(embed=ok_embed(f"DJ role set to {role.mention}"))


@bot.command(aliases=["ly"])
async def lyrics(ctx: commands.Context, *, song_name: str = None):
    player = get_player(ctx.guild.id)

    if not song_name or not song_name.strip():
        if not player.current:
            return await ctx.send(
                embed=err_embed("Nothing playing! Use: `$lyrics Artist - Song Title`")
            )
        song_name = player.current.title

    clean = song_name
    for pat in [
        "(official", "(lyrics", "(audio)", "(video)", "(hd)", "(4k)", "[", "]",
        "ft.", "feat.", "official video", "music video",
    ]:
        idx = clean.lower().find(pat)
        if idx != -1:
            clean = clean[:idx].strip()

    parts = clean.split(" - ", 1)

    if len(parts) == 2:
        artist, title_q = parts[0].strip(), parts[1].strip()
    else:
        artist, title_q = "", clean.strip()

    if not artist or not title_q:
        return await ctx.send(
            # BUG FIX: was missing closing backtick
            embed=err_embed("Use: `$lyrics Artist - Song Title`")
        )

    msg = await ctx.send(embed=make_embed(C_LUNA, f"🔍 Fetching lyrics for **{clean[:60]}**..."))

    lyrics_text = None

    for a, t in [(artist, title_q), (artist, clean), (clean, clean)]:
        if not a or not t:
            continue
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"https://api.lyrics.ovh/v1/{a}/{t}",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as r:
                    if r.status == 200:
                        d = await r.json()
                        if d.get("lyrics"):
                            lyrics_text = d["lyrics"]
                            break
        except Exception:
            continue

    if not lyrics_text:
        return await msg.edit(embed=err_embed(f"No lyrics found for **{clean[:60]}**."))

    lyrics_text = lyrics_text.replace("\r\n", "\n").strip()
    chunks      = [lyrics_text[i : i + 3800] for i in range(0, len(lyrics_text), 3800)]

    for i, c in enumerate(chunks):
        em = make_embed(C_LUNA, c)
        em.title = f"📜 {clean[:60]}" + (f" ({i+1}/{len(chunks)})" if len(chunks) > 1 else "")
        if i == 0:
            await msg.edit(embed=em)
        else:
            try:
                await ctx.send(embed=em)
            except Exception:
                pass


@bot.command()
async def history(ctx: commands.Context):
    try:
        conn = _db()
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT title, url, duration, platform FROM history "
            "WHERE guild_id=? ORDER BY id DESC LIMIT 10",
            (ctx.guild.id,),
        ).fetchall()
        conn.close()
    except Exception:
        return await ctx.send(embed=err_embed("Database error."))

    if not rows:
        return await ctx.send(embed=make_embed(C_LUNA, "📜 No history yet."))

    lines = []
    for i, r in enumerate(rows):
        plat   = r["title"] or "unknown"
        plat_k = r["platform"] or "unknown"
        k_flag = " 🟢" if is_kurdish(r["title"]) else ""
        # BUG FIX: f-string with same quotes as outer — use a variable for the emoji
        p_emoji = PLATFORM_EMOJIS.get(plat_k, "🎵")
        lines.append(
            f"`{i+1}.` {p_emoji} [{r['title']}]({r['url']}) `{r['duration']}`{k_flag}"
        )

    em = make_embed(C_LUNA, "\n".join(lines))
    em.title = "📜 Recent History"
    await ctx.send(embed=em)


@bot.command()
async def grab(ctx: commands.Context):
    player = get_player(ctx.guild.id)

    if not player.current:
        return await ctx.send(embed=err_embed("Nothing is playing!"))

    song = player.current
    em   = discord.Embed(
        color=C_LUNA,
        title="❤️ Saved!",
        description=f"**[{song.title}]({song.url})**",
    )
    em.add_field(name="Duration", value=song.dur_str, inline=True)
    if song.is_kurdish:
        em.add_field(name="Type", value="🟢 Kurdish", inline=True)
    if song.thumbnail and song.thumbnail.startswith("http"):
        em.set_thumbnail(url=song.thumbnail)

    try:
        await ctx.author.send(embed=em)
        await ctx.send(embed=ok_embed("Saved to your DMs!"))
    except discord.Forbidden:
        await ctx.send(embed=err_embed("Can't DM you — enable DMs from server members."))
    except Exception:
        pass


@bot.command()
async def ping(ctx: commands.Context):
    await ctx.send(embed=make_embed(C_LUNA, f"🏓 Pong! **{round(bot.latency * 1000)}ms**"))


@bot.command(aliases=["stats"])
async def botinfo(ctx: commands.Context):
    uptime         = int(time.time() - bot_start_time)
    hours, rem     = divmod(uptime, 3600)
    mins, secs     = divmod(rem, 60)
    active_players = sum(1 for p in _players.values() if p._playing)

    em = make_embed(C_LUNA)
    em.title = "🎵 Veltra Music Bot"
    em.add_field(name="Prefix",   value="`$`", inline=True)
    em.add_field(name="Servers",  value=str(len(bot.guilds)), inline=True)
    em.add_field(name="Playing",  value=str(active_players), inline=True)
    em.add_field(name="Uptime",   value=f"{hours}h {mins}m {secs}s", inline=True)
    em.add_field(name="Search",   value="VideoMate + YouTube + Invidious", inline=True)
    em.add_field(name="Kurdish",  value="🟢 Enhanced Search", inline=True)
    # BUG FIX: trailing comma made this a tuple — removed it
    em.add_field(
        name="Platforms",
        value="Spotify · Apple Music · SoundCloud · Deezer · Anghami · Facebook · Twitch · Vimeo · YouTube · MP3/MP4",
        inline=False,
    )
    await ctx.send(embed=em)


@bot.command()
async def help(ctx: commands.Context):
    em = make_embed(C_LUNA)
    em.title       = "🎵 Veltra Music Bot — Multi-Platform"
    em.description = (
        "**Just paste a link or type a song name!**\n"
        "🟢 = Kurdish song indicator\n\n"
    )

    em.add_field(
        name="🎵 Direct URL Playback",
        value=(
            "```\n"
            "Spotify      open.spotify.com/track/...\n"
            "Apple Music  music.apple.com/...\n"
            "SoundCloud   soundcloud.com/...\n"
            "Deezer       deezer.com/...\n"
            "Anghami      anghami.com/...\n"
            "Facebook     facebook.com/watch/...\n"
            "Twitch       twitch.tv/...\n"
            "Vimeo        vimeo.com/...\n"
            "YouTube      youtube.com/watch?v=...\n"
            "Direct       example.com/song.mp3\n"
            "```"
        ),
        inline=False,
    )

    em.add_field(
        name="🔍 Search Commands",
        value=(
            "```\n"
            "$play song name        Search & play\n"
            "$kurdish song name     Find Kurdish version 🟢\n"
            "$pause / $resume       Pause / Resume\n"
            "$skip / $s             Skip current\n"
            "$stop                  Stop & clear queue\n"
            "$np                    Now playing\n"
            "$queue / $q            Show queue\n"
            "```"
        ),
        inline=False,
    )

    em.add_field(
        name="⚙️ Settings",
        value=(
            "```\n"
            "$volume <0-200>          Set volume\n"
            "$loop [off/track/queue]  Loop mode\n"
            "$filter <name>           Audio filter\n"
            "$247                     Stay in VC\n"
            "$autoplay                Auto-play Kurdish\n"
            "$kurdishmode             Toggle Kurdish search\n"
            "$djrole [@role]          Set DJ role\n"
            "```"
        ),
        inline=False,
    )

    em.add_field(
        name="📚 More Commands",
        value=(
            "```\n"
            "$lyrics [Artist - Title]  Fetch lyrics\n"
            "$history                  Recent played\n"
            "$grab                     Save to DMs\n"
            "$shuffle / $sh            Shuffle queue\n"
            "$remove <#> / $rm         Remove from queue\n"
            "$skipto <#>               Jump to position\n"
            "$again / $replay          Replay current\n"
            "$ping / $botinfo          Bot stats\n"
            "```"
        ),
        inline=False,
    )

    em.set_footer(text="Paste any link and it plays! | $help for this menu")
    await ctx.send(embed=em)


# ═════════════════════════════════════
#  EVENTS
# ═════════════════════════════════════
@bot.event
async def on_ready():
    log.info(f"Logged in: {bot.user} ({bot.user.id}) | Guilds: {len(bot.guilds)}")
    log.info("★ VIDEOMATE + YOUTUBE + INVIDIOUS ACTIVE ★")
    try:
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name="🎵 Multi-Platform | $help",
            )
        )
    except Exception:
        pass


@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return

    if before.channel and not after.channel:
        vc = before.channel.guild.voice_client

        if vc and vc.channel == before.channel:
            non_bots = [m for m in vc.channel.members if not m.bot]

            if not non_bots:
                player = get_player(vc.guild.id)

                if not player.tfs:
                    await asyncio.sleep(3)
                    non_bots = [m for m in vc.channel.members if not m.bot]

                    if not non_bots and vc.is_connected():
                        player.queue.clear()
                        try:
                            vc.stop()
                        except Exception:
                            pass
                        try:
                            await vc.disconnect()
                        except Exception:
                            pass
                        destroy_player(vc.guild.id)


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CommandNotFound):
        return

    if isinstance(error, commands.MissingPermissions):
        try:
            await ctx.send(embed=err_embed("You don't have permission to do that!"))
        except Exception:
            pass
        return

    if isinstance(error, commands.MissingRequiredArgument):
        try:
            await ctx.send(embed=err_embed(f"Missing argument: `{error.param.name}`"))
        except Exception:
            pass
        return

    if isinstance(error, commands.BadArgument):
        try:
            await ctx.send(embed=err_embed(f"Invalid argument: {error}"))
        except Exception:
            pass
        return

    log.error(f"Command [{ctx.command}] ERROR:\n{traceback.format_exc()}")

    try:
        await ctx.send(embed=err_embed(str(error)[:150]))
    except Exception:
        pass


# ═══════════════════════════════════════
#  RUN BOT
# ═══════════════════════════════════════
if __name__ == "__main__":
    log.info("Starting Veltra Music Bot (VideoMate + YouTube + Invidious)...")
    try:
        bot.run(TOKEN, log_handler=None)
    except discord.LoginFailure:
        log.error("FATAL: Invalid Discord token!")
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log.error(f"FATAL: {e}\n{traceback.format_exc()}")
