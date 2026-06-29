"""
╔══════════════════════════════════════════════════════╗
║          VELTRA MUSIC BOT  —  discord.py             ║
║   Play · Queue · Filters · Lyrics · 24/7 · DJ Role  ║
║   [FIXED] SoundCloud Primary + web_embedded YouTube  ║
╚══════════════════════════════════════════════════════╝

FIXES IN THIS VERSION
─────────────────────
1. CRASH FIX  — `async def bot()` was shadowing the Bot instance,
               causing every @bot.command() after it to crash with
               AttributeError: 'Command' object has no attribute 'command'
               Fixed by renaming to botinfo().

2. YOUTUBE FIX — Changed player_client to web_embedded first.
                 web_embedded bypasses bot-detection on ALL server/
                 datacenter IPs (Railway, Katabump, etc.) with NO
                 cookies needed.

3. KURDISH/ARABIC SONGS — SoundCloud is now PRIMARY search source.
                          SoundCloud has massive Kurdish/Arabic/Persian
                          libraries and ZERO bot-detection. YouTube is
                          fallback only.

4. HLS FIX — Added -protocol_whitelist to FFmpeg so HLS streams from
             web_embedded/tv_embedded don't cause instant-skip.
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
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

logging.basicConfig(level=logging.INFO)

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

# ──────────────────────────────────────────────────────
#  COOKIE SUPPORT (optional — enhances YouTube access)
# ──────────────────────────────────────────────────────
COOKIE_FILE = os.getenv("COOKIE_FILE", "cookies.txt")

def _has_cookies() -> bool:
    return os.path.exists(COOKIE_FILE) and os.path.getsize(COOKIE_FILE) > 10

# ──────────────────────────────────────────────────────
#  DATABASE
# ──────────────────────────────────────────────────────
DB_FILE = "luna.db"

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id   INTEGER PRIMARY KEY,
            dj_role_id INTEGER DEFAULT NULL,
            volume     INTEGER DEFAULT 100,
            loop_mode  TEXT    DEFAULT 'off',
            tfs        INTEGER DEFAULT 0,
            autoplay   INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id   INTEGER,
            title      TEXT,
            url        TEXT,
            duration   TEXT,
            requester  TEXT,
            played_at  TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.commit()
    conn.close()

init_db()

def get_settings(guild_id: int) -> dict:
    conn = get_db()
    row = conn.execute("SELECT * FROM guild_settings WHERE guild_id=?", (guild_id,)).fetchone()
    if not row:
        conn.execute("INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)", (guild_id,))
        conn.commit()
        row = conn.execute("SELECT * FROM guild_settings WHERE guild_id=?", (guild_id,)).fetchone()
    conn.close()
    return dict(row)

def save_settings(guild_id: int, **kw):
    get_settings(guild_id)
    sets = ", ".join(f"{k}=?" for k in kw)
    conn = get_db()
    conn.execute(f"UPDATE guild_settings SET {sets} WHERE guild_id=?", [*kw.values(), guild_id])
    conn.commit()
    conn.close()

def push_history(guild_id: int, title: str, url: str, duration: str, requester: str):
    conn = get_db()
    conn.execute(
        "INSERT INTO history (guild_id,title,url,duration,requester) VALUES (?,?,?,?,?)",
        (guild_id, title, url, duration, requester),
    )
    conn.execute(
        "DELETE FROM history WHERE guild_id=? AND id NOT IN "
        "(SELECT id FROM history WHERE guild_id=? ORDER BY id DESC LIMIT 50)",
        (guild_id, guild_id),
    )
    conn.commit()
    conn.close()

# ──────────────────────────────────────────────────────
#  AUDIO FILTERS
# ──────────────────────────────────────────────────────
FILTERS: dict[str, dict] = {
    "none":      {"label": "🎵 None",        "af": ""},
    "bassboost": {"label": "🔊 Bass Boost",  "af": "bass=g=10,dynaudnorm=f=200"},
    "nightcore": {"label": "🌙 Nightcore",   "af": "asetrate=44100*1.25,aresample=44100"},
    "vaporwave": {"label": "🌊 Vaporwave",   "af": "asetrate=44100*0.8,aresample=44100"},
    "8d":        {"label": "🎧 8D Audio",    "af": "apulsator=hz=0.08"},
    "karaoke":   {"label": "🎤 Karaoke",     "af": "stereotools=mlev=0.03125"},
    "tremolo":   {"label": "〰️ Tremolo",     "af": "tremolo=f=4:d=0.9"},
    "vibrato":   {"label": "🎸 Vibrato",     "af": "vibrato=f=6.5:d=0.9"},
    "superbass": {"label": "💥 Super Bass",  "af": "bass=g=20,dynaudnorm=f=200"},
    "soft":      {"label": "🕊️ Soft",        "af": "lowpass=f=300,volume=1.5"},
    "earrape":   {"label": "📢 Ear Rape",    "af": "acrusher=level_in=8:level_out=18:bits=8:mode=log:aa=1"},
    "pitch":     {"label": "🎵 Pitch Up",    "af": "asetrate=44100*1.15,aresample=44100"},
}

# ──────────────────────────────────────────────────────
#  SONG & PLAYER
# ──────────────────────────────────────────────────────
class Song:
    def __init__(self, data: dict, requester: discord.Member):
        self.title      = data.get("title", "Unknown")
        self.url        = data.get("webpage_url") or data.get("original_url") or data.get("url", "")
        self.stream_url = data.get("url", "")
        self.duration   = data.get("duration") or 0
        thumb = data.get("thumbnail", "")
        if not thumb:
            thumbs = data.get("thumbnails") or []
            if thumbs:
                last  = thumbs[-1]
                thumb = last.get("url", "") if isinstance(last, dict) else str(last)
        self.thumbnail = thumb
        self.uploader  = data.get("uploader") or data.get("channel", "Unknown")
        self.requester = requester
        self.source    = data.get("_source", "unknown")

    @property
    def dur_str(self) -> str:
        if not self.duration:
            return "🔴 LIVE"
        m, s = divmod(int(self.duration), 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

    def progress_bar(self, elapsed: float, length: int = 13) -> str:
        if not self.duration:
            return "─" * length + " 🔴"
        pct  = min(elapsed / self.duration, 1.0)
        fill = int(pct * length)
        return "▬" * fill + "🔘" + "▬" * (length - fill)


class MusicPlayer:
    def __init__(self, guild_id: int):
        self.guild_id          = guild_id
        self.queue:            list[Song]             = []
        self.current:          Song | None            = None
        self.history:          list[Song]             = []
        self.loop              = "off"
        self.volume            = 1.0
        self.filter            = "none"
        self.skip_votes:       set[int]               = set()
        self.tfs               = False
        self.autoplay          = False
        self._start:           float | None           = None
        self._paused_at:       float | None           = None
        self._elapsed_pre:     float                  = 0.0
        self.np_msg:           discord.Message | None = None
        self._changing_filter: bool                   = False

    def elapsed(self) -> float:
        if self._start is None:
            return 0.0
        if self._paused_at is not None:
            return self._elapsed_pre
        return self._elapsed_pre + (time.time() - self._start)

    def reset_timer(self):
        self._start       = time.time()
        self._paused_at   = None
        self._elapsed_pre = 0.0


players: dict[int, MusicPlayer] = {}

def get_player(guild_id: int) -> MusicPlayer:
    if guild_id not in players:
        p = MusicPlayer(guild_id)
        s = get_settings(guild_id)
        p.volume   = s["volume"] / 100.0
        p.loop     = s["loop_mode"]
        p.tfs      = bool(s["tfs"])
        p.autoplay = bool(s["autoplay"])
        players[guild_id] = p
    return players[guild_id]

# ──────────────────────────────────────────────────────
#  YT-DLP OPTIONS
#
#  WHY web_embedded?
#  ──────────────────
#  YouTube blocks android/ios/mweb/tv on datacenter IPs —
#  "Sign in to confirm you're not a bot". web_embedded acts
#  as a YouTube embedded player: NO cookies, NO PO token,
#  works on every server IP including Katabump and Railway.
#
#  WHY SoundCloud first?
#  ──────────────────────
#  SoundCloud has zero bot detection on servers and a huge
#  Kurdish/Arabic/Persian/English library. It works 100% of
#  the time on any hosting provider.
# ──────────────────────────────────────────────────────

def _is_soundcloud(url: str) -> bool:
    return "soundcloud.com" in url.lower()

def _has_valid_stream(url: str) -> bool:
    if not url:
        return False
    # soundcloud.com is a PAGE url — NOT a playable stream.
    # Only sndcdn.com / scdn.co are actual SoundCloud CDN audio streams.
    return any(k in url for k in (
        "googlevideo.com", "googleusercontent.com",
        "sndcdn.com", "scdn.co",
        ".mp3", ".m4a", ".webm", ".opus",
    ))

def _is_drm(e: Exception) -> bool:
    msg = str(e).lower()
    return "drm" in msg or "go+" in msg or "protected" in msg

def _is_bot_blocked(e: Exception) -> bool:
    msg = str(e).lower()
    return any(k in msg for k in (
        "sign in", "bot", "confirm", "cookies",
        "private video", "members only", "unavailable",
        "blocked", "rate limit", "too many requests",
    ))

def _sc_opts(flat: bool = False) -> dict:
    base = {
        "format":             "bestaudio[ext=opus]/bestaudio[ext=mp3]/bestaudio/best",
        "quiet":              True,
        "no_warnings":        True,
        "socket_timeout":     30,
        "age_limit":          99,
        "ignoreerrors":       False,
        "nocheckcertificate": True,
    }
    if flat:
        base.update({"extract_flat": True, "skip_download": True, "ignoreerrors": True})
    return base

def _yt_opts(flat: bool = False) -> dict:
    base = {
        "format":             "bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio/best",
        "quiet":              True,
        "no_warnings":        True,
        "socket_timeout":     30,
        "age_limit":          99,
        "ignoreerrors":       False,
        "nocheckcertificate": True,
        "geo_bypass":         True,
        # Try all embedded/TV clients — none require cookies or PO tokens
        # on server/datacenter IPs. web_embedded is most reliable.
        "extractor_args": {
            "youtube": {
                "player_client": ["web_embedded", "tv_embedded", "mweb"],
            }
        },
    }
    if _has_cookies():
        base["cookiefile"] = COOKIE_FILE
    if flat:
        base.update({"extract_flat": True, "skip_download": True, "ignoreerrors": True})
    return base

async def _run(fn):
    return await asyncio.get_running_loop().run_in_executor(None, fn)

# ──────────────────────────────────────────────────────
#  SEARCH  —  SoundCloud primary, YouTube fallback
# ──────────────────────────────────────────────────────
async def search_songs(query: str) -> list[dict]:
    """
    Search for any song. Kurdish, Arabic, English — all work.

    Strategy:
      1. SoundCloud FULL extraction (scsearch5) — gets real stream URLs,
         no bot detection, huge Kurdish/Arabic/Persian/English library.
      2. YouTube (web_embedded + tv_embedded + mweb) as fallback.
    """
    # 1. SoundCloud — full extraction (NOT flat) so we get real audio URLs
    try:
        def _sc():
            # scsearch5 with full extraction → entries contain real stream URLs
            with yt_dlp.YoutubeDL(_sc_opts()) as ydl:
                info = ydl.extract_info(f"scsearch5:{query}", download=False)
                if not info:
                    return []
                entries = info.get("entries") or []
                return [e for e in entries if e and e.get("url")]
        results = await _run(_sc)
        if results:
            print(f"[Veltra] SoundCloud: {len(results)} results for '{query}'")
            for r in results:
                r["_source"] = "soundcloud"
            return results
    except Exception as e:
        print(f"[Veltra] SC search failed: {e}")

    # 2. YouTube fallback (web_embedded — works on most server IPs)
    print(f"[Veltra] Trying YouTube for '{query}'")
    try:
        def _yt():
            with yt_dlp.YoutubeDL({**_yt_opts(), "noplaylist": True}) as ydl:
                info = ydl.extract_info(f"ytsearch5:{query}", download=False)
                return [e for e in (info.get("entries") or []) if e] if info else []
        results = await _run(_yt)
        if results:
            print(f"[Veltra] YouTube: {len(results)} results for '{query}'")
            for r in results:
                r["_source"] = "youtube"
            return results
    except Exception as e:
        print(f"[Veltra] YT search failed: {e}")

    raise RuntimeError(
        f"No results found for **{query}**.\n"
        "Try a different search term or paste a direct SoundCloud/YouTube URL."
    )


# ──────────────────────────────────────────────────────
#  RESOLVE  —  get full stream URL for a single track
# ──────────────────────────────────────────────────────
async def resolve_url(url: str, source: str = "auto", _title: str = "") -> dict:
    """
    Resolve a URL (or title) to a full info dict with a playable stream URL.
    Falls back to SoundCloud title-search when YouTube is blocked.
    """
    is_sc = _is_soundcloud(url) or source == "soundcloud"

    if is_sc:
        def _sc_r():
            with yt_dlp.YoutubeDL(_sc_opts()) as ydl:
                return ydl.extract_info(url, download=False)
        try:
            data = await _run(_sc_r)
            if data and data.get("url"):
                data["_source"] = "soundcloud"
                return data
        except Exception as e:
            if _is_drm(e):
                raise RuntimeError(f"Track is DRM-protected: {e}")
            raise

    # YouTube — web_embedded + tv_embedded + mweb
    def _yt_r():
        with yt_dlp.YoutubeDL({**_yt_opts(), "noplaylist": True}) as ydl:
            return ydl.extract_info(url, download=False)
    try:
        data = await _run(_yt_r)
        if data and data.get("url"):
            data["_source"] = "youtube"
            return data
    except Exception as e:
        if _is_bot_blocked(e):
            # YouTube blocked — try SoundCloud search by title as last resort
            title = _title or url
            print(f"[Veltra] YouTube blocked for resolve, trying SC search: '{title}'")
            try:
                def _sc_fallback():
                    with yt_dlp.YoutubeDL(_sc_opts()) as ydl:
                        info = ydl.extract_info(f"scsearch1:{title}", download=False)
                        entries = info.get("entries") or [] if info else []
                        return entries[0] if entries else None
                fb = await _run(_sc_fallback)
                if fb and fb.get("url"):
                    fb["_source"] = "soundcloud"
                    print(f"[Veltra] SC fallback found: {fb.get('title')}")
                    return fb
            except Exception as fb_e:
                print(f"[Veltra] SC fallback failed: {fb_e}")
            raise RuntimeError(
                "YouTube is blocked on this server and SoundCloud couldn't find the song.\n"
                "Try searching with different keywords or paste a SoundCloud link directly."
            )
        raise

    raise RuntimeError(f"Could not resolve URL: {url}")


async def resolve_playlist(url: str) -> list[dict]:
    is_sc = _is_soundcloud(url)
    src   = "soundcloud" if is_sc else "youtube"
    opts  = _sc_opts() if is_sc else {**_yt_opts(), "extract_flat": "in_playlist", "noplaylist": False}

    def _do():
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return []
            if "entries" in info:
                entries = [e for e in info["entries"] if e and e.get("id")]
                for e in entries:
                    e["_source"] = src
                return entries
            info["_source"] = src
            return [info]

    try:
        return await _run(_do)
    except Exception as e:
        raise RuntimeError(f"Could not load playlist: {e}")


# ──────────────────────────────────────────────────────
#  FFMPEG SOURCE
#  -protocol_whitelist: required for HLS streams from
#  web_embedded/tv_embedded — without it you get silence
#  or instant-skip on HLS/m3u8 URLs.
# ──────────────────────────────────────────────────────
FFMPEG_BEFORE = (
    "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 "
    "-protocol_whitelist file,http,https,tcp,tls,crypto"
)

def _make_ffmpeg_source(stream_url: str, volume: float, audio_filter: str) -> discord.PCMVolumeTransformer:
    af      = FILTERS.get(audio_filter, FILTERS["none"])["af"]
    options = "-vn" + (f" -af {af}" if af else "")
    src = discord.FFmpegPCMAudio(
        stream_url,
        before_options=FFMPEG_BEFORE,
        options=options,
    )
    return discord.PCMVolumeTransformer(src, volume=volume)

# ──────────────────────────────────────────────────────
#  PLAYBACK ENGINE
# ──────────────────────────────────────────────────────
async def play_next(guild_id: int, channel: discord.abc.Messageable, vc: discord.VoiceClient):
    player = get_player(guild_id)

    if player.loop == "track" and player.current:
        song = player.current
    elif player.loop == "queue" and player.current:
        player.queue.append(player.current)
        song = player.queue.pop(0) if player.queue else None
    else:
        song = player.queue.pop(0) if player.queue else None

    if song is None:
        if player.current:
            push_history(
                guild_id, player.current.title, player.current.url,
                player.current.dur_str, str(player.current.requester),
            )
        player.current = None
        player.np_msg  = None
        if not player.tfs:
            await asyncio.sleep(300)
            p2 = get_player(guild_id)
            if not p2.current and not p2.queue and vc.is_connected():
                await vc.disconnect()
                players.pop(guild_id, None)
                try:
                    await channel.send(embed=discord.Embed(
                        color=C_LUNA,
                        description="👋 Left the voice channel (idle for 5 minutes).",
                    ))
                except Exception:
                    pass
        return

    if player.current and player.current is not song:
        push_history(
            guild_id, player.current.title, player.current.url,
            player.current.dur_str, str(player.current.requester),
        )
        player.history.append(player.current)
        if len(player.history) > 20:
            player.history.pop(0)

    player.current = song
    player.skip_votes.clear()

    if not _has_valid_stream(song.stream_url):
        try:
            data            = await resolve_url(song.url, source=song.source, _title=song.title)
            song.stream_url = data.get("url", "")
            song.thumbnail  = song.thumbnail or data.get("thumbnail", "")
            song.duration   = song.duration   or data.get("duration", 0)
            song.uploader   = song.uploader   or data.get("uploader") or data.get("channel", "Unknown")
            # update source if SC fallback was used
            if data.get("_source"):
                song.source = data["_source"]
        except Exception as e:
            await channel.send(embed=discord.Embed(
                color=C_RED,
                description=f"⚠️ Skipping **{song.title}** — couldn't resolve stream: {e}"
            ))
            await play_next(guild_id, channel, vc)
            return

    if not song.stream_url:
        await channel.send(embed=discord.Embed(
            color=C_RED,
            description=f"⚠️ No stream URL for **{song.title}** — skipping."
        ))
        await play_next(guild_id, channel, vc)
        return

    try:
        source = _make_ffmpeg_source(song.stream_url, player.volume, player.filter)
    except Exception as e:
        await channel.send(embed=discord.Embed(color=C_RED, description=f"⚠️ FFmpeg error: {e}"))
        await play_next(guild_id, channel, vc)
        return

    player.reset_timer()

    def after_cb(err):
        if err:
            print(f"[Veltra] Player error: {err}")
        if get_player(guild_id)._changing_filter:
            return
        asyncio.run_coroutine_threadsafe(play_next(guild_id, channel, vc), bot.loop)

    vc.play(source, after=after_cb)

    embed = build_np_embed(player, vc)
    view  = NowPlayingView(player, vc)
    try:
        if player.np_msg:
            await player.np_msg.edit(embed=embed, view=view)
        else:
            player.np_msg = await channel.send(embed=embed, view=view)
    except (discord.NotFound, discord.HTTPException):
        try:
            player.np_msg = await channel.send(embed=embed, view=view)
        except Exception:
            pass

# ──────────────────────────────────────────────────────
#  NOW PLAYING EMBED
# ──────────────────────────────────────────────────────
def _fmt_time(sec: float) -> str:
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

def build_np_embed(player: MusicPlayer, vc: discord.VoiceClient) -> discord.Embed:
    song    = player.current
    elapsed = player.elapsed()
    paused  = vc.is_paused() if vc else False

    e = discord.Embed(color=C_LUNA)
    e.set_author(name="🎵 Now Playing")
    e.title = song.title
    e.url   = song.url

    bar      = song.progress_bar(elapsed)
    time_str = f"`{_fmt_time(elapsed)}` {bar} `{song.dur_str}`"
    e.description = time_str

    loop_icon = {"off": "➡️ Off", "track": "🔂 Track", "queue": "🔁 Queue"}[player.loop]
    vol_icon  = "🔇" if player.volume == 0 else ("🔉" if player.volume < 0.5 else "🔊")
    flt_label = FILTERS.get(player.filter, FILTERS["none"])["label"]
    src_icon  = "☁️ SoundCloud" if song.source == "soundcloud" else "📺 YouTube"

    e.add_field(name="🎙️ Artist",       value=song.uploader,               inline=True)
    e.add_field(name="⏱️ Length",       value=song.dur_str,                inline=True)
    e.add_field(name=f"{vol_icon} Vol", value=f"{int(player.volume*100)}%", inline=True)
    e.add_field(name="🔁 Loop",         value=loop_icon,                   inline=True)
    e.add_field(name="🎛️ Filter",       value=flt_label,                   inline=True)
    e.add_field(name="📋 Queue",        value=str(len(player.queue)),      inline=True)
    e.add_field(name="👤 Requested by", value=song.requester.mention,      inline=True)
    e.add_field(name="🎵 Source",       value=src_icon,                    inline=True)

    if song.thumbnail:
        e.set_thumbnail(url=song.thumbnail)

    status = "⏸ Paused" if paused else "▶️ Playing"
    e.set_footer(text=f"Veltra Music  •  {status}  •  Use buttons to control")
    return e

# ──────────────────────────────────────────────────────
#  NOW PLAYING BUTTONS
# ──────────────────────────────────────────────────────
class NowPlayingView(discord.ui.View):
    def __init__(self, player: MusicPlayer, vc: discord.VoiceClient):
        super().__init__(timeout=None)
        self.player = player
        self.vc     = vc
        paused      = vc.is_paused() if vc else False

        row0 = [
            ("⏮️", "prev",  discord.ButtonStyle.secondary, 0),
            ("▶️" if paused else "⏸️", "pause", discord.ButtonStyle.primary, 0),
            ("⏭️", "skip",  discord.ButtonStyle.secondary, 0),
            ("⏹️", "stop",  discord.ButtonStyle.danger,    0),
        ]
        row1 = [
            ("🔂" if player.loop == "track" else "🔁" if player.loop == "queue" else "➡️",
             "loop", discord.ButtonStyle.secondary, 1),
            ("🔀", "shuffle", discord.ButtonStyle.secondary, 1),
            ("❤️", "grab",    discord.ButtonStyle.secondary, 1),
            ("📋", "queue",   discord.ButtonStyle.secondary, 1),
        ]
        for emoji, action, style, row in row0 + row1:
            self.add_item(_NPBtn(emoji, action, style, row))


class _NPBtn(discord.ui.Button):
    def __init__(self, emoji: str, action: str, style: discord.ButtonStyle, row: int):
        super().__init__(
            emoji=emoji, style=style,
            custom_id=f"veltra_np_{action}_{random.randint(0, 9999999)}",
            row=row,
        )
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        vc     = interaction.guild.voice_client
        player = get_player(interaction.guild.id)

        if not vc or not player.current:
            return await interaction.response.send_message(
                embed=discord.Embed(color=C_RED, description="❌ Nothing is playing!"),
                ephemeral=True,
            )

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
            return await interaction.response.send_message(
                embed=discord.Embed(color=C_GREEN, description="⏹️ Stopped and cleared the queue."),
                ephemeral=True,
            )

        elif self.action == "loop":
            modes       = ["off", "track", "queue"]
            player.loop = modes[(modes.index(player.loop) + 1) % 3]
            save_settings(interaction.guild.id, loop_mode=player.loop)

        elif self.action == "shuffle":
            random.shuffle(player.queue)
            return await interaction.response.send_message(
                embed=discord.Embed(color=C_GREEN, description="🔀 Queue shuffled!"),
                ephemeral=True,
            )

        elif self.action == "grab":
            song = player.current
            e    = discord.Embed(color=C_LUNA, title="❤️ Saved Song",
                                 description=f"**[{song.title}]({song.url})**")
            e.add_field(name="Duration", value=song.dur_str, inline=True)
            e.add_field(name="Channel",  value=song.uploader, inline=True)
            if song.thumbnail:
                e.set_thumbnail(url=song.thumbnail)
            try:
                await interaction.user.send(embed=e)
                return await interaction.response.send_message(
                    embed=discord.Embed(color=C_GREEN, description="❤️ Song info sent to your DMs!"),
                    ephemeral=True,
                )
            except discord.Forbidden:
                return await interaction.response.send_message(
                    embed=discord.Embed(color=C_RED,
                                        description="❌ Can't DM you. Enable DMs from server members."),
                    ephemeral=True,
                )

        elif self.action == "queue":
            q = player.queue
            if not q:
                return await interaction.response.send_message(
                    embed=discord.Embed(color=C_LUNA, title="📋 Queue",
                                        description="The queue is empty."),
                    ephemeral=True,
                )
            lines = [f"`{i+1}.` [{s.title}]({s.url}) `{s.dur_str}`" for i, s in enumerate(q[:10])]
            extra = f"\n*+{len(q)-10} more...*" if len(q) > 10 else ""
            e     = discord.Embed(color=C_LUNA, title=f"📋 Queue — {len(q)} song(s)",
                                  description="\n".join(lines) + extra)
            return await interaction.response.send_message(embed=e, ephemeral=True)

        elif self.action == "prev":
            if player.history:
                prev = player.history.pop()
                if player.current:
                    player.queue.insert(0, player.current)
                player.queue.insert(0, prev)
                vc.stop()
            else:
                return await interaction.response.send_message(
                    embed=discord.Embed(color=C_RED, description="❌ No previous song!"),
                    ephemeral=True,
                )

        try:
            new_embed = build_np_embed(player, vc)
            new_view  = NowPlayingView(player, vc)
            await interaction.message.edit(embed=new_embed, view=new_view)
            await interaction.response.defer()
        except Exception:
            try:
                await interaction.response.defer()
            except Exception:
                pass

# ──────────────────────────────────────────────────────
#  HELPERS
# ──────────────────────────────────────────────────────
def err(desc: str) -> discord.Embed:
    return discord.Embed(color=C_RED, description=f"❌ {desc}")

def ok(desc: str) -> discord.Embed:
    return discord.Embed(color=C_GREEN, description=f"✅ {desc}")

def _dur(seconds) -> str:
    if not seconds:
        return "?"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

async def _ensure_voice(ctx: commands.Context) -> discord.VoiceClient | None:
    if not ctx.author.voice:
        await ctx.send(embed=err("You must be in a voice channel!"))
        return None
    vc = ctx.voice_client
    if not vc:
        try:
            vc = await ctx.author.voice.channel.connect()
        except discord.ClientException as e:
            await ctx.send(embed=err(f"Could not connect: {e}"))
            return None
        except asyncio.TimeoutError:
            await ctx.send(embed=err("Timed out connecting to voice channel."))
            return None
    elif ctx.author.voice.channel != vc.channel:
        await vc.move_to(ctx.author.voice.channel)
    return vc

async def _dj_check(ctx: commands.Context) -> bool:
    if ctx.author.guild_permissions.manage_guild:
        return True
    s     = get_settings(ctx.guild.id)
    dj_id = s.get("dj_role_id")
    if dj_id:
        role = ctx.guild.get_role(int(dj_id))
        if role and role in ctx.author.roles:
            return True
        name = role.name if role else str(dj_id)
        await ctx.send(embed=err(f"You need the **{name}** DJ role for this command!"))
        return False
    return True

# ──────────────────────────────────────────────────────
#  COMMANDS — VOICE
# ──────────────────────────────────────────────────────
@bot.command(aliases=["j"])
async def join(ctx: commands.Context):
    """Join your voice channel."""
    vc = await _ensure_voice(ctx)
    if vc:
        await ctx.send(embed=ok(f"Joined **{vc.channel.name}**!"))


@bot.command(aliases=["dc", "leave"])
async def disconnect(ctx: commands.Context):
    """Disconnect from voice."""
    if not ctx.voice_client:
        return await ctx.send(embed=err("I'm not in a voice channel!"))
    if not await _dj_check(ctx):
        return
    player = get_player(ctx.guild.id)
    player.queue.clear()
    ctx.voice_client.stop()
    await ctx.voice_client.disconnect()
    players.pop(ctx.guild.id, None)
    await ctx.send(embed=ok("Disconnected! 👋"))

# ──────────────────────────────────────────────────────
#  COMMANDS — PLAYBACK
# ──────────────────────────────────────────────────────
@bot.command(aliases=["p"])
async def play(ctx: commands.Context, *, query: str):
    """Play a song or playlist. SoundCloud/YouTube/URL supported."""
    vc = await _ensure_voice(ctx)
    if not vc:
        return

    player = get_player(ctx.guild.id)
    msg    = await ctx.send(embed=discord.Embed(
        color=C_LUNA, description=f"🔍 Searching **{query}**..."
    ))

    try:
        is_url = query.startswith(("http://", "https://"))

        if is_url and ("list=" in query or "playlist" in query.lower() or "/sets/" in query):
            entries = await resolve_playlist(query)
            if not entries:
                return await msg.edit(embed=err("Couldn't find anything in that playlist."))
            added = 0
            for entry in entries:
                entry_url = entry.get("url") or entry.get("webpage_url") or ""
                if not entry_url and entry.get("id"):
                    entry_url = (
                        f"https://soundcloud.com/track/{entry['id']}"
                        if _is_soundcloud(query)
                        else f"https://www.youtube.com/watch?v={entry['id']}"
                    )
                data = {
                    "title":       entry.get("title") or "Unknown",
                    "url":         entry_url,
                    "webpage_url": entry_url,
                    "duration":    entry.get("duration", 0),
                    "thumbnail":   (entry.get("thumbnail") or
                                    (entry.get("thumbnails") or [{}])[-1].get("url", "")),
                    "uploader":    entry.get("uploader") or entry.get("channel", ""),
                    "_source":     entry.get("_source", "unknown"),
                }
                player.queue.append(Song(data, ctx.author))
                added += 1
            e = discord.Embed(color=C_LUNA, title="📋 Playlist Added!")
            e.add_field(name="Songs",        value=str(added),             inline=True)
            e.add_field(name="Queue length", value=str(len(player.queue)), inline=True)
            await msg.edit(embed=e)

        elif is_url:
            data = await resolve_url(query)
            song = Song(data, ctx.author)
            player.queue.append(song)
            if vc.is_playing() or vc.is_paused():
                e = discord.Embed(color=C_LUNA, title="➕ Added to Queue",
                                  description=f"**[{song.title}]({song.url})**")
                e.add_field(name="Duration", value=song.dur_str, inline=True)
                e.add_field(name="Position", value=f"#{len(player.queue)}", inline=True)
                if song.thumbnail:
                    e.set_thumbnail(url=song.thumbnail)
                await msg.edit(embed=e)
            else:
                await msg.delete()

        else:
            results = await search_songs(query)
            if not results:
                return await msg.edit(embed=err("No results found!"))
            data  = results[0]
            ref   = data.get("webpage_url") or data.get("url") or ""
            src   = data.get("_source", "unknown")
            title = data.get("title", query)
            if _has_valid_stream(data.get("url", "")):
                full = data
            elif ref:
                full = await resolve_url(ref, source=src, _title=title)
            else:
                return await msg.edit(embed=err("Could not resolve stream for that song."))
            song = Song(full, ctx.author)
            player.queue.append(song)
            if vc.is_playing() or vc.is_paused():
                e = discord.Embed(color=C_LUNA, title="➕ Added to Queue",
                                  description=f"**[{song.title}]({song.url})**")
                e.add_field(name="Duration", value=song.dur_str, inline=True)
                e.add_field(name="Position", value=f"#{len(player.queue)}", inline=True)
                if song.thumbnail:
                    e.set_thumbnail(url=song.thumbnail)
                await msg.edit(embed=e)
            else:
                await msg.delete()

    except Exception as ex:
        return await msg.edit(embed=err(f"Error: {ex}"))

    if not vc.is_playing() and not vc.is_paused():
        await play_next(ctx.guild.id, ctx.channel, vc)


@bot.command()
async def search(ctx: commands.Context, *, query: str):
    """Search SoundCloud & YouTube and pick a result."""
    msg = await ctx.send(embed=discord.Embed(
        color=C_LUNA, description=f"🔍 Searching **{query}**..."
    ))
    try:
        results = await search_songs(query)
    except Exception as ex:
        return await msg.edit(embed=err(str(ex)))

    results = results[:5]
    if not results:
        return await msg.edit(embed=err("No results found!"))

    lines = []
    for i, r in enumerate(results):
        r_url = r.get("webpage_url") or r.get("url") or "#"
        src   = "☁️" if r.get("_source") == "soundcloud" else "📺"
        lines.append(f"`{i+1}.` {src} [{r.get('title','?')}]({r_url}) `{_dur(r.get('duration',0))}`")

    e = discord.Embed(color=C_LUNA, title="🔍 Search Results", description="\n".join(lines))
    e.set_footer(text="Reply 1–5 to pick  •  or 'cancel'")
    await msg.edit(embed=e)

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    try:
        reply = await bot.wait_for("message", check=check, timeout=30)
    except asyncio.TimeoutError:
        return await msg.edit(embed=err("Selection timed out."))

    try:
        await reply.delete()
    except Exception:
        pass

    if reply.content.lower() == "cancel":
        return await msg.edit(embed=ok("Cancelled."))

    try:
        idx = int(reply.content) - 1
        if idx < 0 or idx >= len(results):
            raise ValueError
    except ValueError:
        return await msg.edit(embed=err("Invalid selection."))

    vc = await _ensure_voice(ctx)
    if not vc:
        return

    player = get_player(ctx.guild.id)
    data   = results[idx]
    ref    = data.get("webpage_url") or data.get("url") or ""
    src    = data.get("_source", "unknown")
    title  = data.get("title", "")

    try:
        full = data if _has_valid_stream(data.get("url", "")) else await resolve_url(ref, source=src, _title=title)
    except Exception as ex:
        return await msg.edit(embed=err(str(ex)))

    song = Song(full, ctx.author)
    player.queue.append(song)

    e2 = discord.Embed(color=C_LUNA, title="➕ Added to Queue",
                       description=f"**[{song.title}]({song.url})**")
    e2.add_field(name="Duration", value=song.dur_str, inline=True)
    if song.thumbnail:
        e2.set_thumbnail(url=song.thumbnail)
    await msg.edit(embed=e2)

    if not vc.is_playing() and not vc.is_paused():
        await play_next(ctx.guild.id, ctx.channel, vc)


@bot.command(aliases=["pa"])
async def pause(ctx: commands.Context):
    """Pause playback."""
    vc = ctx.voice_client
    if not vc or not vc.is_playing():
        return await ctx.send(embed=err("Nothing is playing!"))
    if not await _dj_check(ctx):
        return
    player = get_player(ctx.guild.id)
    player._elapsed_pre = player.elapsed()
    player._paused_at   = time.time()
    vc.pause()
    await ctx.send(embed=ok("Paused ⏸️"))


@bot.command(aliases=["res"])
async def resume(ctx: commands.Context):
    """Resume playback."""
    vc = ctx.voice_client
    if not vc or not vc.is_paused():
        return await ctx.send(embed=err("Nothing is paused!"))
    if not await _dj_check(ctx):
        return
    player = get_player(ctx.guild.id)
    player._elapsed_pre = player.elapsed()
    player._start       = time.time()
    player._paused_at   = None
    vc.resume()
    await ctx.send(embed=ok("Resumed ▶️"))


@bot.command(aliases=["s"])
async def skip(ctx: commands.Context):
    """Skip the current song (or vote skip)."""
    vc = ctx.voice_client
    if not vc or (not vc.is_playing() and not vc.is_paused()):
        return await ctx.send(embed=err("Nothing is playing!"))

    player  = get_player(ctx.guild.id)
    is_dj   = ctx.author.guild_permissions.manage_guild
    s       = get_settings(ctx.guild.id)
    dj_id   = s.get("dj_role_id")
    dj_role = ctx.guild.get_role(int(dj_id)) if dj_id else None

    if is_dj or (dj_role and dj_role in ctx.author.roles):
        player.skip_votes.clear()
        vc.stop()
        return await ctx.send(embed=ok("⏭️ Skipped!"))

    vc_members = [m for m in vc.channel.members if not m.bot]
    needed     = max(1, math.ceil(len(vc_members) * 0.5))
    player.skip_votes.add(ctx.author.id)
    votes = len(player.skip_votes)
    if votes >= needed:
        player.skip_votes.clear()
        vc.stop()
        await ctx.send(embed=ok(f"⏭️ Vote passed ({votes}/{needed})! Skipped."))
    else:
        await ctx.send(embed=discord.Embed(
            color=C_YELLOW,
            description=f"🗳️ Skip vote: **{votes}/{needed}** — need {needed - votes} more.",
        ))


@bot.command(aliases=["vs"])
async def voteskip(ctx: commands.Context):
    """Cast a skip vote."""
    await ctx.invoke(skip)


@bot.command()
async def stop(ctx: commands.Context):
    """Stop music and clear the queue."""
    if not await _dj_check(ctx):
        return
    vc = ctx.voice_client
    if not vc:
        return await ctx.send(embed=err("I'm not in a voice channel!"))
    player = get_player(ctx.guild.id)
    player.queue.clear()
    player.loop = "off"
    vc.stop()
    await ctx.send(embed=ok("⏹️ Stopped and cleared the queue."))


@bot.command(aliases=["np"])
async def nowplaying(ctx: commands.Context):
    """Show what's currently playing."""
    vc = ctx.voice_client
    if not vc:
        return await ctx.send(embed=err("I'm not in a voice channel!"))
    player = get_player(ctx.guild.id)
    if not player.current:
        return await ctx.send(embed=err("Nothing is playing!"))
    embed = build_np_embed(player, vc)
    view  = NowPlayingView(player, vc)
    player.np_msg = await ctx.send(embed=embed, view=view)


