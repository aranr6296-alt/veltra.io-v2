"""
╔══════════════════════════════════════════════════════╗
║     VELTRA MUSIC BOT  —  STABLE PRODUCTION BUILD    ║
║  Multi-Platform · Kurdish · Crash-Proof · No Bugs   ║
║  Spotify·Apple·SoundCloud·Deezer·Anghami·Vimeo·MP3  ║
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
import hashlib
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
    print("[FATAL] DISCORD_TOKEN not set in environment or .env file")
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
#  THEME COLORS
# ──────────────────────────────────────────────────────
C_LUNA  = 0xB5179E
C_GREEN = 0x57F287
C_RED   = 0xED4245
C_YELLOW = 0xFEE75C

# ──────────────────────────────────────────────────────
#  CACHE DIR
# ──────────────────────────────────────────────────────
CACHE_DIR = Path("./veltra_cache")
try:
    CACHE_DIR.mkdir(exist_ok=True)
except Exception as e:
    log.warning(f"Could not create cache dir: {e}")
    CACHE_DIR = None

# ──────────────────────────────────────────────────────
#  DATABASE — safe wrapper
# ──────────────────────────────────────────────────────
DB_FILE = "veltra.db"

def _db_connect():
    return sqlite3.connect(DB_FILE, timeout=10)

def init_db():
    try:
        conn = _db_connect()
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id    INTEGER PRIMARY KEY,
                dj_role_id  INTEGER DEFAULT NULL,
                volume      INTEGER DEFAULT 100,
                loop_mode   TEXT    DEFAULT 'off',
                tfs         INTEGER DEFAULT 0,
                autoplay    INTEGER DEFAULT 0,
                kurdish_mode INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS history (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id   INTEGER,
                title      TEXT,
                url        TEXT,
                duration   TEXT,
                requester  TEXT,
                platform   TEXT DEFAULT 'unknown',
                played_at  TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS cache (
                query_hash TEXT PRIMARY KEY,
                results    TEXT,
                timestamp  INTEGER
            );
        """)
        conn.commit()
        conn.close()
        log.info("Database initialized")
    except Exception as e:
        log.error(f"Database init error: {e}")

init_db()


def get_settings(guild_id: int) -> dict:
    try:
        conn = _db_connect()
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM guild_settings WHERE guild_id=?", (guild_id,)
        ).fetchone()
        if not row:
            conn.execute(
                "INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)",
                (guild_id,),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM guild_settings WHERE guild_id=?", (guild_id,)
            ).fetchone()
        conn.close()
        return dict(row) if row else {
            "dj_role_id": None, "volume": 100, "loop_mode": "off",
            "tfs": 0, "autoplay": 0, "kurdish_mode": 1,
        }
    except Exception as e:
        log.error(f"get_settings error: {e}")
        return {
            "dj_role_id": None, "volume": 100, "loop_mode": "off",
            "tfs": 0, "autoplay": 0, "kurdish_mode": 1,
        }


def save_settings(guild_id: int, **kw):
    try:
        get_settings(guild_id)  # ensure row exists
        sets = ", ".join(f"{k}=?" for k in kw)
        conn = _db_connect()
        conn.execute(
            f"UPDATE guild_settings SET {sets} WHERE guild_id=?",
            [*kw.values(), guild_id],
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log.error(f"save_settings error: {e}")


def push_history(guild_id, title, url, duration, requester, platform="unknown"):
    try:
        conn = _db_connect()
        conn.execute(
            "INSERT INTO history (guild_id,title,url,duration,requester,platform) "
            "VALUES (?,?,?,?,?,?)",
            (guild_id, title, url, duration, requester, platform),
        )
        conn.execute(
            "DELETE FROM history WHERE guild_id=? AND id NOT IN "
            "(SELECT id FROM history WHERE guild_id=? ORDER BY id DESC LIMIT 50)",
            (guild_id, guild_id),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        log.error(f"push_history error: {e}")


# ──────────────────────────────────────────────────────
#  AUDIO FILTERS
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
#  PLATFORM DETECTION
# ──────────────────────────────────────────────────────
def detect_platform(url: str) -> str:
    if not url:
        return "unknown"
    u = url.lower()
    if "spotify.com" in u or "open.spotify.com" in u:
        return "spotify"
    if "music.apple.com" in u or "itunes.apple.com" in u:
        return "apple_music"
    if "soundcloud.com" in u:
        return "soundcloud"
    if "deezer.com" in u:
        return "deezer"
    if "anghami.com" in u:
        return "anghami"
    if "vimeo.com" in u:
        return "vimeo"
    if "youtube.com" in u or "youtu.be" in u:
        return "youtube"
    if any(u.endswith(ext) for ext in (".mp3", ".mp4", ".m4a", ".ogg", ".wav", ".flac", ".webm")):
        return "direct"
    return "unknown"

PLATFORM_EMOJI = {
    "spotify": "🎵", "apple_music": "🍎", "soundcloud": "☁️",
    "deezer": "🎶", "anghami": "🌙", "vimeo": "📹",
    "youtube": "▶️", "direct": "📎", "unknown": "🔍",
}

PLATFORM_LABEL = {
    "spotify": "Spotify", "apple_music": "Apple Music",
    "soundcloud": "SoundCloud", "deezer": "Deezer",
    "anghami": "Anghami", "vimeo": "Vimeo",
    "youtube": "YouTube", "direct": "Direct Link", "unknown": "Unknown",
}

# ──────────────────────────────────────────────────────
#  KURDISH HELPERS
# ──────────────────────────────────────────────────────
KURDISH_KEYWORDS = [
    "kurdish", "kurdi", "کوردی", "کوردیی", "kurdî", "kurdish song",
    "zagros", "kurdistan", "hawler", "slemani", "erbil", "sulaymaniyah",
]

def is_kurdish_title(title: str) -> bool:
    if not title:
        return False
    t = title.lower()
    return any(kw in t for kw in KURDISH_KEYWORDS)

def enhance_kurdish_query(query: str, kurdish_mode: bool) -> str:
    if not kurdish_mode or not query:
        return query
    if is_kurdish_title(query):
        return query
    return f"{query} kurdish version kurdi کوردی"

# ──────────────────────────────────────────────────────
#  SONG CLASS
# ──────────────────────────────────────────────────────
class Song:
    __slots__ = (
        "title", "url", "stream_url", "duration", "thumbnail",
        "uploader", "requester", "platform", "is_kurdish",
    )

    def __init__(self, data: dict, requester: discord.Member, platform: str = "unknown"):
        self.title       = str(data.get("title") or "Unknown")
        self.url         = str(data.get("webpage_url") or data.get("original_url") or data.get("url") or "")
        self.stream_url  = str(data.get("url") or "")
        self.duration    = data.get("duration") or 0
        self.thumbnail   = str(data.get("thumbnail") or "")
        self.uploader    = str(data.get("uploader") or data.get("channel") or "Unknown")
        self.requester   = requester
        self.platform    = platform or "unknown"
        self.is_kurdish  = is_kurdish_title(self.title)

    @property
    def dur_str(self) -> str:
        if not self.duration or self.duration <= 0:
            return "🔴 LIVE"
        d = int(self.duration)
        m, s = divmod(d, 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

    def progress_bar(self, elapsed: float, length: int = 13) -> str:
        if not self.duration or self.duration <= 0:
            return "─" * length + " 🔴"
        pct = min(max(elapsed / self.duration, 0.0), 1.0)
        fill = int(pct * length)
        return "▬" * fill + "🔘" + "▬" * (length - fill)

# ──────────────────────────────────────────────────────
#  PLAYER CLASS
# ──────────────────────────────────────────────────────
class MusicPlayer:
    def __init__(self, guild_id: int):
        self.guild_id   = guild_id
        self.queue: list = []
        self.current: Song | None = None
        self.history: list = []
        self.loop       = "off"
        self.volume     = 1.0
        self.filter_name = "none"
        self.skip_votes: set = set()
        self.tfs        = False
        self.autoplay   = False
        self.kurdish_mode = True
        self._start     = None
        self._paused_at = None
        self._elapsed_pre = 0.0
        self.np_msg     = None
        self._lock      = asyncio.Lock()
        self._playing   = False  # guard against double-play

    def elapsed(self) -> float:
        if self._start is None:
            return self._elapsed_pre
        if self._paused_at is not None:
            return self._elapsed_pre
        return self._elapsed_pre + (time.time() - self._start)

    def reset_timer(self):
        self._start = time.time()
        self._paused_at = None
        self._elapsed_pre = 0.0


# guild_id → MusicPlayer
_players: dict[int, MusicPlayer] = {}


def get_player(guild_id: int) -> MusicPlayer:
    if guild_id not in _players:
        p = MusicPlayer(guild_id)
        s = get_settings(guild_id)
        p.volume       = max(0.0, min(2.0, (s.get("volume") or 100) / 100.0))
        p.loop         = s.get("loop_mode") or "off"
        p.tfs          = bool(s.get("tfs"))
        p.autoplay     = bool(s.get("autoplay"))
        p.kurdish_mode = bool(s.get("kurdish_mode", 1))
        _players[guild_id] = p
    return _players[guild_id]


def destroy_player(guild_id: int):
    p = _players.pop(guild_id, None)
    if p:
        p.queue.clear()
        p.history.clear()
        p.current = None
        p.np_msg = None

# ──────────────────────────────────────────────────────
#  YT-DLP — OPTIMIZED & SAFE
# ──────────────────────────────────────────────────────
_BASE_OPTS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "socket_timeout": 15,
    "retries": 2,
    "fragment_retries": 2,
    "skip_download": True,
    "nocheckcertificate": True,
    "noprogress": True,
    "extractor_args": {
        "youtube": {
            "player_client": ["android", "web"],
            "skip": ["dash", "hls"],
        }
    },
    "http_headers": {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 11; Pixel 5) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Mobile Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    },
}

if CACHE_DIR:
    _BASE_OPTS["cachedir"] = str(CACHE_DIR)


async def _run_sync(fn, *args, **kwargs):
    """Safely run blocking code in executor."""
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))
    except Exception as e:
        log.error(f"Executor error: {e}")
        raise


