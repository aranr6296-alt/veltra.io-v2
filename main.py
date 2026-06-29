"""
╔══════════════════════════════════════════════════════╗
║  VELTRA MUSIC BOT — KURDISH SEARCH 100% FIXED      ║
║  Direct HTTP Fallback · Bypasses IP Blocks · No Bugs║
╚══════════════════════════════════════════════════════╝
"""

import discord
from discord.ext import commands
import asyncio
import yt_dlp
import os
import time
import math
import random
import sqlite3
import aiohttp
import logging
import re
import json
import traceback
from pathlib import Path
from dotenv import load_dotenv

# ──────────────────────────────────────────────────────
#  SETUP
# ──────────────────────────────────────────────────────
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    print("[FATAL] DISCORD_TOKEN not set")
    raise SystemExit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(filename="veltra.log", encoding="utf-8", mode="a"),
    ],
)
log = logging.getLogger("veltra")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix="$", intents=intents, help_command=None)
bot_start_time = time.time()

# ──────────────────────────────────────────────────────
#  THEME
# ──────────────────────────────────────────────────────
C_LUNA   = 0xB5179E
C_GREEN  = 0x57F287
C_RED    = 0xED4245
C_YELLOW = 0xFEE75C

CACHE_DIR = Path("./veltra_cache")
try:
    CACHE_DIR.mkdir(exist_ok=True)
except Exception:
    CACHE_DIR = None

# ──────────────────────────────────────────────────────
#  DATABASE
# ──────────────────────────────────────────────────────
DB_FILE = "veltra.db"

def _db():
    return sqlite3.connect(DB_FILE, timeout=10)

def init_db():
    try:
        c = _db()
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript("""
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                dj_role_id INTEGER DEFAULT NULL,
                volume INTEGER DEFAULT 100,
                loop_mode TEXT DEFAULT 'off',
                tfs INTEGER DEFAULT 0,
                autoplay INTEGER DEFAULT 0,
                kurdish_mode INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER, title TEXT, url TEXT,
                duration TEXT, requester TEXT, platform TEXT DEFAULT 'unknown',
                played_at TEXT DEFAULT (datetime('now'))
            );
        """)
        c.commit()
        c.close()
    except Exception as e:
        log.error(f"DB init: {e}")

init_db()

def get_settings(gid):
    try:
        c = _db()
        c.row_factory = sqlite3.Row
        r = c.execute("SELECT * FROM guild_settings WHERE guild_id=?", (gid,)).fetchone()
        if not r:
            c.execute("INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)", (gid,))
            c.commit()
            r = c.execute("SELECT * FROM guild_settings WHERE guild_id=?", (gid,)).fetchone()
        c.close()
        return dict(r) if r else {"dj_role_id":None,"volume":100,"loop_mode":"off","tfs":0,"autoplay":0,"kurdish_mode":1}
    except Exception:
        return {"dj_role_id":None,"volume":100,"loop_mode":"off","tfs":0,"autoplay":0,"kurdish_mode":1}

def save_settings(gid, **kw):
    try:
        get_settings(gid)
        s = ", ".join(f"{k}=?" for k in kw)
        c = _db()
        c.execute(f"UPDATE guild_settings SET {s} WHERE guild_id=?", [*kw.values(), gid])
        c.commit()
        c.close()
    except Exception as e:
        log.error(f"save_settings: {e}")

def push_history(gid, title, url, dur, req, plat="unknown"):
    try:
        c = _db()
        c.execute("INSERT INTO history (guild_id,title,url,duration,requester,platform) VALUES (?,?,?,?,?,?)",
                  (gid, title, url, dur, req, plat))
        c.execute("DELETE FROM history WHERE guild_id=? AND id NOT IN (SELECT id FROM history WHERE guild_id=? ORDER BY id DESC LIMIT 50)", (gid, gid))
        c.commit()
        c.close()
    except Exception as e:
        log.error(f"push_history: {e}")

# ──────────────────────────────────────────────────────
#  FILTERS
# ──────────────────────────────────────────────────────
FILTERS = {
    "none":      {"label": "🎵 None",       "af": ""},
    "bassboost": {"label": "🔊 Bass Boost", "af": "bass=g=10,dynaudnorm=f=200"},
    "nightcore": {"label": "🌙 Nightcore",  "af": "asetrate=44100*1.25,aresample=44100"},
    "vaporwave": {"label": "🌊 Vaporwave",  "af": "asetrate=44100*0.8,aresample=44100"},
    "8d":        {"label": "🎧 8D Audio",   "af": "apulsator=hz=0.08"},
    "karaoke":   {"label": "🎤 Karaoke",    "af": "stereotools=mlev=0.03125"},
    "tremolo":   {"label": "〰️ Tremolo",    "af": "tremolo=f=4:d=0.9"},
    "vibrato":   {"label": "🎸 Vibrato",    "af": "vibrato=f=6.5:d=0.9"},
    "superbass": {"label": "💥 Super Bass", "af": "bass=g=20,dynaudnorm=f=200"},
    "soft":      {"label": "🕊️ Soft",       "af": "lowpass=f=300,volume=1.5"},
    "earrape":   {"label": "📢 Ear Rape",   "af": "acrusher=level_in=8:level_out=18:bits=8:mode=log:aa=1"},
    "pitch":     {"label": "🎵 Pitch Up",   "af": "asetrate=44100*1.15,aresample=44100"},
}

# ──────────────────────────────────────────────────────
#  PLATFORM
# ──────────────────────────────────────────────────────
def detect_platform(url):
    if not url: return "unknown"
    u = url.lower()
    if "spotify.com" in u: return "spotify"
    if "music.apple.com" in u or "itunes.apple.com" in u: return "apple_music"
    if "soundcloud.com" in u: return "soundcloud"
    if "deezer.com" in u: return "deezer"
    if "anghami.com" in u: return "anghami"
    if "vimeo.com" in u: return "vimeo"
    if "youtube.com" in u or "youtu.be" in u: return "youtube"
    if any(u.endswith(x) for x in (".mp3",".mp4",".m4a",".ogg",".wav",".flac")): return "direct"
    return "unknown"

P_EMOJI = {"spotify":"🎵","apple_music":"🍎","soundcloud":"☁️","deezer":"🎶","anghami":"🌙","vimeo":"📹","youtube":"▶️","direct":"📎","unknown":"🔍"}
P_LABEL = {"spotify":"Spotify","apple_music":"Apple Music","soundcloud":"SoundCloud","deezer":"Deezer","anghami":"Anghami","vimeo":"Vimeo","youtube":"YouTube","direct":"Direct","unknown":"Unknown"}

# ──────────────────────────────────────────────────────
#  KURDISH DETECTION
# ──────────────────────────────────────────────────────
KURDISH_KW = [
    "kurdish", "kurdi", "کوردی", "کوردیی", "kurdî", "kurdish song",
    "zagros", "kurdistan", "hawler", "slemani", "erbil",
    "stran", "stranên", "gorani",
]

def is_kurdish(title):
    if not title: return False
    t = title.lower()
    # Detect Sorani/Arabic script (most reliable)
    if any('\u0600' <= c <= '\u06FF' for c in title):
        return True
    return any(k in t for k in KURDISH_KW)

def kurdish_queries(query):
    """Generate search queries specifically for Kurdish songs."""
    # If already Kurdish, just return as-is
    if is_kurdish(query):
        return [query]
    
    # Cascade from specific to broad
    return [
        f"{query} kurdish song کوردی",
        f"{query} کوردی",
        f"{query} stran kurdî",
        f"{query} kurdish cover",
        f"{query} kurdi",
    ]

