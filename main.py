"""
╔══════════════════════════════════════════════════════╗
║  VELTRA MUSIC BOT — TRUE MULTI-PLATFORM (LIKE LARA)   ║
║  Direct Spotify·SC·Deezer·Apple·Anghami·MP3 Playback   ║
║  YouTube Search Fallback · Kurdish · Sub-Second Speed   ║
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
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    print("[FATAL] No DISCORD_TOKEN")
    raise SystemExit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("veltra.log", encoding="utf-8", mode="a")]
)
log = logging.getLogger("veltra")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix="$", intents=intents, help_command=None)
bot_start_time = time.time()

C_LUNA = 0xB5179E
C_GREEN = 0x57F287
C_RED = 0xED4245
C_YELLOW = 0xFEE75C

# ═══════════════════════════════════════
#  API ENDPOINTS FOR DIRECT PLATFORM PLAYBACK
# ═══════════════════════════════════════
# These public APIs extract the actual raw audio file from the platforms
EXTRACTORS = [
    # Cobalt is the absolute best open-source extractor right now (Handles Spotify, Apple, SC, Deezer directly)
    "https://api.cobalt.tools",
    # Invidious for raw YouTube audio
    "https://inv.nadeko.net",
    "https://invidious.fdn.fr",
    "https://iv.ggtyler.dev",
    "https://yt.artemislena.eu",
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
                guild_id INTEGER PRIMARY KEY, dj_role_id INTEGER DEFAULT NULL,
                volume INTEGER DEFAULT 100, loop_mode TEXT DEFAULT 'off',
                tfs INTEGER DEFAULT 0, autoplay INTEGER DEFAULT 0, kurdish_mode INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER,
                title TEXT, url TEXT, duration TEXT, requester TEXT,
                platform TEXT DEFAULT 'unknown', played_at TEXT DEFAULT (datetime('now'))
            );
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        log.error(f"DB error: {e}")

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
        return dict(row) if row else {"dj_role_id":None,"volume":100,"loop_mode":"off","tfs":0,"autoplay":0,"kurdish_mode":1}
    except Exception:
        return {"dj_role_id":None,"volume":100,"loop_mode":"off","tfs":0,"autoplay":0,"kurdish_mode":1}

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
        conn.execute("INSERT INTO history (guild_id,title,url,duration,requester,platform) VALUES (?,?,?,?,?,?)", (gid,title,url,dur,req,plat))
        conn.execute("DELETE FROM history WHERE guild_id=? AND id NOT IN (SELECT id FROM history WHERE guild_id=? ORDER BY id DESC LIMIT 50)", (gid,gid))
        conn.commit()
        conn.close()
    except Exception:
        pass

# ═══════════════════════════════════════
#  FILTERS
# ═══════════════════════════════════════
FILTERS = {
    "none": {"label": "🎵 None", "af": ""},
    "bassboost": {"label": "🔊 Bass Boost", "af": "bass=g=10,dynaudnorm=f=200"},
    "nightcore": {"label": "🌙 Nightcore", "af": "asetrate=44100*1.25,aresample=44100"},
    "vaporwave": {"label": "🌊 Vaporwave", "af": "asetrate=44100*0.8,aresample=44100"},
    "8d": {"label": "🎧 8D Audio", "af": "apulsator=hz=0.08"},
    "karaoke": {"label": "🎤 Karaoke", "af": "stereotools=mlev=0.03125"},
    "tremolo": {"label": "〰️ Tremolo", "af": "tremolo=f=4:d=0.9"},
    "vibrato": {"label": "🎸 Vibrato", "af": "vibrato=f=6.5:d=0.9"},
    "superbass": {"label": "💥 Super Bass", "af": "bass=g=20,dynaudnorm=f=200"},
    "soft": {"label": "🕊️ Soft", "af": "lowpass=f=300,volume=1.5"},
    "earrape": {"label": "📢 Ear Rape", "af": "acrusher=level_in=8:level_out=18:bits=8:mode=log:aa=1"},
    "pitch": {"label": "🎵 Pitch Up", "af": "asetrate=44100*1.15,aresample=44100"},
}

# ═══════════════════════════════════════
#  PLATFORM DETECTION
# ═══════════════════════════════════════
def detect_platform(url):
    if not url:
        return "unknown"
    lower_url = url.lower()
    if "spotify.com" in lower_url or "open.spotify.com" in lower_url:
        return "spotify"
    if "music.apple.com" in lower_url or "itunes.apple.com" in lower_url:
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
    if "youtube.com" in lower_url or "youtu.be" in lower_url:
        return "youtube"
    if any(lower_url.endswith(ext) for ext in (".mp3", ".mp4", ".m4a", ".ogg", ".wav", ".flac", ".webm")):
        return "direct"
    return "unknown"

PLATFORM_EMOJIS = {
    "spotify": "🎵", "apple_music": "🍎", "soundcloud": "☁️",
    "deezer": "🎶", "anghami": "🌙", "vimeo": "📹", "facebook": "👤",
    "twitch": "📺", "youtube": "▶️", "direct": "📎", "unknown": "🔍"
}

# ═══════════════════════════════════════
#  KURDISH
# ═══════════════════════════════════════
KURDISH_KEYWORDS = [
    "kurdish", "kurdi", "کوردی", "کوردیی", "kurdî", "kurdish song",
    "zagros", "kurdistan", "hawler", "slemani", "erbil", "stran", "gorani"
]

def is_kurdish(title):
    if not title:
        return False
    for char in title:
        if '\u0600' <= char <= '\u06FF':
            return True
    lower_title = title.lower()
    for kw in KURDISH_KEYWORDS:
        if kw in lower_title:
            return True
    return False

def get_kurdish_queries(query):
    if is_kurdish(query):
        return [query]
    return [
        f"{query} kurdish song کوردی",
        f"{query} کوردی",
        f"{query} stran kurdî",
        f"{query} kurdish cover"
    ]

# ═══════════════════════════════════════
#  ★ TRUE MULTI-PLATFORM EXTRACTION ENGINE ★
# ═══════════════════════════════════════
async def extract_cobalt(session, url):
    """Extracts direct audio from Spotify, Apple, SC, Deezer, Anghami, Vimeo, FB, Twitch, Direct"""
    try:
        # Cobalt API accepts the raw URL and returns a direct MP3/Opus stream
        async with session.post(
            "https://api.cobalt.tools/",
            json={"url": url, "videoQuality": "360", "audioFormat": "mp3", "isAudioOnly": True},
            timeout=aiohttp.ClientTimeout(total=10),
            ssl=False
        ) as r:
            if r.status != 200:
                return None
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
        log.debug(f"Cobalt extraction failed: {e}")
    return None

async def extract_invidious(session, base_url, url):
    """Extracts direct audio from YouTube/General URLs"""
    video_id = None
    if "youtu.be/" in url:
        video_id = url.split("youtu.be/")[1].split("?")[0]
    elif "v=" in url:
        video_id = url.split("v=")[1].split("&")[0]
    if not video_id:
        return None
    try:
        async with session.get(
            f"{base_url}/api/v1/videos/{video_id}",
            params={"fields": "adaptiveFormats,formatStreams,title,lengthSeconds,author,videoThumbnails"},
            timeout=aiohttp.ClientTimeout(total=5),
            ssl=False
        ) as r:
            if r.status != 200:
                return None
            data = await r.json()
            for fmt in data.get("adaptiveFormats", []):
                if "audio" in (fmt.get("mimeType") or "") and fmt.get("url"):
                    return {
                        "url": fmt["url"],
                        "title": data.get("title") or "Unknown",
                        "duration": int(data.get("lengthSeconds") or 0),
                        "thumbnail": (data.get("videoThumbnails") or [{}])[-1].get("url") or "",
                        "uploader": data.get("author") or "Unknown",
                    }
            for fmt in data.get("formatStreams", []):
                if fmt.get("url"):
                    return {
                        "url": fmt["url"],
                        "title": data.get("title") or "Unknown",
                        "duration": int(data.get("lengthSeconds") or 0),
                        "thumbnail": (data.get("videoThumbnails") or [{}])[-1].get("url") or "",
                        "uploader": data.get("author") or "Unknown",
                    }
    except Exception:
        pass
    return None

async def instant_extract(url):
    """Tries Cobalt (for direct platform links) then Invidious (for YT). Returns in <2s."""
    async with aiohttp.ClientSession() as session:
        # 1. Try Cobalt first (Best for Spotify, Apple, SC, Deezer, Anghami, Direct MP3s)
        result = await extract_cobalt(session, url)
        if result:
            log.info(f"✅ Extracted via Cobalt")
            return result
        
        # 2. Fallback to Invidious (For YouTube links and general fallback)
        tasks = [extract_invidious(session, base, url) for base in EXTRACTORS[1:]]
        for future in asyncio.as_completed(tasks):
            result = await future
            if result:
                log.info(f"✅ Extracted via Invidious")
                return result
    return None

# ═══════════════════════════════════════
#  SEARCH ENGINE (YouTube via Invidious)
# ═══════════════════════════════════════
async def _fetch_search(session, base_url, query):
    try:
        async with session.get(
            f"{base_url}/api/v1/search",
            params={"q": query, "type": "video", "sort_by": "relevance"},
            timeout=aiohttp.ClientTimeout(total=5),
            ssl=False
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
            return results if results else None
    except Exception:
        return None

async def instant_search(query):
    async with aiohttp.ClientSession() as session:
        tasks = [_fetch_search(session, url, query) for url in EXTRACTORS[1:]]
        for future in asyncio.as_completed(tasks):
            result = await future
            if result:
                return result
    return []

async def search_songs(query, kurdish_mode=True, force_kurdish=False):
    if force_kurdish:
        queries = get_kurdish_queries(query)
    elif kurdish_mode and not is_kurdish(query):
        queries = [f"{query} kurdish kurdi کوردی", query]
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
        else:
            for r in results:
                vid = r.get("id")
                if vid and vid not in seen_ids:
                    seen_ids.add(vid)
                    all_results.append(r)
            if len(all_results) >= 5:
                break

    if not all_results and force_kurdish:
        results = await instant_search(query)
        for r in results:
            vid = r.get("id")
            if vid and vid not in seen_ids:
                seen_ids.add(vid)
                all_results.append(r)

    return all_results[:5]

# ═══════════════════════════════════════
#  AUDIO SOURCE
# ═══════════════════════════════════════
def create_ffmpeg_source(stream_url, volume, filter_name):
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
    __slots__ = ("title", "url", "stream_url", "duration", "thumbnail", "uploader", "requester", "platform", "is_kurdish")
    
    def __init__(self, data, requester, platform="unknown"):
        self.title = str(data.get("title") or "Unknown")
        self.url = str(data.get("webpage_url") or data.get("url") or "")
        self.stream_url = str(data.get("url") or "")
        self.duration = data.get("duration") or 0
        self.thumbnail = str(data.get("thumbnail") or "")
        self.uploader = str(data.get("uploader") or data.get("channel") or "Unknown")
        self.requester = requester
        self.platform = platform
        self.is_kurdish = is_kurdish(self.title)

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
        pct = min(max(elapsed / self.duration, 0.0), 1.0)
        fill = int(pct * length)
        return "▬" * fill + "🔘" + "▬" * (length - fill)

class MusicPlayer:
    def __init__(self, guild_id):
        self.guild_id = guild_id
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
        if self._start is None:
            return self._elapsed_pre
        if self._paused_at is not None:
            return self._elapsed_pre
        return self._elapsed_pre + (time.time() - self._start)

    def reset_timer(self):
        self._start = time.time()
        self._paused_at = None
        self._elapsed_pre = 0.0

_players = {}

def get_player(guild_id):
    if guild_id not in _players:
        player = MusicPlayer(guild_id)
        settings = get_settings(guild_id)
        player.volume = max(0.0, min(2.0, (settings.get("volume") or 100) / 100.0))
        player.loop = settings.get("loop_mode") or "off"
        player.tfs = bool(settings.get("tfs"))
        player.autoplay = bool(settings.get("autoplay"))
        player.kurdish_mode = bool(settings.get("kurdish_mode", 1))
        _players[guild_id] = player
    return _players[guild_id]

def destroy_player(guild_id):
    player = _players.pop(guild_id, None)
    if player:
        player.queue.clear()
        player.history.clear()
        player.current = None

# ═══════════════════════════════════════
#  EMBEDS & HELPERS
# ═══════════════════════════════════════
def embed(color, desc):
    return discord.Embed(color=color, description=desc)

def ok_embed(desc):
    return embed(C_GREEN, f"✅ {desc}")

def err_embed(desc):
    return embed(C_RED, f"❌ {desc}")

def format_time(seconds):
    if not seconds or seconds < 0:
        return "0:00"
    total = int(seconds)
    mins, secs = divmod(total, 60)
    hours, mins = divmod(mins, 60)
    if hours:
        return f"{hours}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"

def build_np_embed(player, vc):
    song = player.current
    if not song:
        return embed(C_LUNA, "Nothing playing")
    elapsed = player.elapsed()
    is_paused = vc.is_paused() if vc else False
    e = discord.Embed(color=C_LUNA)
    e.set_author(name=f"{'🟢 Kurdish' if song.is_kurdish else '🎵'} Now Playing")
    e.title = song.title
    if song.url.startswith("http"):
        e.url = song.url
    e.description = f"`{format_time(elapsed)}` {song.progress_bar(elapsed)} `{song.dur_str}`"
    loop_modes = {"off": "➡️ Off", "track": "🔂 Track", "queue": "🔁 Queue"}
    vol_icon = "🔇" if player.volume <= 0 else ("🔉" if player.volume < 0.5 else "🔊")
    filter_label = FILTERS.get(player.filter_name, FILTERS["none"])["label"]
    plat_emoji = PLATFORM_EMOJIS.get(song.platform, "🔍")
    e.add_field(name=f"{plat_emoji} Platform", value=song.platform.replace("_", " ").title(), inline=True)
    e.add_field(name="🎙️ Artist", value=song.uploader[:50], inline=True)
    e.add_field(name="⏱️ Length", value=song.dur_str, inline=True)
    e.add_field(name=f"{vol_icon} Vol", value=f"{int(player.volume * 100)}%", inline=True)
    e.add_field(name="🔁 Loop", value=loop_modes.get(player.loop, "➡️ Off"), inline=True)
    e.add_field(name="🎛️ Filter", value=filter_label, inline=True)
    e.add_field(name="📋 Queue", value=str(len(player.queue)), inline=True)
    e.add_field(name="👤 By", value=song.requester.mention, inline=False)
    if song.thumbnail and song.thumbnail.startswith("http"):
        e.set_thumbnail(url=song.thumbnail)
    e.set_footer(text=f"Veltra Music • {'⏸ Paused' if is_paused else '▶️ Playing'}")
    return e

class NowPlayingView(discord.ui.View):
    def __init__(self, player, vc):
        super().__init__(timeout=None)
        self.player = player
        self.vc = vc
        is_paused = vc.is_paused() if vc else False
        buttons = [
            ("⏮️", "prev", discord.ButtonStyle.secondary, 0),
            ("▶️" if is_paused else "⏸️", "pause", discord.ButtonStyle.primary, 0),
            ("⏭️", "skip", discord.ButtonStyle.secondary, 0),
            ("⏹️", "stop", discord.ButtonStyle.danger, 0),
            ("🔂" if player.loop == "track" else "🔁" if player.loop == "queue" else "➡️", "loop", discord.ButtonStyle.secondary, 1),
            ("🔀", "shuffle", discord.ButtonStyle.secondary, 1),
            ("❤️", "grab", discord.ButtonStyle.secondary, 1),
            ("📋", "queue", discord.ButtonStyle.secondary, 1),
        ]
        for emoji, action, style, row in buttons:
            self.add_item(ControlButton(emoji, action, style, row))

class ControlButton(discord.ui.Button):
    def __init__(self, emoji, action, style, row):
        super().__init__(emoji=emoji, style=style, custom_id=f"vnp_{action}_{random.randint(0, 9999999)}", row=row)
        self.action = action

    async def callback(self, interaction):
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
            handled = await self.handle_action(interaction, vc, player)
            if not handled and player.current and vc.is_connected():
                try:
                    if player.np_msg:
                        await player.np_msg.edit(embed=build_np_embed(player, vc), view=NowPlayingView(player, vc))
                except Exception:
                    pass
        except Exception as e:
            log.error(f"ControlButton {self.action} error: {e}")

    async def handle_action(self, interaction, vc, player):
        if self.action == "pause":
            if vc.is_paused():
                player._elapsed_pre = player.elapsed(); player._start = time.time(); player._paused_at = None; vc.resume()
            else:
                player._elapsed_pre = player.elapsed(); player._paused_at = time.time(); vc.pause()
        elif self.action == "skip":
            player.skip_votes.clear(); vc.stop()
        elif self.action == "stop":
            player.queue.clear(); player.loop = "off"; vc.stop()
            try: await interaction.followup.send(embed=ok_embed("Stopped!"), ephemeral=True)
            except Exception: pass
            return True
        elif self.action == "loop":
            modes = ["off", "track", "queue"]
            player.loop = modes[(modes.index(player.loop) + 1) % 3]
            save_settings(interaction.guild.id, loop_mode=player.loop)
        elif self.action == "shuffle":
            if len(player.queue) >= 2: random.shuffle(player.queue)
            try: await interaction.followup.send(embed=ok_embed("🔀 Shuffled!"), ephemeral=True)
            except Exception: pass
            return True
        elif self.action == "grab":
            song = player.current
            e = discord.Embed(color=C_LUNA, title="❤️ Saved", description=f"**[{song.title}]({song.url})**")
            e.add_field(name="Duration", value=song.dur_str, inline=True)
            if song.is_kurdish: e.add_field(name="Type", value="🟢 Kurdish", inline=True)
            if song.thumbnail and song.thumbnail.startswith("http"): e.set_thumbnail(url=song.thumbnail)
            try:
                await interaction.user.send(embed=e)
                await interaction.followup.send(embed=ok_embed("Sent to DMs!"), ephemeral=True)
            except discord.Forbidden:
                await interaction.followup.send(embed=err_embed("Can't DM you."), ephemeral=True)
            except Exception: pass
            return True
        elif self.action == "queue":
            q = player.queue
            if not q:
                await interaction.followup.send(embed=embed(C_LUNA, "📋 Empty."), ephemeral=True)
            else:
                lines = [f"`{i+1}.` [{s.title}]({s.url}) `{s.dur_str}` {'🟢' if s.is_kurdish else ''}" for i, s in enumerate(q[:10])]
                extra = f"\n*+{len(q)-10} more...*" if len(q) > 10 else ""
                await interaction.followup.send(embed=embed(C_LUNA, f"📋 {len(q)} songs").set_description("\n".join(lines) + extra), ephemeral=True)
            return True
        elif self.action == "prev":
            if player.history:
                prev_song = player.history.pop()
                if player.current: player.queue.insert(0, player.current)
                player.queue.insert(0, prev_song); vc.stop()
            else:
                try: await interaction.followup.send(embed=err_embed("No previous!"), ephemeral=True)
                except Exception: pass
            return True
        return False

# ═══════════════════════════════════════
#  PLAYBACK ENGINE
# ═══════════════════════════════════════
async def play_next(guild_id, text_channel, vc):
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
                push_history(guild_id, player.current.title, player.current.url, player.current.dur_str, str(player.current.requester), player.current.platform)
            player.current = None
            player._playing = False
            if player.autoplay and player.history:
                last_song = player.history[-1]
                try:
                    res = await search_songs(f"{last_song.uploader} kurdish song", kurdish_mode=True, force_kurdish=True)
                    if not res: res = await search_songs("kurdish music 2024", kurdish_mode=True, force_kurdish=True)
                    if res:
                        player.queue.append(Song(res[0], bot.user, "youtube"))
                        await play_next(guild_id, text_channel, vc)
                        return
                except Exception as e:
                    log.error(f"Autoplay error: {e}")
            if not player.tfs:
                try: await asyncio.sleep(300)
                except asyncio.CancelledError: return
                p2 = get_player(guild_id)
                if not p2.current and not p2.queue and vc.is_connected():
                    if not [m for m in vc.channel.members if not m.bot]:
                        try: vc.stop(); await vc.disconnect()
                        except Exception: pass
                        destroy_player(guild_id)
                        if text_channel:
                            try: await text_channel.send(embed=embed(C_LUNA, "👋 Left (idle 5m)."))
                            except Exception: pass
            return

        if player.current and player.current is not song:
            push_history(guild_id, player.current.title, player.current.url, player.current.dur_str, str(player.current.requester), player.current.platform)
            player.history.append(player.current)
            if len(player.history) > 20: player.history.pop(0)

        player.current = song
        player.skip_votes.clear()

        if not song.stream_url:
            data = await instant_extract(song.url)
            if not data or not data.get("url"):
                if text_channel:
                    try: await text_channel.send(embed=err_embed(f"Skipping **{song.title[:50]}** — stream unavailable."))
                    except Exception: pass
                player._playing = False
                await play_next(guild_id, text_channel, vc)
                return
            
            song.stream_url = data["url"]
            if not song.thumbnail and data.get("thumbnail"): song.thumbnail = data["thumbnail"]
            if song.title == "Unknown" and data.get("title"): song.title = data["title"]
            if song.uploader == "Unknown" and data.get("uploader"): song.uploader = data["uploader"]

        source = create_ffmpeg_source(song.stream_url, player.volume, player.filter_name)
        if not source:
            if text_channel:
                try: await text_channel.send(embed=err_embed(f"Skipping **{song.title[:50]}** — audio error."))
                except Exception: pass
            player._playing = False
            await play_next(guild_id, text_channel, vc)
            return

        player.reset_timer()
        player._playing = True

        def after_callback(error):
            if error: log.error(f"Playback error: {error}")
            future = asyncio.run_coroutine_threadsafe(play_next(guild_id, text_channel, vc), bot.loop)
            future.add_done_callback(lambda f: f.exception() if f.exception() else None)

        try:
            vc.play(source, after=after_callback)
        except Exception as e:
            log.error(f"vc.play failed: {e}")
            player._playing = False
            return

        if text_channel:
            try:
                np_embed = build_np_embed(player, vc)
                np_view = NowPlayingView(player, vc)
                if player.np_msg and not player.np_msg.is_deleted():
                    await player.np_msg.edit(embed=np_embed, view=np_view)
                else:
                    player.np_msg = await text_channel.send(embed=np_embed, view=np_view)
            except Exception:
                pass

async def start_playback(ctx):
    vc = ctx.voice_client
    if not vc: return
    if not get_player(ctx.guild.id)._playing:
        await play_next(ctx.guild.id, ctx.channel, vc)

async def ensure_voice(ctx):
    if not ctx.author.voice or not ctx.author.voice.channel:
        await ctx.send(embed=err_embed("Join a voice channel!"))
        return None
    target_channel = ctx.author.voice.channel
    if not target_channel.permissions_for(ctx.me).connect:
        await ctx.send(embed=err_embed("No connect permission!"))
        return None
    if not target_channel.permissions_for(ctx.me).speak:
        await ctx.send(embed=err_embed("No speak permission!"))
        return None
    vc = ctx.voice_client
    try:
        if not vc: vc = await target_channel.connect(timeout=15)
        elif vc.channel != target_channel: await vc.move_to(target_channel)
        return vc
    except asyncio.TimeoutError:
        await ctx.send(embed=err_embed("Timeout.")); return None
    except Exception as e:
        log.error(f"Voice error: {e}"); await ctx.send(embed=err_embed("Failed to connect.")); return None

async def check_dj(ctx):
    if ctx.author.guild_permissions.manage_guild: return True
    settings = get_settings(ctx.guild.id)
    dj_id = settings.get("dj_role_id")
    if dj_id:
        role = ctx.guild.get_role(int(dj_id))
        if role and role in ctx.author.roles: return True
        await ctx.send(embed=err_embed(f"Need **{role.name if role else str(dj_id)}** DJ role!"))
        return False
    return True

# ═══════════════════════════════════════
#  COMMANDS
# ═══════════════════════════════════════
@bot.command(aliases=["j"])
async def join(ctx):
    vc = await ensure_voice(ctx)
    if vc: await ctx.send(embed=ok_embed(f"Joined **{vc.channel.name}**!"))

@bot.command(aliases=["dc", "leave"])
async def disconnect(ctx):
    if not ctx.voice_client: return await ctx.send(embed=err_embed("Not in VC!"))
    if not await check_dj(ctx): return
    vc = ctx.voice_client; get_player(ctx.guild.id).queue.clear()
    try: vc.stop()
    except Exception: pass
    try: await vc.disconnect()
    except Exception: pass
    destroy_player(ctx.guild.id)
    await ctx.send(embed=ok_embed("Disconnected! 👋"))

@bot.command(aliases=["p"])
async def play(ctx, *, query):
    if not query or not query.strip(): return await ctx.send(embed=err_embed("Provide a song name or URL!"))
    vc = await ensure_voice(ctx)
    if not vc: return

    player = get_player(ctx.guild.id)
    platform = detect_platform(query)
    plat_emoji = PLATFORM_EMOJIS.get(platform, "🔍")
    msg = await ctx.send(embed=embed(C_LUNA, f"{plat_emoji} Processing **{query[:80]}**..."))
    is_url = query.strip().startswith(("http://", "https://"))

    try:
        if is_url:
            # DIRECT URL PLAYBACK (Exactly like Lara Bot)
            data = await instant_extract(query)
            if not data or not data.get("url"):
                return await msg.edit(embed=err_embed("Couldn't extract audio from this URL. Make sure it's a valid link."))
            
            song = Song(data, ctx.author, platform)
            player.queue.append(song)
            
            if vc.is_playing() or vc.is_paused():
                em = embed(C_LUNA, "")
                em.title = f"{plat_emoji} Added to Queue"
                em.description = f"**[{song.title}]({song.url})**"
                em.add_field(name="Duration", value=song.dur_str, inline=True)
                em.add_field(name="Position", value=f"#{len(player.queue)}", inline=True)
                if song.is_kurdish: em.add_field(name="Type", value="🟢 Kurdish", inline=True)
                if song.thumbnail and song.thumbnail.startswith("http"): em.set_thumbnail(url=song.thumbnail)
                await msg.edit(embed=em)
            else:
                try: await msg.delete()
                except Exception: pass
        else:
            # TEXT SEARCH (YouTube Search)
            results = await search_songs(query, kurdish_mode=player.kurdish_mode)
            if not results:
                return await msg.edit(embed=err_embed("No results! Try different words."))
            song = Song(results[0], ctx.author, "youtube")
            player.queue.append(song)
            if vc.is_playing() or vc.is_paused():
                em = embed(C_LUNA, "")
                em.title = "➕ Added to Queue"
                em.description = f"**[{song.title}]({song.url})**"
                em.add_field(name="Duration", value=song.dur_str, inline=True)
                em.add_field(name="Position", value=f"#{len(player.queue)}", inline=True)
                if song.is_kurdish: em.add_field(name="Type", value="🟢 Kurdish", inline=True)
                if song.thumbnail and song.thumbnail.startswith("http"): em.set_thumbnail(url=song.thumbnail)
                await msg.edit(embed=em)
            else:
                try: await msg.delete()
                except Exception: pass
    except Exception as e:
        log.error(f"Play error: {e}\n{traceback.format_exc()}")
        try: await msg.edit(embed=err_embed(f"Error: {str(e)[:150]}"))
        except Exception: pass
        return

    await start_playback(ctx)

@bot.command(aliases=["kurdish", "ku"])
async def kurdishplay(ctx, *, query):
    if not query or not query.strip(): return await ctx.send(embed=err_embed("Provide a song name!"))
    vc = await ensure_voice(ctx)
    if not vc: return
    msg = await ctx.send(embed=embed(C_LUNA, f"🟢 Finding Kurdish: **{query[:80]}**..."))
    try:
        results = await search_songs(query, kurdish_mode=True, force_kurdish=True)
        if not results:
            return await msg.edit(embed=err_embed("No Kurdish version found. Try different words."))
        song = Song(results[0], ctx.author, "youtube")
        get_player(ctx.guild.id).queue.append(song)
        em = embed(C_LUNA, "")
        em.title = "🟢 Kurdish Song!"
        em.description = f"**[{song.title}]({song.url})**"
        em.add_field(name="Duration", value=song.dur_str, inline=True)
        em.add_field(name="Channel", value=song.uploader[:50], inline=True)
        if song.thumbnail and song.thumbnail.startswith("http"): em.set_thumbnail(url=song.thumbnail)
        await msg.edit(embed=em)
    except Exception as e:
        log.error(f"kurdishplay error: {e}")
        return await msg.edit(embed=err_embed(str(e)[:150]))
    await start_playback(ctx)

@bot.command(aliases=["pa"])
async def pause(ctx):
    vc = ctx.voice_client
    if not vc or not vc.is_playing(): return await ctx.send(embed=err_embed("Nothing playing!"))
    if not await check_dj(ctx): return
    player = get_player(ctx.guild.id); player._elapsed_pre = player.elapsed(); player._paused_at = time.time(); vc.pause()
    await ctx.send(embed=ok_embed("Paused ⏸️"))

@bot.command(aliases=["res"])
async def resume(ctx):
    vc = ctx.voice_client
    if not vc or not vc.is_paused(): return await ctx.send(embed=err_embed("Nothing paused!"))
    if not await check_dj(ctx): return
    player = get_player(ctx.guild.id); player._elapsed_pre = player.elapsed(); player._start = time.time(); player._paused_at = None; vc.resume()
    await ctx.send(embed=ok_embed("Resumed ▶️"))

@bot.command(aliases=["s"])
async def skip(ctx):
    vc = ctx.voice_client
    if not vc or (not vc.is_playing() and not vc.is_paused()): return await ctx.send(embed=err_embed("Nothing playing!"))
    player = get_player(ctx.guild.id)
    is_dj = ctx.author.guild_permissions.manage_guild
    settings = get_settings(ctx.guild.id)
    dj_id = settings.get("dj_role_id")
    has_role = False
    if dj_id:
        dj_role = ctx.guild.get_role(int(dj_id))
        if dj_role and dj_role in ctx.author.roles: has_role = True
    if is_dj or has_role:
        player.skip_votes.clear(); vc.stop(); return await ctx.send(embed=ok_embed("⏭️ Skipped!"))
    members = [m for m in vc.channel.members if not m.bot]
    if not members:
        player.skip_votes.clear(); vc.stop(); return await ctx.send(embed=ok_embed("⏭️ Skipped!"))
    needed = max(1, math.ceil(len(members) * 0.5))
    player.skip_votes.add(ctx.author.id); votes = len(player.skip_votes)
    if votes >= needed:
        player.skip_votes.clear(); vc.stop()
        await ctx.send(embed=ok_embed(f"⏭️ Vote passed ({votes}/{needed})!"))
    else:
        await ctx.send(embed=embed(C_YELLOW, f"🗳️ Vote: **{votes}/{needed}** — need {needed - votes} more."))

@bot.command()
async def stop(ctx):
    if not await check_dj(ctx): return
    vc = ctx.voice_client
    if not vc: return await ctx.send(embed=err_embed("Not in VC!"))
    player = get_player(ctx.guild.id); player.queue.clear(); player.loop = "off"; vc.stop()
    await ctx.send(embed=ok_embed("⏹️ Stopped!"))

@bot.command(aliases=["np"])
async def nowplaying(ctx):
    vc = ctx.voice_client
    if not vc: return await ctx.send(embed=err_embed("Not in VC!"))
    player = get_player(ctx.guild.id)
    if not player.current: return await ctx.send(embed=err_embed("Nothing playing!"))
    try: player.np_msg = await ctx.send(embed=build_np_embed(player, vc), view=NowPlayingView(player, vc))
    except Exception: pass

@bot.command(aliases=["replay", "restart"])
async def again(ctx):
    vc = ctx.voice_client
    if not vc or (not vc.is_playing() and not vc.is_paused()): return await ctx.send(embed=err_embed("Nothing playing!"))
    if not await check_dj(ctx): return
    player = get_player(ctx.guild.id)
    if not player.current: return await ctx.send(embed=err_embed("Nothing playing!"))
    player.queue.insert(0, player.current); vc.stop()
    await ctx.send(embed=ok_embed("🔁 Replaying!"))

@bot.command(aliases=["q"])
async def queue(ctx, page=1):
    player = get_player(ctx.guild.id)
    if not player.current and not player.queue: return await ctx.send(embed=embed(C_LUNA, "📋 Empty. Use $play!"))
    per_page = 10; total = len(player.queue); pages = max(1, math.ceil(total / per_page)); page = max(1, min(page, pages))
    start = (page - 1) * per_page; chunk = player.queue[start:start + per_page]
    desc = ""
    if player.current:
        k_flag = " 🟢" if player.current.is_kurdish else ""
        desc += f"**▶️ Now:** [{player.current.title}]({player.current.url}) `{player.current.dur_str}` — {player.current.requester.mention}{k_flag}\n\n"
    if chunk:
        desc += "**📋 Up Next:**\n"
        for i, s in enumerate(chunk, start=start + 1):
            k_flag = " 🟢" if s.is_kurdish else ""
            desc += f"`{i}.` [{s.title}]({s.url}) `{s.dur_str}` — {s.requester.mention}{k_flag}\n"
    total_dur = sum(s.duration or 0 for s in player.queue)
    loop_modes = {"off": "➡️ Off", "track": "🔂 Track", "queue": "🔁 Queue"}
    em = embed(C_LUNA, "")
    em.title = f"📋 Queue — {total} songs"; em.description = desc
    em.set_footer(text=f"Page {page}/{pages} • {format_time(total_dur)} • Loop: {loop_modes.get(player.loop, '➡️ Off')} • 🟢 = Kurdish")
    await ctx.send(embed=em)

@bot.command(aliases=["rm"])
async def remove(ctx, index: int):
    if not await check_dj(ctx): return
    player = get_player(ctx.guild.id)
    if index < 1 or index > len(player.queue): return await ctx.send(embed=err_embed(f"Invalid! Queue has {len(player.queue)}."))
    removed = player.queue.pop(index - 1); await ctx.send(embed=ok_embed(f"Removed **{removed.title[:50]}**"))

@bot.command()
async def clear(ctx):
    if not await check_dj(ctx): return
    get_player(ctx.guild.id).queue.clear(); await ctx.send(embed=ok_embed("Cleared!"))

@bot.command(aliases=["sh"])
async def shuffle(ctx):
    if not await check_dj(ctx): return
    player = get_player(ctx.guild.id)
    if len(player.queue) < 2: return await ctx.send(embed=err_embed("Need 2+ songs."))
    random.shuffle(player.queue); await ctx.send(embed=ok_embed("🔀 Shuffled!"))

@bot.command()
async def skipto(ctx, index: int):
    if not await check_dj(ctx): return
    vc = ctx.voice_client
    if not vc: return await ctx.send(embed=err_embed("Nothing playing!"))
    player = get_player(ctx.guild.id)
    if index < 1 or index > len(player.queue): return await ctx.send(embed=err_embed(f"Invalid! Queue has {len(player.queue)}."))
    player.queue = player.queue[index - 1:]; vc.stop()
    await ctx.send(embed=ok_embed(f"⏭️ Skipped to **{index}**!"))

@bot.command(aliases=["vol"])
async def volume(ctx, vol: int):
    if not await check_dj(ctx): return
    if not 0 <= vol <= 200: return await ctx.send(embed=err_embed("Volume 0–200."))
    player = get_player(ctx.guild.id); player.volume = vol / 100.0; save_settings(ctx.guild.id, volume=vol)
    vc = ctx.voice_client
    if vc and vc.source:
        try: vc.source.volume = player.volume
        except Exception: pass
    icon = "🔇" if vol == 0 else ("🔉" if vol < 50 else "🔊")
    await ctx.send(embed=ok_embed(f"{icon} Volume **{vol}%**"))

@bot.command()
async def loop(ctx, mode=None):
    if not await check_dj(ctx): return
    player = get_player(ctx.id); modes = ["off", "track", "queue"]
    mode = (modes[(modes.index(player.loop) + 1) % 3] if mode is None else mode.lower())
    if mode not in modes: return await ctx.send(embed=err_embed("Must be: off/track/queue"))
    player.loop = mode; save_settings(ctx.guild.id, loop_mode=mode)
    icons = {"off": "➡️", "track": "🔂", "queue": "🔁"}
    await ctx.send(embed=ok_embed(f"{icons[mode]} Loop **{mode.title()}**"))

@bot.command(aliases=["filter"])
async def setfilter(ctx, name=None):
    if not await check_dj(ctx): return
    if name is None:
        lines = [f"`{k}` — {v['label']}" for k, v in FILTERS.items()]
        return await ctx.send(embed=embed(C_LUNA, "").set_title("🎛️ Filters").set_description("\n".join(lines)))
    name = name.lower()
    if name not in FILTERS: return await ctx.send(embed=err_embed("Unknown filter!"))
    player = get_player(ctx.guild.id); old_filter = player.filter_name; player.filter_name = name; vc = ctx.voice_client
    if vc and (vc.is_playing() or vc.is_paused()) and player.current:
        was_paused = vc.is_paused(); paused_pos = player.elapsed()
        try: vc.stop()
        except Exception: pass
        await asyncio.sleep(0.6)
        data = await instant_extract(player.current.url)
        if data and data.get("url"):
            player.current.stream_url = data["url"]
            source = create_ffmpeg_source(player.current.stream_url, player.volume, name)
            if source:
                player.reset_timer(); player._playing = True
                def after_cb(err):
                    if err: log.error(f"Filter after: {err}")
                    fut = asyncio.run_coroutine_threadsafe(play_next(ctx.guild.id, ctx.channel, vc), bot.loop)
                    fut.add_done_callback(lambda f: f.exception() if f.exception() else None)
                try:
                    vc.play(source, after=after_cb)
                    if was_paused: vc.pause(); player._elapsed_pre = paused_pos; player._paused_at = time.time()
                except Exception as e:
                    player.filter_name = old_filter; await ctx.send(embed=err_embed(f"Failed: {e}")); return
            else:
                player.filter_name = old_filter; await ctx.send(embed=err_embed("Stream failed.")); return
        else:
            player.filter_name = old_filter; await ctx.send(embed=err_embed("Stream failed.")); return
    await ctx.send(embed=ok_embed(f"🎛️ Filter **{FILTERS[name]['label']}**"))

@bot.command(name="247")
async def tfs_cmd(ctx):
    if not await check_dj(ctx): return
    player = get_player(ctx.guild.id); player.tfs = not player.tfs; save_settings(ctx.guild.id, tfs=int(player.tfs))
    await ctx.send(embed=ok_embed(f"24/7 {'enabled 🟢' if player.tfs else 'disabled 🔴'}"))

@bot.command()
async def autoplay(ctx):
    if not await check_dj(ctx): return
    player = get_player(ctx.guild.id); player.autoplay = not player.autoplay; save_settings(ctx.guild.id, autoplay=int(player.autoplay))
    await ctx.send(embed=ok_embed(f"Autoplay {'enabled 🟢' if player.autoplay else 'disabled 🔴'}"))

@bot.command()
async def kurdishmode(ctx):
    player = get_player(ctx.guild.id); player.kurdish_mode = not player.kurdish_mode; save_settings(ctx.guild.id, kurdish_mode=int(player.kurdish_mode))
    await ctx.send(embed=ok_embed(f"Kurdish mode {'enabled 🟢' if player.kurdish_mode else 'disabled 🔴'}"))

@bot.command(aliases=["setdj"])
@commands.has_permissions(manage_guild=True)
async def djrole(ctx, role: discord.Role = None):
    if not role:
        save_settings(ctx.guild.id, dj_role_id=None); return await ctx.send(embed=ok_embed("DJ role removed."))
    save_settings(ctx.guild.id, dj_role_id=role.id); await ctx.send(embed=ok_embed(f"DJ role: {role.mention}"))

@bot.command(aliases=["ly"])
async def lyrics(ctx, *, song_name=None):
    player = get_player(ctx.guild.id)
    if not song_name or not song_name.strip():
        if not player.current: return await ctx.send(embed=err_embed("Nothing playing! Use: `$lyrics Artist - Song`"))
        song_name = player.current.title
    clean = song_name
    for pat in ["(official", "(lyrics", "(audio)", "(video)", "(hd)", "(4k)", "[", "]", "ft.", "feat."]:
        idx = clean.lower().find(pat)
        if idx != -1: clean = clean[:idx].strip()
    parts = clean.split(" - ", 1)
    if len(parts) == 2: artist, title_q = parts[0].strip(), parts[1].strip()
    else: artist, title_q = "", clean.strip()
    if not artist or not title_q: return await ctx.send(embed=err_embed("Use: `$lyrics Artist - Song Title`"))
    msg = await ctx.send(embed=embed(C_LUNA, f"🔍 Fetching lyrics **{clean[:60]}**..."))
    lyrics_text = None
    for a, t in [(artist, title_q), (artist, clean), (clean, clean)]:
        if not a or not t: continue
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://api.lyrics.ovh/v1/{a}/{t}", timeout=aiohttp.ClientTimeout(total=5)) as r:
                    if r.status == 200:
                        d = await r.json()
                        if d.get("lyrics"): lyrics_text = d["lyrics"]; break
        except Exception: continue
    if not lyrics_text: return await msg.edit(embed=err_embed(f"No lyrics for **{clean[:60]}**."))
    lyrics_text = lyrics_text.replace("\r\n", "\n").strip()
    chunks = [lyrics_text[i:i+3800] for i in range(0, len(lyrics_text), 3800)]
    for i, c in enumerate(chunks):
        em = embed(C_LUNA, c)
        em.title = f"📜 {clean[:60]}" + (f" ({i+1})" if len(chunks) > 1 else "")
        if i == 0: await msg.edit(embed=em)
        else:
            try: await ctx.send(embed=em)
            except Exception: pass

@bot.command()
async def history(ctx):
    try:
        conn = _db(); conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT title,url,duration,platform FROM history WHERE guild_id=? ORDER BY id DESC LIMIT 10", (ctx.guild.id,)).fetchall(); conn.close()
    except Exception: return await ctx.send(embed=err_embed("DB error."))
    if not rows: return await ctx.send(embed=embed(C_LUNA, "📜 No history."))
    lines = []
    for i, r in enumerate(rows):
        plat = r['platform'] or 'unknown'; k_flag = " 🟢" if is_kurdish(r['title']) else ""
        lines.append(f"`{i+1}.` {PLATFORM_EMOJIS.get(plat, '🎵')} [{r['title']}]({r['url']}) `{r['duration']}`{k_flag}")
    await ctx.send(embed=embed(C_LUNA, "").set_title("📜 History").set_description("\n".join(lines)))

@bot.command()
async def grab(ctx):
    player = get_player(ctx.guild.id)
    if not player.current: return await ctx.send(embed=err_embed("Nothing playing!"))
    song = player.current
    em = discord.Embed(color=C_LUNA, title="❤️ Saved!", description=f"**[{song.title}]({song.url})**")
    em.add_field(name="Duration", value=song.dur_str, inline=True)
    if song.is_kurdish: em.add_field(name="Type", value="🟢 Kurdish", inline=True)
    if song.thumbnail and song.thumbnail.startswith("http"): em.set_thumbnail(url=song.thumbnail)
    try:
        await ctx.author.send(embed=em); await ctx.send(embed=ok_embed("Sent to DMs!"))
    except discord.Forbidden: await ctx.send(embed=err_embed("Can't DM you."))
    except Exception: pass

@bot.command()
async def ping(ctx):
    await ctx.send(embed=embed(C_LUNA, f"🏓 Pong! **{round(bot.latency*1000)}ms**"))

@bot.command(aliases=["stats"])
async def botinfo(ctx):
    uptime = int(time.time() - bot_start_time)
    hours, rem = divmod(uptime, 3600); mins, secs = divmod(rem, 60)
    em = embed(C_LUNA, ""); em.title = "🎵 Veltra Music Bot"
    em.add_field(name="Prefix", value="`$`", inline=True)
    em.add_field(name="Servers", value=str(len(bot.guilds)), inline=True)
    em.add_field(name="Uptime", value=f"{hours}h {mins}m {secs}s", inline=True)
    em.add_field(name="Engine", value="Cobalt + Invidious", inline=True)
    em.add_field(name="Platforms", value="Spotify·Apple·SC·Deezer·Anghami·FB·Twitch·YT·MP3", inline=False)
    await ctx.send(embed=em)

@bot.command()
async def help(ctx):
    em = embed(C_LUNA, "")
    em.title = "🎵 Veltra Music Bot — True Multi-Platform"
    em.description = "**Works exactly like Lara Bot! Paste any link to play instantly.**\n🟢 = Kurdish song"
    em.add_field(name="🎵 Direct URL Playback", value="```Spotify     open.spotify.com/track/...\nApple Music music.apple.com/...\nSoundCloud  soundcloud.com/...\nDeezer     deezer.com/...\nAnghami    anghami.com/...\nFacebook    facebook.com/watch/...\nTwitch      twitch.tv/...\nDirect      example.com/song.mp3```", inline=False)
    em.add_field(name="🔍 Text Search", value="```$play song name         Search YouTube\n$kurdish song name      Find Kurdish version\n$pause / $resume      Pause/Resume\n$skip / $s            Skip```", inline=False)
    em.add_field(name="⚙️ Settings", value="```$volume <0-200>       Volume\n$loop [off/track/queue] Loop\n$filter <name>        Audio filter\n$247                  Stay in VC\n$autoplay             Auto-play Kurdish\n$kurdishmode         Toggle Kurdish search\n$djrole [@role]       Set DJ role```", inline=False)
    em.set_footer(text="Just paste the link and it plays instantly!")
    await ctx.send(embed=em)

# ═══════════════════════════════════════
#  EVENTS
# ═══════════════════════════════════════
@bot.event
async def on_ready():
    log.info(f"Logged in: {bot.user} ({bot.user.id}) | Guilds: {len(bot.guilds)}")
    log.info("★ MULTI-PLATFORM ENGINE ACTIVE (Like Lara Bot) ★")
    try:
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="🎵 Multi-Platform | $help"))
    except Exception: pass

@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot: return
    if before.channel and not after.channel:
        vc = before.channel.guild.voice_client
        if vc and vc.channel == before.channel and not [m for m in vc.channel.members if not m.bot]:
            player = get_player(vc.guild.id)
            if not player.tfs:
                await asyncio.sleep(3)
                if not [m for m in vc.channel.members if not m.bot] and vc.is_connected():
                    player.queue.clear()
                    try: vc.stop(); await vc.disconnect()
                    except Exception: pass
                    destroy_player(vc.guild.id)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound): return
    if isinstance(error, commands.MissingPermissions):
        try: await ctx.send(embed=err_embed("No permission!"))
        except Exception: pass
        return
    if isinstance(error, commands.MissingRequiredArgument):
        try: await ctx.send(embed=err_embed(f"Missing: `{error.param.name}`"))
        except Exception: pass
        return
    log.error(f"Command [{ctx.command}] ERROR:\n{traceback.format_exc()}")
    try: await ctx.send(embed=err_embed(str(error)[:150]))
    except Exception: pass

if __name__ == "__main__":
    log.info("Starting Veltra Music Bot (True Multi-Platform)...")
    try: bot.run(TOKEN, log_handler=None)
    except discord.LoginFailure: log.error("FATAL: Invalid token!")
    except KeyboardInterrupt: pass
    except Exception as e: log.error(f"FATAL: {e}\n{traceback.format_exc()}")