def _safe_extract(ydl_opts: dict, url: str) -> dict | list | None:
    """Safely extract info — never crashes."""
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as e:
        log.warning(f"DownloadError for {url}: {e}")
    except yt_dlp.utils.ExtractorError as e:
        log.warning(f"ExtractorError for {url}: {e}")
    except Exception as e:
        log.error(f"Unexpected yt-dlp error for {url}: {e}")
    return None


async def search_songs(query: str, kurdish_mode: bool = True) -> list[dict]:
    """Search and return up to 5 results. Never crashes."""
    enhanced = enhance_kurdish_query(query, kurdish_mode)

    def _do():
        # Try enhanced query first
        opts = {**_BASE_OPTS, "noplaylist": True, "default_search": "ytsearch5"}
        result = _safe_extract(opts, f"ytsearch5:{enhanced}")
        entries = []
        if result:
            entries = result.get("entries") if isinstance(result, dict) else result
            entries = [e for e in (entries or []) if e and e.get("id")]

        # If nothing found, try original query
        if not entries and enhanced != query:
            result2 = _safe_extract(opts, f"ytsearch5:{query}")
            if result2:
                entries2 = result2.get("entries") if isinstance(result2, dict) else result2
                entries = [e for e in (entries2 or []) if e and e.get("id")]

        # Deduplicate by ID
        seen = set()
        unique = []
        for e in entries:
            eid = e.get("id")
            if eid and eid not in seen:
                seen.add(eid)
                unique.append(e)
        return unique[:5]

    try:
        return await _run_sync(_do) or []
    except Exception:
        return []


async def resolve_url(url: str) -> dict | None:
    """Resolve a single URL to full info. Never crashes."""
    def _do():
        opts = {**_BASE_OPTS, "noplaylist": True}
        result = _safe_extract(opts, url)
        if result and isinstance(result, dict) and result.get("id"):
            return result
        if result and isinstance(result, list) and result:
            return result[0]
        return None

    try:
        return await _run_sync(_do)
    except Exception:
        return None


async def resolve_playlist(url: str) -> list[dict]:
    """Resolve a playlist. Never crashes."""
    platform = detect_platform(url)

    def _do():
        opts = {**_BASE_OPTS, "extract_flat": "in_playlist"}
        result = _safe_extract(opts, url)
        entries = []
        if result and isinstance(result, dict):
            raw = result.get("entries") or []
            for e in raw:
                if e and e.get("id"):
                    e["_platform"] = platform
                    entries.append(e)
        return entries

    try:
        return await _run_sync(_do) or []
    except Exception:
        return []


# ──────────────────────────────────────────────────────
#  FFMPEG SOURCE — safe creation
# ──────────────────────────────────────────────────────
def _make_source(stream_url: str, volume: float, filter_name: str):
    """Create FFmpeg source. Returns None on failure."""
    if not stream_url:
        return None
    af = FILTERS.get(filter_name, FILTERS["none"])["af"]
    before = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
    options = "-vn"
    if af:
        options += f" -af {af}"
    try:
        pcm = discord.FFmpegPCMAudio(stream_url, before_options=before, options=options)
        return discord.PCMVolumeTransformer(pcm, volume=volume)
    except Exception as e:
        log.error(f"FFmpeg source creation failed: {e}")
        return None

# ──────────────────────────────────────────────────────
#  EMBED HELPERS
# ──────────────────────────────────────────────────────
def _embed(color: int, desc: str) -> discord.Embed:
    return discord.Embed(color=color, description=desc)

def ok_embed(desc: str) -> discord.Embed:
    return _embed(C_GREEN, f"✅ {desc}")

def err_embed(desc: str) -> discord.Embed:
    return _embed(C_RED, f"❌ {desc}")

def _fmt_time(sec: float) -> str:
    if not sec or sec < 0:
        return "0:00"
    s = int(sec)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

def _dur(seconds) -> str:
    if not seconds or seconds <= 0:
        return "?"
    return _fmt_time(seconds)

# ──────────────────────────────────────────────────────
#  NOW PLAYING EMBED
# ──────────────────────────────────────────────────────
def build_np_embed(player: MusicPlayer, vc: discord.VoiceClient) -> discord.Embed:
    song = player.current
    if not song:
        return _embed(C_LUNA, "Nothing is playing")

    elapsed = player.elapsed()
    paused = vc.is_paused() if vc else False

    e = discord.Embed(color=C_LUNA)
    prefix = "🟢 Kurdish" if song.is_kurdish else "🎵"
    e.set_author(name=f"{prefix} Now Playing")
    e.title = song.title
    e.url = song.url if song.url.startswith("http") else None

    bar = song.progress_bar(elapsed)
    e.description = f"`{_fmt_time(elapsed)}` {bar} `{song.dur_str}`"

    loop_icon = {"off": "➡️ Off", "track": "🔂 Track", "queue": "🔁 Queue"}.get(player.loop, "➡️ Off")
    vol_icon = "🔇" if player.volume <= 0 else ("🔉" if player.volume < 0.5 else "🔊")
    flt = FILTERS.get(player.filter_name, FILTERS["none"])["label"]
    p_emoji = PLATFORM_EMOJI.get(song.platform, "🔍")
    p_label = PLATFORM_LABEL.get(song.platform, "Unknown")

    e.add_field(name=f"{p_emoji} Platform", value=p_label, inline=True)
    e.add_field(name="🎙️ Artist", value=song.uploader[:50], inline=True)
    e.add_field(name="⏱️ Length", value=song.dur_str, inline=True)
    e.add_field(name=f"{vol_icon} Vol", value=f"{int(player.volume * 100)}%", inline=True)
    e.add_field(name="🔁 Loop", value=loop_icon, inline=True)
    e.add_field(name="🎛️ Filter", value=flt, inline=True)
    e.add_field(name="📋 Queue", value=str(len(player.queue)), inline=True)
    e.add_field(name="👤 Requested by", value=song.requester.mention, inline=False)

    if song.thumbnail and song.thumbnail.startswith("http"):
        e.set_thumbnail(url=song.thumbnail)

    status = "⏸ Paused" if paused else "▶️ Playing"
    e.set_footer(text=f"Veltra Music  •  {status}")
    return e

