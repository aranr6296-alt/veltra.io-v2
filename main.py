"""
╔══════════════════════════════════════════════════════╗
║  VELTRA MUSIC BOT — TRUE MULTI-PLATFORM (LIKE LARA)   ║
║  Spotify·SC·Deezer·Apple·Anghami·FB·Twitch·YT·MP3    ║
║  yt-dlp Engine · Kurdish · Sub-Second Speed           ║
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
import functools
import concurrent.futures
from dotenv import load_dotenv

# yt-dlp for reliable extraction
import yt_dlp

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    print("[FATAL] No DISCORD_TOKEN in .env file")
    raise SystemExit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("veltra.log", encoding="utf-8", mode="a")
    ]
)
log = logging.getLogger("veltra")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix="$", intents=intents, help_command=None)
bot_start_time = time.time()

# Thread pool for sync yt-dlp calls
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

C_LUNA   = 0xB5179E
C_GREEN  = 0x57F287
C_RED    = 0xED4245
C_YELLOW = 0xFEE75C

# ═══════════════════════════════════════
#  COBALT FALLBACK (Spotify, Apple, Deezer, Anghami, Vimeo, FB, Twitch)
# ═══════════════════════════════════════
COBALT_INSTANCES = [
    "https://api.cobalt.tools",
    "https://cobalt.api.timelessnesses.me",
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
                guild_id INTEGER,
                title TEXT,
                url TEXT,
                duration TEXT,
                requester TEXT,
                platform TEXT DEFAULT 'unknown',
                played_at TEXT DEFAULT (datetime('now'))
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
        row = conn.execute("SELECT * FROM guild_settings WHERE guild_id=?", (gid,)).fetchone()
        if not row:
            conn.execute("INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)", (gid,))
            conn.commit()
            row = conn.execute("SELECT * FROM guild_settings WHERE guild_id=?", (gid,)).fetchone()
        conn.close()
        return dict(row) if row else {
            "dj_role_id": None, "volume": 100, "loop_mode": "off",
            "tfs": 0, "autoplay": 0, "kurdish_mode": 1
        }
    except Exception:
        return {"dj_role_id": None, "volume": 100, "loop_mode": "off",
                "tfs": 0, "autoplay": 0, "kurdish_mode": 1}

def save_settings(gid, **kw):
    try:
        get_settings(gid)
        sets = ", ".join(f"{k}=?" for k in kw)
        conn = _db()
        conn.execute(f"UPDATE guild_settings SET {sets} WHERE guild_id=?", [*kw.values(), gid])
        conn.commit()
        conn.close()
    except Exception as e:
        log.error(f"save_settings: {e}")

def push_history(gid, title, url, dur, req, plat="unknown"):
    try:
        conn = _db()
        conn.execute(
            "INSERT INTO history (guild_id,title,url,duration,requester,platform) VALUES (?,?,?,?,?,?)",
            (gid, title, url, dur, req, plat)
        )
        conn.execute(
            "DELETE FROM history WHERE guild_id=? AND id NOT IN "
            "(SELECT id FROM history WHERE guild_id=? ORDER BY id DESC LIMIT 50)",
            (gid, gid)
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
    "tremolo":    {"label": "〰️ Tremolo",     "af": "tremolo=f=4:d=0.9"},
    "vibrato":    {"label": "🎸 Vibrato",     "af": "vibrato=f=6.5:d=0.9"},
    "superbass":  {"label": "💥 Super Bass",  "af": "bass=g=20,dynaudnorm=f=200"},
    "soft":       {"label": "🕊️ Soft",        "af": "lowpass=f=300,volume=1.5"},
    "earrape":    {"label": "📢 Ear Rape",    "af": "acrusher=level_in=8:level_out=18:bits=8:mode=log:aa=1"},
    "pitch":      {"label": "🎵 Pitch Up",   "af": "asetrate=44100*1.15,aresample=44100"},
}

# ═══════════════════════════════════════
#  PLATFORM DETECTION
# ═══════════════════════════════════════
def detect_platform(url: str) -> str:
    if not url:
        return "unknown"
    lower = url.lower()
    if "open.spotify.com" in lower or "spotify.com" in lower:
        return "spotify"
    if "music.apple.com" in lower or "itunes.apple.com" in lower:
        return "apple_music"
    if "soundcloud.com" in lower:
        return "soundcloud"
    if "deezer.com" in lower:
        return "deezer"
    if "anghami.com" in lower:
        return "anghami"
    if "facebook.com" in lower or "fb.watch" in lower or "fb.com" in lower:
        return "facebook"
    if "twitch.tv" in lower:
        return "twitch"
    if "vimeo.com" in lower:
        return "vimeo"
    if "music.youtube.com" in lower:
        return "youtube_music"
    if "youtube.com" in lower or "youtu.be" in lower:
        return "youtube"
    if any(lower.endswith(ext) for ext in (".mp3", ".mp4", ".m4a", ".ogg", ".wav", ".flac", ".webm", ".opus")):
        return "direct"
    return "unknown"

PLATFORM_EMOJIS = {
    "spotify":       "<:spotify:1> 🎵",
    "apple_music":   "🍎",
    "soundcloud":    "☁️",
    "deezer":        "🎶",
    "anghami":       "🌙",
    "vimeo":         "📹",
    "facebook":      "👤",
    "twitch":        "📺",
    "youtube_music": "🎵",
    "youtube":       "▶️",
    "direct":        "📎",
    "unknown":       "🔍",
}

PLATFORM_EMOJIS = {
    "spotify":       "🎵",
    "apple_music":   "🍎",
    "soundcloud":    "☁️",
    "deezer":        "🎶",
    "anghami":       "🌙",
    "vimeo":         "📹",
    "facebook":      "👤",
    "twitch":        "📺",
    "youtube_music": "🎵",
    "youtube":       "▶️",
    "direct":        "📎",
    "unknown":       "🔍",
}

# ═══════════════════════════════════════
#  KURDISH DETECTION
# ═══════════════════════════════════════
KURDISH_KEYWORDS = [
    "kurdish", "kurdi", "کوردی", "کوردیی", "kurdî", "kurdish song",
    "zagros", "kurdistan", "hawler", "slemani", "erbil", "duhok",
    "stran", "gorani", "xoshtrin", "nazy", "koma", "dengbej",
    "bahdini", "sorani", "kurmanji"
]

def is_kurdish(title: str) -> bool:
    if not title:
        return False
    # Arabic/Kurdish Unicode block
    for char in title:
        if '\u0600' <= char <= '\u06FF':
            return True
    lower = title.lower()
    return any(kw in lower for kw in KURDISH_KEYWORDS)

def get_kurdish_queries(query: str) -> list:
    if is_kurdish(query):
        return [query, f"{query} official", f"{query} stran"]
    return [
        f"{query} kurdish song کوردی",
        f"{query} کوردی",
        f"{query} stran kurdî",
        f"{query} kurdish cover",
        f"{query} kurdish music",
    ]

# ═══════════════════════════════════════
#  ★ YT-DLP ENGINE (Primary) ★
# ═══════════════════════════════════════
YDL_OPTS_SEARCH = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "extract_flat": True,
    "default_search": "ytsearch5",
    "noplaylist": True,
    "skip_download": True,
    "socket_timeout": 8,
}

YDL_OPTS_EXTRACT = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "skip_download": True,
    "socket_timeout": 10,
    "extractor_retries": 2,
    "source_address": "0.0.0.0",
}

def _ydl_search_sync(query: str, count: int = 5) -> list:
    """Synchronous yt-dlp search — run in executor."""
    opts = {**YDL_OPTS_SEARCH, "default_search": f"ytsearch{count}"}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(query, download=False)
            if not info:
                return []
            entries = info.get("entries") or ([info] if info.get("id") else [])
            results = []
            for e in entries:
                if not e:
                    continue
                vid = e.get("id") or e.get("url")
                if not vid:
                    continue
                url = e.get("webpage_url") or e.get("url") or f"https://www.youtube.com/watch?v={vid}"
                thumb = e.get("thumbnail") or f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg"
                results.append({
                    "id": vid,
                    "title": e.get("title") or "Unknown",
                    "url": url,
                    "webpage_url": url,
                    "duration": int(e.get("duration") or 0),
                    "thumbnail": thumb,
                    "uploader": e.get("uploader") or e.get("channel") or "Unknown",
                    "channel": e.get("channel") or e.get("uploader") or "Unknown",
                })
            return results
    except Exception as ex:
        log.debug(f"ydl_search error: {ex}")
        return []

def _ydl_extract_sync(url: str) -> dict | None:
    """Synchronous yt-dlp extraction — run in executor."""
    try:
        with yt_dlp.YoutubeDL(YDL_OPTS_EXTRACT) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return None
            # Pick the best audio-only format
            stream_url = None
            formats = info.get("formats") or []
            # Prefer audio-only
            audio_fmts = [f for f in formats if f.get("acodec") != "none" and f.get("vcodec") == "none"]
            if audio_fmts:
                best = max(audio_fmts, key=lambda f: f.get("abr") or f.get("tbr") or 0)
                stream_url = best.get("url")
            if not stream_url:
                # Fall back to combined formats
                all_fmts = [f for f in formats if f.get("url")]
                if all_fmts:
                    stream_url = all_fmts[-1]["url"]
            if not stream_url:
                stream_url = info.get("url")
            if not stream_url:
                return None
            thumb = info.get("thumbnail") or ""
            vid = info.get("id") or ""
            return {
                "url": stream_url,
                "webpage_url": info.get("webpage_url") or url,
                "title": info.get("title") or "Unknown",
                "duration": int(info.get("duration") or 0),
                "thumbnail": thumb or (f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg" if vid else ""),
                "uploader": info.get("uploader") or info.get("channel") or "Unknown",
                "channel": info.get("channel") or info.get("uploader") or "Unknown",
            }
    except Exception as ex:
        log.debug(f"ydl_extract error: {ex}")
        return None

async def ydl_search(query: str, count: int = 5) -> list:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _ydl_search_sync, query, count)

async def ydl_extract(url: str) -> dict | None:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _ydl_extract_sync, url)

# ═══════════════════════════════════════
#  COBALT FALLBACK (Spotify / Apple / Deezer / Anghami / etc.)
# ═══════════════════════════════════════
async def extract_cobalt(session: aiohttp.ClientSession, url: str) -> dict | None:
    """Try each Cobalt instance for non-YouTube platform audio."""
    for base in COBALT_INSTANCES:
        try:
            # Cobalt v2 API format
            async with session.post(
                f"{base}/",
                json={
                    "url": url,
                    "videoQuality": "360",
                    "audioFormat": "mp3",
                    "isAudioOnly": True,
                    "disableMetadata": False,
                },
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=12),
            ) as r:
                if r.status != 200:
                    continue
                data = await r.json()
                status = data.get("status")
                if status == "error":
                    continue
                stream_url = data.get("url")
                if stream_url:
                    return {
                        "url": stream_url,
                        "webpage_url": url,
                        "title": data.get("filename") or "Unknown",
                        "duration": 0,
                        "thumbnail": "",
                        "uploader": "Unknown",
                    }
        except Exception as ex:
            log.debug(f"Cobalt {base} failed: {ex}")
    return None

async def instant_extract(url: str) -> dict | None:
    """
    Primary: yt-dlp (handles YouTube, SoundCloud, Twitch, Vimeo, Dailymotion, etc.)
    Fallback: Cobalt (Spotify, Apple Music, Deezer, Anghami, Facebook)
    """
    platform = detect_platform(url)

    # Platforms where yt-dlp won't work — try Cobalt first
    cobalt_first = {"spotify", "apple_music", "deezer", "anghami"}

    if platform in cobalt_first:
        async with aiohttp.ClientSession() as sess:
            result = await extract_cobalt(sess, url)
        if result:
            log.info(f"✅ Extracted via Cobalt ({platform})")
            return result
        # Cobalt failed — try yt-dlp anyway
        result = await ydl_extract(url)
        if result:
            log.info(f"✅ Extracted via yt-dlp fallback ({platform})")
            return result
        return None

    # For everything else (YouTube, SoundCloud, Twitch, direct, etc.) try yt-dlp first
    result = await ydl_extract(url)
    if result:
        log.info(f"✅ Extracted via yt-dlp ({platform})")
        return result

    # Last resort: Cobalt
    async with aiohttp.ClientSession() as sess:
        result = await extract_cobalt(sess, url)
    if result:
        log.info(f"✅ Extracted via Cobalt fallback ({platform})")
    return result

# ═══════════════════════════════════════
#  SEARCH ENGINE
# ═══════════════════════════════════════
async def search_songs(query: str, kurdish_mode: bool = True, force_kurdish: bool = False) -> list:
    """
    Search YouTube via yt-dlp. Optionally bias toward Kurdish results.
    """
    if force_kurdish:
        queries = get_kurdish_queries(query)
    elif kurdish_mode and not is_kurdish(query):
        queries = [f"{query} kurdish song کوردی", query]
    else:
        queries = [query]

    all_results = []
    seen_ids = set()

    for q in queries:
        results = await ydl_search(q, count=5)
        if not results:
            continue

        if force_kurdish or (kurdish_mode and not is_kurdish(query)):
            kurdish_results = [r for r in results if is_kurdish(r.get("title", ""))]
            target = kurdish_results if kurdish_results else results
        else:
            target = results

        for r in target:
            vid = r.get("id")
            if vid and vid not in seen_ids:
                seen_ids.add(vid)
                all_results.append(r)

        if len(all_results) >= 5:
            break

    if not all_results:
        # Last resort: plain search without Kurdish bias
        results = await ydl_search(query, count=5)
        for r in results:
            vid = r.get("id")
            if vid and vid not in seen_ids:
                seen_ids.add(vid)
                all_results.append(r)

    return all_results[:5]

# ═══════════════════════════════════════
#  AUDIO SOURCE
# ═══════════════════════════════════════
def create_ffmpeg_source(stream_url: str, volume: float, filter_name: str):
    if not stream_url:
        return None
    af = FILTERS.get(filter_name, FILTERS["none"])["af"]
    before_opts = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
    options = "-vn"
    if af:
        options += f" -af {af}"
    try:
        pcm = discord.FFmpegPCMAudio(stream_url, before_options=before_opts, options=options)
        return discord.PCMVolumeTransformer(pcm, volume=volume)
    except Exception as e:
        log.error(f"FFmpeg error: {e}")
        return None

# ═══════════════════════════════════════
#  SONG & PLAYER
# ═══════════════════════════════════════
class Song:
    __slots__ = ("title", "url", "stream_url", "duration", "thumbnail",
                 "uploader", "requester", "platform", "is_kurdish")

    def __init__(self, data: dict, requester, platform: str = "unknown"):
        self.title      = str(data.get("title") or "Unknown")
        self.url        = str(data.get("webpage_url") or data.get("url") or "")
        self.stream_url = str(data.get("url") or "")
        self.duration   = data.get("duration") or 0
        self.thumbnail  = str(data.get("thumbnail") or "")
        self.uploader   = str(data.get("uploader") or data.get("channel") or "Unknown")
        self.requester  = requester
        self.platform   = platform
        self.is_kurdish = is_kurdish(self.title)

    @property
    def dur_str(self) -> str:
        if not self.duration or self.duration <= 0:
            return "🔴 LIVE"
        total = int(self.duration)
        mins, secs = divmod(total, 60)
        hours, mins = divmod(mins, 60)
        if hours:
            return f"{hours}:{mins:02d}:{secs:02d}"
        return f"{mins}:{secs:02d}"

    def progress_bar(self, elapsed: float, length: int = 13) -> str:
        if not self.duration or self.duration <= 0:
            return "─" * length + " 🔴"
        pct  = min(max(elapsed / self.duration, 0.0), 1.0)
        fill = int(pct * length)
        return "▬" * fill + "🔘" + "▬" * (length - fill)


class MusicPlayer:
    def __init__(self, guild_id: int):
        self.guild_id    = guild_id
        self.queue       = []
        self.current     = None
        self.history     = []
        self.loop        = "off"
        self.volume      = 1.0
        self.filter_name = "none"
        self.skip_votes  = set()
        self.tfs         = False
        self.autoplay    = False
        self.kurdish_mode = True
        self._start      = None
        self._paused_at  = None
        self._elapsed_pre = 0.0
        self.np_msg      = None
        self._lock       = asyncio.Lock()
        self._playing    = False
        # Set to True during filter swaps so after_callback skips queue advancement
        self._filter_swap = False

    def elapsed(self) -> float:
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
        player    = MusicPlayer(guild_id)
        settings  = get_settings(guild_id)
        player.volume       = max(0.0, min(2.0, (settings.get("volume") or 100) / 100.0))
        player.loop         = settings.get("loop_mode") or "off"
        player.tfs          = bool(settings.get("tfs"))
        player.autoplay     = bool(settings.get("autoplay"))
        player.kurdish_mode = bool(settings.get("kurdish_mode", 1))
        _players[guild_id] = player
    return _players[guild_id]

def destroy_player(guild_id: int):
    player = _players.pop(guild_id, None)
    if player:
        player.queue.clear()
        player.history.clear()
        player.current = None

# ═══════════════════════════════════════
#  EMBEDS & HELPERS
# ═══════════════════════════════════════
def make_embed(color: int, desc: str = "") -> discord.Embed:
    return discord.Embed(color=color, description=desc or None)

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

def build_np_embed(player: MusicPlayer, vc) -> discord.Embed:
    song = player.current
    if not song:
        return make_embed(C_LUNA, "Nothing playing")
    elapsed   = player.elapsed()
    is_paused = vc.is_paused() if vc else False
    e = discord.Embed(color=C_LUNA)
    e.set_author(name=f"{'🟢 Kurdish' if song.is_kurdish else '🎵'} Now Playing")
    e.title = song.title[:255]
    if song.url.startswith("http"):
        e.url = song.url
    e.description = f"`{format_time(elapsed)}` {song.progress_bar(elapsed)} `{song.dur_str}`"
    loop_modes = {"off": "➡️ Off", "track": "🔂 Track", "queue": "🔁 Queue"}
    vol_icon   = "🔇" if player.volume <= 0 else ("🔉" if player.volume < 0.5 else "🔊")
    filter_lbl = FILTERS.get(player.filter_name, FILTERS["none"])["label"]
    plat_emoji = PLATFORM_EMOJIS.get(song.platform, "🔍")
    e.add_field(name=f"{plat_emoji} Platform", value=song.platform.replace("_", " ").title(), inline=True)
    e.add_field(name="🎙️ Artist",   value=song.uploader[:50], inline=True)
    e.add_field(name="⏱️ Length",   value=song.dur_str,        inline=True)
    e.add_field(name=f"{vol_icon} Volume", value=f"{int(player.volume*100)}%", inline=True)
    e.add_field(name="🔁 Loop",    value=loop_modes.get(player.loop, "➡️ Off"), inline=True)
    e.add_field(name="🎛️ Filter",  value=filter_lbl,           inline=True)
    e.add_field(name="📋 Queue",   value=str(len(player.queue)), inline=True)
    e.add_field(name="👤 By",      value=song.requester.mention, inline=False)
    if song.thumbnail and song.thumbnail.startswith("http"):
        e.set_thumbnail(url=song.thumbnail)
    e.set_footer(text=f"Veltra Music • {'⏸ Paused' if is_paused else '▶️ Playing'}")
    return e

# ═══════════════════════════════════════
#  NOW-PLAYING VIEW (Buttons)
# ═══════════════════════════════════════
class NowPlayingView(discord.ui.View):
    def __init__(self, player: MusicPlayer, vc):
        super().__init__(timeout=None)
        self.player = player
        self.vc     = vc
        is_paused   = vc.is_paused() if vc else False
        buttons = [
            ("⏮️",                                                               "prev",    discord.ButtonStyle.secondary, 0),
            ("▶️" if is_paused else "⏸️",                                       "pause",   discord.ButtonStyle.primary,   0),
            ("⏭️",                                                               "skip",    discord.ButtonStyle.secondary, 0),
            ("⏹️",                                                               "stop",    discord.ButtonStyle.danger,    0),
            ("🔂" if player.loop == "track" else "🔁" if player.loop == "queue" else "➡️",
                                                                                  "loop",    discord.ButtonStyle.secondary, 1),
            ("🔀",                                                               "shuffle", discord.ButtonStyle.secondary, 1),
            ("❤️",                                                               "grab",    discord.ButtonStyle.secondary, 1),
            ("📋",                                                               "queue",   discord.ButtonStyle.secondary, 1),
        ]
        for emoji, action, style, row in buttons:
            self.add_item(ControlButton(emoji, action, style, row))


class ControlButton(discord.ui.Button):
    def __init__(self, emoji: str, action: str, style, row: int):
        super().__init__(
            emoji=emoji,
            style=style,
            custom_id=f"vnp_{action}_{random.randint(0, 9_999_999)}",
            row=row,
        )
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception:
            return
        if not interaction.guild or not interaction.guild.voice_client:
            await interaction.followup.send(embed=err_embed("I'm not in a voice channel!"), ephemeral=True)
            return
        vc     = interaction.guild.voice_client
        player = get_player(interaction.guild.id)

        # Require the user to be in the same VC (except grab/queue which are read-only)
        if self.action not in ("grab", "queue"):
            member_vc = interaction.user.voice.channel if interaction.user.voice else None
            if not member_vc or member_vc != vc.channel:
                await interaction.followup.send(
                    embed=err_embed("You must be in the same voice channel to use controls!"),
                    ephemeral=True
                )
                return

            # DJ check for destructive actions
            if self.action in ("stop", "shuffle", "loop"):
                is_dj = interaction.user.guild_permissions.manage_guild
                settings = get_settings(interaction.guild.id)
                dj_id    = settings.get("dj_role_id")
                has_role = False
                if dj_id:
                    dj_role  = interaction.guild.get_role(int(dj_id))
                    has_role = bool(dj_role and dj_role in interaction.user.roles)
                if not is_dj and not has_role:
                    await interaction.followup.send(
                        embed=err_embed("You need DJ permissions for this action!"),
                        ephemeral=True
                    )
                    return

        if not player.current:
            await interaction.followup.send(embed=err_embed("Nothing is playing!"), ephemeral=True)
            return

        try:
            handled = await self.handle_action(interaction, vc, player)
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
            log.error(f"ControlButton {self.action} error: {e}")

    async def handle_action(self, interaction: discord.Interaction, vc, player: MusicPlayer) -> bool:
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
            modes       = ["off", "track", "queue"]
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
            e    = discord.Embed(color=C_LUNA, title="❤️ Saved", description=f"**[{song.title}]({song.url})**")
            e.add_field(name="Duration", value=song.dur_str, inline=True)
            if song.is_kurdish:
                e.add_field(name="Type", value="🟢 Kurdish", inline=True)
            if song.thumbnail and song.thumbnail.startswith("http"):
                e.set_thumbnail(url=song.thumbnail)
            try:
                await interaction.user.send(embed=e)
                await interaction.followup.send(embed=ok_embed("Sent to DMs!"), ephemeral=True)
            except discord.Forbidden:
                await interaction.followup.send(embed=err_embed("Can't DM you — open DMs first."), ephemeral=True)
            except Exception:
                pass
            return True

        elif self.action == "queue":
            q = player.queue
            if not q:
                await interaction.followup.send(embed=make_embed(C_LUNA, "📋 Queue is empty."), ephemeral=True)
            else:
                lines = [
                    f"`{i+1}.` [{s.title[:50]}]({s.url}) `{s.dur_str}` {'🟢' if s.is_kurdish else ''}"
                    for i, s in enumerate(q[:10])
                ]
                extra = f"\n*+{len(q)-10} more...*" if len(q) > 10 else ""
                em = discord.Embed(color=C_LUNA, title=f"📋 Queue — {len(q)} songs",
                                   description="\n".join(lines) + extra)
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
                    await interaction.followup.send(embed=err_embed("No previous song!"), ephemeral=True)
                except Exception:
                    pass
            return True

        return False

# ═══════════════════════════════════════
#  PLAYBACK ENGINE
# ═══════════════════════════════════════
async def play_next(guild_id: int, text_channel, vc):
    player = get_player(guild_id)
    # If a filter swap is in progress, let setfilter handle restarting playback
    if player._filter_swap:
        return
    if player._lock.locked():
        return

    # Only hold the lock for the state-transition part (song selection + playback start).
    # Long-running async work (extraction, message sends, idle sleep) happens OUTSIDE the lock.
    async with player._lock:
        if not vc or not vc.is_connected():
            return

        # Determine next song
        song = None
        if player.loop == "track" and player.current:
            song = player.current
        elif player.loop == "queue" and player.current:
            player.queue.append(player.current)
            song = player.queue.pop(0) if player.queue else None
        else:
            song = player.queue.pop(0) if player.queue else None

        if not song:
            # Queue exhausted
            if player.current:
                push_history(
                    guild_id, player.current.title, player.current.url,
                    player.current.dur_str, str(player.current.requester),
                    player.current.platform,
                )
            player.current  = None
            player._playing = False
            do_autoplay = player.autoplay
            do_tfs      = player.tfs
            last_song   = player.history[-1] if player.history else None
        else:
            do_autoplay = False
            do_tfs      = player.tfs
            last_song   = None

    # ── Everything below is outside the lock ──────────────────────────────

    if song is None:
        # Autoplay: find related Kurdish song
        if do_autoplay and last_song:
            try:
                res = await search_songs(
                    f"{last_song.uploader} kurdish song", kurdish_mode=True, force_kurdish=True
                )
                if not res:
                    res = await search_songs("kurdish music 2024", kurdish_mode=True, force_kurdish=True)
                if res:
                    get_player(guild_id).queue.append(Song(res[0], bot.user, "youtube"))
                    await play_next(guild_id, text_channel, vc)
                    return
            except Exception as e:
                log.error(f"Autoplay error: {e}")

        # Leave after 5 min idle (unless 24/7 enabled)
        if not do_tfs:
            try:
                await asyncio.sleep(300)
            except asyncio.CancelledError:
                return
            p2 = get_player(guild_id)
            if not p2.current and not p2.queue and vc.is_connected():
                real_members = [m for m in vc.channel.members if not m.bot]
                if not real_members:
                    try:
                        vc.stop()
                        await vc.disconnect()
                    except Exception:
                        pass
                    destroy_player(guild_id)
                    if text_channel:
                        try:
                            await text_channel.send(embed=make_embed(C_LUNA, "👋 Left voice (idle 5 min)."))
                        except Exception:
                            pass
        return

    # We have a song — acquire lock briefly to update state
    async with player._lock:
        if not vc or not vc.is_connected():
            return
        # Push previous song to history
        if player.current and player.current is not song:
            push_history(
                guild_id, player.current.title, player.current.url,
                player.current.dur_str, str(player.current.requester),
                player.current.platform,
            )
            player.history.append(player.current)
            if len(player.history) > 20:
                player.history.pop(0)
        player.current    = song
        player.skip_votes.clear()

    # Extract stream URL (outside lock — can take time)
    if not song.stream_url or song.stream_url == song.url:
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
        song.stream_url = data["url"]
        if not song.thumbnail and data.get("thumbnail"):
            song.thumbnail = data["thumbnail"]
        if (song.title in ("Unknown", "") or not song.title) and data.get("title"):
            song.title = data["title"]
        if (song.uploader in ("Unknown", "") or not song.uploader) and data.get("uploader"):
            song.uploader = data["uploader"]
        if not song.duration and data.get("duration"):
            song.duration = data["duration"]

    source = create_ffmpeg_source(song.stream_url, player.volume, player.filter_name)
    if not source:
        if text_channel:
            try:
                await text_channel.send(embed=err_embed(f"Skipping **{song.title[:50]}** — audio error."))
            except Exception:
                pass
        player._playing = False
        await play_next(guild_id, text_channel, vc)
        return

    player.reset_timer()
    player._playing = True

    def after_callback(error):
        if error:
            log.error(f"Playback error: {error}")
        # Skip queue advancement if a filter swap is managing its own restart
        if get_player(guild_id)._filter_swap:
            return
        future = asyncio.run_coroutine_threadsafe(
            play_next(guild_id, text_channel, vc), bot.loop
        )
        future.add_done_callback(lambda f: f.exception() if f.exception() else None)

    try:
        vc.play(source, after=after_callback)
    except Exception as e:
        log.error(f"vc.play failed: {e}")
        player._playing = False
        return

    # Send / update Now Playing embed
    if text_channel:
        try:
            np_embed = build_np_embed(player, vc)
            np_view  = NowPlayingView(player, vc)
            if player.np_msg:
                try:
                    await player.np_msg.edit(embed=np_embed, view=np_view)
                except Exception:
                    player.np_msg = await text_channel.send(embed=np_embed, view=np_view)
            else:
                player.np_msg = await text_channel.send(embed=np_embed, view=np_view)
        except Exception as e:
            log.debug(f"NP embed update failed: {e}")


async def start_playback(ctx):
    vc = ctx.voice_client
    if not vc:
        return
    if not get_player(ctx.guild.id)._playing:
        await play_next(ctx.guild.id, ctx.channel, vc)


async def ensure_voice(ctx):
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send(embed=err_embed("Join a voice channel first!"))
        return None
    target = ctx.author.voice.channel
    if not target.permissions_for(ctx.me).connect:
        await ctx.send(embed=err_embed("I don't have permission to join that channel!"))
        return None
    if not target.permissions_for(ctx.me).speak:
        await ctx.send(embed=err_embed("I don't have permission to speak in that channel!"))
        return None
    vc = ctx.voice_client
    try:
        if not vc:
            vc = await target.connect(timeout=15)
        elif vc.channel != target:
            await vc.move_to(target)
        return vc
    except asyncio.TimeoutError:
        await ctx.send(embed=err_embed("Timed out connecting to voice channel."))
        return None
    except Exception as e:
        log.error(f"Voice connect error: {e}")
        await ctx.send(embed=err_embed("Failed to connect to voice channel."))
        return None


async def check_dj(ctx) -> bool:
    if ctx.author.guild_permissions.manage_guild:
        return True
    settings = get_settings(ctx.guild.id)
    dj_id    = settings.get("dj_role_id")
    if dj_id:
        role = ctx.guild.get_role(int(dj_id))
        if role and role in ctx.author.roles:
            return True
        name = role.name if role else str(dj_id)
        await ctx.send(embed=err_embed(f"You need the **{name}** DJ role!"))
        return False
    return True

# ═══════════════════════════════════════
#  COMMANDS — VOICE
# ═══════════════════════════════════════
@bot.command(aliases=["j"])
async def join(ctx):
    vc = await ensure_voice(ctx)
    if vc:
        await ctx.send(embed=ok_embed(f"Joined **{vc.channel.name}**!"))


@bot.command(aliases=["dc", "leave"])
async def disconnect(ctx):
    if not ctx.voice_client:
        return await ctx.send(embed=err_embed("I'm not in a voice channel!"))
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

# ═══════════════════════════════════════
#  COMMANDS — PLAYBACK
# ═══════════════════════════════════════
@bot.command(aliases=["p"])
async def play(ctx, *, query: str = ""):
    if not query.strip():
        return await ctx.send(embed=err_embed("Provide a song name or URL!\nExample: `$play Despacito` or paste a Spotify/YouTube link."))
    vc = await ensure_voice(ctx)
    if not vc:
        return

    player     = get_player(ctx.guild.id)
    is_url     = query.strip().startswith(("http://", "https://"))
    platform   = detect_platform(query) if is_url else "youtube"
    plat_emoji = PLATFORM_EMOJIS.get(platform, "🔍")

    msg = await ctx.send(embed=make_embed(C_LUNA, f"{plat_emoji} Processing **{query[:80]}**..."))

    try:
        if is_url:
            data = await instant_extract(query)
            if not data or not data.get("url"):
                return await msg.edit(embed=err_embed(
                    "Couldn't extract audio from this URL.\n"
                    "Make sure it's a valid public link."
                ))
            song = Song(data, ctx.author, platform)
            player.queue.append(song)
        else:
            results = await search_songs(query, kurdish_mode=player.kurdish_mode)
            if not results:
                return await msg.edit(embed=err_embed("No results found! Try different keywords."))
            # Extract the actual stream URL
            data = await instant_extract(results[0]["webpage_url"])
            if not data or not data.get("url"):
                return await msg.edit(embed=err_embed("Couldn't load that song. Try another."))
            song = Song(data, ctx.author, "youtube")
            # Merge search metadata (thumbnail, title)
            if not song.thumbnail and results[0].get("thumbnail"):
                song.thumbnail = results[0]["thumbnail"]
            song.is_kurdish = is_kurdish(song.title)

        if vc.is_playing() or vc.is_paused():
            em = discord.Embed(color=C_LUNA)
            em.title       = f"{plat_emoji} Added to Queue"
            em.description = f"**[{song.title[:200]}]({song.url})**"
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


@bot.command(aliases=["search", "sr"])
async def find(ctx, *, query: str = ""):
    """Search and pick a song from results."""
    if not query.strip():
        return await ctx.send(embed=err_embed("Provide a search query!"))
    vc = await ensure_voice(ctx)
    if not vc:
        return

    msg     = await ctx.send(embed=make_embed(C_LUNA, f"🔍 Searching **{query[:80]}**..."))
    results = await search_songs(query, kurdish_mode=False)

    if not results:
        return await msg.edit(embed=err_embed("No results found!"))

    lines = [
        f"`{i+1}.` **{r['title'][:70]}** `{format_time(r.get('duration', 0))}` — {r.get('uploader','')[:30]}"
        for i, r in enumerate(results)
    ]
    em = discord.Embed(color=C_LUNA, title="🔍 Search Results", description="\n".join(lines))
    em.set_footer(text="Type the number (1–5) to play, or 'cancel'")
    await msg.edit(embed=em)

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    try:
        reply = await bot.wait_for("message", timeout=30.0, check=check)
    except asyncio.TimeoutError:
        return await ctx.send(embed=err_embed("Timed out — search cancelled."), delete_after=5)

    if reply.content.lower() in ("cancel", "c"):
        return await ctx.send(embed=make_embed(C_LUNA, "Search cancelled."), delete_after=3)

    try:
        choice = int(reply.content.strip())
        if not 1 <= choice <= len(results):
            raise ValueError
    except ValueError:
        return await ctx.send(embed=err_embed("Invalid choice."), delete_after=5)

    selected = results[choice - 1]
    msg2     = await ctx.send(embed=make_embed(C_LUNA, f"▶️ Loading **{selected['title'][:80]}**..."))
    data     = await instant_extract(selected["webpage_url"])

    if not data or not data.get("url"):
        return await msg2.edit(embed=err_embed("Couldn't load that song."))

    player = get_player(ctx.guild.id)
    song   = Song(data, ctx.author, "youtube")
    if not song.thumbnail and selected.get("thumbnail"):
        song.thumbnail = selected["thumbnail"]
    player.queue.append(song)

    if vc.is_playing() or vc.is_paused():
        em = discord.Embed(color=C_LUNA)
        em.title       = "➕ Added to Queue"
        em.description = f"**[{song.title}]({song.url})**"
        em.add_field(name="Duration", value=song.dur_str, inline=True)
        em.add_field(name="Position", value=f"#{len(player.queue)}", inline=True)
        if song.thumbnail and song.thumbnail.startswith("http"):
            em.set_thumbnail(url=song.thumbnail)
        await msg2.edit(embed=em)
    else:
        try:
            await msg2.delete()
        except Exception:
            pass
    await start_playback(ctx)


@bot.command(aliases=["kp", "kurdish", "ku"])
async def kurdishplay(ctx, *, query: str = ""):
    """Find and play a Kurdish version of a song."""
    if not query.strip():
        return await ctx.send(embed=err_embed("Provide a song name!\nExample: `$kurdish Gangnam Style`"))
    vc = await ensure_voice(ctx)
    if not vc:
        return

    msg = await ctx.send(embed=make_embed(C_LUNA, f"🟢 Finding Kurdish: **{query[:80]}**..."))
    try:
        results = await search_songs(query, kurdish_mode=True, force_kurdish=True)
        if not results:
            return await msg.edit(embed=err_embed("No Kurdish version found. Try different keywords."))

        data = await instant_extract(results[0]["webpage_url"])
        if not data or not data.get("url"):
            return await msg.edit(embed=err_embed("Couldn't load that song."))

        song = Song(data, ctx.author, "youtube")
        if not song.thumbnail and results[0].get("thumbnail"):
            song.thumbnail = results[0]["thumbnail"]
        song.is_kurdish = True

        player = get_player(ctx.guild.id)
        player.queue.append(song)

        em = discord.Embed(color=C_LUNA)
        em.title       = "🟢 Kurdish Song Added!"
        em.description = f"**[{song.title}]({song.url})**"
        em.add_field(name="Duration", value=song.dur_str,   inline=True)
        em.add_field(name="Channel",  value=song.uploader[:50], inline=True)
        if song.thumbnail and song.thumbnail.startswith("http"):
            em.set_thumbnail(url=song.thumbnail)
        await msg.edit(embed=em)

    except Exception as e:
        log.error(f"kurdishplay error: {e}")
        return await msg.edit(embed=err_embed(str(e)[:150]))
    await start_playback(ctx)


@bot.command(aliases=["pa"])
async def pause(ctx):
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
async def resume(ctx):
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
async def skip(ctx):
    vc = ctx.voice_client
    if not vc or (not vc.is_playing() and not vc.is_paused()):
        return await ctx.send(embed=err_embed("Nothing is playing!"))
    player   = get_player(ctx.guild.id)
    is_dj    = ctx.author.guild_permissions.manage_guild
    settings = get_settings(ctx.guild.id)
    dj_id    = settings.get("dj_role_id")
    has_role = False
    if dj_id:
        dj_role  = ctx.guild.get_role(int(dj_id))
        has_role = bool(dj_role and dj_role in ctx.author.roles)

    if is_dj or has_role or ctx.author == player.current.requester:
        player.skip_votes.clear()
        vc.stop()
        return await ctx.send(embed=ok_embed("⏭️ Skipped!"))

    # Voter must be in the same voice channel
    if not ctx.author.voice or ctx.author.voice.channel != vc.channel:
        return await ctx.send(embed=err_embed("You must be in the same voice channel to vote skip!"))

    members = [m for m in vc.channel.members if not m.bot]
    if not members:
        player.skip_votes.clear()
        vc.stop()
        return await ctx.send(embed=ok_embed("⏭️ Skipped!"))

    needed = max(1, math.ceil(len(members) * 0.5))
    player.skip_votes.add(ctx.author.id)
    votes = len(player.skip_votes)
    if votes >= needed:
        player.skip_votes.clear()
        vc.stop()
        await ctx.send(embed=ok_embed(f"⏭️ Vote passed ({votes}/{needed})!"))
    else:
        await ctx.send(embed=make_embed(
            C_YELLOW, f"🗳️ Vote skip: **{votes}/{needed}** — need {needed - votes} more."
        ))


@bot.command()
async def stop(ctx):
    if not await check_dj(ctx):
        return
    vc = ctx.voice_client
    if not vc:
        return await ctx.send(embed=err_embed("I'm not in a voice channel!"))
    player = get_player(ctx.guild.id)
    player.queue.clear()
    player.loop = "off"
    vc.stop()
    await ctx.send(embed=ok_embed("⏹️ Stopped and queue cleared!"))


@bot.command(aliases=["np"])
async def nowplaying(ctx):
    vc = ctx.voice_client
    if not vc:
        return await ctx.send(embed=err_embed("I'm not in a voice channel!"))
    player = get_player(ctx.guild.id)
    if not player.current:
        return await ctx.send(embed=err_embed("Nothing is playing!"))
    try:
        player.np_msg = await ctx.send(embed=build_np_embed(player, vc), view=NowPlayingView(player, vc))
    except Exception as e:
        log.error(f"nowplaying embed error: {e}")


@bot.command(aliases=["replay", "restart"])
async def again(ctx):
    vc = ctx.voice_client
    if not vc or (not vc.is_playing() and not vc.is_paused()):
        return await ctx.send(embed=err_embed("Nothing is playing!"))
    if not await check_dj(ctx):
        return
    player = get_player(ctx.guild.id)
    if not player.current:
        return await ctx.send(embed=err_embed("Nothing to replay!"))
    player.queue.insert(0, player.current)
    vc.stop()
    await ctx.send(embed=ok_embed("🔁 Replaying current song!"))

# ═══════════════════════════════════════
#  COMMANDS — QUEUE
# ═══════════════════════════════════════
@bot.command(aliases=["q"])
async def queue(ctx, page: int = 1):
    player = get_player(ctx.guild.id)
    if not player.current and not player.queue:
        return await ctx.send(embed=make_embed(C_LUNA, "📋 Queue is empty. Use `$play` to add songs!"))

    per_page = 10
    total    = len(player.queue)
    pages    = max(1, math.ceil(total / per_page))
    page     = max(1, min(page, pages))
    start    = (page - 1) * per_page
    chunk    = player.queue[start:start + per_page]

    desc = ""
    if player.current:
        k = " 🟢" if player.current.is_kurdish else ""
        desc += (
            f"**▶️ Now:** [{player.current.title[:60]}]({player.current.url})"
            f" `{player.current.dur_str}` — {player.current.requester.mention}{k}\n\n"
        )
    if chunk:
        desc += "**📋 Up Next:**\n"
        for i, s in enumerate(chunk, start=start + 1):
            k = " 🟢" if s.is_kurdish else ""
            desc += f"`{i}.` [{s.title[:50]}]({s.url}) `{s.dur_str}` — {s.requester.mention}{k}\n"

    total_dur  = sum(s.duration or 0 for s in player.queue)
    loop_modes = {"off": "➡️ Off", "track": "🔂 Track", "queue": "🔁 Queue"}
    em         = discord.Embed(color=C_LUNA, title=f"📋 Queue — {total} songs", description=desc)
    em.set_footer(
        text=f"Page {page}/{pages} • Total: {format_time(total_dur)} • "
             f"Loop: {loop_modes.get(player.loop,'➡️ Off')} • 🟢 = Kurdish"
    )
    await ctx.send(embed=em)


@bot.command(aliases=["rm"])
async def remove(ctx, index: int):
    if not await check_dj(ctx):
        return
    player = get_player(ctx.guild.id)
    if index < 1 or index > len(player.queue):
        return await ctx.send(embed=err_embed(f"Invalid index! Queue has {len(player.queue)} songs."))
    removed = player.queue.pop(index - 1)
    await ctx.send(embed=ok_embed(f"Removed **{removed.title[:50]}**"))


@bot.command()
async def clear(ctx):
    if not await check_dj(ctx):
        return
    get_player(ctx.guild.id).queue.clear()
    await ctx.send(embed=ok_embed("Queue cleared!"))


@bot.command(aliases=["sh"])
async def shuffle(ctx):
    if not await check_dj(ctx):
        return
    player = get_player(ctx.guild.id)
    if len(player.queue) < 2:
        return await ctx.send(embed=err_embed("Need at least 2 songs to shuffle!"))
    random.shuffle(player.queue)
    await ctx.send(embed=ok_embed("🔀 Queue shuffled!"))


@bot.command()
async def skipto(ctx, index: int):
    if not await check_dj(ctx):
        return
    vc = ctx.voice_client
    if not vc:
        return await ctx.send(embed=err_embed("Nothing is playing!"))
    player = get_player(ctx.guild.id)
    if index < 1 or index > len(player.queue):
        return await ctx.send(embed=err_embed(f"Invalid index! Queue has {len(player.queue)} songs."))
    player.queue = player.queue[index - 1:]
    vc.stop()
    await ctx.send(embed=ok_embed(f"⏭️ Jumped to position **{index}**!"))

# ═══════════════════════════════════════
#  COMMANDS — SETTINGS
# ═══════════════════════════════════════
@bot.command(aliases=["vol"])
async def volume(ctx, vol: int):
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
async def loop(ctx, mode: str = None):
    if not await check_dj(ctx):
        return
    player = get_player(ctx.guild.id)  # FIX: was ctx.id (wrong attribute)
    modes  = ["off", "track", "queue"]
    if mode is None:
        mode = modes[(modes.index(player.loop) + 1) % 3]
    else:
        mode = mode.lower()
    if mode not in modes:
        return await ctx.send(embed=err_embed("Loop mode must be: `off` / `track` / `queue`"))
    player.loop = mode
    save_settings(ctx.guild.id, loop_mode=mode)
    icons = {"off": "➡️", "track": "🔂", "queue": "🔁"}
    await ctx.send(embed=ok_embed(f"{icons[mode]} Loop set to **{mode.title()}**"))


@bot.command(aliases=["filter"])
async def setfilter(ctx, name: str = None):
    if not await check_dj(ctx):
        return
    if name is None:
        lines = [f"`{k}` — {v['label']}" for k, v in FILTERS.items()]
        em = discord.Embed(color=C_LUNA, title="🎛️ Available Filters", description="\n".join(lines))
        em.set_footer(text="Use: $filter <name>")
        return await ctx.send(embed=em)

    name = name.lower()
    if name not in FILTERS:
        return await ctx.send(embed=err_embed(f"Unknown filter `{name}`! Use `$filter` to see all filters."))

    player      = get_player(ctx.guild.id)
    old_filter  = player.filter_name
    player.filter_name = name
    vc          = ctx.voice_client

    if vc and (vc.is_playing() or vc.is_paused()) and player.current:
        was_paused = vc.is_paused()
        paused_pos = player.elapsed()
        # Set flag BEFORE stopping so after_callback skips queue advancement
        player._filter_swap = True
        try:
            vc.stop()
        except Exception:
            pass
        await asyncio.sleep(0.5)

        data = await instant_extract(player.current.url)
        if data and data.get("url"):
            player.current.stream_url = data["url"]
            source = create_ffmpeg_source(player.current.stream_url, player.volume, name)
            if source:
                player.reset_timer()
                player._playing = True
                def after_cb(err):
                    if err:
                        log.error(f"Filter after: {err}")
                    # Clear filter_swap flag then resume normal queue
                    p = get_player(ctx.guild.id)
                    p._filter_swap = False
                    fut = asyncio.run_coroutine_threadsafe(
                        play_next(ctx.guild.id, ctx.channel, vc), bot.loop
                    )
                    fut.add_done_callback(lambda f: f.exception() if f.exception() else None)
                try:
                    vc.play(source, after=after_cb)
                    if was_paused:
                        vc.pause()
                        player._elapsed_pre = paused_pos
                        player._paused_at   = time.time()
                except Exception as e:
                    player._filter_swap = False
                    player.filter_name  = old_filter
                    return await ctx.send(embed=err_embed(f"Failed to apply filter: {e}"))
            else:
                player._filter_swap = False
                player.filter_name  = old_filter
                return await ctx.send(embed=err_embed("Stream failed."))
        else:
            player._filter_swap = False
            player.filter_name  = old_filter
            return await ctx.send(embed=err_embed("Couldn't reload stream."))

    await ctx.send(embed=ok_embed(f"🎛️ Filter set to **{FILTERS[name]['label']}**"))


@bot.command(name="247")
async def tfs_cmd(ctx):
    if not await check_dj(ctx):
        return
    player      = get_player(ctx.guild.id)
    player.tfs  = not player.tfs
    save_settings(ctx.guild.id, tfs=int(player.tfs))
    state = "enabled 🟢" if player.tfs else "disabled 🔴"
    await ctx.send(embed=ok_embed(f"24/7 mode {state}"))


@bot.command()
async def autoplay(ctx):
    if not await check_dj(ctx):
        return
    player          = get_player(ctx.guild.id)
    player.autoplay = not player.autoplay
    save_settings(ctx.guild.id, autoplay=int(player.autoplay))
    state = "enabled 🟢" if player.autoplay else "disabled 🔴"
    await ctx.send(embed=ok_embed(f"Autoplay {state}"))


@bot.command()
async def kurdishmode(ctx):
    player              = get_player(ctx.guild.id)
    player.kurdish_mode = not player.kurdish_mode
    save_settings(ctx.guild.id, kurdish_mode=int(player.kurdish_mode))
    state = "enabled 🟢" if player.kurdish_mode else "disabled 🔴"
    await ctx.send(embed=ok_embed(f"Kurdish mode {state}"))


@bot.command(aliases=["setdj"])
@commands.has_permissions(manage_guild=True)
async def djrole(ctx, role: discord.Role = None):
    if not role:
        save_settings(ctx.guild.id, dj_role_id=None)
        return await ctx.send(embed=ok_embed("DJ role removed — everyone can control music now."))
    save_settings(ctx.guild.id, dj_role_id=role.id)
    await ctx.send(embed=ok_embed(f"DJ role set to {role.mention}"))

# ═══════════════════════════════════════
#  COMMANDS — INFO / UTILS
# ═══════════════════════════════════════
@bot.command(aliases=["ly"])
async def lyrics(ctx, *, song_name: str = ""):
    player = get_player(ctx.guild.id)
    if not song_name.strip():
        if not player.current:
            return await ctx.send(embed=err_embed("Nothing is playing! Use: `$lyrics Artist - Song Title`"))
        song_name = player.current.title

    clean = song_name
    for pat in ["(official", "(lyrics", "(audio)", "(video)", "(hd)", "(4k)", "[", "]", "ft.", "feat."]:
        idx = clean.lower().find(pat)
        if idx != -1:
            clean = clean[:idx].strip()

    parts = clean.split(" - ", 1)
    if len(parts) == 2:
        artist, title_q = parts[0].strip(), parts[1].strip()
    else:
        artist, title_q = "", clean.strip()

    if not title_q:
        return await ctx.send(embed=err_embed("Use: `$lyrics Artist - Song Title`"))

    msg         = await ctx.send(embed=make_embed(C_LUNA, f"🔍 Fetching lyrics for **{clean[:60]}**..."))
    lyrics_text = None

    pairs = [(artist, title_q), (artist, clean), (clean, clean)]
    for a, t in pairs:
        if not a or not t:
            continue
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"https://api.lyrics.ovh/v1/{a}/{t}",
                    timeout=aiohttp.ClientTimeout(total=6)
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
    chunks      = [lyrics_text[i:i+3800] for i in range(0, len(lyrics_text), 3800)]
    for i, c in enumerate(chunks):
        suffix = f" (Part {i+1})" if len(chunks) > 1 else ""
        em     = discord.Embed(color=C_LUNA, title=f"📜 {clean[:60]}{suffix}", description=c)
        if i == 0:
            await msg.edit(embed=em)
        else:
            try:
                await ctx.send(embed=em)
            except Exception:
                pass


@bot.command()
async def history(ctx):
    try:
        conn = _db()
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT title,url,duration,platform FROM history WHERE guild_id=? ORDER BY id DESC LIMIT 10",
            (ctx.guild.id,)
        ).fetchall()
        conn.close()
    except Exception:
        return await ctx.send(embed=err_embed("Database error."))

    if not rows:
        return await ctx.send(embed=make_embed(C_LUNA, "📜 No listening history yet."))

    lines = []
    for i, r in enumerate(rows):
        plat   = r["platform"] or "unknown"
        k_flag = " 🟢" if is_kurdish(r["title"]) else ""
        emoji  = PLATFORM_EMOJIS.get(plat, "🎵")
        lines.append(f"`{i+1}.` {emoji} [{r['title'][:55]}]({r['url']}) `{r['duration']}`{k_flag}")

    em = discord.Embed(color=C_LUNA, title="📜 Recent History", description="\n".join(lines))
    await ctx.send(embed=em)


@bot.command()
async def grab(ctx):
    player = get_player(ctx.guild.id)
    if not player.current:
        return await ctx.send(embed=err_embed("Nothing is playing!"))
    song = player.current
    em   = discord.Embed(color=C_LUNA, title="❤️ Saved to DMs!",
                         description=f"**[{song.title}]({song.url})**")
    em.add_field(name="Duration", value=song.dur_str, inline=True)
    em.add_field(name="Platform", value=song.platform.replace("_", " ").title(), inline=True)
    if song.is_kurdish:
        em.add_field(name="Type", value="🟢 Kurdish", inline=True)
    if song.thumbnail and song.thumbnail.startswith("http"):
        em.set_thumbnail(url=song.thumbnail)
    try:
        await ctx.author.send(embed=em)
        await ctx.send(embed=ok_embed("Sent to your DMs! ❤️"))
    except discord.Forbidden:
        await ctx.send(embed=err_embed("I can't DM you — enable DMs from server members."))
    except Exception:
        pass


@bot.command()
async def ping(ctx):
    await ctx.send(embed=make_embed(C_LUNA, f"🏓 Pong! **{round(bot.latency * 1000)}ms**"))


@bot.command(aliases=["stats"])
async def botinfo(ctx):
    uptime        = int(time.time() - bot_start_time)
    hours, rem    = divmod(uptime, 3600)
    mins, secs    = divmod(rem, 60)
    active_guilds = sum(1 for g in bot.guilds if g.voice_client)

    em = discord.Embed(color=C_LUNA, title="🎵 Veltra Music Bot")
    em.add_field(name="Prefix",        value="`$`",                        inline=True)
    em.add_field(name="Servers",       value=str(len(bot.guilds)),         inline=True)
    em.add_field(name="Active VCs",    value=str(active_guilds),           inline=True)
    em.add_field(name="Uptime",        value=f"{hours}h {mins}m {secs}s", inline=True)
    em.add_field(name="Ping",          value=f"{round(bot.latency*1000)}ms", inline=True)
    em.add_field(name="Engine",        value="yt-dlp + Cobalt",           inline=True)
    em.add_field(
        name="Platforms",
        value="YouTube · Spotify · Apple Music · SoundCloud · Deezer · "
              "Anghami · Facebook · Twitch · Vimeo · Direct MP3/MP4",
        inline=False,
    )
    em.add_field(name="Kurdish Mode", value="🟢 Full Support", inline=False)
    await ctx.send(embed=em)


@bot.command()
async def help(ctx):
    em = discord.Embed(color=C_LUNA, title="🎵 Veltra Music Bot — Full Help")
    em.description = (
        "**Prefix: `$`** | Works just like Lara Bot!\n"
        "Paste any link or type a song name to play instantly. 🟢 = Kurdish song"
    )
    em.add_field(
        name="🔗 Direct URL Playback",
        value=(
            "```"
            "Spotify      open.spotify.com/track/...\n"
            "Apple Music  music.apple.com/...\n"
            "SoundCloud   soundcloud.com/...\n"
            "Deezer       deezer.com/...\n"
            "Anghami      anghami.com/...\n"
            "Facebook     facebook.com/watch/...\n"
            "Twitch       twitch.tv/...\n"
            "YouTube      youtube.com/watch?v=...\n"
            "Direct       example.com/song.mp3"
            "```"
        ),
        inline=False,
    )
    em.add_field(
        name="🔍 Search & Playback",
        value=(
            "```"
            "$play <song/URL>      Play song or URL\n"
            "$find <query>         Search & pick from list\n"
            "$kurdish <song>       Find Kurdish version\n"
            "$np                   Now Playing panel\n"
            "$pause / $resume      Pause / Resume\n"
            "$skip / $skipto <n>   Skip / Jump to #\n"
            "$stop                 Stop & clear queue\n"
            "$queue [page]         Show queue\n"
            "$again                Replay current song\n"
            "$grab                 Save song to DMs\n"
            "$lyrics [Artist-Song] Show lyrics"
            "```"
        ),
        inline=False,
    )
    em.add_field(
        name="⚙️ Settings",
        value=(
            "```"
            "$volume <0-200>         Volume\n"
            "$loop [off/track/queue] Loop mode\n"
            "$filter [name]          Audio filter\n"
            "$shuffle                Shuffle queue\n"
            "$remove <n>             Remove from queue\n"
            "$clear                  Clear queue\n"
            "$247                    24/7 stay in VC\n"
            "$autoplay               Auto-play related\n"
            "$kurdishmode            Toggle Kurdish search\n"
            "$djrole [@role]         Set DJ role\n"
            "$history                Recent songs\n"
            "$botinfo                Bot statistics\n"
            "$ping                   Latency check"
            "```"
        ),
        inline=False,
    )
    em.add_field(
        name="🎛️ Audio Filters",
        value="`none` `bassboost` `nightcore` `vaporwave` `8d` `karaoke` `tremolo` `vibrato` `superbass` `soft` `earrape` `pitch`",
        inline=False,
    )
    em.set_footer(text="Just paste a link and it plays instantly! | $help")
    await ctx.send(embed=em)

# ═══════════════════════════════════════
#  EVENTS
# ═══════════════════════════════════════
@bot.event
async def on_ready():
    log.info(f"Logged in as: {bot.user} (ID: {bot.user.id})")
    log.info(f"Connected to {len(bot.guilds)} guild(s)")
    log.info("★ VELTRA MULTI-PLATFORM ENGINE ACTIVE ★")
    try:
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name="🎵 Multi-Platform | $help"
            )
        )
    except Exception:
        pass


@bot.event
async def on_voice_state_update(member: discord.Member, before, after):
    if member.bot:
        return
    if before.channel and not after.channel:
        vc = before.channel.guild.voice_client
        if vc and vc.channel == before.channel:
            real_members = [m for m in vc.channel.members if not m.bot]
            if not real_members:
                player = get_player(vc.guild.id)
                if not player.tfs:
                    await asyncio.sleep(3)
                    if not [m for m in vc.channel.members if not m.bot] and vc.is_connected():
                        player.queue.clear()
                        try:
                            vc.stop()
                            await vc.disconnect()
                        except Exception:
                            pass
                        destroy_player(vc.guild.id)


@bot.event
async def on_command_error(ctx, error):
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
            await ctx.send(embed=err_embed(f"Bad argument: {error}"))
        except Exception:
            pass
        return
    log.error(f"Command [{ctx.command}] error:\n{traceback.format_exc()}")
    try:
        await ctx.send(embed=err_embed(str(error)[:150]))
    except Exception:
        pass


# ═══════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════
if __name__ == "__main__":
    log.info("Starting Veltra Music Bot...")
    try:
        bot.run(TOKEN, log_handler=None)
    except discord.LoginFailure:
        log.error("FATAL: Invalid Discord token! Check your .env file.")
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log.error(f"FATAL: {e}\n{traceback.format_exc()}")