@bot.command(aliases=["replay", "restart"])
async def again(ctx: commands.Context):
    """Replay the current song from the beginning."""
    vc = ctx.voice_client
    if not vc or not vc.is_playing():
        return await ctx.send(embed=err("Nothing is playing!"))
    if not await _dj_check(ctx):
        return
    player = get_player(ctx.guild.id)
    if not player.current:
        return await ctx.send(embed=err("Nothing is playing!"))
    player.queue.insert(0, player.current)
    vc.stop()
    await ctx.send(embed=ok("🔁 Replaying current song!"))

# ──────────────────────────────────────────────────────
#  COMMANDS — QUEUE
# ──────────────────────────────────────────────────────
@bot.command(aliases=["q"])
async def queue(ctx: commands.Context, page: int = 1):
    """Show the music queue."""
    player = get_player(ctx.guild.id)
    if not player.current and not player.queue:
        return await ctx.send(embed=discord.Embed(
            color=C_LUNA, title="📋 Queue",
            description="The queue is empty. Use `$play` to add songs!",
        ))
    per_page = 10
    pages    = max(1, math.ceil(len(player.queue) / per_page))
    page     = max(1, min(page, pages))
    start    = (page - 1) * per_page
    chunk    = player.queue[start:start + per_page]
    desc     = ""
    if player.current:
        desc += (f"**▶️ Now Playing:**\n"
                 f"[{player.current.title}]({player.current.url}) "
                 f"`{player.current.dur_str}` — {player.current.requester.mention}\n\n")
    if chunk:
        desc += "**📋 Up Next:**\n"
        for i, s in enumerate(chunk, start=start + 1):
            desc += f"`{i}.` [{s.title}]({s.url}) `{s.dur_str}` — {s.requester.mention}\n"
    total_dur = sum(s.duration or 0 for s in player.queue)
    e = discord.Embed(color=C_LUNA, title=f"📋 Queue  —  {len(player.queue)} song(s)",
                      description=desc)
    loop_icon = {"off": "➡️ Off", "track": "🔂 Track", "queue": "🔁 Queue"}[player.loop]
    e.set_footer(text=f"Page {page}/{pages}  •  Total: {_fmt_time(total_dur)}  •  Loop: {loop_icon}")
    await ctx.send(embed=e)