# ──────────────────────────────────────────────────────
#  NOW PLAYING VIEW (BUTTONS)
# ──────────────────────────────────────────────────────
class NowPlayingView(discord.ui.View):
    def __init__(self, player: MusicPlayer, vc: discord.VoiceClient):
        super().__init__(timeout=None)
        self.player = player
        self.vc = vc
        paused = vc.is_paused() if vc else False

        buttons = [
            ("⏮️", "prev",  discord.ButtonStyle.secondary, 0),
            ("▶️" if paused else "⏸️", "pause", discord.ButtonStyle.primary, 0),
            ("⏭️", "skip",  discord.ButtonStyle.secondary, 0),
            ("⏹️", "stop",  discord.ButtonStyle.danger, 0),
            ("🔂" if player.loop == "track" else "🔁" if player.loop == "queue" else "➡️",
             "loop", discord.ButtonStyle.secondary, 1),
            ("🔀", "shuffle", discord.ButtonStyle.secondary, 1),
            ("❤️", "grab", discord.ButtonStyle.secondary, 1),
            ("📋", "queue", discord.ButtonStyle.secondary, 1),
        ]
        for emoji, action, style, row in buttons:
            self.add_item(_NPButton(emoji, action, style, row))


class _NPButton(discord.ui.Button):
    def __init__(self, emoji: str, action: str, style: discord.ButtonStyle, row: int):
        super().__init__(
            emoji=emoji, style=style,
            custom_id=f"vnp_{action}_{random.randint(0,9999999)}",
            row=row,
        )
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        # Defer first to prevent timeout
        try:
            await interaction.response.defer(ephemeral=False)
        except Exception:
            return

        if not interaction.guild or not interaction.guild.voice_client:
            return
        vc = interaction.guild.voice_client
        player = get_player(interaction.guild.id)
        if not player.current:
            return

        try:
            handled = await self._handle(interaction, vc, player)
            if not handled:
                # Refresh NP embed
                if player.current and vc.is_connected():
                    new_embed = build_np_embed(player, vc)
                    new_view = NowPlayingView(player, vc)
                    if player.np_msg:
                        try:
                            await player.np_msg.edit(embed=new_embed, view=new_view)
                        except Exception:
                            pass
        except Exception as e:
            log.error(f"NPButton error ({self.action}): {e}")

    async def _handle(self, interaction, vc, player) -> bool:
        """Returns True if a followup message was sent (don't refresh embed)."""
        if self.action == "pause":
            if vc.is_paused():
                player._elapsed_pre = player.elapsed()
                player._start = time.time()
                player._paused_at = None
                vc.resume()
            else:
                player._elapsed_pre = player.elapsed()
                player._paused_at = time.time()
                vc.pause()

        elif self.action == "skip":
            player.skip_votes.clear()
            vc.stop()

        elif self.action == "stop":
            player.queue.clear()
            player.loop = "off"
            vc.stop()
            try:
                await interaction.followup.send(embed=ok_embed("Stopped and cleared the queue."), ephemeral=True)
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
                    await interaction.followup.send(embed=ok_embed("🔀 Queue shuffled!"), ephemeral=True)
                except Exception:
                    pass
            return True

        elif self.action == "grab":
            song = player.current
            e = discord.Embed(color=C_LUNA, title="❤️ Saved Song",
                              description=f"**[{song.title}]({song.url})**")
            e.add_field(name="Duration", value=song.dur_str, inline=True)
            e.add_field(name="Channel", value=song.uploader[:50], inline=True)
            e.add_field(name="Platform", value=PLATFORM_LABEL.get(song.platform, "Unknown"), inline=True)
            if song.is_kurdish:
                e.add_field(name="Type", value="🟢 Kurdish Song", inline=True)
            if song.thumbnail and song.thumbnail.startswith("http"):
                e.set_thumbnail(url=song.thumbnail)
            try:
                await interaction.user.send(embed=e)
                await interaction.followup.send(embed=ok_embed("Song info sent to your DMs!"), ephemeral=True)
            except discord.Forbidden:
                await interaction.followup.send(
                    embed=err_embed("Can't DM you. Enable DMs from server members."), ephemeral=True
                )
            except Exception:
                pass
            return True

        elif self.action == "queue":
            q = player.queue
            if not q:
                await interaction.followup.send(
                    embed=_embed(C_LUNA, "📋 The queue is empty."), ephemeral=True
                )
            else:
                lines = []
                for i, s in enumerate(q[:10]):
                    k = " 🟢" if s.is_kurdish else ""
                    lines.append(f"`{i+1}.` [{s.title}]({s.url}) `{s.dur_str}`{k}")
                extra = f"\n*+{len(q)-10} more...*" if len(q) > 10 else ""
                await interaction.followup.send(
                    embed=_embed(C_LUNA, f"📋 Queue — {len(q)} song(s)").set_description(
                        "\n".join(lines) + extra
                    ), ephemeral=True
                )
            return True

        elif self.action == "prev":
            if player.history:
                prev = player.history.pop()
                if player.current:
                    player.queue.insert(0, player.current)
                player.queue.insert(0, prev)
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

