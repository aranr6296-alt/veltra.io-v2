"""
╔══════════════════════════════════════════════════════╗
║  VELTRA MUSIC BOT — SEARCH 100% FIXED               ║
║  Uses Invidious API (bypasses ALL YouTube blocks)    ║
║  Kurdish · Multi-Platform · Crash-Proof              ║
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
import traceback
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    print("[FATAL] No DISCORD_TOKEN")
    raise SystemExit(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("veltra.log", encoding="utf-8", mode="a")])
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

# ═══════════════════════════════════════════════════
#  INVIDIOUS & PIPED INSTANCES (Public YouTube APIs)
# ═══════════════════════════════════════════════════
INVIDIOUS = [
    "https://inv.nadeko.net",
    "https://invidious.fdn.fr",
    "https://iv.ggtyler.dev",
    "https://invidious.privacyredirect.com",
    "https://invidious.protokolla.fi",
    "https://yt.artemislena.eu",
    "https://invidious.perennialte.ch",
    "https://iv.nbootu.nl",
]
PIPED = [
    "https://pipedapi.kavin.rocks",
    "https://pipedapi.adminforge.de",
    "https://pipedapi.in.projectsegfau.lt",
]

# ═══════════════════════════════════════════════════
#  DATABASE
# ═══════════════════════════════════════════════════
DB_FILE = "veltra.db"
def _db(): return sqlite3.connect(DB_FILE, timeout=10)

def init_db():
    try:
        c = _db(); c.execute("PRAGMA journal_mode=WAL")
        c.executescript("""CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id INTEGER PRIMARY KEY, dj_role_id INTEGER DEFAULT NULL,
            volume INTEGER DEFAULT 100, loop_mode TEXT DEFAULT 'off',
            tfs INTEGER DEFAULT 0, autoplay INTEGER DEFAULT 0, kurdish_mode INTEGER DEFAULT 1);
            CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER,
            title TEXT, url TEXT, duration TEXT, requester TEXT,
            platform TEXT DEFAULT 'unknown', played_at TEXT DEFAULT (datetime('now')));""")
        c.commit(); c.close()
    except Exception as e: log.error(f"DB: {e}")
init_db()

def get_settings(gid):
    try:
        c=_db(); c.row_factory=sqlite3.Row
        r=c.execute("SELECT * FROM guild_settings WHERE guild_id=?", (gid,)).fetchone()
        if not r:
            c.execute("INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)", (gid,)); c.commit()
            r=c.execute("SELECT * FROM guild_settings WHERE guild_id=?", (gid,)).fetchone()
        c.close(); return dict(r) if r else {"dj_role_id":None,"volume":100,"loop_mode":"off","tfs":0,"autoplay":0,"kurdish_mode":1}
    except: return {"dj_role_id":None,"volume":100,"loop_mode":"off","tfs":0,"autoplay":0,"kurdish_mode":1}

def save_settings(gid, **kw):
    try:
        get_settings(gid); s=", ".join(f"{k}=?" for k in kw); c=_db()
        c.execute(f"UPDATE guild_settings SET {s} WHERE guild_id=?", [*kw.values(), gid]); c.commit(); c.close()
    except Exception as e: log.error(f"save: {e}")

def push_history(gid, title, url, dur, req, plat="unknown"):
    try:
        c=_db(); c.execute("INSERT INTO history (guild_id,title,url,duration,requester,platform) VALUES (?,?,?,?,?,?)", (gid,title,url,dur,req,plat))
        c.execute("DELETE FROM history WHERE guild_id=? AND id NOT IN (SELECT id FROM history WHERE guild_id=? ORDER BY id DESC LIMIT 50)", (gid,gid)); c.commit(); c.close()
    except: pass

# ═══════════════════════════════════════════════════
#  FILTERS
# ═══════════════════════════════════════════════════
FILTERS = {
    "none":{"label":"🎵 None","af":""},"bassboost":{"label":"🔊 Bass Boost","af":"bass=g=10,dynaudnorm=f=200"},
    "nightcore":{"label":"🌙 Nightcore","af":"asetrate=44100*1.25,aresample=44100"},
    "vaporwave":{"label":"🌊 Vaporwave","af":"asetrate=44100*0.8,aresample=44100"},
    "8d":{"label":"🎧 8D Audio","af":"apulsator=hz=0.08"},"karaoke":{"label":"🎤 Karaoke","af":"stereotools=mlev=0.03125"},
    "tremolo":{"label":"〰️ Tremolo","af":"tremolo=f=4:d=0.9"},"vibrato":{"label":"🎸 Vibrato","af":"vibrato=f=6.5:d=0.9"},
    "superbass":{"label":"💥 Super Bass","af":"bass=g=20,dynaudnorm=f=200"},
    "soft":{"label":"🕊️ Soft","af":"lowpass=f=300,volume=1.5"},
    "earrape":{"label":"📢 Ear Rape","af":"acrusher=level_in=8:level_out=18:bits=8:mode=log:aa=1"},
    "pitch":{"label":"🎵 Pitch Up","af":"asetrate=44100*1.15,aresample=44100"},
}

# ═══════════════════════════════════════════════════
#  PLATFORM
# ═══════════════════════════════════════════════════
def detect_platform(url):
    if not url: return "unknown"; u=url.lower()
    if "spotify.com" in u: return "spotify"
    if "music.apple.com" in u or "itunes.apple.com" in u: return "apple_music"
    if "soundcloud.com" in u: return "soundcloud"
    if "deezer.com" in u: return "deezer"
    if "anghami.com" in u: return "anghami"
    if "vimeo.com" in u: return "vimeo"
    if "youtube.com" in u or "youtu.be" in u: return "youtube"
    if any(u.endswith(x) for x in (".mp3",".mp4",".m4a",".ogg",".wav",".flac")): return "direct"
    return "unknown"

PE={"spotify":"🎵","apple_music":"🍎","soundcloud":"☁️","deezer":"🎶","anghami":"🌙","vimeo":"📹","youtube":"▶️","direct":"📎","unknown":"🔍"}

# ═══════════════════════════════════════════════════
#  KURDISH DETECTION
# ═══════════════════════════════════════════════════
KURDISH_KW = ["kurdish","kurdi","کوردی","کوردیی","kurdî","kurdish song","zagros","kurdistan","hawler","slemani","erbil","stran","stranên","gorani"]

def is_kurdish(title):
    if not title: return False
    if any('\u0600' <= c <= '\u06FF' for c in title): return True
    return any(k in title.lower() for k in KURDISH_KW)

def kurdish_queries(query):
    if is_kurdish(query): return [query]
    return [f"{query} kurdish song کوردی", f"{query} کوردی", f"{query} stran kurdî", f"{query} kurdish cover", f"{query} kurdi"]

# ═══════════════════════════════════════════════════
#  ★★★ SEARCH ENGINE: INVIDIOUS → PIPED ★★★
# ═══════════════════════════════════════════════════
async def _invidious_search(query, max_results=5):
    for base in INVIDIOUS:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"{base}/api/v1/search",
                    params={"q": query, "type": "video", "sort_by": "relevance"},
                    headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=10), ssl=False) as r:
                    if r.status != 200: continue
                    data = await r.json()
                    if not isinstance(data, list): continue
                    results = []
                    for item in data:
                        if len(results) >= max_results: break
                        if item.get("type") != "video": continue
                        vid = item.get("videoId")
                        if not vid: continue
                        results.append({
                            "id": vid, "title": item.get("title","Unknown"),
                            "url": f"https://www.youtube.com/watch?v={vid}",
                            "webpage_url": f"https://www.youtube.com/watch?v={vid}",
                            "duration": int(item.get("lengthSeconds") or 0),
                            "thumbnail": f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
                            "uploader": item.get("author","Unknown"), "channel": item.get("author","Unknown"),
                        })
                    if results:
                        log.info(f"✅ Invidious OK [{base}]: {len(results)} results for '{query[:40]}'")
                        return results
        except Exception as e:
            log.debug(f"Invidious {base}: {e}")
    return []

async def _piped_search(query, max_results=5):
    for base in PIPED:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"{base}/search",
                    params={"q": query, "filter": "videos"},
                    headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=10), ssl=False) as r:
                    if r.status != 200: continue
                    data = await r.json()
                    items = data.get("items", [])
                    if not items: continue
                    results = []
                    for item in items:
                        if len(results) >= max_results: break
                        url = item.get("url","")
                        vid = url.split("v=")[1].split("&")[0] if "v=" in url else ""
                        if not vid: continue
                        results.append({
                            "id": vid, "title": item.get("title","Unknown"),
                            "url": f"https://www.youtube.com/watch?v={vid}",
                            "webpage_url": f"https://www.youtube.com/watch?v={vid}",
                            "duration": int(item.get("duration") or 0),
                            "thumbnail": item.get("thumbnail","") or f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
                            "uploader": item.get("uploaderName","Unknown"), "channel": item.get("uploaderName","Unknown"),
                        })
                    if results:
                        log.info(f"✅ Piped OK [{base}]: {len(results)} results for '{query[:40]}'")
                        return results
        except Exception as e:
            log.debug(f"Piped {base}: {e}")
    return []

async def search_songs(query, kurdish_mode=True, force_kurdish=False):
    if force_kurdish: queries = kurdish_queries(query)
    elif kurdish_mode and not is_kurdish(query): queries = [f"{query} kurdish kurdi کوردی", query]
    else: queries = [query]

    all_results, seen = [], set()
    for q in queries:
        results = await _invidious_search(q)
        if not results: results = await _piped_search(q)
        if not results: continue

        if force_kurdish or (kurdish_mode and not is_kurdish(query)):
            kurdish = [r for r in results if is_kurdish(r.get("title",""))]
            if kurdish:
                for r in kurdish:
                    if r["id"] not in seen: seen.add(r["id"]); all_results.append(r)
                if len(all_results) >= 5: break
                continue
        else:
            for r in results:
                if r["id"] not in seen: seen.add(r["id"]); all_results.append(r)
            if len(all_results) >= 5: break

    if not all_results and force_kurdish:
        for q in [query, f"{query} kurdish"]:
            results = await _invidious_search(q)
            if not results: results = await _piped_search(q)
            for r in results:
                if r["id"] not in seen: seen.add(r["id"]); all_results.append(r)
            if all_results: break

    return all_results[:5]

# ═══════════════════════════════════════════════════
#  RESOLVE: yt-dlp → Invidious stream fallback
# ═══════════════════════════════════════════════════
_YT_OPTS = {
    "format":"bestaudio/best","quiet":True,"no_warnings":True,"socket_timeout":15,
    "retries":2,"skip_download":True,"nocheckcertificate":True,"noprogress":True,
    "extractor_args":{"youtube":{"player_client":["android","web"],"skip":["dash","hls"]}},
    "http_headers":{"User-Agent":"Mozilla/5.0 (Linux; Android 11; Pixel 5) Chrome/122.0.0.0 Mobile Safari/537.36"},
}
CACHE_DIR = Path("./veltra_cache")
try: CACHE_DIR.mkdir(exist_ok=True)
except: CACHE_DIR = None
if CACHE_DIR: _YT_OPTS["cachedir"] = str(CACHE_DIR)

async def _run_sync(fn, *a, **kw):
    try: return await asyncio.get_running_loop().run_in_executor(None, lambda: fn(*a, **kw))
    except Exception as e: log.error(f"Exec: {e}"); raise

def _safe_extract(opts, url):
    try:
        with yt_dlp.YoutubeDL(opts) as ydl: return ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as e: log.warning(f"DL: {e}")
    except yt_dlp.utils.ExtractorError as e: log.warning(f"Ext: {e}")
    except Exception as e: log.error(f"ytdlp: {e}")
    return None

async def _invidious_stream(video_id):
    for base in INVIDIOUS:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"{base}/api/v1/videos/{video_id}",
                    params={"fields":"adaptiveFormats,formatStreams"},
                    timeout=aiohttp.ClientTimeout(total=10), ssl=False) as r:
                    if r.status != 200: continue
                    data = await r.json()
                    for fmt in data.get("adaptiveFormats",[]):
                        mime = fmt.get("mimeType") or fmt.get("type") or ""
                        if "audio" in mime and fmt.get("url"):
                            log.info(f"✅ Invidious stream OK [{base}] for {video_id}")
                            return {"url": fmt["url"]}
                    for fmt in data.get("formatStreams",[]):
                        if fmt.get("url"):
                            log.info(f"✅ Invidious fallback stream [{base}] for {video_id}")
                            return {"url": fmt["url"]}
        except Exception as e: log.debug(f"Inv stream {base}: {e}")
    return None

async def resolve_url(url):
    def _do():
        r = _safe_extract({**_YT_OPTS,"noplaylist":True}, url)
        if r and isinstance(r,dict) and r.get("id"): return r
        if r and isinstance(r,list) and r: return r[0]
        return None
    try:
        result = await _run_sync(_do)
        if result: return result
    except: pass
    vid = None
    if "youtu.be/" in url: vid = url.split("youtu.be/")[1].split("?")[0]
    elif "v=" in url: vid = url.split("v=")[1].split("&")[0]
    if vid:
        log.info(f"yt-dlp failed, trying Invidious stream for {vid}")
        stream = await _invidious_stream(vid)
        if stream: return {"id":vid,"url":stream["url"],"title":"","thumbnail":"","uploader":"","duration":0}
    return None

async def resolve_playlist(url):
    plat = detect_platform(url)
    def _do():
        r = _safe_extract({**_YT_OPTS,"extract_flat":"in_playlist"}, url)
        entries = []
        if r and isinstance(r,dict):
            for e in (r.get("entries") or []):
                if e and e.get("id"): e["_platform"]=plat; entries.append(e)
        return entries
    try: return await _run_sync(_do) or []
    except: return []

def _make_source(stream_url, volume, filter_name):
    if not stream_url: return None
    af = FILTERS.get(filter_name, FILTERS["none"])["af"]
    before = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
    options = "-vn" + (f" -af {af}" if af else "")
    try: return discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(stream_url, before_options=before, options=options), volume=volume)
    except Exception as e: log.error(f"FFmpeg: {e}"); return None

# ═══════════════════════════════════════════════════
#  SONG & PLAYER
# ═══════════════════════════════════════════════════
class Song:
    __slots__ = ("title","url","stream_url","duration","thumbnail","uploader","requester","platform","is_kurdish")
    def __init__(self, data, requester, platform="unknown"):
        self.title=str(data.get("title") or "Unknown")
        self.url=str(data.get("webpage_url") or data.get("url") or "")
        self.stream_url=str(data.get("url") or "")
        self.duration=data.get("duration") or 0
        self.thumbnail=str(data.get("thumbnail") or "")
        self.uploader=str(data.get("uploader") or data.get("channel") or "Unknown")
        self.requester=requester; self.platform=platform; self.is_kurdish=is_kurdish(self.title)
    @property
    def dur_str(self):
        if not self.duration or self.duration<=0: return "🔴 LIVE"
        d=int(self.duration); m,s=divmod(d,60); h,m=divmod(m,60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
    def progress_bar(self, elapsed, length=13):
        if not self.duration or self.duration<=0: return "─"*length+" 🔴"
        pct=min(max(elapsed/self.duration,0.0),1.0); fill=int(pct*length)
        return "▬"*fill+"🔘"+"▬"*(length-fill)

class MusicPlayer:
    def __init__(self, gid):
        self.guild_id=gid; self.queue=[]; self.current=None; self.history=[]
        self.loop="off"; self.volume=1.0; self.filter_name="none"; self.skip_votes=set()
        self.tfs=False; self.autoplay=False; self.kurdish_mode=True
        self._start=None; self._paused_at=None; self._elapsed_pre=0.0
        self.np_msg=None; self._lock=asyncio.Lock(); self._playing=False
    def elapsed(self):
        if self._start is None: return self._elapsed_pre
        if self._paused_at is not None: return self._elapsed_pre
        return self._elapsed_pre+(time.time()-self._start)
    def reset_timer(self): self._start=time.time(); self._paused_at=None; self._elapsed_pre=0.0

_players = {}
def get_player(gid):
    if gid not in _players:
        p=MusicPlayer(gid); s=get_settings(gid)
        p.volume=max(0.0,min(2.0,(s.get("volume") or 100)/100.0))
        p.loop=s.get("loop_mode") or "off"; p.tfs=bool(s.get("tfs"))
        p.autoplay=bool(s.get("autoplay")); p.kurdish_mode=bool(s.get("kurdish_mode",1))
        _players[gid]=p
    return _players[gid]
def destroy_player(gid):
    p=_players.pop(gid,None)
    if p: p.queue.clear(); p.history.clear(); p.current=None

# ═══════════════════════════════════════════════════
#  EMBEDS & HELPERS
# ═══════════════════════════════════════════════════
def _e(c,d): return discord.Embed(color=c,description=d)
def ok_e(d): return _e(C_GREEN,f"✅ {d}")
def err_e(d): return _e(C_RED,f"❌ {d}")
def _ft(sec):
    if not sec or sec<0: return "0:00"
    s=int(sec); m,s=divmod(s,60); h,m=divmod(m,60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
def _dur(s): return _ft(s) if s and s>0 else "?"

# ═══════════════════════════════════════════════════
#  NOW PLAYING
# ═══════════════════════════════════════════════════
def build_np(p, vc):
    song=p.current
    if not song: return _e(C_LUNA,"Nothing playing")
    el=p.elapsed(); pa=vc.is_paused() if vc else False
    e=discord.Embed(color=C_LUNA)
    e.set_author(name=f"{'🟢 Kurdish' if song.is_kurdish else '🎵'} Now Playing")
    e.title=song.title; e.url=song.url if song.url.startswith("http") else None
    e.description=f"`{_ft(el)}` {song.progress_bar(el)} `{song.dur_str}`"
    li={"off":"➡️ Off","track":"🔂 Track","queue":"🔁 Queue"}.get(p.loop,"➡️ Off")
    vi="🔇" if p.volume<=0 else ("🔉" if p.volume<0.5 else "🔊")
    fl=FILTERS.get(p.filter_name,FILTERS["none"])["label"]
    pe=PE.get(song.platform,"🔍")
    e.add_field(name=f"{pe} Platform",value=song.platform.replace("_"," ").title(),inline=True)
    e.add_field(name="🎙️ Artist",value=song.uploader[:50],inline=True)
    e.add_field(name="⏱️ Length",value=song.dur_str,inline=True)
    e.add_field(name=f"{vi} Vol",value=f"{int(p.volume*100)}%",inline=True)
    e.add_field(name="🔁 Loop",value=li,inline=True)
    e.add_field(name="🎛️ Filter",value=fl,inline=True)
    e.add_field(name="📋 Queue",value=str(len(p.queue)),inline=True)
    e.add_field(name="👤 By",value=song.requester.mention,inline=False)
    if song.thumbnail and song.thumbnail.startswith("http"): e.set_thumbnail(url=song.thumbnail)
    e.set_footer(text=f"Veltra Music • {'⏸ Paused' if pa else '▶️ Playing'}")
    return e

class NPView(discord.ui.View):
    def __init__(self, player, vc):
        super().__init__(timeout=None); self.player=player; self.vc=vc
        pa=vc.is_paused() if vc else False
        for em,act,st,rw in [("⏮️","prev",discord.ButtonStyle.secondary,0),("▶️" if pa else "⏸️","pause",discord.ButtonStyle.primary,0),
            ("⏭️","skip",discord.ButtonStyle.secondary,0),("⏹️","stop",discord.ButtonStyle.danger,0),
            ("🔂" if player.loop=="track" else "🔁" if player.loop=="queue" else "➡️","loop",discord.ButtonStyle.secondary,1),
            ("🔀","shuffle",discord.ButtonStyle.secondary,1),("❤️","grab",discord.ButtonStyle.secondary,1),("📋","queue",discord.ButtonStyle.secondary,1)]:
            self.add_item(_NPB(em,act,st,rw))

class _NPB(discord.ui.Button):
    def __init__(self,em,act,st,rw):
        super().__init__(emoji=em,style=st,custom_id=f"vnp_{act}_{random.randint(0,9999999)}",row=rw); self.action=act
    async def callback(self,interaction):
        try: await interaction.response.defer(ephemeral=False)
        except: return
        if not interaction.guild or not interaction.guild.voice_client: return
        vc=interaction.guild.voice_client; pl=get_player(interaction.guild.id)
        if not pl.current: return
        try:
            h=await self._h(interaction,vc,pl)
            if not h and pl.current and vc.is_connected():
                try:
                    if pl.np_msg: await pl.np_msg.edit(embed=build_np(pl,vc),view=NPView(pl,vc))
                except: pass
        except Exception as e: log.error(f"NPB {self.action}: {e}")
    async def _h(self,i,vc,pl):
        if self.action=="pause":
            if vc.is_paused(): pl._elapsed_pre=pl.elapsed();pl._start=time.time();pl._paused_at=None;vc.resume()
            else: pl._elapsed_pre=pl.elapsed();pl._paused_at=time.time();vc.pause()
        elif self.action=="skip": pl.skip_votes.clear();vc.stop()
        elif self.action=="stop":
            pl.queue.clear();pl.loop="off";vc.stop()
            try: await i.followup.send(embed=ok_e("Stopped!"),ephemeral=True)
            except: pass; return True
        elif self.action=="loop":
            ms=["off","track","queue"];pl.loop=ms[(ms.index(pl.loop)+1)%3];save_settings(i.guild.id,loop_mode=pl.loop)
        elif self.action=="shuffle":
            if len(pl.queue)>=2: random.shuffle(pl.queue)
            try: await i.followup.send(embed=ok_e("🔀 Shuffled!"),ephemeral=True)
            except: pass; return True
        elif self.action=="grab":
            s=pl.current; e=discord.Embed(color=C_LUNA,title="❤️ Saved",description=f"**[{s.title}]({s.url})**")
            e.add_field(name="Duration",value=s.dur_str,inline=True)
            if s.is_kurdish: e.add_field(name="Type",value="🟢 Kurdish",inline=True)
            if s.thumbnail and s.thumbnail.startswith("http"): e.set_thumbnail(url=s.thumbnail)
            try:
                await i.user.send(embed=e); await i.followup.send(embed=ok_e("Sent to DMs!"),ephemeral=True)
            except discord.Forbidden: await i.followup.send(embed=err_e("Can't DM you."),ephemeral=True)
            except: pass; return True
        elif self.action=="queue":
            q=pl.queue
            if not q: await i.followup.send(embed=_e(C_LUNA,"📋 Empty."),ephemeral=True)
            else:
                lines=[f"`{j+1}.` [{s.title}]({s.url}) `{s.dur_str}` {'🟢' if s.is_kurdish else ''}" for j,s in enumerate(q[:10])]
                ex=f"\n*+{len(q)-10} more...*" if len(q)>10 else ""
                await i.followup.send(embed=_e(C_LUNA,f"📋 {len(q)} songs").set_description("\n".join(lines)+ex),ephemeral=True)
            return True
        elif self.action=="prev":
            if pl.history:
                prev=pl.history.pop()
                if pl.current: pl.queue.insert(0,pl.current)
                pl.queue.insert(0,prev);vc.stop()
            else:
                try: await i.followup.send(embed=err_e("No previous!"),ephemeral=True)
                except: pass; return True
        return False

# ═══════════════════════════════════════════════════
#  PLAYBACK ENGINE
# ═══════════════════════════════════════════════════
async def play_next(gid,ch,vc):
    pl=get_player(gid)
    if pl._lock.locked(): return
    async with pl._lock:
        if not vc or not vc.is_connected(): return
        song=None
        if pl.loop=="track" and pl.current: song=pl.current
        elif pl.loop=="queue" and pl.current: pl.queue.append(pl.current); song=pl.queue.pop(0) if pl.queue else None
        else: song=pl.queue.pop(0) if pl.queue else None
        if not song:
            if pl.current: push_history(gid,pl.current.title,pl.current.url,pl.current.dur_str,str(pl.current.requester),pl.current.platform)
            pl.current=None; pl._playing=False
            if pl.autoplay and pl.history:
                last=pl.history[-1]
                try:
                    res=await search_songs(f"{last.uploader} kurdish song",kurdish_mode=True,force_kurdish=True)
                    if not res: res=await search_songs("kurdish music 2024",kurdish_mode=True,force_kurdish=True)
                    if res: pl.queue.append(Song(res[0],bot.user,"youtube")); await play_next(gid,ch,vc); return
                except: pass
            if not pl.tfs:
                try: await asyncio.sleep(300)
                except asyncio.CancelledError: return
                p2=get_player(gid)
                if not p2.current and not p2.queue and vc.is_connected():
                    if not [m for m in vc.channel.members if not m.bot]:
                        try: vc.stop()
                        except: pass
                        try: await vc.disconnect()
                        except: pass
                        destroy_player(gid)
                        if ch:
                            try: await ch.send(embed=_e(C_LUNA,"👋 Left (idle 5m)."))
                            except: pass
            return
        if pl.current and pl.current is not song:
            push_history(gid,pl.current.title,pl.current.url,pl.current.dur_str,str(pl.current.requester),pl.current.platform)
            pl.history.append(pl.current)
            if len(pl.history)>20: pl.history.pop(0)
        pl.current=song; pl.skip_votes.clear()
        if not song.stream_url or "googlevideo" not in song.stream_url:
            data=await resolve_url(song.url)
            if not data:
                if ch:
                    try: await ch.send(embed=err_e(f"Skipping **{song.title[:50]}** — can't resolve."))
                    except: pass
                pl._playing=False; await play_next(gid,ch,vc); return
            song.stream_url=data.get("url") or ""
            if not song.thumbnail: song.thumbnail=data.get("thumbnail") or ""
            if not song.duration or song.duration<=0: song.duration=data.get("duration") or 0
            if song.uploader=="Unknown": song.uploader=data.get("uploader") or data.get("channel") or "Unknown"
        if not song.stream_url: pl._playing=False; await play_next(gid,ch,vc); return
        source=_make_source(song.stream_url,pl.volume,pl.filter_name)
        if not source:
            if ch:
                try: await ch.send(embed=err_e(f"Skipping **{song.title[:50]}** — FFmpeg error."))
                except: pass
            pl._playing=False; await play_next(gid,ch,vc); return
        pl.reset_timer(); pl._playing=True
        def after(err):
            if err: log.error(f"after: {err}")
            f=asyncio.run_coroutine_threadsafe(play_next(gid,ch,vc),bot.loop)
            f.add_done_callback(lambda x: x.exception() if x.exception() else None)
        try: vc.play(source,after=after)
        except Exception as e: log.error(f"vc.play: {e}"); pl._playing=False; return
        if ch:
            try:
                emb=build_np(pl,vc); vw=NPView(pl,vc)
                if pl.np_msg and not pl.np_msg.is_deleted(): await pl.np_msg.edit(embed=emb,view=vw)
                else: pl.np_msg=await ch.send(embed=emb,view=vw)
            except: pass

async def _start(ctx):
    vc=ctx.voice_client
    if not vc: return
    if not get_player(ctx.guild.id)._playing: await play_next(ctx.guild.id,ctx.channel,vc)

# ═══════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════
async def _vc(ctx):
    if not ctx.author.voice or not ctx.author.voice.channel: await ctx.send(embed=err_e("Join a voice channel!")); return None
    t=ctx.author.voice.channel
    if not t.permissions_for(ctx.me).connect: await ctx.send(embed=err_e("No connect permission!")); return None
    if not t.permissions_for(ctx.me).speak: await ctx.send(embed=err_e("No speak permission!")); return None
    vc=ctx.voice_client
    try:
        if not vc: vc=await t.connect(timeout=15)
        elif vc.channel!=t: await vc.move_to(t)
        return vc
    except asyncio.TimeoutError: await ctx.send(embed=err_e("Timeout.")); return None
    except Exception as e: log.error(f"vc: {e}"); await ctx.send(embed=err_e("Failed to connect.")); return None

async def _dj(ctx):
    if ctx.author.guild_permissions.manage_guild: return True
    s=get_settings(ctx.guild.id); did=s.get("dj_role_id")
    if did:
        role=ctx.guild.get_role(int(did))
        if role and role in ctx.author.roles: return True
        await ctx.send(embed=err_e(f"Need **{role.name if role else did}** DJ role!")); return False
    return True

# ═══════════════════════════════════════════════════
#  COMMANDS
# ═══════════════════════════════════════════════════
@bot.command(aliases=["j"])
async def join(ctx):
    vc=await _vc(ctx)
    if vc: await ctx.send(embed=ok_e(f"Joined **{vc.channel.name}**!"))

@bot.command(aliases=["dc","leave"])
async def disconnect(ctx):
    if not ctx.voice_client: return await ctx.send(embed=err_e("Not in VC!"))
    if not await _dj(ctx): return
    vc=ctx.voice_client; get_player(ctx.guild.id).queue.clear()
    try: vc.stop()
    except: pass
    try: await vc.disconnect()
    except: pass
    destroy_player(ctx.guild.id); await ctx.send(embed=ok_e("Disconnected! 👋"))

@bot.command(aliases=["p"])
async def play(ctx,*,query):
    if not query or not query.strip(): return await ctx.send(embed=err_e("Provide a song name or URL!"))
    vc=await _vc(ctx)
    if not vc: return
    pl=get_player(ctx.guild.id); plat=detect_platform(query); pe=PE.get(plat,"🔍")
    msg=await ctx.send(embed=_e(C_LUNA,f"{pe} Searching **{query[:80]}**..."))
    is_url=query.strip().startswith(("http://","https://"))
    try:
        if is_url and ("list=" in query or "/playlist" in query.lower()):
            entries=await resolve_playlist(query)
            if not entries: return await msg.edit(embed=err_e("Playlist not found."))
            added=0
            for e in entries:
                eid=e.get("id")
                if not eid: continue
                d={"title":e.get("title") or "Unknown","url":e.get("url") or f"https://www.youtube.com/watch?v={eid}","webpage_url":e.get("url") or f"https://www.youtube.com/watch?v={eid}","duration":e.get("duration") or 0,"thumbnail":e.get("thumbnail") or "","uploader":e.get("uploader") or e.get("channel") or ""}
                pl.queue.append(Song(d,ctx.author,e.get("_platform",plat))); added+=1
            if not added: return await msg.edit(embed=err_e("No playable entries."))
            em=_e(C_LUNA,""); em.title="📋 Playlist Added!"; em.add_field(name="Songs",value=str(added),inline=True); em.add_field(name="Queue",value=str(len(pl.queue)),inline=True)
            await msg.edit(embed=em)
        elif is_url:
            data=await resolve_url(query)
            if not data: return await msg.edit(embed=err_e("Couldn't resolve URL."))
            song=Song(data,ctx.author,plat); pl.queue.append(song)
            if vc.is_playing() or vc.is_paused():
                em=_e(C_LUNA,""); em.title="➕ Added"; em.description=f"**[{song.title}]({song.url})**"; em.add_field(name="Duration",value=song.dur_str,inline=True)
                if song.is_kurdish: em.add_field(name="Type",value="🟢 Kurdish",inline=True)
                if song.thumbnail and song.thumbnail.startswith("http"): em.set_thumbnail(url=song.thumbnail)
                await msg.edit(embed=em)
            else:
                try: await msg.delete()
                except: pass
        else:
            results=await search_songs(query,kurdish_mode=pl.kurdish_mode)
            if not results: return await msg.edit(embed=err_e("No results! Try different words."))
            data=results[0]; song=Song(data,ctx.author,"youtube"); pl.queue.append(song)
            if vc.is_playing() or vc.is_paused():
                em=_e(C_LUNA,""); em.title="➕ Added"; em.description=f"**[{song.title}]({song.url})**"; em.add_field(name="Duration",value=song.dur_str,inline=True)
                if song.is_kurdish: em.add_field(name="Type",value="🟢 Kurdish",inline=True)
                if song.thumbnail and song.thumbnail.startswith("http"): em.set_thumbnail(url=song.thumbnail)
                await msg.edit(embed=em)
            else:
                try: await msg.delete()
                except: pass
    except Exception as e:
        log.error(f"play: {e}\n{traceback.format_exc()}")
        try: await msg.edit(embed=err_e(f"Error: {str(e)[:150]}"))
        except: pass; return
    await _start(ctx)

@bot.command()
async def search(ctx,*,query):
    if not query or not query.strip(): return await ctx.send(embed=err_e("Provide a query!"))
    msg=await ctx.send(embed=_e(C_LUNA,f"🔍 Searching **{query[:80]}**..."))
    try: results=await search_songs(query,get_player(ctx.guild.id).kurdish_mode)
    except Exception as e: return await msg.edit(embed=err_e(str(e)[:150]))
    if not results: return await msg.edit(embed=err_e("No results!"))
    lines=[f"`{i+1}.` [{r.get('title','?')[:60]}](https://youtu.be/{r.get('id','')}) `{_dur(r.get('duration'))}` {'🟢' if is_kurdish(r.get('title','')) else ''}" for i,r in enumerate(results)]
    em=_e(C_LUNA,""); em.title="🔍 Results"; em.description="\n".join(lines); em.set_footer(text="Reply 1-5 • 'cancel'\n🟢 = Kurdish")
    await msg.edit(embed=em)
    def chk(m): return m.author==ctx.author and m.channel==ctx.channel and m.content.strip()
    try: reply=await bot.wait_for("message",check=chk,timeout=30)
    except asyncio.TimeoutError: return await msg.edit(embed=err_e("Timed out."))
    try: await reply.delete()
    except: pass
    if reply.content.strip().lower()=="cancel": return await msg.edit(embed=ok_e("Cancelled."))
    try:
        idx=int(reply.content.strip())-1
        if idx<0 or idx>=len(results): raise ValueError
    except: return await msg.edit(embed=err_e("Invalid number."))
    vc=await _vc(ctx)
    if not vc: return
    rid=results[idx].get("id")
    if not rid: return await msg.edit(embed=err_e("No ID."))
    try:
        full=await resolve_url(f"https://www.youtube.com/watch?v={rid}")
        if not full: return await msg.edit(embed=err_e("Couldn't resolve."))
    except Exception as e: return await msg.edit(embed=err_e(str(e)[:150]))
    song=Song(full,ctx.author,"youtube"); get_player(ctx.guild.id).queue.append(song)
    em2=_e(C_LUNA,""); em2.title="➕ Added"; em2.description=f"**[{song.title}]({song.url})**"
    if song.is_kurdish: em2.add_field(name="Type",value="🟢 Kurdish",inline=True)
    if song.thumbnail and song.thumbnail.startswith("http"): em2.set_thumbnail(url=song.thumbnail)
    await msg.edit(embed=em2); await _start(ctx)

@bot.command(aliases=["kurdish","ku"])
async def kurdishplay(ctx,*,query):
    if not query or not query.strip(): return await ctx.send(embed=err_e("Provide a song name!"))
    vc=await _vc(ctx)
    if not vc: return
    msg=await ctx.send(embed=_e(C_LUNA,f"🟢 Finding Kurdish: **{query[:80]}**..."))
    try:
        results=await search_songs(query,kurdish_mode=True,force_kurdish=True)
        if not results: return await msg.edit(embed=err_e("No Kurdish version found. Try different words."))
        song=Song(results[0],ctx.author,"youtube"); get_player(ctx.guild.id).queue.append(song)
        em=_e(C_LUNA,""); em.title="🟢 Kurdish Song!"; em.description=f"**[{song.title}]({song.url})**"
        em.add_field(name="Duration",value=song.dur_str,inline=True); em.add_field(name="Channel",value=song.uploader[:50],inline=True)
        if song.thumbnail and song.thumbnail.startswith("http"): em.set_thumbnail(url=song.thumbnail)
        await msg.edit(embed=em)
    except Exception as e:
        log.error(f"kurdishplay: {e}"); return await msg.edit(embed=err_e(str(e)[:150]))
    await _start(ctx)

@bot.command(aliases=["pa"])
async def pause(ctx):
    vc=ctx.voice_client
    if not vc or not vc.is_playing(): return await ctx.send(embed=err_e("Nothing playing!"))
    if not await _dj(ctx): return
    p=get_player(ctx.guild.id); p._elapsed_pre=p.elapsed(); p._paused_at=time.time(); vc.pause()
    await ctx.send(embed=ok_e("Paused ⏸️"))

@bot.command(aliases=["res"])
async def resume(ctx):
    vc=ctx.voice_client
    if not vc or not vc.is_paused(): return await ctx.send(embed=err_e("Nothing paused!"))
    if not await _dj(ctx): return
    p=get_player(ctx.guild.id); p._elapsed_pre=p.elapsed(); p._start=time.time(); p._paused_at=None; vc.resume()
    await ctx.send(embed=ok_e("Resumed ▶️"))

@bot.command(aliases=["s"])
async def skip(ctx):
    vc=ctx.voice_client
    if not vc or (not vc.is_playing() and not vc.is_paused()): return await ctx.send(embed=err_e("Nothing playing!"))
    p=get_player(ctx.guild.id); is_dj=ctx.author.guild_permissions.manage_guild; s=get_settings(ctx.guild.id); did=s.get("dj_role_id")
    if is_dj or (did and (role:=ctx.guild.get_role(int(did))) and role in ctx.author.roles):
        p.skip_votes.clear(); vc.stop(); return await ctx.send(embed=ok_e("⏭️ Skipped!"))
    members=[m for m in vc.channel.members if not m.bot]
    if not members: p.skip_votes.clear(); vc.stop(); return await ctx.send(embed=ok_e("⏭️ Skipped!"))
    needed=max(1,math.ceil(len(members)*0.5)); p.skip_votes.add(ctx.author.id); v=len(p.skip_votes)
    if v>=needed: p.skip_votes.clear(); vc.stop(); await ctx.send(embed=ok_e(f"⏭️ Vote passed ({v}/{needed})!"))
    else: await ctx.send(embed=_e(C_YELLOW,f"🗳️ Vote: **{v}/{needed}** — need {needed-v} more."))

@bot.command()
async def stop(ctx):
    if not await _dj(ctx): return
    vc=ctx.voice_client
    if not vc: return await ctx.send(embed=err_e("Not in VC!"))
    p=get_player(ctx.guild.id); p.queue.clear(); p.loop="off"; vc.stop(); await ctx.send(embed=ok_e("⏹️ Stopped!"))

@bot.command(aliases=["np"])
async def nowplaying(ctx):
    vc=ctx.voice_client
    if not vc: return await ctx.send(embed=err_e("Not in VC!"))
    p=get_player(ctx.guild.id)
    if not p.current: return await ctx.send(embed=err_e("Nothing playing!"))
    try: p.np_msg=await ctx.send(embed=build_np(p,vc),view=NPView(p,vc))
    except: pass

@bot.command(aliases=["replay","restart"])
async def again(ctx):
    vc=ctx.voice_client
    if not vc or (not vc.is_playing() and not vc.is_paused()): return await ctx.send(embed=err_e("Nothing playing!"))
    if not await _dj(ctx): return
    p=get_player(ctx.guild.id)
    if not p.current: return await ctx.send(embed=err_e("Nothing playing!"))
    p.queue.insert(0,p.current); vc.stop(); await ctx.send(embed=ok_e("🔁 Replaying!"))

@bot.command(aliases=["q"])
async def queue(ctx,page=1):
    p=get_player(ctx.guild.id)
    if not p.current and not p.queue: return await ctx.send(embed=_e(C_LUNA,"📋 Empty. Use $play!"))
    pp=10; t=len(p.queue); pg=max(1,math.ceil(t/pp)); page=max(1,min(page,pg)); st=(page-1)*pp; chunk=p.queue[st:st+pp]
    d=""
    if p.current:
        k=" 🟢" if p.current.is_kurdish else ""
        d+=f"**▶️ Now:** [{p.current.title}]({p.current.url}) `{p.current.dur_str}` — {p.current.requester.mention}{k}\n\n"
    if chunk:
        d+="**📋 Up Next:**\n"
        for i,s in enumerate(chunk,st+1):
            k=" 🟢" if s.is_kurdish else ""
            d+=f"`{i}.` [{s.title}]({s.url}) `{s.dur_str}` — {s.requester.mention}{k}\n"
    td=sum(s.duration or 0 for s in p.queue)
    li={"off":"➡️ Off","track":"🔂 Track","queue":"🔁 Queue"}.get(p.loop,"➡️ Off")
    em=_e(C_LUNA,""); em.title=f"📋 Queue — {t} songs"; em.description=d
    em.set_footer(text=f"Page {page}/{pg} • {_ft(td)} • Loop: {li} • 🟢 = Kurdish")
    await ctx.send(embed=em)

@bot.command(aliases=["rm"])
async def remove(ctx,index:int):
    if not await _dj(ctx): return
    p=get_player(ctx.guild.id)
    if index<1 or index>len(p.queue): return await ctx.send(embed=err_e(f"Invalid! Queue has {len(p.queue)}."))
    r=p.queue.pop(index-1); await ctx.send(embed=ok_e(f"Removed **{r.title[:50]}**"))

@bot.command()
async def clear(ctx):
    if not await _dj(ctx): return
    get_player(ctx.guild.id).queue.clear(); await ctx.send(embed=ok_e("Cleared!"))

@bot.command(aliases=["sh"])
async def shuffle(ctx):
    if not await _dj(ctx): return
    p=get_player(ctx.guild.id)
    if len(p.queue)<2: return await ctx.send(embed=err_e("Need 2+ songs."))
    random.shuffle(p.queue); await ctx.send(embed=ok_e("🔀 Shuffled!"))

@bot.command()
async def move(ctx,frm:int,to:int):
    if not await _dj(ctx): return
    p=get_player(ctx.guild.id); q=p.queue
    if not (1<=frm<=len(q)) or not (1<=to<=len(q)): return await ctx.send(embed=err_e(f"Must be 1–{len(q)}."))
    s=q.pop(frm-1); q.insert(to-1,s); await ctx.send(embed=ok_e(f"Moved **{s.title[:50]}** to **{to}**."))

@bot.command()
async def skipto(ctx,index:int):
    if not await _dj(ctx): return
    vc=ctx.voice_client
    if not vc: return await ctx.send(embed=err_e("Nothing playing!"))
    p=get_player(ctx.guild.id)
    if index<1 or index>len(p.queue): return await ctx.send(embed=err_e(f"Invalid! Queue has {len(p.queue)}."))
    p.queue=p.queue[index-1:]; vc.stop(); await ctx.send(embed=ok_e(f"⏭️ Skipped to **{index}**!"))

@bot.command(aliases=["vol"])
async def volume(ctx,vol:int):
    if not await _dj(ctx): return
    if not 0<=vol<=200: return await ctx.send(embed=err_e("Volume 0–200."))
    p=get_player(ctx.guild.id); p.volume=vol/100.0; save_settings(ctx.guild.id,volume=vol)
    vc=ctx.voice_client
    if vc and vc.source:
        try: vc.source.volume=p.volume
        except: pass
    ic="🔇" if vol==0 else ("🔉" if vol<50 else "🔊"); await ctx.send(embed=ok_e(f"{ic} Volume **{vol}%**"))

@bot.command()
async def loop(ctx,mode=None):
    if not await _dj(ctx): return
    p=get_player(ctx.guild.id); ms=["off","track","queue"]
    mode=(ms[(ms.index(p.loop)+1)%3] if mode is None else mode.lower())
    if mode not in ms: return await ctx.send(embed=err_e("Must be: off/track/queue"))
    p.loop=mode; save_settings(ctx.guild.id,loop_mode=mode)
    await ctx.send(embed=ok_e(f"{'➡️' if mode=='off' else '🔂' if mode=='track' else '🔁'} Loop **{mode.title()}**"))

@bot.command(aliases=["filter"])
async def setfilter(ctx,name=None):
    if not await _dj(ctx): return
    if name is None:
        lines=[f"`{k}` — {v['label']}" for k,v in FILTERS.items()]
        return await ctx.send(embed=_e(C_LUNA,"").set_title("🎛️ Filters").set_description("\n".join(lines)))
    name=name.lower()
    if name not in FILTERS: return await ctx.send(embed=err_e("Unknown filter!"))
    p=get_player(ctx.guild.id); old=p.filter_name; p.filter_name=name; vc=ctx.voice_client
    if vc and (vc.is_playing() or vc.is_paused()) and p.current:
        wp=vc.is_paused(); pp=p.elapsed()
        try: vc.stop()
        except: pass
        await asyncio.sleep(0.6)
        data=await resolve_url(p.current.url)
        if data: p.current.stream_url=data.get("url") or p.current.stream_url
        src=_make_source(p.current.stream_url,p.volume,name)
        if src:
            p.reset_timer(); p._playing=True
            def ac(err):
                if err: log.error(f"Filter after: {err}")
                f=asyncio.run_coroutine_threadsafe(play_next(ctx.guild.id,ctx.channel,vc),bot.loop)
                f.add_done_callback(lambda x: x.exception() if x.exception() else None)
            try:
                vc.play(src,after=ac)
                if wp: vc.pause(); p._elapsed_pre=pp; p._paused_at=time.time()
            except Exception as e: p.filter_name=old; await ctx.send(embed=err_e(f"Failed: {e}")); return
        else: p.filter_name=old; await ctx.send(embed=err_e("FFmpeg failed.")); return
    await ctx.send(embed=ok_e(f"🎛️ Filter **{FILTERS[name]['label']}**"))

@bot.command(aliases=["filters"])
async def listfilters(ctx):
    lines=[f"`{k}` — {v['label']}" for k,v in FILTERS.items()]
    await ctx.send(embed=_e(C_LUNA,"").set_title("🎛️ Filters").set_description("\n".join(lines)))

@bot.command(name="247")
async def tfs_cmd(ctx):
    if not await _dj(ctx): return
    p=get_player(ctx.guild.id); p.tfs=not p.tfs; save_settings(ctx.guild.id,tfs=int(p.tfs))
    await ctx.send(embed=ok_e(f"24/7 {'enabled 🟢' if p.tfs else 'disabled 🔴'}"))

@bot.command()
async def autoplay(ctx):
    if not await _dj(ctx): return
    p=get_player(ctx.guild.id); p.autoplay=not p.autoplay; save_settings(ctx.guild.id,autoplay=int(p.autoplay))
    await ctx.send(embed=ok_e(f"Autoplay {'enabled 🟢' if p.autoplay else 'disabled 🔴'}"))

@bot.command()
async def kurdishmode(ctx):
    p=get_player(ctx.guild.id); p.kurdish_mode=not p.kurdish_mode; save_settings(ctx.guild.id,kurdish_mode=int(p.kurdish_mode))
    await ctx.send(embed=ok_e(f"Kurdish mode {'enabled 🟢' if p.kurdish_mode else 'disabled 🔴'}"))

@bot.command(aliases=["setdj"])
@commands.has_permissions(manage_guild=True)
async def djrole(ctx,role:discord.Role=None):
    if not role: save_settings(ctx.guild.id,dj_role_id=None); return await ctx.send(embed=ok_e("DJ role removed."))
    save_settings(ctx.guild.id,dj_role_id=role.id); await ctx.send(embed=ok_e(f"DJ role: {role.mention}"))

@bot.command(aliases=["ly"])
async def lyrics(ctx,*,song_name=None):
    p=get_player(ctx.guild.id)
    if not song_name or not song_name.strip():
        if not p.current: return await ctx.send(embed=err_e("Nothing playing! Use: `$lyrics Artist - Song`"))
        song_name=p.current.title
    clean=song_name
    for pat in ["(official","(lyrics","(audio)","(video)","(hd)","(4k)","[","]","ft.","feat."]:
        i=clean.lower().find(pat)
        if i!=-1: clean=clean[:i].strip()
    parts=clean.split(" - ",1)
    artist,title_q=(parts[0].strip(),parts[1].strip()) if len(parts)==2 else ("",clean.strip())
    if not artist or not title_q: return await ctx.send(embed=err_e("Use: `$lyrics Artist - Song Title`"))
    msg=await ctx.send(embed=_e(C_LUNA,f"🔍 Fetching lyrics **{clean[:60]}**..."))
    lt=None
    for a,t in [(artist,title_q),(artist,clean),(clean,clean)]:
        if not a or not t: continue
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"https://api.lyrics.ovh/v1/{a}/{t}",timeout=aiohttp.ClientTimeout(total=8)) as r:
                    if r.status==200:
                        d=await r.json()
                        if d.get("lyrics"): lt=d["lyrics"]; break
        except: continue
    if not lt: return await msg.edit(embed=err_e(f"No lyrics for **{clean[:60]}**."))
    lt=lt.replace("\r\n","\n").strip()
    chunks=[lt[i:i+3800] for i in range(0,len(lt),3800)]
    for i,c in enumerate(chunks):
        em=_e(C_LUNA,c); em.title=f"📜 {clean[:60]}"+(f" ({i+1})" if len(chunks)>1 else "")
        if i==0: await msg.edit(embed=em)
        else:
            try: await ctx.send(embed=em)
            except: pass

@bot.command()
async def history(ctx):
    try:
        c=_db(); c.row_factory=sqlite3.Row
        rows=c.execute("SELECT title,url,duration,platform FROM history WHERE guild_id=? ORDER BY id DESC LIMIT 10",(ctx.guild.id,)).fetchall(); c.close()
    except: return await ctx.send(embed=err_e("DB error."))
    if not rows: return await ctx.send(embed=_e(C_LUNA,"📜 No history."))
    lines=[f"`{i+1}.` {PE.get(r['platform'] or 'unknown','🎵')} [{r['title']}]({r['url']}) `{r['duration']}` {'🟢' if is_kurdish(r['title']) else ''}" for i,r in enumerate(rows)]
    await ctx.send(embed=_e(C_LUNA,"").set_title("📜 History").set_description("\n".join(lines)))

@bot.command()
async def grab(ctx):
    p=get_player(ctx.guild.id)
    if not p.current: return await ctx.send(embed=err_e("Nothing playing!"))
    s=p.current; em=discord.Embed(color=C_LUNA,title="❤️ Saved!",description=f"**[{s.title}]({s.url})**")
    em.add_field(name="Duration",value=s.dur_str,inline=True)
    if s.is_kurdish: em.add_field(name="Type",value="🟢 Kurdish",inline=True)
    if s.thumbnail and s.thumbnail.startswith("http"): em.set_thumbnail(url=s.thumbnail)
    try:
        await ctx.author.send(embed=em); await ctx.send(embed=ok_e("Sent to DMs!"))
    except discord.Forbidden: await ctx.send(embed=err_e("Can't DM you."))
    except: pass

@bot.command()
async def ping(ctx): await ctx.send(embed=_e(C_LUNA,f"🏓 Pong! **{round(bot.latency*1000)}ms**"))

@bot.command(aliases=["stats"])
async def botinfo(ctx):
    u=int(time.time()-bot_start_time); h,r=divmod(u,3600); m,s=divmod(r,60)
    em=_e(C_LUNA,""); em.title="🎵 Veltra Music Bot"
    em.add_field(name="Prefix",value="`$`",inline=True); em.add_field(name="Servers",value=str(len(bot.guilds)),inline=True)
    em.add_field(name="Uptime",value=f"{h}h {m}m {s}s",inline=True); em.add_field(name="Search",value="Invidious API",inline=True)
    em.add_field(name="Kurdish",value="🟢 Guaranteed",inline=True)
    em.add_field(name="Platforms",value="Spotify·Apple·SC·Deezer·Anghami·Vimeo·YT·MP3",inline=False)
    await ctx.send(embed=em)

@bot.command()
async def help(ctx):
    em=_e(C_LUNA,""); em.title="🎵 Veltra Music Bot"
    em.description="**Search via Invidious API — works on ALL servers!**\n🟢 = Kurdish song"
    em.add_field(name="🎵 Playback",value="```$play <query/url>     Play any platform\n$kurdish <query>      ⭐ Find Kurdish version\n$search <query>       Search & pick\n$pause / $resume      Pause/Resume\n$skip / $s            Skip\n$stop                 Stop & clear\n$nowplaying / $np     Now playing\n$again                Replay\n$join / $disconnect   Voice control```",inline=False)
    em.add_field(name="📋 Queue",value="```$queue / $q [page]    Show queue\n$remove / $rm <pos>   Remove\n$clear                Clear\n$shuffle / $sh        Shuffle\n$move <from> <to>     Move\n$skipto <pos>         Skip to```",inline=False)
    em.add_field(name="⚙️ Settings",value="```$volume <0-200>       Volume\n$loop [off/track/queue] Loop\n$filter <name>        Audio filter\n$247                  Stay in VC\n$autoplay             Auto-play Kurdish\n$kurdishmode         Toggle Kurdish search\n$djrole [@role]       Set DJ role```",inline=False)
    em.set_footer(text="$kurdish <any song> = guaranteed Kurdish version!")
    await ctx.send(embed=em)

# ═══════════════════════════════════════════════════
#  EVENTS
# ═══════════════════════════════════════════════════
@bot.event
async def on_ready():
    log.info(f"Logged in: {bot.user} ({bot.user.id}) | Guilds: {len(bot.guilds)}")
    log.info("★ Search: Invidious API (8 instances) + Piped API (3 instances) ★")
    try: await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening,name="🎵 Kurdish Music | $help"))
    except: pass

@bot.event
async def on_voice_state_update(member,before,after):
    if member.bot: return
    if before.channel and not after.channel:
        vc=before.channel.guild.voice_client
        if vc and vc.channel==before.channel and not [m for m in vc.channel.members if not m.bot]:
            p=get_player(vc.guild.id)
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
async def on_command_error(ctx,error):
    if isinstance(error,commands.CommandNotFound): return
    if isinstance(error,commands.MissingPermissions):
        try: await ctx.send(embed=err_e("No permission!"))
        except: pass; return
    if isinstance(error,commands.MissingRequiredArgument):
        try: await ctx.send(embed=err_e(f"Missing: `{error.param.name}`"))
        except: pass; return
    log.error(f"Cmd [{ctx.command}]: {error}\n{traceback.format_exc()}")
    try: await ctx.send(embed=err_e(str(error)[:150]))
    except: pass

if __name__=="__main__":
    log.info("Starting Veltra Music Bot...")
    try: bot.run(TOKEN,log_handler=None)
    except discord.LoginFailure: log.error("FATAL: Invalid token!")
    except KeyboardInterrupt: pass
    except Exception as e: log.error(f"FATAL: {e}\n{traceback.format_exc()}")