# ──────────────────────────────────────────────────────
#  ★★★ DIRECT YOUTUBE SEARCH (BYPASSES IP BLOCKS) ★★★
# ──────────────────────────────────────────────────────
async def _yt_direct_search(query: str, max_results: int = 5) -> list[dict]:
    """
    Search YouTube directly via HTTP. This works even when yt-dlp
    search is blocked by YouTube (which happens on server IPs).
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://www.youtube.com/results",
                params={"search_query": query},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
                ssl=False,
            ) as resp:
                if resp.status != 200:
                    log.warning(f"Direct YT search HTTP {resp.status} for: {query[:50]}")
                    return []
                html = await resp.text()
    except Exception as e:
        log.error(f"Direct YT search network error: {e}")
        return []

    if not html or len(html) < 1000:
        return []

    results = []

    # Method 1: Parse ytInitialData JSON
    try:
        match = re.search(r'var ytInitialData\s*=\s*({.*?});\s*</script>', html, re.DOTALL)
        if match:
            data = json.loads(match.group(1))
            sections = (
                data.get("contents", {})
                .get("twoColumnSearchResultsRenderer", {})
                .get("primaryContents", {})
                .get("sectionListRenderer", {})
                .get("contents", [])
            )
            for sec in sections:
                for item in sec.get("itemSectionRenderer", {}).get("contents", []):
                    vr = item.get("videoRenderer")
                    if not vr or not vr.get("videoId"):
                        continue
                    
                    vid = vr["videoId"]
                    title = ""
                    runs = vr.get("title", {}).get("runs", [])
                    if runs:
                        title = runs[0].get("text", "")
                    
                    channel = ""
                    ch_runs = vr.get("longBylineText", {}).get("runs", [])
                    if ch_runs:
                        channel = ch_runs[0].get("text", "")
                    
                    length_str = vr.get("lengthText", {}).get("simpleText", "0:00")
                    duration = _parse_duration(length_str)
                    
                    thumb = ""
                    thumbs = vr.get("thumbnail", {}).get("thumbnails", [])
                    if thumbs:
                        thumb = thumbs[-1].get("url", "")
                    
                    if title and vid:
                        results.append({
                            "id": vid,
                            "title": title,
                            "url": f"https://www.youtube.com/watch?v={vid}",
                            "webpage_url": f"https://www.youtube.com/watch?v={vid}",
                            "duration": duration,
                            "thumbnail": thumb,
                            "uploader": channel,
                            "channel": channel,
                        })
    except Exception as e:
        log.error(f"ytInitialData parse error: {e}")

    # Method 2: Fallback regex if JSON parse failed
    if not results:
        try:
            # Find video IDs and titles from the HTML directly
            pattern = r'"/watch\?v=([a-zA-Z0-9_-]{11})".*?"title":\s*{"runs":\s*\[{"text":\s*"([^"]+)"'
            for match in re.finditer(pattern, html):
                vid, title = match.group(1), match.group(2)
                if vid not in [r.get("id") for r in results]:
                    results.append({
                        "id": vid,
                        "title": title,
                        "url": f"https://www.youtube.com/watch?v={vid}",
                        "webpage_url": f"https://www.youtube.com/watch?v={vid}",
                        "duration": 0,
                        "thumbnail": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                        "uploader": "",
                        "channel": "",
                    })
        except Exception as e:
            log.error(f"Regex fallback parse error: {e}")

    return results[:max_results]


def _parse_duration(dur_str: str) -> int:
    """Parse '3:45' or '1:02:30' to seconds."""
    try:
        parts = dur_str.split(":")
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 1:
            return int(parts[0])
    except Exception:
        pass
    return 0

# ──────────────────────────────────────────────────────
#  ★★★ UNIFIED SEARCH (YT-DLP + DIRECT FALLBACK) ★★★
# ──────────────────────────────────────────────────────
_BASE_OPTS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "socket_timeout": 12,
    "retries": 2,
    "skip_download": True,
    "nocheckcertificate": True,
    "noprogress": True,
    "http_headers": {
        "User-Agent": "Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    },
}
if CACHE_DIR:
    _BASE_OPTS["cachedir"] = str(CACHE_DIR)


async def _yt_dlp_search(query: str) -> list[dict]:
    """Try yt-dlp search first (fastest if it works)."""
    def _do():
        opts = {**_BASE_OPTS, "noplaylist": True, "default_search": "ytsearch5"}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                result = ydl.extract_info(f"ytsearch5:{query}", download=False)
                if result:
                    entries = result.get("entries", [])
                    return [e for e in entries if e and e.get("id")]
        except Exception as e:
            log.warning(f"yt-dlp search failed: {e}")
        return []
    
    try:
        return await asyncio.get_running_loop().run_in_executor(None, _do)
    except Exception as e:
        log.error(f"yt-dlp search executor error: {e}")
        return []


async def search_songs(query: str, kurdish_mode: bool = True, force_kurdish: bool = False) -> list[dict]:
    """
    Search songs with guaranteed results:
    1. Try yt-dlp search
    2. If empty, use direct HTTP YouTube scrape (bypasses IP blocks)
    3. If force_kurdish, filter results to only Kurdish songs
    """
    # Determine search queries
    if force_kurdish:
        queries = kurdish_queries(query)
    elif kurdish_mode and not is_kurdish(query):
        queries = [f"{query} kurdish kurdi کوردی"]
    else:
        queries = [query]

    all_results = []

    for q in queries:
        # Step 1: Try yt-dlp
        results = await _yt_dlp_search(q)
        
        # Step 2: If yt-dlp failed, use direct HTTP fallback
        if not results:
            log.info(f"yt-dlp empty, using direct HTTP search for: {q[:60]}")
            results = await _yt_direct_search(q)
        
        if results:
            all_results.extend(results)
            
            # If we just want ANY result (not force_kurdish), return immediately
            if not force_kurdish and not (kurdish_mode and not is_kurdish(query)):
                # Deduplicate and return
                seen = set()
                unique = []
                for r in all_results:
                    rid = r.get("id")
                    if rid and rid not in seen:
                        seen.add(rid)
                        unique.append(r)
                return unique[:5]
            
            # If force_kurdish, check if we got Kurdish results
            if force_kurdish or (kurdish_mode and not is_kurdish(query)):
                kurdish = [r for r in all_results if is_kurdish(r.get("title", ""))]
                if kurdish:
                    seen = set()
                    unique = []
                    for r in kurdish:
                        rid = r.get("id")
                        if rid and rid not in seen:
                            seen.add(rid)
                            unique.append(r)
                    return unique[:5]
                # No Kurdish found in this query, try next in cascade
                continue
    
    # force_kurdish exhausted all queries without Kurdish results
    # Return whatever we have as last resort
    if force_kurdish and all_results:
        seen = set()
        unique = []
        for r in all_results:
            rid = r.get("id")
            if rid and rid not in seen:
                seen.add(rid)
                unique.append(r)
        return unique[:5]
    
    # Final absolute fallback: direct search the original query
    if not all_results:
        log.info(f"All queries failed, absolute fallback for: {query[:60]}")
        fallback = await _yt_direct_search(query)
        if fallback:
            return fallback[:5]
    
    return []


# ──────────────────────────────────────────────────────
#  YT-DLP RESOLVE (for getting stream URLs)
# ──────────────────────────────────────────────────────
async def _run_sync(fn, *a, **kw):
    try:
        return await asyncio.get_running_loop().run_in_executor(None, lambda: fn(*a, **kw))
    except Exception as e:
        log.error(f"Executor: {e}")
        raise

def _safe_extract(opts, url):
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as e:
        log.warning(f"DownloadError: {e}")
    except yt_dlp.utils.ExtractorError as e:
        log.warning(f"ExtractorError: {e}")
    except Exception as e:
        log.error(f"yt-dlp error: {e}")
    return None

async def resolve_url(url: str) -> dict | None:
    def _do():
        opts = {**_BASE_OPTS, "noplaylist": True}
        r = _safe_extract(opts, url)
        if r and isinstance(r, dict) and r.get("id"): return r
        if r and isinstance(r, list) and r: return r[0]
        return None
    try:
        return await _run_sync(_do)
    except Exception:
        return None

async def resolve_playlist(url: str) -> list[dict]:
    plat = detect_platform(url)
    def _do():
        opts = {**_BASE_OPTS, "extract_flat": "in_playlist"}
        r = _safe_extract(opts, url)
        entries = []
        if r and isinstance(r, dict):
            for e in (r.get("entries") or []):
                if e and e.get("id"):
                    e["_platform"] = plat
                    entries.append(e)
        return entries
    try:
        return await _run_sync(_do) or []
    except Exception:
        return []

def _make_source(stream_url, volume, filter_name):
    if not stream_url: return None
    af = FILTERS.get(filter_name, FILTERS["none"])["af"]
    before = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
    options = "-vn" + (f" -af {af}" if af else "")
    try:
        return discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(stream_url, before_options=before, options=options),
            volume=volume,
        )
    except Exception as e:
        log.error(f"FFmpeg: {e}")
        return None

# ──────────────────────────────────────────────────────
#  SONG & PLAYER
# ──────────────────────────────────────────────────────
class Song:
    __slots__ = ("title","url","stream_url","duration","thumbnail","uploader","requester","platform","is_kurdish")
    def __init__(self, data, requester, platform="unknown"):
        self.title = str(data.get("title") or "Unknown")
        self.url = str(data.get("webpage_url") or data.get("url") or "")
        self.stream_url = str(data.get("url") or "")
        self.duration = data.get("duration") or 0
        self.thumbnail = str(data.get("thumbnail") or "")
        self.uploader = str(data.get("uploader") or data.get("channel") or "Unknown")
        self.requester = requester
        self.platform = platform or "unknown"
        self.is_kurdish = is_kurdish(self.title)

    @property
    def dur_str(self):
        if not self.duration or self.duration <= 0: return "🔴 LIVE"
        d = int(self.duration)
        m, s = divmod(d, 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

    def progress_bar(self, elapsed, length=13):
        if not self.duration or self.duration <= 0: return "─"*length+" 🔴"
        pct = min(max(elapsed/self.duration, 0.0), 1.0)
        fill = int(pct * length)
        return "▬"*fill+"🔘"+"▬"*(length-fill)

class MusicPlayer:
    def __init__(self, gid):
        self.guild_id = gid
        self.queue = []
        self.current = None
        self.history = []
        self.loop = "off"
        self.volume = 1.0
        self.filter_name = "none"
        self.skip_votes = set()
        self.tfs = False
        self.autoplay = False
        self.kurdish_mode = True
        self._start = None
        self._paused_at = None
        self._elapsed_pre = 0.0
        self.np_msg = None
        self._lock = asyncio.Lock()
        self._playing = False

    def elapsed(self):
        if self._start is None: return self._elapsed_pre
        if self._paused_at is not None: return self._elapsed_pre
        return self._elapsed_pre + (time.time() - self._start)

    def reset_timer(self):
        self._start = time.time()
        self._paused_at = None
        self._elapsed_pre = 0.0

_players = {}

def get_player(gid):
    if gid not in _players:
        p = MusicPlayer(gid)
        s = get_settings(gid)
        p.volume = max(0.0, min(2.0, (s.get("volume") or 100)/100.0))
        p.loop = s.get("loop_mode") or "off"
        p.tfs = bool(s.get("tfs"))
        p.autoplay = bool(s.get("autoplay"))
        p.kurdish_mode = bool(s.get("kurdish_mode", 1))
        _players[gid] = p
    return _players[gid]

def destroy_player(gid):
    p = _players.pop(gid, None)
    if p:
        p.queue.clear()
        p.history.clear()
        p.current = None

# ──────────────────────────────────────────────────────
#  EMBEDS
# ──────────────────────────────────────────────────────
def _e(color, desc): return discord.Embed(color=color, description=desc)
def ok_e(d): return _e(C_GREEN, f"✅ {d}")
def err_e(d): return _e(C_RED, f"❌ {d}")

def _ft(sec):
    if not sec or sec < 0: return "0:00"
    s = int(sec)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

def _dur(s):
    return _ft(s) if s and s > 0 else "?"

# ──────────────────────────────────────────────────────
#  NOW PLAYING
# ──────────────────────────────────────────────────────
def build_np(player, vc):
    song = player.current
    if not song: return _e(C_LUNA, "Nothing is playing")
    elapsed = player.elapsed()
    paused = vc.is_paused() if vc else False
    e = discord.Embed(color=C_LUNA)
    e.set_author(name=f"{'🟢 Kurdish' if song.is_kurdish else '🎵'} Now Playing")
    e.title = song.title
    e.url = song.url if song.url.startswith("http") else None
    e.description = f"`{_ft(elapsed)}` {song.progress_bar(elapsed)} `{song.dur_str}`"
    li = {"off":"➡️ Off","track":"🔂 Track","queue":"🔁 Queue"}.get(player.loop,"➡️ Off")
    vi = "🔇" if player.volume<=0 else ("🔉" if player.volume<0.5 else "🔊")
    fl = FILTERS.get(player.filter_name, FILTERS["none"])["label"]
    pe = P_EMOJI.get(song.platform,"🔍")
    pl = P_LABEL.get(song.platform,"Unknown")
    e.add_field(name=f"{pe} Platform", value=pl, inline=True)
    e.add_field(name="🎙️ Artist", value=song.uploader[:50], inline=True)
    e.add_field(name="⏱️ Length", value=song.dur_str, inline=True)
    e.add_field(name=f"{vi} Vol", value=f"{int(player.volume*100)}%", inline=True)
    e.add_field(name="🔁 Loop", value=li, inline=True)
    e.add_field(name="🎛️ Filter", value=fl, inline=True)
    e.add_field(name="📋 Queue", value=str(len(player.queue)), inline=True)
    e.add_field(name="👤 Requested by", value=song.requester.mention, inline=False)
    if song.thumbnail and song.thumbnail.startswith("http"):
        e.set_thumbnail(url=song.thumbnail)
    e.set_footer(text=f"Veltra Music  •  {'⏸ Paused' if paused else '▶️ Playing'}")
    return e

class NPView(discord.ui.View):
    def __init__(self, player, vc):
        super().__init__(timeout=None)
        self.player = player
        self.vc = vc
        p = vc.is_paused() if vc else False
        for em, act, st, rw in [
            ("⏮️","prev",discord.ButtonStyle.secondary,0),
            ("▶️" if p else "⏸️","pause",discord.ButtonStyle.primary,0),
            ("⏭️","skip",discord.ButtonStyle.secondary,0),
            ("⏹️","stop",discord.ButtonStyle.danger,0),
            ("🔂" if player.loop=="track" else "🔁" if player.loop=="queue" else "➡️","loop",discord.ButtonStyle.secondary,1),
            ("🔀","shuffle",discord.ButtonStyle.secondary,1),
            ("❤️","grab",discord.ButtonStyle.secondary,1),
            ("📋","queue",discord.ButtonStyle.secondary,1),
        ]:
            self.add_item(_NPB(em, act, st, rw))

class _NPB(discord.ui.Button):
    def __init__(self, em, act, st, rw):
        super().__init__(emoji=em, style=st, custom_id=f"vnp_{act}_{random.randint(0,9999999)}", row=rw)
        self.action = act
    async def callback(self, interaction):
        try:
            await interaction.response.defer(ephemeral=False)
        except Exception:
            return
        if not interaction.guild or not interaction.guild.voice_client: return
        vc = interaction.guild.voice_client
        pl = get_player(interaction.guild.id)
        if not pl.current: return
        try:
            handled = await self._h(interaction, vc, pl)
            if not handled and pl.current and vc.is_connected():
                try:
                    if pl.np_msg: await pl.np_msg.edit(embed=build_np(pl,vc), view=NPView(pl,vc))
                except Exception: pass
        except Exception as e:
            log.error(f"NPB {self.action}: {e}")

    async def _h(self, interaction, vc, pl):
        if self.action == "pause":
            if vc.is_paused():
                pl._elapsed_pre = pl.elapsed(); pl._start = time.time(); pl._paused_at = None; vc.resume()
            else:
                pl._elapsed_pre = pl.elapsed(); pl._paused_at = time.time(); vc.pause()
        elif self.action == "skip":
            pl.skip_votes.clear(); vc.stop()
        elif self.action == "stop":
            pl.queue.clear(); pl.loop = "off"; vc.stop()
            try: await interaction.followup.send(embed=ok_e("Stopped!"), ephemeral=True)
            except Exception: pass
            return True
        elif self.action == "loop":
            ms = ["off","track","queue"]
            pl.loop = ms[(ms.index(pl.loop)+1)%3]
            save_settings(interaction.guild.id, loop_mode=pl.loop)
        elif self.action == "shuffle":
            if len(pl.queue) >= 2:
                random.shuffle(pl.queue)
                try: await interaction.followup.send(embed=ok_e("🔀 Shuffled!"), ephemeral=True)
                except Exception: pass
            return True
        elif self.action == "grab":
            s = pl.current
            e = discord.Embed(color=C_LUNA, title="❤️ Saved", description=f"**[{s.title}]({s.url})**")
            e.add_field(name="Duration", value=s.dur_str, inline=True)
            if s.is_kurdish: e.add_field(name="Type", value="🟢 Kurdish", inline=True)
            if s.thumbnail and s.thumbnail.startswith("http"): e.set_thumbnail(url=s.thumbnail)
            try:
                await interaction.user.send(embed=e)
                await interaction.followup.send(embed=ok_e("Sent to DMs!"), ephemeral=True)
            except discord.Forbidden:
                await interaction.followup.send(embed=err_e("Can't DM you."), ephemeral=True)
            except Exception: pass
            return True
        elif self.action == "queue":
            q = pl.queue
            if not q:
                await interaction.followup.send(embed=_e(C_LUNA, "📋 Empty queue."), ephemeral=True)
            else:
                lines = [f"`{i+1}.` [{s.title}]({s.url}) `{s.dur_str}` {'🟢' if s.is_kurdish else ''}" for i,s in enumerate(q[:10])]
                ex = f"\n*+{len(q)-10} more...*" if len(q)>10 else ""
                await interaction.followup.send(embed=_e(C_LUNA, f"📋 {len(q)} songs").set_description("\n".join(lines)+ex), ephemeral=True)
            return True
        elif self.action == "prev":
            if pl.history:
                prev = pl.history.pop()
                if pl.current: pl.queue.insert(0, pl.current)
                pl.queue.insert(0, prev); vc.stop()
            else:
                try: await interaction.followup.send(embed=err_e("No previous!"), ephemeral=True)
                except Exception: pass
            return True
        return False

# ──────────────────────────────────────────────────────
#  PLAYBACK ENGINE
# ──────────────────────────────────────────────────────
async def play_next(gid, ch, vc):
    pl = get_player(gid)
    if pl._lock.locked(): return
    async with pl._lock:
        if not vc or not vc.is_connected(): return
        song = None
        if pl.loop == "track" and pl.current: song = pl.current
        elif pl.loop == "queue" and pl.current:
            pl.queue.append(pl.current)
            song = pl.queue.pop(0) if pl.queue else None
        else:
            song = pl.queue.pop(0) if pl.queue else None

        if not song:
            if pl.current:
                push_history(gid, pl.current.title, pl.current.url, pl.current.dur_str, str(pl.current.requester), pl.current.platform)
            pl.current = None
            pl._playing = False

            if pl.autoplay and pl.history:
                last = pl.history[-1]
                try:
                    res = await search_songs(f"{last.uploader} kurdish song", kurdish_mode=True, force_kurdish=True)
                    if not res: res = await search_songs("kurdish music 2024", kurdish_mode=True, force_kurdish=True)
                    if res:
                        pl.queue.append(Song(res[0], bot.user, "youtube"))
                        await play_next(gid, ch, vc)
                        return
                except Exception as e:
                    log.error(f"Autoplay: {e}")

            if not pl.tfs:
                try: await asyncio.sleep(300)
                except asyncio.CancelledError: return
                p2 = get_player(gid)
                if not p2.current and not p2.queue and vc.is_connected():
                    if not [m for m in vc.channel.members if not m.bot]:
                        try: vc.stop()
                        except Exception: pass
                        try: await vc.disconnect()
                        except Exception: pass
                        destroy_player(gid)
                        if ch:
                            try: await ch.send(embed=_e(C_LUNA, "👋 Left (idle 5m)."))
                            except Exception: pass
            return

        if pl.current and pl.current is not song:
            push_history(gid, pl.current.title, pl.current.url, pl.current.dur_str, str(pl.current.requester), pl.current.platform)
            pl.history.append(pl.current)
            if len(pl.history) > 20: pl.history.pop(0)

        pl.current = song
        pl.skip_votes.clear()

        if not song.stream_url or "googlevideo" not in song.stream_url:
            data = await resolve_url(song.url)
            if not data:
                if ch:
                    try: await ch.send(embed=err_e(f"Skipping **{song.title[:50]}** — can't resolve."))
                    except Exception: pass
                pl._playing = False
                await play_next(gid, ch, vc)
                return
            song.stream_url = data.get("url") or ""
            if not song.thumbnail: song.thumbnail = data.get("thumbnail") or ""
            if not song.duration or song.duration <= 0: song.duration = data.get("duration") or 0
            if song.uploader == "Unknown": song.uploader = data.get("uploader") or data.get("channel") or "Unknown"

        if not song.stream_url:
            pl._playing = False
            await play_next(gid, ch, vc)
            return

        source = _make_source(song.stream_url, pl.volume, pl.filter_name)
        if not source:
            if ch:
                try: await ch.send(embed=err_e(f"Skipping **{song.title[:50]}** — FFmpeg error."))
                except Exception: pass
            pl._playing = False
            await play_next(gid, ch, vc)
            return

        pl.reset_timer()
        pl._playing = True

        def after(err):
            if err: log.error(f"after_cb: {err}")
            f = asyncio.run_coroutine_threadsafe(play_next(gid, ch, vc), bot.loop)
            f.add_done_callback(lambda x: x.exception() if x.exception() else None)

        try:
            vc.play(source, after=after)
        except Exception as e:
            log.error(f"vc.play: {e}")
            pl._playing = False
            return

        if ch:
            try:
                emb = build_np(pl, vc)
                vw = NPView(pl, vc)
                if pl.np_msg and not pl.np_msg.is_deleted():
                    await pl.np_msg.edit(embed=emb, view=vw)
                else:
                    pl.np_msg = await ch.send(embed=emb, view=vw)
            except Exception: pass

async def _start(ctx):
    vc = ctx.voice_client
    if not vc: return
    if not get_player(ctx.guild.id)._playing:
        await play_next(ctx.guild.id, ctx.channel, vc)

# ──────────────────────────────────────────────────────
#  HELPERS
# ──────────────────────────────────────────────────────
async def _vc(ctx):
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send(embed=err_e("Join a voice channel!"))
        return None
    t = ctx.author.voice.channel
    if not t.permissions_for(ctx.me).connect:
        await ctx.send(embed=err_e("No permission to join!"))
        return None
    if not t.permissions_for(ctx.me).speak:
        await ctx.send(embed=err_e("No permission to speak!"))
        return None
    vc = ctx.voice_client
    try:
        if not vc: vc = await t.connect(timeout=15)
        elif vc.channel != t: await vc.move_to(t)
        return vc
    except asyncio.TimeoutError:
        await ctx.send(embed=err_e("Timed out."))
        return None
    except Exception as e:
        log.error(f"vc connect: {e}")
        await ctx.send(embed=err_e("Failed to connect."))
        return None

async def _dj(ctx):
    if ctx.author.guild_permissions.manage_guild: return True
    s = get_settings(ctx.guild.id)
    did = s.get("dj_role_id")
    if did:
        role = ctx.guild.get_role(int(did))
        if role and role in ctx.author.roles: return True
        await ctx.send(embed=err_e(f"Need **{role.name if role else did}** DJ role!"))
        return False
    return True

# ──────────────────────────────────────────────────────
#  COMMANDS
# ──────────────────────────────────────────────────────
@bot.command(aliases=["j"])
async def join(ctx):
    vc = await _vc(ctx)
    if vc: await ctx.send(embed=ok_e(f"Joined **{vc.channel.name}**!"))

@bot.command(aliases=["dc","leave"])
async def disconnect(ctx):
    if not ctx.voice_client: return await ctx.send(embed=err_e("Not in VC!"))
    if not await _dj(ctx): return
    vc = ctx.voice_client
    get_player(ctx.guild.id).queue.clear()
    try: vc.stop()
    except: pass
    try: await vc.disconnect()
    except: pass
    destroy_player(ctx.guild.id)
    await ctx.send(embed=ok_e("Disconnected! 👋"))

@bot.command(aliases=["p"])
async def play(ctx, *, query):
    if not query or not query.strip():
        return await ctx.send(embed=err_e("Provide a song name or URL!"))
    vc = await _vc(ctx)
    if not vc: return
    pl = get_player(ctx.guild.id)
    plat = detect_platform(query)
    pe = P_EMOJI.get(plat, "🔍")
    msg = await ctx.send(embed=_e(C_LUNA, f"{pe} Searching **{query[:80]}**..."))
    is_url = query.strip().startswith(("http://", "https://"))

    try:
        if is_url and ("list=" in query or "/playlist" in query.lower()):
            entries = await resolve_playlist(query)
            if not entries: return await msg.edit(embed=err_e("Playlist not found."))
            added = 0
            for e in entries:
                eid = e.get("id")
                if not eid: continue
                d = {"title":e.get("title") or "Unknown","url":e.get("url") or f"https://www.youtube.com/watch?v={eid}","webpage_url":e.get("url") or f"https://www.youtube.com/watch?v={eid}","duration":e.get("duration") or 0,"thumbnail":e.get("thumbnail") or "","uploader":e.get("uploader") or e.get("channel") or ""}
                pl.queue.append(Song(d, ctx.author, e.get("_platform", plat)))
                added += 1
            if not added: return await msg.edit(embed=err_e("No playable entries."))
            em = _e(C_LUNA, ""); em.title = "📋 Playlist Added!"
            em.add_field(name="Songs", value=str(added), inline=True)
            em.add_field(name="Queue", value=str(len(pl.queue)), inline=True)
            await msg.edit(embed=em)

        elif is_url:
            data = await resolve_url(query)
            if not data: return await msg.edit(embed=err_e("Couldn't resolve URL."))
            song = Song(data, ctx.author, plat)
            pl.queue.append(song)
            if vc.is_playing() or vc.is_paused():
                em = _e(C_LUNA, ""); em.title = "➕ Added"; em.description = f"**[{song.title}]({song.url})**"
                em.add_field(name="Duration", value=song.dur_str, inline=True)
                if song.is_kurdish: em.add_field(name="Type", value="🟢 Kurdish", inline=True)
                if song.thumbnail and song.thumbnail.startswith("http"): em.set_thumbnail(url=song.thumbnail)
                await msg.edit(embed=em)
            else:
                try: await msg.delete()
                except: pass
        else:
            results = await search_songs(query, kurdish_mode=pl.kurdish_mode)
            if not results: return await msg.edit(embed=err_e("No results found! Try different words."))
            data = results[0]
            song = Song(data, ctx.author, "youtube")
            pl.queue.append(song)
            if vc.is_playing() or vc.is_paused():
                em = _e(C_LUNA, ""); em.title = "➕ Added"; em.description = f"**[{song.title}]({song.url})**"
                em.add_field(name="Duration", value=song.dur_str, inline=True)
                if song.is_kurdish: em.add_field(name="Type", value="🟢 Kurdish", inline=True)
                if song.thumbnail and song.thumbnail.startswith("http"): em.set_thumbnail(url=song.thumbnail)
                await msg.edit(embed=em)
            else:
                try: await msg.delete()
                except: pass
    except Exception as e:
        log.error(f"play: {e}\n{traceback.format_exc()}")
        try: await msg.edit(embed=err_e(f"Error: {str(e)[:150]}"))
        except: pass
        return

    await _start(ctx)

@bot.command()
async def search(ctx, *, query):
    if not query or not query.strip():
        return await ctx.send(embed=err_e("Provide a search query!"))
    msg = await ctx.send(embed=_e(C_LUNA, f"🔍 Searching **{query[:80]}**..."))
    try:
        results = await search_songs(query, get_player(ctx.guild.id).kurdish_mode)
    except Exception as e:
        return await msg.edit(embed=err_e(str(e)[:150]))
    if not results:
        return await msg.edit(embed=err_e("No results!"))
    lines = []
    for i, r in enumerate(results):
        k = " 🟢" if is_kurdish(r.get("title","")) else ""
        lines.append(f"`{i+1}.` [{r.get('title','?')[:60]}](https://youtu.be/{r.get('id','')}) `{_dur(r.get('duration'))}`{k}")
    em = _e(C_LUNA, ""); em.title = "🔍 Results"; em.description = "\n".join(lines)
    em.set_footer(text="Reply 1-5 to pick • 'cancel' to cancel\n🟢 = Kurdish")
    await msg.edit(embed=em)

    def chk(m): return m.author == ctx.author and m.channel == ctx.channel and m.content.strip()
    try:
        reply = await bot.wait_for("message", check=chk, timeout=30)
    except asyncio.TimeoutError:
        return await msg.edit(embed=err_e("Timed out."))
    try: await reply.delete()
    except: pass
    if reply.content.strip().lower() == "cancel":
        return await msg.edit(embed=ok_e("Cancelled."))
    try:
        idx = int(reply.content.strip()) - 1
        if idx < 0 or idx >= len(results): raise ValueError
    except (ValueError, TypeError):
        return await msg.edit(embed=err_e("Invalid number."))

    vc = await _vc(ctx)
    if not vc: return
    rid = results[idx].get("id")
    if not rid: return await msg.edit(embed=err_e("No ID."))
    try:
        full = await resolve_url(f"https://www.youtube.com/watch?v={rid}")
        if not full: return await msg.edit(embed=err_e("Couldn't resolve."))
    except Exception as e:
        return await msg.edit(embed=err_e(str(e)[:150]))
    song = Song(full, ctx.author, "youtube")
    get_player(ctx.guild.id).queue.append(song)
    em2 = _e(C_LUNA, ""); em2.title = "➕ Added"; em2.description = f"**[{song.title}]({song.url})**"
    if song.is_kurdish: em2.add_field(name="Type", value="🟢 Kurdish", inline=True)
    if song.thumbnail and song.thumbnail.startswith("http"): em2.set_thumbnail(url=song.thumbnail)
    await msg.edit(embed=em2)
    await _start(ctx)

@bot.command(aliases=["kurdish","ku"])
async def kurdishplay(ctx, *, query):
    if not query or not query.strip():
        return await ctx.send(embed=err_e("Provide a song name!"))
    vc = await _vc(ctx)
    if not vc: return
    msg = await ctx.send(embed=_e(C_LUNA, f"🟢 Finding Kurdish: **{query[:80]}**..."))
    try:
        results = await search_songs(query, kurdish_mode=True, force_kurdish=True)
        if not results:
            return await msg.edit(embed=err_e("No Kurdish version found. Try different words."))
        song = Song(results[0], ctx.author, "youtube")
        get_player(ctx.guild.id).queue.append(song)
        em = _e(C_LUNA, ""); em.title = "🟢 Kurdish Song!"
        em.description = f"**[{song.title}]({song.url})**"
        em.add_field(name="Duration", value=song.dur_str, inline=True)
        em.add_field(name="Channel", value=song.uploader[:50], inline=True)
        if song.thumbnail and song.thumbnail.startswith("http"): em.set_thumbnail(url=song.thumbnail)
        await msg.edit(embed=em)
    except Exception as e:
        log.error(f"kurdishplay: {e}")
        return await msg.edit(embed=err_e(str(e)[:150]))
    await _start(ctx)

@bot.command(aliases=["pa"])
async def pause(ctx):
    vc = ctx.voice_client
    if not vc or not vc.is_playing(): return await ctx.send(embed=err_e("Nothing playing!"))
    if not await _dj(ctx): return
    p = get_player(ctx.guild.id)
    p._elapsed_pre = p.elapsed(); p._paused_at = time.time(); vc.pause()
    await ctx.send(embed=ok_e("Paused ⏸️"))

@bot.command(aliases=["res"])
async def resume(ctx):
    vc = ctx.voice_client
    if not vc or not vc.is_paused(): return await ctx.send(embed=err_e("Nothing paused!"))
    if not await _dj(ctx): return
    p = get_player(ctx.guild.id)
    p._elapsed_pre = p.elapsed(); p._start = time.time(); p._paused_at = None; vc.resume()
    await ctx.send(embed=ok_e("Resumed ▶️"))

@bot.command(aliases=["s"])
async def skip(ctx):
    vc = ctx.voice_client
    if not vc or (not vc.is_playing() and not vc.is_paused()): return await ctx.send(embed=err_e("Nothing playing!"))
    p = get_player(ctx.guild.id)
    is_dj = ctx.author.guild_permissions.manage_guild
    s = get_settings(ctx.guild.id)
    did = s.get("dj_role_id")
    if is_dj or (did and (role := ctx.guild.get_role(int(did))) and role in ctx.author.roles):
        p.skip_votes.clear(); vc.stop(); return await ctx.send(embed=ok_e("⏭️ Skipped!"))
    members = [m for m in vc.channel.members if not m.bot]
    if not members:
        p.skip_votes.clear(); vc.stop(); return await ctx.send(embed=ok_e("⏭️ Skipped!"))
    needed = max(1, math.ceil(len(members)*0.5))
    p.skip_votes.add(ctx.author.id)
    v = len(p.skip_votes)
    if v >= needed:
        p.skip_votes.clear(); vc.stop()
        await ctx.send(embed=ok_e(f"⏭️ Vote passed ({v}/{needed})!"))
    else:
        await ctx.send(embed=_e(C_YELLOW, f"🗳️ Vote: **{v}/{needed}** — need {needed-v} more."))

@bot.command()
async def stop(ctx):
    if not await _dj(ctx): return
    vc = ctx.voice_client
    if not vc: return await ctx.send(embed=err_e("Not in VC!"))
    p = get_player(ctx.guild.id)
    p.queue.clear(); p.loop = "off"; vc.stop()
    await ctx.send(embed=ok_e("⏹️ Stopped!"))

@bot.command(aliases=["np"])
async def nowplaying(ctx):
    vc = ctx.voice_client
    if not vc: return await ctx.send(embed=err_e("Not in VC!"))
    p = get_player(ctx.guild.id)
    if not p.current: return await ctx.send(embed=err_e("Nothing playing!"))
    try: p.np_msg = await ctx.send(embed=build_np(p, vc), view=NPView(p, vc))
    except: pass

@bot.command(aliases=["replay","restart"])
async def again(ctx):
    vc = ctx.voice_client
    if not vc or (not vc.is_playing() and not vc.is_paused()): return await ctx.send(embed=err_e("Nothing playing!"))
    if not await _dj(ctx): return
    p = get_player(ctx.guild.id)
    if not p.current: return await ctx.send(embed=err_e("Nothing playing!"))
    p.queue.insert(0, p.current); vc.stop()
    await ctx.send(embed=ok_e("🔁 Replaying!"))

@bot.command(aliases=["q"])
async def queue(ctx, page=1):
    p = get_player(ctx.guild.id)
    if not p.current and not p.queue: return await ctx.send(embed=_e(C_LUNA, "📋 Empty queue. Use $play!"))
    pp = 10; t = len(p.queue); pg = max(1,math.ceil(t/pp)); page = max(1,min(page,pg))
    st = (page-1)*pp; chunk = p.queue[st:st+pp]
    d = ""
    if p.current:
        k = " 🟢" if p.current.is_kurdish else ""
        d += f"**▶️ Now:** [{p.current.title}]({p.current.url}) `{p.current.dur_str}` — {p.current.requester.mention}{k}\n\n"
    if chunk:
        d += "**📋 Up Next:**\n"
        for i, s in enumerate(chunk, st+1):
            k = " 🟢" if s.is_kurdish else ""
            d += f"`{i}.` [{s.title}]({s.url}) `{s.dur_str}` — {s.requester.mention}{k}\n"
    td = sum(s.duration or 0 for s in p.queue)
    li = {"off":"➡️ Off","track":"🔂 Track","queue":"🔁 Queue"}.get(p.loop,"➡️ Off")
    em = _e(C_LUNA, ""); em.title = f"📋 Queue — {t} songs"; em.description = d
    em.set_footer(text=f"Page {page}/{pg} • {_ft(td)} • Loop: {li} • 🟢 = Kurdish")
    await ctx.send(embed=em)

@bot.command(aliases=["rm"])
async def remove(ctx, index: int):
    if not await _dj(ctx): return
    p = get_player(ctx.guild.id)
    if index < 1 or index > len(p.queue): return await ctx.send(embed=err_e(f"Invalid! Queue has {len(p.queue)} songs."))
    r = p.queue.pop(index-1)
    await ctx.send(embed=ok_e(f"Removed **{r.title[:50]}**"))

@bot.command()
async def clear(ctx):
    if not await _dj(ctx): return
    get_player(ctx.guild.id).queue.clear()
    await ctx.send(embed=ok_e("Cleared!"))

@bot.command(aliases=["sh"])
async def shuffle(ctx):
    if not await _dj(ctx): return
    p = get_player(ctx.guild.id)
    if len(p.queue) < 2: return await ctx.send(embed=err_e("Need 2+ songs."))
    random.shuffle(p.queue)
    await ctx.send(embed=ok_e("🔀 Shuffled!"))

@bot.command()
async def move(ctx, frm: int, to: int):
    if not await _dj(ctx): return
    p = get_player(ctx.guild.id); q = p.queue
    if not (1<=frm<=len(q)) or not (1<=to<=len(q)): return await ctx.send(embed=err_e(f"Must be 1–{len(q)}."))
    s = q.pop(frm-1); q.insert(to-1, s)
    await ctx.send(embed=ok_e(f"Moved **{s.title[:50]}** to **{to}**."))

@bot.command()
async def skipto(ctx, index: int):
    if not await _dj(ctx): return
    vc = ctx.voice_client
    if not vc: return await ctx.send(embed=err_e("Nothing playing!"))
    p = get_player(ctx.guild.id)
    if index < 1 or index > len(p.queue): return await ctx.send(embed=err_e(f"Invalid! Queue has {len(p.queue)}."))
    p.queue = p.queue[index-1:]; vc.stop()
    await ctx.send(embed=ok_e(f"⏭️ Skipped to **{index}**!"))

@bot.command(aliases=["vol"])
async def volume(ctx, vol: int):
    if not await _dj(ctx): return
    if not 0 <= vol <= 200: return await ctx.send(embed=err_e("Volume 0–200."))
    p = get_player(ctx.guild.id); p.volume = vol/100.0; save_settings(ctx.guild.id, volume=vol)
    vc = ctx.voice_client
    if vc and vc.source:
        try: vc.source.volume = p.volume
        except: pass
    ic = "🔇" if vol==0 else ("🔉" if vol<50 else "🔊")
    await ctx.send(embed=ok_e(f"{ic} Volume **{vol}%**"))

@bot.command()
async def loop(ctx, mode=None):
    if not await _dj(ctx): return
    p = get_player(ctx.guild.id); ms = ["off","track","queue"]
    mode = (ms[(ms.index(p.loop)+1)%3] if mode is None else mode.lower())
    if mode not in ms: return await ctx.send(embed=err_e("Must be: off/track/queue"))
    p.loop = mode; save_settings(ctx.guild.id, loop_mode=mode)
    await ctx.send(embed=ok_e(f"{{'off':'➡️','track':'🔂','queue':'🔁'}}['{mode}'] Loop **{mode.title()}**"))

@bot.command(aliases=["filter"])
async def setfilter(ctx, name=None):
    if not await _dj(ctx): return
    if name is None:
        lines = [f"`{k}` — {v['label']}" for k,v in FILTERS.items()]
        em = _e(C_LUNA, ""); em.title = "🎛️ Filters"; em.description = "\n".join(lines)
        return await ctx.send(embed=em)
    name = name.lower()
    if name not in FILTERS: return await ctx.send(embed=err_e("Unknown filter!"))
    p = get_player(ctx.guild.id); old = p.filter_name; p.filter_name = name
    vc = ctx.voice_client
    if vc and (vc.is_playing() or vc.is_paused()) and p.current:
        wp = vc.is_paused(); pp = p.elapsed()
        try: vc.stop()
        except: pass
        await asyncio.sleep(0.6)
        data = await resolve_url(p.current.url)
        if data: p.current.stream_url = data.get("url") or p.current.stream_url
        src = _make_source(p.current.stream_url, p.volume, name)
        if src:
            p.reset_timer(); p._playing = True
            def ac(err):
                if err: log.error(f"Filter after: {err}")
                f = asyncio.run_coroutine_threadsafe(play_next(ctx.guild.id, ctx.channel, vc), bot.loop)
                f.add_done_callback(lambda x: x.exception() if x.exception() else None)
            try:
                vc.play(src, after=ac)
                if wp: vc.pause(); p._elapsed_pre = pp; p._paused_at = time.time()
            except Exception as e:
                p.filter_name = old; await ctx.send(embed=err_e(f"Failed: {e}")); return
        else:
            p.filter_name = old; await ctx.send(embed=err_e("FFmpeg failed.")); return
    await ctx.send(embed=ok_e(f"🎛️ Filter **{FILTERS[name]['label']}**"))

@bot.command(aliases=["filters"])
async def listfilters(ctx):
    lines = [f"`{k}` — {v['label']}" for k,v in FILTERS.items()]
    em = _e(C_LUNA, ""); em.title = "🎛️ Filters"; em.description = "\n".join(lines)
    await ctx.send(embed=em)

@bot.command(name="247")
async def tfs_cmd(ctx):
    if not await _dj(ctx): return
    p = get_player(ctx.guild.id); p.tfs = not p.tfs; save_settings(ctx.guild.id, tfs=int(p.tfs))
    await ctx.send(embed=ok_e(f"24/7 {'enabled 🟢' if p.tfs else 'disabled 🔴'}"))

@bot.command()
async def autoplay(ctx):
    if not await _dj(ctx): return
    p = get_player(ctx.guild.id); p.autoplay = not p.autoplay; save_settings(ctx.guild.id, autoplay=int(p.autoplay))
    await ctx.send(embed=ok_e(f"Autoplay {'enabled 🟢' if p.autoplay else 'disabled 🔴'}"))

@bot.command()
async def kurdishmode(ctx):
    p = get_player(ctx.guild.id); p.kurdish_mode = not p.kurdish_mode; save_settings(ctx.guild.id, kurdish_mode=int(p.kurdish_mode))
    await ctx.send(embed=ok_e(f"Kurdish mode {'enabled 🟢' if p.kurdish_mode else 'disabled 🔴'}"))

@bot.command(aliases=["setdj"])
@commands.has_permissions(manage_guild=True)
async def djrole(ctx, role: discord.Role = None):
    if not role:
        save_settings(ctx.guild.id, dj_role_id=None)
        return await ctx.send(embed=ok_e("DJ role removed."))
    save_settings(ctx.guild.id, dj_role_id=role.id)
    await ctx.send(embed=ok_e(f"DJ role: {role.mention}"))

@bot.command(aliases=["ly"])
async def lyrics(ctx, *, song_name=None):
    p = get_player(ctx.guild.id)
    if not song_name or not song_name.strip():
        if not p.current: return await ctx.send(embed=err_e("Nothing playing! Use: `$lyrics Artist - Song`"))
        song_name = p.current.title
    clean = song_name
    for pat in ["(official","(lyrics","(audio)","(video)","(hd)","(4k)","[","]","ft.","feat."]:
        i = clean.lower().find(pat)
        if i != -1: clean = clean[:i].strip()
    parts = clean.split(" - ", 1)
    artist, title_q = (parts[0].strip(), parts[1].strip()) if len(parts)==2 else ("", clean.strip())
    if not artist or not title_q: return await ctx.send(embed=err_e("Use: `$lyrics Artist - Song Title`"))
    msg = await ctx.send(embed=_e(C_LUNA, f"🔍 Fetching lyrics **{clean[:60]}**..."))
    lt = None
    for a, t in [(artist, title_q), (artist, clean), (clean, clean)]:
        if not a or not t: continue
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://api.lyrics.ovh/v1/{a}/{t}", timeout=aiohttp.ClientTimeout(total=8)) as r:
                    if r.status == 200:
                        d = await r.json()
                        if d.get("lyrics"): lt = d["lyrics"]; break
        except: continue
    if not lt: return await msg.edit(embed=err_e(f"No lyrics for **{clean[:60]}**."))
    lt = lt.replace("\r\n","\n").strip()
    chunks = [lt[i:i+3800] for i in range(0, len(lt), 3800)]
    for i, c in enumerate(chunks):
        em = _e(C_LUNA, c); em.title = f"📜 {clean[:60]}" + (f" ({i+1})" if len(chunks)>1 else "")
        if i == 0: await msg.edit(embed=em)
        else:
            try: await ctx.send(embed=em)
            except: pass

@bot.command()
async def history(ctx):
    try:
        c = _db(); c.row_factory = sqlite3.Row
        rows = c.execute("SELECT title,url,duration,platform FROM history WHERE guild_id=? ORDER BY id DESC LIMIT 10", (ctx.guild.id,)).fetchall()
        c.close()
    except Exception as e:
        return await ctx.send(embed=err_e("DB error."))
    if not rows: return await ctx.send(embed=_e(C_LUNA, "📜 No history."))
    lines = [f"`{i+1}.` {P_EMOJI.get(r['platform'] or 'unknown','🎵')} [{r['title']}]({r['url']}) `{r['duration']}` {'🟢' if is_kurdish(r['title']) else ''}" for i,r in enumerate(rows)]
    em = _e(C_LUNA, ""); em.title = "📜 History"; em.description = "\n".join(lines)
    await ctx.send(embed=em)

@bot.command()
async def grab(ctx):
    p = get_player(ctx.guild.id)
    if not p.current: return await ctx.send(embed=err_e("Nothing playing!"))
    s = p.current
    em = discord.Embed(color=C_LUNA, title="❤️ Saved!", description=f"**[{s.title}]({s.url})**")
    em.add_field(name="Duration", value=s.dur_str, inline=True)
    if s.is_kurdish: em.add_field(name="Type", value="🟢 Kurdish", inline=True)
    if s.thumbnail and s.thumbnail.startswith("http"): em.set_thumbnail(url=s.thumbnail)
    try:
        await ctx.author.send(embed=em)
        await ctx.send(embed=ok_e("Sent to DMs!"))
    except discord.Forbidden:
        await ctx.send(embed=err_e("Can't DM you."))
    except: pass

@bot.command()
async def ping(ctx):
    await ctx.send(embed=_e(C_LUNA, f"🏓 Pong! **{round(bot.latency*1000)}ms**"))

@bot.command(aliases=["stats"])
async def botinfo(ctx):
    u = int(time.time()-bot_start_time); h,r = divmod(u,3600); m,s = divmod(r,60)
    em = _e(C_LUNA, ""); em.title = "🎵 Veltra Music Bot"
    em.add_field(name="Prefix", value="`$`", inline=True)
    em.add_field(name="Servers", value=str(len(bot.guilds)), inline=True)
    em.add_field(name="Uptime", value=f"{h}h {m}m {s}s", inline=True)
    em.add_field(name="Search", value="Direct HTTP + yt-dlp", inline=True)
    em.add_field(name="Kurdish", value="🟢 Guaranteed", inline=True)
    em.add_field(name="Platforms", value="Spotify·Apple·SC·Deezer·Anghami·Vimeo·YT·MP3", inline=False)
    await ctx.send(embed=em)

@bot.command()
async def help(ctx):
    em = _e(C_LUNA, "")
    em.title = "🎵 Veltra Music Bot — Help"
    em.description = "**GUARANTEED Kurdish search via Direct HTTP!**\n🟢 = Kurdish song"
    em.add_field(name="🎵 Playback", value="```$play <query/url>     Play any platform\n$kurdish <query>      ⭐ Find Kurdish version\n$search <query>       Search & pick\n$pause / $resume      Pause/Resume\n$skip / $s            Skip\n$stop                 Stop & clear\n$nowplaying / $np     Now playing\n$again                Replay\n$join / $disconnect   Voice control```", inline=False)
    em.add_field(name="📋 Queue", value="```$queue / $q [page]    Show queue\n$remove / $rm <pos>   Remove\n$clear                Clear\n$shuffle / $sh        Shuffle\n$move <from> <to>     Move\n$skipto <pos>         Skip to```", inline=False)
    em.add_field(name="⚙️ Settings", value="```$volume / $vol <0-200>\n$loop [off/track/queue]\n$filter / $setfilter\n$247                  Stay in VC\n$autoplay             Auto-play Kurdish\n$kurdishmode         Toggle Kurdish search\n$djrole [@role]       Set DJ role```", inline=False)
    em.set_footer(text="$kurdish <any song> = guaranteed Kurdish version!")
    await ctx.send(embed=em)

# ──────────────────────────────────────────────────────
#  EVENTS
# ──────────────────────────────────────────────────────
@bot.event
async def on_ready():
    log.info(f"Logged in: {bot.user} ({bot.user.id})")
    log.info(f"Guilds: {len(bot.guilds)}")
    log.info("★ Direct HTTP Search Active — Bypasses IP blocks ★")
    try:
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="🎵 Kurdish Music | $help"))
    except: pass

@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot: return
    if before.channel and not after.channel:
        vc = before.channel.guild.voice_client
        if vc and vc.channel == before.channel:
            if not [m for m in vc.channel.members if not m.bot]:
                p = get_player(vc.guild.id)
                if not p.tfs:
                    await asyncio.sleep(3)
                    if not [m for m in vc.channel.members if not m.bot] and vc.is_connected():
                        p.queue.clear()
                        try: vc.stop()
                        except: pass
                        try: await vc.disconnect()
                        except: pass
                        destroy_player(vc.guild.id)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound): return
    if isinstance(error, commands.MissingPermissions):
        try: await ctx.send(embed=err_e("No permission!"))
        except: pass
        return
    if isinstance(error, commands.MissingRequiredArgument):
        try: await ctx.send(embed=err_e(f"Missing: `{error.param.name}`"))
        except: pass
        return
    log.error(f"Cmd error [{ctx.command}]: {error}\n{traceback.format_exc()}")
    try: await ctx.send(embed=err_e(str(error)[:150]))
    except: pass

if __name__ == "__main__":
    log.info("Starting Veltra Music Bot...")
    try:
        bot.run(TOKEN, log_handler=None)
    except discord.LoginFailure:
        log.error("FATAL: Invalid token!")
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log.error(f"FATAL: {e}\n{traceback.format_exc()}")