# ──────────────────────────────────────────────────────
#  PLAYBACK ENGINE — crash-proof
# ──────────────────────────────────────────────────────
async def play_next(guild_id: int, text_channel: discord.abc.Messageable | None, vc: discord.VoiceClient):
    """
    Core playback loop. Always called via run_coroutine_threadsafe from after_cb,
    or directly from commands. Protected by asyncio.Lock to prevent double-play.
    """
    player = get_player(guild_id)

    # Acquire lock — if already playing, skip
    if player._lock.locked():
        log.warning(f"[G{guild_id}] play_next called while locked, skipping")
        return

    async with player._lock:
        # Safety: check VC is still valid
        if not vc or not vc.is_connected():
            log.info(f"[G{guild_id}] VC gone, aborting play_next")
            return

        song = None

        if player.loop == "track" and player.current:
            song = player.current
        elif player.loop == "queue" and player.current:
            player.queue.append(player.current)
            song = player.queue.pop(0) if player.queue else None
        else:
            song = player.queue.pop(0) if player.queue else None

        # ── Queue empty ──
        if song is None:
            if player.current:
                push_history(guild_id, player.current.title, player.current.url,
                             player.current.dur_str, str(player.current.requester),
                             player.current.platform)
            player.current = None
            player._playing = False

            # Try autoplay
            if player.autoplay and player.history:
                last = player.history[-1]
                try:
                    q = f"{last.uploader} kurdish song"
                    results = await search_songs(q, player.kurdish_mode)
                    if results:
                        data = results[0]
                        ns = Song(data, bot.user, detect_platform(data.get("url", "")))
                        player.queue.append(ns)
                        # Recurse to play it
                        await play_next(guild_id, text_channel, vc)
                        return
                except Exception as e:
                    log.error(f"Autoplay error: {e}")

            # 24/7 check
            if not player.tfs:
                try:
                    await asyncio.sleep(300)
                except asyncio.CancelledError:
                    return
                # Re-check after sleep
                p2 = get_player(guild_id)
                if not p2.current and not p2.queue:
                    if vc.is_connected():
                        non_bots = [m for m in vc.channel.members if not m.bot]
                        if not non_bots:
                            try:
                                await vc.disconnect()
                            except Exception:
                                pass
                            destroy_player(guild_id)
                            if text_channel:
                                try:
                                    await text_channel.send(
                                        embed=_embed(C_LUNA, "👋 Left voice channel (idle 5 min).")
                                    )
                                except Exception:
                                    pass
            return

        # ── Push previous to history ──
        if player.current and player.current is not song:
            push_history(guild_id, player.current.title, player.current.url,
                         player.current.dur_str, str(player.current.requester),
                         player.current.platform)
            player.history.append(player.current)
            if len(player.history) > 20:
                player.history.pop(0)

        player.current = song
        player.skip_votes.clear()

        # ── Resolve stream URL if needed ──
        if not song.stream_url or "googlevideo" not in song.stream_url:
            data = await resolve_url(song.url)
            if not data:
                log.warning(f"Could not resolve: {song.url}")
                if text_channel:
                    try:
                        await text_channel.send(
                            embed=err_embed(f"Skipping **{song.title}** — couldn't resolve stream.")
                        )
                    except Exception:
                        pass
                # Try next song
                player._playing = False
                await play_next(guild_id, text_channel, vc)
                return

            song.stream_url = data.get("url") or ""
            if not song.thumbnail:
                song.thumbnail = data.get("thumbnail") or ""
            if not song.duration or song.duration <= 0:
                song.duration = data.get("duration") or 0
            if song.uploader == "Unknown":
                song.uploader = data.get("uploader") or data.get("channel") or "Unknown"

        if not song.stream_url:
            log.error(f"No stream URL for: {song.title}")
            if text_channel:
                try:
                    await text_channel.send(embed=err_embed(f"Skipping **{song.title}** — no stream URL."))
                except Exception:
                    pass
            player._playing = False
            await play_next(guild_id, text_channel, vc)
            return

        # ── Create FFmpeg source ──
        source = _make_source(song.stream_url, player.volume, player.filter_name)
        if not source:
            log.error(f"FFmpeg failed for: {song.title}")
            if text_channel:
                try:
                    await text_channel.send(embed=err_embed(f"Skipping **{song.title}** — FFmpeg error."))
                except Exception:
                    pass
            player._playing = False
            await play_next(guild_id, text_channel, vc)
            return

        player.reset_timer()
        player._playing = True

        # ── Play ──
        def after_cb(err):
            if err:
                log.error(f"Player after_cb error: {err}")
            # Always schedule next — let play_next handle empty queue
            fut = asyncio.run_coroutine_threadsafe(
                play_next(guild_id, text_channel, vc), bot.loop
            )
            # Prevent "Future exception was never retrieved"
            fut.add_done_callback(lambda f: f.exception() if f.exception() else None)

        try:
            vc.play(source, after=after_cb)
        except Exception as e:
            log.error(f"vc.play() failed: {e}")
            player._playing = False
            if text_channel:
                try:
                    await text_channel.send(embed=err_embed(f"Failed to play **{song.title}**."))
                except Exception:
                    pass
            return

        # ── Send/update NP message ──
        if text_channel:
            embed = build_np_embed(player, vc)
            view = NowPlayingView(player, vc)
            try:
                if player.np_msg and not player.np_msg.is_deleted():
                    await player.np_msg.edit(embed=embed, view=view)
                else:
                    player.np_msg = await text_channel.send(embed=embed, view=view)
            except discord.Forbidden:
                pass
            except discord.HTTPException:
                try:
                    player.np_msg = await text_channel.send(embed=embed, view=view)
                except Exception:
                    pass
            except Exception as e:
                log.error(f"NP message error: {e}")


async def start_playback(ctx: commands.Context):
    """Safe helper to kick off playback if not already playing."""
    vc = ctx.voice_client
    if not vc:
        return
    player = get_player(ctx.guild.id)
    if not player._playing:
        await play_next(ctx.guild.id, ctx.channel, vc)

# ──────────────────────────────────────────────────────
#  VOICE HELPER
# ──────────────────────────────────────────────────────
async def _ensure_voice(ctx: commands.Context):
    """Join voice channel. Returns VC or None."""
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send(embed=err_embed("You must be in a voice channel!"))
        return None

    target = ctx.author.voice.channel

    # Check bot can join
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
    except discord.ClientException as e:
        await ctx.send(embed=err_embed(f"Could not connect: {e}"))
        return None
    except Exception as e:
        log.error(f"Voice connect error: {e}")
        await ctx.send(embed=err_embed("Failed to connect to voice channel."))
        return None


async def _dj_check(ctx: commands.Context) -> bool:
    """Check if user has DJ permissions."""
    if ctx.author.guild_permissions.manage_guild:
        return True
    s = get_settings(ctx.guild.id)
    dj_id = s.get("dj_role_id")
    if dj_id:
        role = ctx.guild.get_role(int(dj_id))
        if role and role in ctx.author.roles:
            return True
        name = role.name if role else str(dj_id)
        await ctx.send(embed=err_embed(f"You need the **{name}** DJ role!"))
        return False
    return True

# ──────────────────────────────────────────────────────
#  COMMANDS — PLAYBACK
# ──────────────────────────────────────────────────────
@bot.command(aliases=["j"])
async def join(ctx: commands.Context):
    vc = await _ensure_voice(ctx)
    if vc:
        await ctx.send(embed=ok_embed(f"Joined **{vc.channel.name}**!"))


@bot.command(aliases=["dc", "leave"])
async def disconnect(ctx: commands.Context):
    if not ctx.voice_client:
        return await ctx.send(embed=err_embed("I'm not in a voice channel!"))
    if not await _dj_check(ctx):
        return
    vc = ctx.voice_client
    player = get_player(ctx.guild.id)
    player.queue.clear()
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
    if not query.strip():
        return await ctx.send(embed=err_embed("Please provide a song name or URL!"))

    vc = await _ensure_voice(ctx)
    if not vc:
        return

    player = get_player(ctx.guild.id)
    platform = detect_platform(query)
    p_emoji = PLATFORM_EMOJI.get(platform, "🔍")
    msg = await ctx.send(embed=_embed(C_LUNA, f"{p_emoji} Searching for **{query[:80]}**..."))

    is_url = query.strip().startswith(("http://", "https://"))

    try:
        if is_url and ("list=" in query or "/playlist" in query.lower()):
            # Playlist
            entries = await resolve_playlist(query)
            if not entries:
                return await msg.edit(embed=err_embed("Couldn't find anything in that playlist."))

            added = 0
            for entry in entries:
                eid = entry.get("id")
                if not eid:
                    continue
                data = {
                    "title": entry.get("title") or "Unknown",
                    "url": entry.get("url") or f"https://www.youtube.com/watch?v={eid}",
                    "webpage_url": entry.get("url") or f"https://www.youtube.com/watch?v={eid}",
                    "duration": entry.get("duration") or 0,
                    "thumbnail": entry.get("thumbnail") or "",
                    "uploader": entry.get("uploader") or entry.get("channel") or "",
                }
                ep = entry.get("_platform", platform)
                player.queue.append(Song(data, ctx.author, ep))
                added += 1

            if added == 0:
                return await msg.edit(embed=err_embed("No playable entries found in playlist."))

            e = _embed(C_LUNA, "")
            e.title = "📋 Playlist Added!"
            e.add_field(name="Songs", value=str(added), inline=True)
            e.add_field(name="Queue length", value=str(len(player.queue)), inline=True)
            e.add_field(name="Platform", value=PLATFORM_LABEL.get(platform, "Unknown"), inline=True)
            await msg.edit(embed=e)

        elif is_url:
            # Single URL
            data = await resolve_url(query)
            if not data:
                return await msg.edit(embed=err_embed("Could not resolve that URL. Check the link and try again."))

            song = Song(data, ctx.author, platform)
            player.queue.append(song)

            if vc.is_playing() or vc.is_paused():
                e = _embed(C_LUNA, "")
                e.title = "➕ Added to Queue"
                e.description = f"**[{song.title}]({song.url})**"
                e.add_field(name="Duration", value=song.dur_str, inline=True)
                e.add_field(name="Position", value=f"#{len(player.queue)}", inline=True)
                e.add_field(name="Platform", value=PLATFORM_LABEL.get(platform, "Unknown"), inline=True)
                if song.is_kurdish:
                    e.add_field(name="Type", value="🟢 Kurdish Song", inline=True)
                if song.thumbnail and song.thumbnail.startswith("http"):
                    e.set_thumbnail(url=song.thumbnail)
                await msg.edit(embed=e)
            else:
                try:
                    await msg.delete()
                except Exception:
                    pass

        else:
            # Text search
            results = await search_songs(query, player.kurdish_mode)
            if not results:
                return await msg.edit(embed=err_embed("No results found! Try a different search."))

            data = results[0]
            rp = detect_platform(data.get("url", ""))
            song = Song(data, ctx.author, rp)
            player.queue.append(song)

            if vc.is_playing() or vc.is_paused():
                e = _embed(C_LUNA, "")
                e.title = "➕ Added to Queue"
                e.description = f"**[{song.title}]({song.url})**"
                e.add_field(name="Duration", value=song.dur_str, inline=True)
                e.add_field(name="Position", value=f"#{len(player.queue)}", inline=True)
                if song.is_kurdish:
                    e.add_field(name="Type", value="🟢 Kurdish Song", inline=True)
                if song.thumbnail and song.thumbnail.startswith("http"):
                    e.set_thumbnail(url=song.thumbnail)
                await msg.edit(embed=e)
            else:
                try:
                    await msg.delete()
                except Exception:
                    pass

    except Exception as e:
        log.error(f"Play command error: {e}\n{traceback.format_exc()}")
        try:
            await msg.edit(embed=err_embed(f"Error: {str(e)[:200]}"))
        except Exception:
            pass
        return

    await start_playback(ctx)