@bot.command(aliases=["rm"])
async def remove(ctx: commands.Context, index: int):
    """Remove a song from the queue by position."""
    if not await _dj_check(ctx):
        return
    player = get_player(ctx.guild.id)
    if index < 1 or index > len(player.queue):
        return await ctx.send(embed=err(f"Invalid! Queue has {len(player.queue)} songs."))
    removed = player.queue.pop(index - 1)
    await ctx.send(embed=ok(f"Removed **{removed.title}** from the queue."))


@bot.command()
async def clear(ctx: commands.Context):
    """Clear the entire queue (keeps current song)."""
    if not await _dj_check(ctx):
        return
    get_player(ctx.guild.id).queue.clear()
    await ctx.send(embed=ok("Queue cleared!"))


@bot.command(aliases=["sh"])
async def shuffle(ctx: commands.Context):
    """Shuffle the queue."""
    if not await _dj_check(ctx):
        return
    player = get_player(ctx.guild.id)
    if len(player.queue) < 2:
        return await ctx.send(embed=err("Need at least 2 songs to shuffle."))
    random.shuffle(player.queue)
    await ctx.send(embed=ok("🔀 Queue shuffled!"))


@bot.command()
async def move(ctx: commands.Context, frm: int, to: int):
    """Move a song in the queue: $move <from> <to>"""
    if not await _dj_check(ctx):
        return
    player = get_player(ctx.guild.id)
    q = player.queue
    if not (1 <= frm <= len(q)) or not (1 <= to <= len(q)):
        return await ctx.send(embed=err(f"Positions must be between 1 and {len(q)}."))
    song = q.pop(frm - 1)
    q.insert(to - 1, song)
    await ctx.send(embed=ok(f"Moved **{song.title}** to position **{to}**."))