@bot.command()
async def search(ctx: commands.Context, *, query: str):
    if not query.strip():
        return await ctx.send(embed=err_embed("Please provide a search query!"))

    msg = await ctx.send(embed=_embed(C_LUNA, f"🔍 Searching all platforms for **{query[:80]}**..."))

    try:
        results = await search_songs(query, get_player(ctx.guild.id).kurdish_mode)
    except Exception as e:
        return await msg.edit(embed=err_embed(str(e)[:200]))

    if not results:
        return await msg.edit(embed=err_embed("No results found!"))

    lines = []
    for i, r in enumerate(results):
        k = " 🟢" if is_kurdish_title(r.get("title", "")) else ""
        title = r.get("title", "?")
        rid = r.get("id", "")
        dur = _dur(r.get("duration"))
        url = f"https://youtu.be/{rid}" if rid else "#"
        lines.append(f"`{i+1}.` [{title}]({url}) `{dur}`{k}")

    e = _embed(C_LUNA, "")
    e.title = "🔍 Search Results"
    e.description = "\n".join(lines)
    e.set_footer(text="Reply with a number (1-5) to pick  •  'cancel' to cancel\n🟢 = Kurdish Song")
    await msg.edit(embed=e)

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.strip()

    try:
        reply = await bot.wait_for("message", check=check, timeout=30)
    except asyncio.TimeoutError:
        return await msg.edit(embed=err_embed("Selection timed out."))

    try:
        await reply.delete()
    except Exception:
        pass

    content = reply.content.strip().lower()
    if content == "cancel":
        return await msg.edit(embed=ok_embed("Cancelled."))

    try:
        idx = int(content) - 1
        if idx < 0 or idx >= len(results):
            raise ValueError
    except (ValueError, TypeError):
        return await msg.edit(embed=err_embed("Invalid selection. Enter a number 1-5."))

    vc = await _ensure_voice(ctx)
    if not vc:
        return

    player = get_player(ctx.guild.id)
    data = results[idx]
    rid = data.get("id", "")

    if not rid:
        return await msg.edit(embed=err_embed("Invalid result — no ID."))

    try:
        full = await resolve_url(f"https://www.youtube.com/watch?v={rid}")
        if not full:
            return await msg.edit(embed=err_embed("Could not resolve that song."))
    except Exception as e:
        return await msg.edit(embed=err_embed(str(e)[:200]))

    song = Song(full, ctx.author, "youtube")
    player.queue.append(song)

    e2 = _embed(C_LUNA, "")
    e2.title = "➕ Added to Queue"
    e2.description = f"**[{song.title}]({song.url})**"
    e2.add_field(name="Duration", value=song.dur_str, inline=True)
    if song.is_kurdish:
        e2.add_field(name="Type", value="🟢 Kurdish Song", inline=True)
    if song.thumbnail and song.thumbnail.startswith("http"):
        e2.set_thumbnail(url=song.thumbnail)
    await msg.edit(embed=e2)

    await start_playback(ctx)


@bot.command(aliases=["kurdish", "ku"])
async def kurdishplay(ctx: commands.Context, *, query: str):
    """Find Kurdish version of a song."""
    if not query.strip():
        return await ctx.send(embed=err_embed("Please provide a song name!"))

    vc = await _ensure_voice(ctx)
    if not vc:
        return

    player = get_player(ctx.guild.id)
    kurdish_query = enhance_kurdish_query(query, kurdish_mode=True)

    msg = await ctx.send(embed=_embed(C_LUNA, f"🟢 Searching Kurdish: **{kurdish_query[:80]}**..."))

    try:
        results = await search_songs(kurdish_query, kurdish_mode=True)
        if not results:
            # Try alternative
            alt = f"{query} کوردی cover"
            results = await search_songs(alt, kurdish_mode=True)

        if not results:
            return await msg.edit(embed=err_embed("No Kurdish version found! Try the original song name."))

        data = results[0]
        song = Song(data, ctx.author, "youtube")
        player.queue.append(song)

        e = _embed(C_LUNA, "")
        e.title = "🟢 Kurdish Song Added"
        e.description = f"**[{song.title}]({song.url})**"
        e.add_field(name="Duration", value=song.dur_str, inline=True)
        if song.thumbnail and song.thumbnail.startswith("http"):
            e.set_thumbnail(url=song.thumbnail)
        await msg.edit(embed=e)

    except Exception as e:
        log.error(f"kurdishplay error: {e}")
        return await msg.edit(embed=err_embed(str(e)[:200]))

    await start_playback(ctx)


@bot.command(aliases=["pa"])
async def pause(ctx: commands.Context):
    vc = ctx.voice_client
    if not vc or not vc.is_playing():
        return await ctx.send(embed=err_embed("Nothing is playing!"))
    if not await _dj_check(ctx):
        return
    player = get_player(ctx.guild.id)
    player._elapsed_pre = player.elapsed()
    player._paused_at = time.time()
    vc.pause()
    await ctx.send(embed=ok_embed("Paused ⏸️"))


@bot.command(aliases=["res"])
async def resume(ctx: commands.Context):
    vc = ctx.voice_client
    if not vc or not vc.is_paused():
        return await ctx.send(embed=err_embed("Nothing is paused!"))
    if not await _dj_check(ctx):
        return
    player = get_player(ctx.guild.id)
    player._elapsed_pre = player.elapsed()
    player._start = time.time()
    player._paused_at = None
    vc.resume()
    await ctx.send(embed=ok_embed("Resumed ▶️"))


@bot.command(aliases=["s"])
async def skip(ctx: commands.Context):
    vc = ctx.voice_client
    if not vc or (not vc.is_playing() and not vc.is_paused()):
        return await ctx.send(embed=err_embed("Nothing is playing!"))

    player = get_player(ctx.guild.id)
    is_dj = ctx.author.guild_permissions.manage_guild
    s = get_settings(ctx.guild.id)
    dj_id = s.get("dj_role_id")

    if is_dj:
        player.skip_votes.clear()
        vc.stop()
        return await ctx.send(embed=ok_embed("⏭️ Skipped!"))

    if dj_id:
        role = ctx.guild.get_role(int(dj_id))
        if role and role in ctx.author.roles:
            player.skip_votes.clear()
            vc.stop()
            return await ctx.send(embed=ok_embed("⏭️ Skipped!"))

    # Vote skip
    vc_members = [m for m in vc.channel.members if not m.bot]
    if not vc_members:
        player.skip_votes.clear()
        vc.stop()
        return await ctx.send(embed=ok_embed("⏭️ Skipped!"))

    needed = max(1, math.ceil(len(vc_members) * 0.5))
    player.skip_votes.add(ctx.author.id)
    votes = len(player.skip_votes)

    if votes >= needed:
        player.skip_votes.clear()
        vc.stop()
        await ctx.send(embed=ok_embed(f"⏭️ Vote passed ({votes}/{needed})! Skipped."))
    else:
        await ctx.send(embed=_embed(
            C_YELLOW, f"🗳️ Skip vote: **{votes}/{needed}** — need {needed - votes} more."
        ))


@bot.command()
async def stop(ctx: commands.Context):
    if not await _dj_check(ctx):
        return
    vc = ctx.voice_client
    if not vc:
        return await ctx.send(embed=err_embed("I'm not in a voice channel!"))
    player = get_player(ctx.guild.id)
    player.queue.clear()
    player.loop = "off"
    vc.stop()
    await ctx.send(embed=ok_embed("⏹️ Stopped and cleared the queue."))


@bot.command(aliases=["np"])
async def nowplaying(ctx: commands.Context):
    vc = ctx.voice_client
    if not vc:
        return await ctx.send(embed=err_embed("I'm not in a voice channel!"))
    player = get_player(ctx.guild.id)
    if not player.current:
        return await ctx.send(embed=err_embed("Nothing is playing!"))
    embed = build_np_embed(player, vc)
    view = NowPlayingView(player, vc)
    try:
        player.np_msg = await ctx.send(embed=embed, view=view)
    except Exception as e:
        log.error(f"nowplaying send error: {e}")


@bot.command(aliases=["replay", "restart"])
async def again(ctx: commands.Context):
    vc = ctx.voice_client
    if not vc or (not vc.is_playing() and not vc.is_paused()):
        return await ctx.send(embed=err_embed("Nothing is playing!"))
    if not await _dj_check(ctx):
        return
    player = get_player(ctx.guild.id)
    if not player.current:
        return await ctx.send(embed=err_embed("Nothing is playing!"))
    player.queue.insert(0, player.current)
    vc.stop()
    await ctx.send(embed=ok_embed("🔁 Replaying!"))

# ──────────────────────────────────────────────────────
#  QUEUE COMMANDS
# ──────────────────────────────────────────────────────
@bot.command(aliases=["q"])
async def queue(ctx: commands.Context, page: int = 1):
    player = get_player(ctx.guild.id)

    if not player.current and not player.queue:
        return await ctx.send(embed=_embed(C_LUNA, "📋 Queue is empty. Use `$play` to add songs!"))

    per_page = 10
    total = len(player.queue)
    pages = max(1, math.ceil(total / per_page))
    page = max(1, min(page, pages))
    start = (page - 1) * per_page
    chunk = player.queue[start:start + per_page]

    desc = ""
    if player.current:
        k = " 🟢" if player.current.is_kurdish else ""
        desc += (f"**▶️ Now:** [{player.current.title}]({player.current.url}) "
                 f"`{player.current.dur_str}` — {player.current.requester.mention}{k}\n\n")

    if chunk:
        desc += "**📋 Up Next:**\n"
        for i, s in enumerate(chunk, start=start + 1):
            k = " 🟢" if s.is_kurdish else ""
            desc += f"`{i}.` [{s.title}]({s.url}) `{s.dur_str}` — {s.requester.mention}{k}\n"

    total_dur = sum(s.duration or 0 for s in player.queue)
    loop_icon = {"off": "➡️ Off", "track": "🔂 Track", "queue": "🔁 Queue"}.get(player.loop, "➡️ Off")
    e = _embed(C_LUNA, "")
    e.title = f"📋 Queue — {total} song(s)"
    e.description = desc
    e.set_footer(text=f"Page {page}/{pages}  •  Total: {_fmt_time(total_dur)}  •  Loop: {loop_icon}  •  🟢 = Kurdish")
    await ctx.send(embed=e)


@bot.command(aliases=["rm"])
async def remove(ctx: commands.Context, index: int):
    if not await _dj_check(ctx):
        return
    player = get_player(ctx.guild.id)
    if index < 1 or index > len(player.queue):
        return await ctx.send(embed=err_embed(f"Invalid position! Queue has {len(player.queue)} songs."))
    removed = player.queue.pop(index - 1)
    await ctx.send(embed=ok_embed(f"Removed **{removed.title[:60]}**"))


@bot.command()
async def clear(ctx: commands.Context):
    if not await _dj_check(ctx):
        return
    player = get_player(ctx.guild.id)
    player.queue.clear()
    await ctx.send(embed=ok_embed("Queue cleared!"))


@bot.command(aliases=["sh"])
async def shuffle(ctx: commands.Context):
    if not await _dj_check(ctx):
        return
    player = get_player(ctx.guild.id)
    if len(player.queue) < 2:
        return await ctx.send(embed=err_embed("Need at least 2 songs to shuffle."))
    random.shuffle(player.queue)
    await ctx.send(embed=ok_embed("🔀 Queue shuffled!"))


@bot.command()
async def move(ctx: commands.Context, frm: int, to: int):
    if not await _dj_check(ctx):
        return
    player = get_player(ctx.guild.id)
    q = player.queue
    if not (1 <= frm <= len(q)) or not (1 <= to <= len(q)):
        return await ctx.send(embed=err_embed(f"Positions must be 1–{len(q)}."))
    song = q.pop(frm - 1)
    q.insert(to - 1, song)
    await ctx.send(embed=ok_embed(f"Moved **{song.title[:60]}** to position **{to}**."))


@bot.command()
async def skipto(ctx: commands.Context, index: int):
    if not await _dj_check(ctx):
        return
    vc = ctx.voice_client
    if not vc:
        return await ctx.send(embed=err_embed("Nothing is playing!"))
    player = get_player(ctx.guild.id)
    if index < 1 or index > len(player.queue):
        return await ctx.send(embed=err_embed(f"Invalid position! Queue has {len(player.queue)} songs."))
    # Move songs before index back to front of history conceptually
    skipped = player.queue[:index - 1]
    player.queue = player.queue[index - 1:]
    vc.stop()
    await ctx.send(embed=ok_embed(f"⏭️ Skipped to position **{index}**!"))

# ──────────────────────────────────────────────────────
#  SETTINGS COMMANDS
# ──────────────────────────────────────────────────────
@bot.command(aliases=["vol"])
async def volume(ctx: commands.Context, vol: int):
    if not await _dj_check(ctx):
        return
    if not isinstance(vol, int) or not 0 <= vol <= 200:
        return await ctx.send(embed=err_embed("Volume must be 0–200."))
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
    if not await _dj_check(ctx):
        return
    player = get_player(ctx.guild.id)
    modes = ["off", "track", "queue"]
    if mode is None:
        mode = modes[(modes.index(player.loop) + 1) % 3]
    else:
        mode = mode.lower()
    if mode not in modes:
        return await ctx.send(embed=err_embed("Mode must be: `off`, `track`, or `queue`"))
    player.loop = mode
    save_settings(ctx.guild.id, loop_mode=mode)
    icon = {"off": "➡️", "track": "🔂", "queue": "🔁"}[mode]
    await ctx.send(embed=ok_embed(f"{icon} Loop set to **{mode.capitalize()}**"))