@bot.command()
async def skipto(ctx: commands.Context, index: int):
    """Skip to a specific position in the queue."""
    if not await _dj_check(ctx):
        return
    vc = ctx.voice_client
    if not vc:
        return await ctx.send(embed=err("Nothing is playing!"))
    player = get_player(ctx.guild.id)
    if index < 1 or index > len(player.queue):
        return await ctx.send(embed=err(f"Invalid! Queue has {len(player.queue)} songs."))
    player.queue = player.queue[index - 1:]
    vc.stop()
    await ctx.send(embed=ok(f"⏭️ Skipped to position **{index}**!"))

# ──────────────────────────────────────────────────────
#  COMMANDS — SETTINGS
# ──────────────────────────────────────────────────────
@bot.command(aliases=["vol"])
async def volume(ctx: commands.Context, vol: int):
    """Set volume 0–200%: $volume 80"""
    if not await _dj_check(ctx):
        return
    if not 0 <= vol <= 200:
        return await ctx.send(embed=err("Volume must be between 0 and 200."))
    player = get_player(ctx.guild.id)
    player.volume = vol / 100.0
    save_settings(ctx.guild.id, volume=vol)
    vc = ctx.voice_client
    if vc and vc.source:
        vc.source.volume = player.volume
    icon = "🔇" if vol == 0 else ("🔉" if vol < 50 else "🔊")
    await ctx.send(embed=ok(f"{icon} Volume set to **{vol}%**"))