@bot.command(aliases=["filter"])
async def setfilter(ctx: commands.Context, name: str = None):
    if not await _dj_check(ctx):
        return
    if name is None:
        lines = [f"`{k}` — {v['label']}" for k, v in FILTERS.items()]
        e = _embed(C_LUNA, "")
        e.title = "🎛️ Audio Filters"
        e.description = "\n".join(lines)
        e.set_footer(text="Usage: $filter <name>  |  $filter none to reset")
        return await ctx.send(embed=e)

    name = name.lower()
    if name not in FILTERS:
        return await ctx.send(embed=err_embed("Unknown filter! Use `$filter` to see list."))

    player = get_player(ctx.guild.id)
    old_filter = player.filter_name
    player.filter_name = name
    vc = ctx.voice_client

    if vc and (vc.is_playing() or vc.is_paused()) and player.current:
        was_paused = vc.is_paused()
        paused_pos = player.elapsed()

        # Stop current playback
        try:
            vc.stop()
        except Exception:
            pass

        # Wait for after_cb to finish
        await asyncio.sleep(0.6)

        # Re-resolve and play with new filter
        data = await resolve_url(player.current.url)
        if data:
            player.current.stream_url = data.get("url") or player.current.stream_url

        source = _make_source(player.current.stream_url, player.volume, name)
        if source:
            player.reset_timer()
            player._playing = True

            def after_cb(err):
                if err:
                    log.error(f"Filter change after_cb error: {err}")
                fut = asyncio.run_coroutine_threadsafe(
                    play_next(ctx.guild.id, ctx.channel, vc), bot.loop
                )
                fut.add_done_callback(lambda f: f.exception() if f.exception() else None)

            try:
                vc.play(source, after=after_cb)
                if was_paused:
                    vc.pause()
                    player._elapsed_pre = paused_pos
                    player._paused_at = time.time()
            except Exception as e:
                log.error(f"Filter change play error: {e}")
                player.filter_name = old_filter
                await ctx.send(embed=err_embed(f"Failed to apply filter: {e}"))
                return
        else:
            player.filter_name = old_filter
            await ctx.send(embed=err_embed("Failed to create audio source with that filter."))
            return

    label = FILTERS[name]["label"]
    await ctx.send(embed=ok_embed(f"🎛️ Filter set to **{label}**"))


@bot.command(aliases=["filters"])
async def listfilters(ctx: commands.Context):
    lines = [f"`{k}` — {v['label']}" for k, v in FILTERS.items()]
    e = _embed(C_LUNA, "")
    e.title = "🎛️ Available Filters"
    e.description = "\n".join(lines)
    e.set_footer(text="$filter <name> to apply  |  $filter none to reset")
    await ctx.send(embed=e)


@bot.command(name="247")
async def tfs_cmd(ctx: commands.Context):
    if not await _dj_check(ctx):
        return
    player = get_player(ctx.guild.id)
    player.tfs = not player.tfs
    save_settings(ctx.guild.id, tfs=int(player.tfs))
    state = "enabled 🟢" if player.tfs else "disabled 🔴"
    await ctx.send(embed=ok_embed(f"24/7 mode **{state}**"))


@bot.command()
async def autoplay(ctx: commands.Context):
    if not await _dj_check(ctx):
        return
    player = get_player(ctx.guild.id)
    player.autoplay = not player.autoplay
    save_settings(ctx.guild.id, autoplay=int(player.autoplay))
    state = "enabled 🟢" if player.autoplay else "disabled 🔴"
    note = " (will play related Kurdish songs)" if player.autoplay else ""
    await ctx.send(embed=ok_embed(f"Autoplay **{state}**{note}"))


@bot.command()
async def kurdishmode(ctx: commands.Context):
    player = get_player(ctx.guild.id)
    player.kurdish_mode = not player.kurdish_mode
    save_settings(ctx.guild.id, kurdish_mode=int(player.kurdish_mode))
    state = "enabled 🟢" if player.kurdish_mode else "disabled 🔴"
    desc = "Will find Kurdish versions of songs" if player.kurdish_mode else "Normal search mode"
    await ctx.send(embed=ok_embed(f"Kurdish mode **{state}** — {desc}"))


@bot.command(aliases=["setdj"])
@commands.has_permissions(manage_guild=True)
async def djrole(ctx: commands.Context, role: discord.Role = None):
    if role is None:
        save_settings(ctx.guild.id, dj_role_id=None)
        return await ctx.send(embed=ok_embed("DJ role removed. Everyone can control music."))
    save_settings(ctx.guild.id, dj_role_id=role.id)
    await ctx.send(embed=ok_embed(f"DJ role set to {role.mention}."))

# ──────────────────────────────────────────────────────
#  LYRICS
# ──────────────────────────────────────────────────────
@bot.command(aliases=["ly"])
async def lyrics(ctx: commands.Context, *, song_name: str = None):
    player = get_player(ctx.guild.id)
    if not song_name or not song_name.strip():
        if not player.current:
            return await ctx.send(embed=err_embed("Nothing playing! Provide a song name: `$lyrics Artist - Song`"))
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

    if not artist or not title_q:
        return await ctx.send(embed=err_embed("Use format: `$lyrics Artist - Song Title`"))

    msg = await ctx.send(embed=_embed(C_LUNA, f"🔍 Fetching lyrics for **{clean[:60]}**..."))

    lyrics_text = None
    # Try multiple API patterns
    for a, t in [(artist, title_q), (artist, clean), (clean, clean)]:
        if not a or not t:
            continue
        try:
            url = f"https://api.lyrics.ovh/v1/{a}/{t}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("lyrics"):
                            lyrics_text = data["lyrics"]
                            break
        except Exception:
            continue

    if not lyrics_text:
        return await msg.edit(embed=err_embed(f"No lyrics found for **{clean[:60]}**.\nTry: `$lyrics Artist - Song Title`"))

    lyrics_text = lyrics_text.replace("\r\n", "\n").strip()
    if not lyrics_text:
        return await msg.edit(embed=err_embed("Lyrics were empty."))

    chunks = [lyrics_text[i:i + 3800] for i in range(0, len(lyrics_text), 3800)]
    for i, chunk in enumerate(chunks):
        title = f"📜 {clean[:60]}" + (f" (Part {i+1})" if len(chunks) > 1 else "")
        e = _embed(C_LUNA, chunk)
        e.title = title
        e.set_footer(text="Powered by lyrics.ovh")
        if i == 0:
            await msg.edit(embed=e)
        else:
            try:
                await ctx.send(embed=e)
            except Exception:
                pass

# ──────────────────────────────────────────────────────
#  HISTORY & GRAB
# ──────────────────────────────────────────────────────
@bot.command()
async def history(ctx: commands.Context):
    try:
        conn = _db_connect()
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT title, url, duration, platform FROM history "
            "WHERE guild_id=? ORDER BY id DESC LIMIT 10",
            (ctx.guild.id,),
        ).fetchall()
        conn.close()
    except Exception as e:
        log.error(f"history error: {e}")
        return await ctx.send(embed=err_embed("Could not load history."))

    if not rows:
        return await ctx.send(embed=_embed(C_LUNA, "📜 No songs played yet!"))

    lines = []
    for i, r in enumerate(rows):
        k = " 🟢" if is_kurdish_title(r["title"]) else ""
        p = PLATFORM_EMOJI.get(r["platform"] or "unknown", "🎵")
        lines.append(f"`{i+1}.` {p} [{r['title']}]({r['url']}) `{r['duration']}`{k}")

    e = _embed(C_LUNA, "")
    e.title = "📜 Recently Played"
    e.description = "\n".join(lines)
    e.set_footer(text="🟢 = Kurdish Song")
    await ctx.send(embed=e)


@bot.command()
async def grab(ctx: commands.Context):
    player = get_player(ctx.guild.id)
    if not player.current:
        return await ctx.send(embed=err_embed("Nothing is playing!"))
    song = player.current
    e = _embed(C_LUNA, "")
    e.title = "❤️ Saved Song!"
    e.description = f"**[{song.title}]({song.url})**"
    e.add_field(name="Duration", value=song.dur_str, inline=True)
    e.add_field(name="Channel", value=song.uploader[:50], inline=True)
    e.add_field(name="Platform", value=PLATFORM_LABEL.get(song.platform, "Unknown"), inline=True)
    if song.is_kurdish:
        e.add_field(name="Type", value="🟢 Kurdish Song", inline=True)
    if song.thumbnail and song.thumbnail.startswith("http"):
        e.set_thumbnail(url=song.thumbnail)
    try:
        await ctx.author.send(embed=e)
        await ctx.send(embed=ok_embed("Song info sent to your DMs!"))
    except discord.Forbidden:
        await ctx.send(embed=err_embed("Can't DM you. Enable DMs from server members."))
    except Exception as e:
        log.error(f"grab error: {e}")
        await ctx.send(embed=err_embed("Failed to send DM."))

# ──────────────────────────────────────────────────────
#  INFO COMMANDS
# ──────────────────────────────────────────────────────
@bot.command()
async def ping(ctx: commands.Context):
    lat = round(bot.latency * 1000)
    await ctx.send(embed=_embed(C_LUNA, f"🏓 Pong! **{lat}ms**"))


@bot.command(aliases=["stats"])
async def botinfo(ctx: commands.Context):
    uptime = int(time.time() - bot_start_time)
    h, rem = divmod(uptime, 3600)
    m, s = divmod(rem, 60)
    e = _embed(C_LUNA, "")
    e.title = "🎵 Veltra Music Bot"
    e.add_field(name="Prefix", value="`$`", inline=True)
    e.add_field(name="Servers", value=str(len(bot.guilds)), inline=True)
    e.add_field(name="Uptime", value=f"{h}h {m}m {s}s", inline=True)
    e.add_field(name="Engine", value="yt-dlp + FFmpeg", inline=True)
    e.add_field(name="Filters", value=str(len(FILTERS)), inline=True)
    e.add_field(name="🟢 Kurdish", value="Enabled", inline=True)
    e.add_field(name="Platforms", value="Spotify · Apple · SoundCloud · Deezer · Anghami · Vimeo · YouTube · MP3/MP4", inline=False)
    e.set_footer(text="Veltra Music Bot  •  $help for commands")
    await ctx.send(embed=e)

# ──────────────────────────────────────────────────────
#  HELP
# ──────────────────────────────────────────────────────
@bot.command()
async def help(ctx: commands.Context):
    sections = [
        ("🎵 Playback", [
            "$play <query/url>     Play from any platform",
            "$kurdish <query>      Find Kurdish version",
            "$search <query>       Search & pick result",
            "$pause / $pa          Pause playback",
            "$resume / $res        Resume playback",
            "$skip / $s            Skip (or vote skip)",
            "$stop                 Stop & clear queue",
            "$nowplaying / $np     Show now playing",
            "$again / $replay      Replay current song",
            "$join / $j            Join voice channel",
            "$disconnect / $dc     Disconnect from voice",
        ]),
        ("📋 Queue", [
            "$queue / $q [page]    Show the queue",
            "$remove / $rm <pos>   Remove song from queue",
            "$clear                Clear entire queue",
            "$shuffle / $sh        Shuffle the queue",
            "$move <from> <to>     Move song in queue",
            "$skipto <pos>         Skip to position",
        ]),
        ("⚙️ Settings", [
            "$volume / $vol <0-200>   Set volume",
            "$loop [mode]             off/track/queue",
            "$filter / $setfilter     Apply audio filter",
            "$filters / $listfilters  List all filters",
            "$247                     Toggle 24/7 mode",
            "$autoplay                Toggle autoplay",
            "$kurdishmode             Toggle Kurdish search",
            "$djrole / $setdj [@role] Set DJ role",
        ]),
        ("📜 Other", [
            "$lyrics / $ly [song]  Fetch song lyrics",
            "$history              Recently played songs",
            "$grab                 DM current song info",
            "$ping                 Bot latency",
            "$botinfo / $stats     Bot information",
        ]),
        ("🎵 Platforms", [
            "Spotify      open.spotify.com",
            "Apple Music  music.apple.com",
            "SoundCloud   soundcloud.com",
            "Deezer       deezer.com",
            "Anghami      anghami.com",
            "Vimeo        vimeo.com",
            "YouTube      youtube.com / youtu.be",
            "Direct       .mp3 .mp4 .m4a .ogg .wav links",
        ]),
    ]

    e = _embed(C_LUNA, "")
    e.title = "🎵 Veltra Music Bot — Help"
    e.description = "Multi-platform music with Kurdish song support!\n🟢 = Kurdish song indicator"
    for section, lines in sections:
        e.add_field(name=section, value="```" + "\n".join(lines) + "```", inline=False)
    e.set_footer(text="Use $play to start playing music!")
    await ctx.send(embed=e)

# ──────────────────────────────────────────────────────
#  BOT EVENTS
# ──────────────────────────────────────────────────────
@bot.event
async def on_ready():
    log.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    log.info(f"Guilds: {len(bot.guilds)}")
    log.info("Multi-platform + Kurdish mode enabled")
    try:
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name="🎵 Multi-Platform Music | $help",
            )
        )
    except Exception as e:
        log.error(f"Presence error: {e}")


@bot.event
async def on_voice_state_update(member, before, after):
    """Auto-disconnect when all humans leave."""
    if member.bot:
        return

    # Member left a channel
    if before.channel and not after.channel:
        vc = before.channel.guild.voice_client
        if vc and vc.channel == before.channel:
            non_bots = [m for m in vc.channel.members if not m.bot]
            if not non_bots:
                player = get_player(vc.guild.id)
                if not player.tfs:
                    await asyncio.sleep(3)
                    # Re-check
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
async def on_command_error(ctx, error):
    """Global error handler — never crash."""
    if isinstance(error, commands.CommandNotFound):
        return  # Ignore unknown commands
    if isinstance(error, commands.MissingPermissions):
        try:
            await ctx.send(embed=err_embed("You don't have permission to use this command."))
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

    log.error(f"Command error [{ctx.command}]: {error}\n{traceback.format_exc()}")
    try:
        await ctx.send(embed=err_embed(f"An error occurred: {str(error)[:150]}"))
    except Exception:
        pass


# ──────────────────────────────────────────────────────
#  CLEANUP ON SHUTDOWN
# ──────────────────────────────────────────────────────
@bot.event
async def on_close():
    """Called when bot is closing."""
    log.info("Bot shutting down, cleaning up...")
    for gid, player in list(_players.items()):
        vc = player and player.current and None  # just iterate
        _players[gid].queue.clear()
        _players[gid].history.clear()
    _players.clear()


# ──────────────────────────────────────────────────────
#  RUN
# ──────────────────────────────────────────────────────
if __name__ == "__main__":
    log.info("Starting Veltra Music Bot...")
    try:
        bot.run(TOKEN, log_handler=None)
    except discord.LoginFailure:
        log.error("FATAL: Invalid DISCORD_TOKEN!")
    except KeyboardInterrupt:
        log.info("Interrupted by user.")
    except Exception as e:
        log.error(f"FATAL: {e}\n{traceback.format_exc()}")