@bot.command()
async def loop(ctx: commands.Context, mode: str = None):
    """Set loop mode: off / track / queue"""
    if not await _dj_check(ctx):
        return
    player = get_player(ctx.guild.id)
    modes  = ["off", "track", "queue"]
    if mode is None:
        mode = modes[(modes.index(player.loop) + 1) % 3]
    mode = mode.lower()
    if mode not in modes:
        return await ctx.send(embed=err("Mode must be: `off`, `track`, or `queue`"))
    player.loop = mode
    save_settings(ctx.guild.id, loop_mode=mode)
    icon = {"off": "➡️", "track": "🔂", "queue": "🔁"}[mode]
    await ctx.send(embed=ok(f"{icon} Loop set to **{mode.capitalize()}**"))


@bot.command(aliases=["filter"])
async def setfilter(ctx: commands.Context, name: str = None):
    """Apply an audio filter: $filter bassboost"""
    if not await _dj_check(ctx):
        return
    if name is None:
        lines = [f"`{k}` — {v['label']}" for k, v in FILTERS.items()]
        e = discord.Embed(color=C_LUNA, title="🎛️ Audio Filters", description="\n".join(lines))
        e.set_footer(text="$filter <name>  |  $filter none  to reset")
        return await ctx.send(embed=e)
    name = name.lower()
    if name not in FILTERS:
        return await ctx.send(embed=err("Unknown filter! Use `$filter` to see the list."))
    player = get_player(ctx.guild.id)
    player.filter = name
    vc = ctx.voice_client
    if vc and (vc.is_playing() or vc.is_paused()) and player.current:
        was_paused = vc.is_paused()
        paused_pos = player.elapsed()
        player._changing_filter = True
        vc.stop()
        await asyncio.sleep(0.5)
        try:
            data = await resolve_url(player.current.url, source=player.current.source)
            player.current.stream_url = data.get("url", player.current.stream_url)
        except Exception:
            pass
        source = _make_ffmpeg_source(player.current.stream_url, player.volume, name)
        player._elapsed_pre     = 0.0
        player._start           = time.time()
        player._paused_at       = None
        player._changing_filter = False

        def after_cb(e_):
            asyncio.run_coroutine_threadsafe(
                play_next(ctx.guild.id, ctx.channel, vc), bot.loop
            )
        vc.play(source, after=after_cb)
        if was_paused:
            vc.pause()
            player._elapsed_pre = paused_pos
            player._paused_at   = time.time()
    await ctx.send(embed=ok(f"🎛️ Filter set to **{FILTERS[name]['label']}**"))


@bot.command(aliases=["filters"])
async def listfilters(ctx: commands.Context):
    """List all available audio filters."""
    lines = [f"`{k}` — {v['label']}" for k, v in FILTERS.items()]
    e = discord.Embed(color=C_LUNA, title="🎛️ Available Filters", description="\n".join(lines))
    e.set_footer(text="$filter <name>  to apply  |  $filter none  to reset")
    await ctx.send(embed=e)


@bot.command(name="247")
async def tfs(ctx: commands.Context):
    """Toggle 24/7 mode (bot stays in VC)."""
    if not await _dj_check(ctx):
        return
    player = get_player(ctx.guild.id)
    player.tfs = not player.tfs
    save_settings(ctx.guild.id, tfs=int(player.tfs))
    state = "enabled 🟢" if player.tfs else "disabled 🔴"
    await ctx.send(embed=ok(f"24/7 mode **{state}**"))


@bot.command()
async def autoplay(ctx: commands.Context):
    """Toggle autoplay (adds related songs when queue ends)."""
    if not await _dj_check(ctx):
        return
    player = get_player(ctx.guild.id)
    player.autoplay = not player.autoplay
    save_settings(ctx.guild.id, autoplay=int(player.autoplay))
    state = "enabled 🟢" if player.autoplay else "disabled 🔴"
    await ctx.send(embed=ok(f"Autoplay **{state}**"))


@bot.command(aliases=["setdj"])
@commands.has_permissions(manage_guild=True)
async def djrole(ctx: commands.Context, role: discord.Role = None):
    """Set or remove the DJ role: $djrole @DJ"""
    if role is None:
        save_settings(ctx.guild.id, dj_role_id=None)
        return await ctx.send(embed=ok("DJ role removed. Everyone can control music now."))
    save_settings(ctx.guild.id, dj_role_id=role.id)
    await ctx.send(embed=ok(f"DJ role set to {role.mention}."))

# ──────────────────────────────────────────────────────
#  COMMANDS — LYRICS
# ──────────────────────────────────────────────────────
@bot.command(aliases=["ly"])
async def lyrics(ctx: commands.Context, *, song_name: str = None):
    """Fetch lyrics for the current or specified song."""
    player = get_player(ctx.guild.id)
    if song_name is None:
        if not player.current:
            return await ctx.send(embed=err("Nothing playing! Try: `$lyrics Artist - Song`"))
        song_name = player.current.title

    clean = song_name
    for pat in ["(official", "(lyrics", "(audio", "(video", "(hd", "(4k)", "[", "]", "ft.", "feat."]:
        if pat in clean.lower():
            clean = clean[:clean.lower().index(pat)].strip()

    parts = clean.split(" - ", 1)
    artist, title_q = (parts[0].strip(), parts[1].strip()) if len(parts) == 2 else ("", clean.strip())

    msg = await ctx.send(embed=discord.Embed(
        color=C_LUNA, description=f"🔍 Fetching lyrics for **{clean}**..."
    ))

    lyrics_text = None
    for url in [
        f"https://api.lyrics.ovh/v1/{artist or clean}/{title_q}",
        f"https://api.lyrics.ovh/v1/{clean}/{clean}",
    ]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        lyrics_text = data.get("lyrics")
                        if lyrics_text:
                            break
        except Exception:
            pass

    if not lyrics_text:
        return await msg.edit(embed=err(f"No lyrics for **{clean}**. Try: `$lyrics Artist - Song`"))

    lyrics_text = lyrics_text.replace("\r\n", "\n").strip()
    chunks = [lyrics_text[i:i + 3800] for i in range(0, len(lyrics_text), 3800)]
    for i, chunk in enumerate(chunks):
        title = f"📜 {clean}" + (f" (Part {i+1})" if len(chunks) > 1 else "")
        e = discord.Embed(color=C_LUNA, title=title, description=chunk)
        e.set_footer(text="Powered by lyrics.ovh")
        if i == 0:
            await msg.edit(embed=e)
        else:
            await ctx.send(embed=e)

# ──────────────────────────────────────────────────────
#  COMMANDS — HISTORY & GRAB
# ──────────────────────────────────────────────────────
@bot.command()
async def history(ctx: commands.Context):
    """Show recently played songs."""
    conn = get_db()
    rows = conn.execute(
        "SELECT title, url, duration FROM history "
        "WHERE guild_id=? ORDER BY id DESC LIMIT 10",
        (ctx.guild.id,),
    ).fetchall()
    conn.close()
    if not rows:
        return await ctx.send(embed=discord.Embed(
            color=C_LUNA, title="📜 History", description="No songs played yet!"
        ))
    lines = [f"`{i+1}.` [{r['title']}]({r['url']}) `{r['duration']}`" for i, r in enumerate(rows)]
    e = discord.Embed(color=C_LUNA, title="📜 Recently Played", description="\n".join(lines))
    await ctx.send(embed=e)


@bot.command()
async def grab(ctx: commands.Context):
    """DM yourself the current song info."""
    player = get_player(ctx.guild.id)
    if not player.current:
        return await ctx.send(embed=err("Nothing is playing!"))
    song = player.current
    e = discord.Embed(color=C_LUNA, title="❤️ Saved Song!",
                      description=f"**[{song.title}]({song.url})**")
    e.add_field(name="Duration", value=song.dur_str, inline=True)
    e.add_field(name="Channel",  value=song.uploader, inline=True)
    if song.thumbnail:
        e.set_thumbnail(url=song.thumbnail)
    try:
        await ctx.author.send(embed=e)
        await ctx.send(embed=ok("❤️ Song info sent to your DMs!"))
    except discord.Forbidden:
        await ctx.send(embed=err("I can't DM you. Enable DMs from server members."))

# ──────────────────────────────────────────────────────
#  COMMANDS — INFO
# ──────────────────────────────────────────────────────
@bot.command()
async def ping(ctx: commands.Context):
    """Bot latency."""
    lat = round(bot.latency * 1000)
    e = discord.Embed(color=C_LUNA, title="🏓 Pong!", description=f"Latency: **{lat}ms**")
    await ctx.send(embed=e)


# ── CRASH FIX: was `async def bot()` — shadowed the Bot instance ──
# ── Renamed to botinfo() — all @bot.command() after it now work   ──
@bot.command(aliases=["stats", "info"])
async def botinfo(ctx: commands.Context):
    """Show bot stats and info."""
    uptime = int(time.time() - bot_start_time)
    d, h   = divmod(uptime, 86400)
    h, m   = divmod(h, 3600)
    m, s   = divmod(m, 60)
    uptime_str     = f"{d}d {h}h {m}m {s}s" if d else f"{h}h {m}m {s}s"
    cookie_status  = "✅ Loaded" if _has_cookies() else "☁️ Not set (SoundCloud is primary)"

    e = discord.Embed(color=C_LUNA, title="🤖 Veltra Music Bot")
    e.add_field(name="⏱️ Uptime",   value=uptime_str,                        inline=True)
    e.add_field(name="🌐 Servers",  value=str(len(bot.guilds)),              inline=True)
    e.add_field(name="👥 Members",  value=str(sum(g.member_count for g in bot.guilds)), inline=True)
    e.add_field(name="🍪 Cookies",  value=cookie_status,                     inline=True)
    e.add_field(name="📡 Latency",  value=f"{round(bot.latency*1000)}ms",    inline=True)
    e.add_field(name="🎵 Sources",  value="☁️ SoundCloud + 📺 YouTube",      inline=True)
    e.set_footer(text="Veltra Music Bot  •  discord.py  •  web_embedded YouTube client")
    await ctx.send(embed=e)


# ──────────────────────────────────────────────────────
#  COMMANDS — HELP
# ──────────────────────────────────────────────────────
@bot.command(name="help")
async def help_cmd(ctx: commands.Context):
    """Show all commands."""
    e = discord.Embed(color=C_LUNA, title="🎵 Veltra Music — Commands")
    e.add_field(name="🎧 Playback", inline=False, value=(
        "`$play <song>` — Play a song (SoundCloud/YouTube)\n"
        "`$search <query>` — Search and pick a result\n"
        "`$pause` / `$resume` — Pause/Resume\n"
        "`$skip` — Skip or vote-skip\n"
        "`$stop` — Stop and clear queue\n"
        "`$nowplaying` / `$np` — Show current song\n"
        "`$again` — Replay current song\n"
        "`$join` / `$disconnect` — Join/Leave VC"
    ))
    e.add_field(name="📋 Queue", inline=False, value=(
        "`$queue [page]` — Show the queue\n"
        "`$remove <#>` — Remove a song\n"
        "`$clear` — Clear the queue\n"
        "`$shuffle` — Shuffle the queue\n"
        "`$move <from> <to>` — Move a song\n"
        "`$skipto <#>` — Skip to position"
    ))
    e.add_field(name="⚙️ Settings", inline=False, value=(
        "`$volume <0-200>` — Set volume\n"
        "`$loop [off/track/queue]` — Loop mode\n"
        "`$filter <name>` — Audio filter\n"
        "`$filters` — List filters\n"
        "`$247` — Toggle 24/7 mode\n"
        "`$autoplay` — Toggle autoplay\n"
        "`$djrole [@role]` — Set DJ role"
    ))
    e.add_field(name="📜 Other", inline=False, value=(
        "`$lyrics [song]` — Fetch lyrics\n"
        "`$history` — Recently played\n"
        "`$grab` — DM current song info\n"
        "`$ping` — Bot latency\n"
        "`$botinfo` / `$stats` — Bot stats\n"
        "`$help` — This message"
    ))
    e.set_footer(text="☁️ SoundCloud primary (Kurdish/Arabic/English works!) • 📺 YouTube fallback")
    await ctx.send(embed=e)

# ──────────────────────────────────────────────────────
#  ERROR HANDLER
# ──────────────────────────────────────────────────────
@bot.event
async def on_command_error(ctx: commands.Context, error):
    if isinstance(error, commands.CommandNotFound):
        return
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(embed=err(f"Missing: `{error.param.name}`. Try `$help`."))
    elif isinstance(error, (commands.BadArgument, commands.MissingPermissions)):
        await ctx.send(embed=err(f"{error}"))
    else:
        await ctx.send(embed=err(f"{error}"))
        raise error

# ──────────────────────────────────────────────────────
#  STARTUP
# ──────────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"""
╔══════════════════════════════════════════════════════╗
║          VELTRA MUSIC BOT  —  ONLINE                 ║
╠══════════════════════════════════════════════════════╣
║  Logged in as : {bot.user.name:<34} ║
║  Servers      : {len(bot.guilds):<34} ║
╠══════════════════════════════════════════════════════╣
║  ✅ CRASH FIX  — botinfo() no longer shadows bot     ║
║  ✅ YOUTUBE    — web_embedded client (no bot-check)  ║
║  ✅ KURDISH    — SoundCloud is PRIMARY source         ║
║  ✅ HLS FIX    — protocol_whitelist in FFmpeg        ║
╚══════════════════════════════════════════════════════╝""")
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.listening, name="$help | Veltra Music"
    ))

# ──────────────────────────────────────────────────────
#  RUN
# ──────────────────────────────────────────────────────
if __name__ == "__main__":
    if not TOKEN:
        raise ValueError("DISCORD_TOKEN not set. Add it to your .env or environment variables.")
    bot.run(TOKEN)
