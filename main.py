#  MUSIC SYSTEM  —  veltra Pro Music (powered by yt-dlp + FFmpeg)
#  Supports: YouTube · SoundCloud · Vimeo · Spotify* · Apple Music* ·
#            Deezer* · Anghami* · Direct MP3/MP4 links
#  (* resolves track name from the page, then searches YouTube for audio)
# ══════════════════════════════════════════════════════════════════════════════

C_MUSIC  = 0xB5179E
C_MGREEN = 0x57F287
C_MRED   = 0xED4245
C_MYELLOW= 0xFEE75C

# ── Music database (history + per-guild settings) ─────────────────────────────
_MUSIC_DB = "music.db"

def _mdb():
    conn = sqlite3.connect(_MUSIC_DB)
    conn.row_factory = sqlite3.Row
    return conn

def _init_music_db():
    c = _mdb()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS guild_music (
            guild_id   INTEGER PRIMARY KEY,
            dj_role_id INTEGER DEFAULT NULL,
            volume     INTEGER DEFAULT 100,
            loop_mode  TEXT    DEFAULT 'off',
            tfs        INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS song_history (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id  INTEGER,
            title     TEXT,
            url       TEXT,
            duration  TEXT,
            requester TEXT,
            played_at TEXT DEFAULT (datetime('now'))
        );
    """)
    c.commit(); c.close()

_init_music_db()

def _get_gsettings(gid):
    c = _mdb()
    row = c.execute("SELECT * FROM guild_music WHERE guild_id=?", (gid,)).fetchone()
    if not row:
        c.execute("INSERT OR IGNORE INTO guild_music (guild_id) VALUES (?)", (gid,))
        c.commit()
        row = c.execute("SELECT * FROM guild_music WHERE guild_id=?", (gid,)).fetchone()
    c.close(); return dict(row)

def _save_gsettings(gid, **kw):
    _get_gsettings(gid)
    sets = ", ".join(f"{k}=?" for k in kw)
    c = _mdb()
    c.execute(f"UPDATE guild_music SET {sets} WHERE guild_id=?", [*kw.values(), gid])
    c.commit(); c.close()

def _push_history(gid, title, url, dur, req):
    c = _mdb()
    c.execute(
        "INSERT INTO song_history (guild_id,title,url,duration,requester) VALUES (?,?,?,?,?)",
        (gid, title, url, dur, req),
    )
    c.execute(
        "DELETE FROM song_history WHERE guild_id=? AND id NOT IN "
        "(SELECT id FROM song_history WHERE guild_id=? ORDER BY id DESC LIMIT 50)",
        (gid, gid),
    )
    c.commit(); c.close()

# ── Audio filters ─────────────────────────────────────────────────────────────
MUSIC_FILTERS = {
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
    "pitch":     {"label": "🎵 Pitch Up",   "af": "asetrate=44100*1.15,aresample=44100"},
}

# ── yt-dlp helpers ────────────────────────────────────────────────────────────
# Kurdish regions: IQ=Iraq (Sorani), TR=Turkey (Kurmanji), IR=Iran (Sorani/Badinani)
_KURDISH_RE = re.compile(r'[\u0600-\u06FF\u0750-\u077F]')   # Arabic/Sorani Kurdish script

def _is_kurdish(text: str) -> bool:
    """Detect Sorani Kurdish (Arabic script) or common Kurdish Latin keywords."""
    if _KURDISH_RE.search(text):
        return True
    kw = ["kurdish","kurdi","kürtçe","kurmanji","sorani","badinani","hawler","silêmanî",
          "duhok","zaxo","erbil","suleymaniyah","kurd"]
    t = text.lower()
    return any(k in t for k in kw)

def _make_ydl_opts(region: str = "US") -> dict:
    """Build yt-dlp options for the given ISO country region."""
    lang_map = {
        "IQ": "ku,ku-IQ,ar-IQ,ar;q=0.8,en;q=0.5",
        "TR": "ku,ku-TR,tr;q=0.8,en;q=0.5",
        "IR": "ku,ku-IR,fa;q=0.8,en;q=0.5",
    }
    accept_lang = lang_map.get(region, "en-US,en;q=0.9")
    return {
        "format": "bestaudio/best",
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 20,
        "source_address": "0.0.0.0",
        "geo_bypass": True,
        "nocheckcertificate": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web"],
                "skip": ["dash", "hls"],
            }
        },
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Mobile Safari/537.36"
            ),
            "Accept-Language": accept_lang,
        },
    }

_YDL_BASE = _make_ydl_opts("US")

# Per-guild search region (default US; Kurdish auto-switches to IQ)
_guild_regions: dict = {}

def _region_for(guild_id: int, query: str = "") -> str:
    explicit = _guild_regions.get(guild_id, "US")
    if explicit != "US":
        return explicit
    # Auto-detect Kurdish text → use Iraq region
    if query and _is_kurdish(query):
        return "IQ"
    return "US"

async def _run_ydl(fn):
    return await asyncio.get_running_loop().run_in_executor(None, fn)

async def _ydl_search(query: str, guild_id: int = 0) -> list:
    region = _region_for(guild_id, query)
    def _do():
        opts = {**_make_ydl_opts(region), "noplaylist": True, "default_search": "ytsearch5"}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch5:{query}", download=False)
            entries = info.get("entries", [info])
            return [e for e in entries if e]
    return await _run_ydl(_do)

async def _ydl_resolve(url: str, guild_id: int = 0) -> dict:
    region = _region_for(guild_id)
    def _do():
        opts = {**_make_ydl_opts(region), "noplaylist": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
    return await _run_ydl(_do)

async def _ydl_playlist(url: str, guild_id: int = 0) -> list:
    region = _region_for(guild_id)
    def _do():
        opts = {**_make_ydl_opts(region), "extract_flat": "in_playlist", "noplaylist": False}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if "entries" in info:
                return [e for e in info["entries"] if e and e.get("id")]
            return [info]
    return await _run_ydl(_do)

# ── Multi-platform detection & resolution ─────────────────────────────────────
_PLATFORM_ICONS = {
    "spotify":    "🟢 Spotify",
    "applemusic": "🍎 Apple Music",
    "deezer":     "🟣 Deezer",
    "anghami":    "🎵 Anghami",
    "soundcloud": "🔶 SoundCloud",
    "vimeo":      "🔵 Vimeo",
    "direct":     "📁 Direct Link",
    "youtube":    "▶️ YouTube",
}

def _detect_platform(url: str) -> str:
    u = url.lower()
    if "spotify.com" in u:           return "spotify"
    if "music.apple.com" in u or "itunes.apple.com" in u: return "applemusic"
    if "deezer.com" in u:            return "deezer"
    if "anghami.com" in u:           return "anghami"
    if "soundcloud.com" in u:        return "soundcloud"
    if "vimeo.com" in u:             return "vimeo"
    if re.search(r'\.(mp3|mp4|m4a|ogg|webm|flac|wav|opus)(\?|$)', u): return "direct"
    return "youtube"

async def _scrape_og_title(url: str, platform: str) -> str:
    """Scrape og:title from a platform page to get track name for YouTube search."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers,
                                   timeout=aiohttp.ClientTimeout(total=10),
                                   allow_redirects=True) as resp:
                if resp.status != 200:
                    return ""
                html = await resp.text(errors="ignore")
        m = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\'](.*?)["\']', html)
        if m:
            title = m.group(1).strip()
            for suffix in [" - Spotify", " | Spotify", " on Spotify",
                           " - Apple Music", " | Apple Music",
                           " - Deezer", " | Deezer", " - Anghami", " | Anghami"]:
                if title.endswith(suffix):
                    title = title[: -len(suffix)].strip()
            return title
    except Exception as e:
        print(f"[Music] Scrape error ({platform}): {e}")
    return ""

async def _resolve_platform(url: str, guild_id: int = 0) -> dict:
    """Return a yt-dlp-compatible info dict for any supported URL."""
    platform = _detect_platform(url)

    if platform == "direct":
        name = url.split("?")[0].split("/")[-1] or "Direct Audio"
        return {"title": name, "url": url, "webpage_url": url,
                "duration": 0, "thumbnail": "", "uploader": "Direct Link"}

    if platform in ("youtube", "soundcloud", "vimeo"):
        return await _ydl_resolve(url, guild_id)

    # Spotify / Apple Music / Deezer / Anghami — scrape title → search YouTube
    title = await _scrape_og_title(url, platform)
    if not title:
        raise ValueError(f"Couldn't read track info from {_PLATFORM_ICONS.get(platform, platform)}. Is the link public?")
    results = await _ydl_search(title, guild_id)
    if not results:
        raise ValueError(f"No YouTube match found for: {title}")
    return results[0]

# ── FFmpeg source ─────────────────────────────────────────────────────────────
def _make_music_source(stream_url: str, volume: float, audio_filter: str):
    af = MUSIC_FILTERS.get(audio_filter, MUSIC_FILTERS["none"])["af"]
    options = "-vn" + (f" -af {af}" if af else "")
    src = discord.FFmpegPCMAudio(
        stream_url,
        before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin",
        options=options,
    )
    return discord.PCMVolumeTransformer(src, volume=volume)

# ── Song ──────────────────────────────────────────────────────────────────────
class Song:
    __slots__ = ("title","url","stream_url","duration","thumbnail","uploader","requester","platform")

    def __init__(self, data: dict, requester, platform: str = "youtube"):
        self.title      = data.get("title", "Unknown")
        self.url        = data.get("webpage_url") or data.get("original_url") or data.get("url", "")
        self.stream_url = data.get("url", "")
        self.duration   = data.get("duration") or 0
        self.thumbnail  = data.get("thumbnail", "")
        self.uploader   = data.get("uploader") or data.get("channel", "Unknown")
        self.requester  = requester
        self.platform   = platform

    @property
    def dur_str(self) -> str:
        if not self.duration: return "🔴 LIVE"
        m, s = divmod(int(self.duration), 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

    def progress_bar(self, elapsed: float, length: int = 14) -> str:
        if not self.duration: return "─" * length + " 🔴"
        pct  = min(elapsed / self.duration, 1.0)
        fill = int(pct * length)
        return "▬" * fill + "🔘" + "▬" * (length - fill)

    @property
    def icon(self) -> str:
        return {"spotify":"🟢","applemusic":"🍎","soundcloud":"🔶",
                "deezer":"🟣","anghami":"🎵","vimeo":"🔵",
                "direct":"📁","youtube":"▶️"}.get(self.platform, "🎵")

# ── MusicPlayer ───────────────────────────────────────────────────────────────
class MusicPlayer:
    def __init__(self, gid: int):
        self.guild_id       = gid
        self.queue: list    = []
        self.current        = None
        self.history: list  = []
        self.loop           = "off"
        self.volume         = 1.0
        self.audio_filter   = "none"
        self.skip_votes     = set()
        self.tfs            = False
        self._start         = None
        self._paused_at     = None
        self._elapsed_pre   = 0.0
        self.np_msg         = None
        self._changing_filter = False

    def elapsed(self) -> float:
        if self._start is None: return 0.0
        if self._paused_at is not None: return self._elapsed_pre
        return self._elapsed_pre + (time.time() - self._start)

    def reset_timer(self):
        self._start = time.time(); self._paused_at = None; self._elapsed_pre = 0.0

_music_players: dict = {}

def _get_player(gid: int) -> MusicPlayer:
    if gid not in _music_players:
        p = MusicPlayer(gid)
        s = _get_gsettings(gid)
        p.volume = s["volume"] / 100.0
        p.loop   = s["loop_mode"]
        p.tfs    = bool(s["tfs"])
        _music_players[gid] = p
    return _music_players[gid]

# ── Now Playing embed ─────────────────────────────────────────────────────────
def _fmt_dur(sec) -> str:
    if not sec: return "0:00"
    m, s = divmod(int(sec), 60); h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

def _build_np_embed(player: MusicPlayer, vc) -> discord.Embed:
    song    = player.current
    elapsed = player.elapsed()
    paused  = vc.is_paused() if vc else False

    # Luna/Lana style — deep purple embed with large thumbnail banner
    e = discord.Embed(color=0x9B59B6)
    status_icon = "⏸️" if paused else "🎵"
    e.set_author(name=f"{status_icon}  Now Playing  —  Hill Music")

    title_display = song.title if len(song.title) <= 60 else song.title[:57] + "..."
    e.title = title_display
    if song.url and song.url.startswith("http"):
        e.url = song.url

    # Progress bar
    bar  = song.progress_bar(elapsed, 16)
    e.description = (
        f"\n"
        f"`{_fmt_dur(elapsed)}` **{bar}** `{song.dur_str}`\n"
    )

    loop_disp = {"off": "➡️ Off", "track": "🔂 Track", "queue": "🔁 Queue"}[player.loop]
    vol_icon  = "🔇" if player.volume == 0 else ("🔉" if player.volume < 0.5 else "🔊")
    flt_label = MUSIC_FILTERS.get(player.audio_filter, MUSIC_FILTERS["none"])["label"]

    e.add_field(name="🎤  Artist",          value=f"```{song.uploader}```",        inline=True)
    e.add_field(name="⏱️  Duration",        value=f"```{song.dur_str}```",          inline=True)
    e.add_field(name=f"{vol_icon}  Volume", value=f"```{int(player.volume*100)}%```", inline=True)
    e.add_field(name="🔁  Loop",            value=f"```{loop_disp}```",              inline=True)
    e.add_field(name="🎛️  Filter",          value=f"```{flt_label}```",              inline=True)
    e.add_field(name="📋  Queue",           value=f"```{len(player.queue)} track(s)```", inline=True)
    e.add_field(name="👤  Requested by",    value=song.requester.mention,           inline=False)

    if song.thumbnail:
        e.set_image(url=song.thumbnail)

    platform_name = {
        "spotify":"Spotify","applemusic":"Apple Music","soundcloud":"SoundCloud",
        "deezer":"Deezer","anghami":"Anghami","vimeo":"Vimeo",
        "direct":"Direct","youtube":"YouTube",
    }.get(song.platform, "YouTube")

    e.set_footer(text=f"Hill Music  •  {platform_name}  •  {'⏸  Paused' if paused else '▶️  Playing'}")
    return e

# ── Now Playing buttons ───────────────────────────────────────────────────────
class NPView(discord.ui.View):
    def __init__(self, player: MusicPlayer, vc):
        super().__init__(timeout=None)
        paused = vc.is_paused() if vc else False
        btns = [
            ("⏮️","prev",   discord.ButtonStyle.secondary, 0),
            ("▶️" if paused else "⏸️","pause",discord.ButtonStyle.primary,0),
            ("⏭️","skip",   discord.ButtonStyle.secondary, 0),
            ("⏹️","mstop",  discord.ButtonStyle.danger,    0),
            ("🔂" if player.loop=="track" else "🔁" if player.loop=="queue" else "➡️",
             "loop",discord.ButtonStyle.secondary,1),
            ("🔀","shuffle",discord.ButtonStyle.secondary, 1),
            ("❤️","grab",   discord.ButtonStyle.secondary, 1),
            ("📋","qview",  discord.ButtonStyle.secondary, 1),
        ]
        for emoji, action, style, row in btns:
            self.add_item(_NPBtn(emoji, action, style, row))

class _NPBtn(discord.ui.Button):
    def __init__(self, emoji, action, style, row):
        super().__init__(emoji=emoji, style=style, row=row,
                         custom_id=f"hm_{action}_{random.randint(0,9999999)}")
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        vc     = interaction.guild.voice_client
        player = _get_player(interaction.guild.id)
        if not vc or not player.current:
            return await interaction.response.send_message(
                embed=discord.Embed(color=C_MRED, description="❌ Nothing is playing!"), ephemeral=True)

        if self.action == "pause":
            if vc.is_paused():
                player._elapsed_pre = player.elapsed(); player._start = time.time(); player._paused_at = None
                vc.resume()
            else:
                player._elapsed_pre = player.elapsed(); player._paused_at = time.time()
                vc.pause()
        elif self.action == "skip":
            player.skip_votes.clear(); vc.stop()
        elif self.action == "mstop":
            player.queue.clear(); player.loop = "off"; vc.stop()
            return await interaction.response.send_message(
                embed=discord.Embed(color=C_MGREEN, description="⏹️ Stopped & cleared queue."), ephemeral=True)
        elif self.action == "loop":
            modes = ["off","track","queue"]
            player.loop = modes[(modes.index(player.loop)+1)%3]
            _save_gsettings(interaction.guild.id, loop_mode=player.loop)
        elif self.action == "shuffle":
            random.shuffle(player.queue)
            return await interaction.response.send_message(
                embed=discord.Embed(color=C_MGREEN, description="🔀 Queue shuffled!"), ephemeral=True)
        elif self.action == "grab":
            song = player.current
            e = discord.Embed(color=C_MUSIC, title="❤️ Saved Song",
                              description=f"**[{song.title}]({song.url})**")
            e.add_field(name="Duration", value=song.dur_str, inline=True)
            e.add_field(name="Artist",   value=song.uploader, inline=True)
            if song.thumbnail: e.set_thumbnail(url=song.thumbnail)
            try:
                await interaction.user.send(embed=e)
                return await interaction.response.send_message(
                    embed=discord.Embed(color=C_MGREEN, description="❤️ Sent to your DMs!"), ephemeral=True)
            except discord.Forbidden:
                return await interaction.response.send_message(
                    embed=discord.Embed(color=C_MRED, description="❌ Enable DMs from server members."), ephemeral=True)
        elif self.action == "qview":
            q = player.queue
            if not q:
                return await interaction.response.send_message(
                    embed=discord.Embed(color=C_MUSIC, title="📋 Queue", description="Queue is empty."), ephemeral=True)
            lines = [f"`{i+1}.` [{s.title}]({s.url}) `{s.dur_str}`" for i,s in enumerate(q[:10])]
            extra = f"\n*+{len(q)-10} more...*" if len(q)>10 else ""
            return await interaction.response.send_message(
                embed=discord.Embed(color=C_MUSIC, title=f"📋 Queue — {len(q)} song(s)",
                                    description="\n".join(lines)+extra), ephemeral=True)
        elif self.action == "prev":
            if player.history:
                prev = player.history.pop()
                if player.current: player.queue.insert(0, player.current)
                player.queue.insert(0, prev); vc.stop()
            else:
                return await interaction.response.send_message(
                    embed=discord.Embed(color=C_MRED, description="❌ No previous song!"), ephemeral=True)
        try:
            await interaction.message.edit(embed=_build_np_embed(player, vc), view=NPView(player, vc))
            await interaction.response.defer()
        except Exception:
            try: await interaction.response.defer()
            except Exception: pass

# ── Playback engine ───────────────────────────────────────────────────────────
async def _music_play_next(guild_id: int, channel, vc):
    player = _get_player(guild_id)

    if player.loop == "track" and player.current:
        song = player.current
    elif player.loop == "queue" and player.current:
        player.queue.append(player.current)
        song = player.queue.pop(0) if player.queue else None
    else:
        song = player.queue.pop(0) if player.queue else None

    if song is None:
        if player.current:
            _push_history(guild_id, player.current.title, player.current.url,
                          player.current.dur_str, str(player.current.requester))
        player.current = None; player.np_msg = None
        if not player.tfs:
            await asyncio.sleep(300)
            p2 = _get_player(guild_id)
            if not p2.current and not p2.queue and vc.is_connected():
                await vc.disconnect(); _music_players.pop(guild_id, None)
                try:
                    await channel.send(embed=discord.Embed(
                        color=C_MUSIC, description="👋 Left voice channel (idle 5 min)."))
                except Exception: pass
        return

    if player.current and player.current is not song:
        _push_history(guild_id, player.current.title, player.current.url,
                      player.current.dur_str, str(player.current.requester))
        player.history.append(player.current)
        if len(player.history) > 20: player.history.pop(0)

    player.current = song; player.skip_votes.clear()

    # Resolve stream URL for entries that only have a webpage_url
    if not song.stream_url or song.stream_url == song.url:
        try:
            data = await _ydl_resolve(song.url, guild_id)
            song.stream_url = data.get("url", "")
            song.thumbnail  = song.thumbnail or data.get("thumbnail", "")
            song.duration   = song.duration   or data.get("duration", 0)
            song.uploader   = song.uploader   or data.get("uploader") or data.get("channel", "Unknown")
        except Exception as e:
            try:
                await channel.send(embed=discord.Embed(
                    color=C_MRED, description=f"⚠️ Skipping **{song.title}** — {e}"))
            except Exception: pass
            await _music_play_next(guild_id, channel, vc); return

    try:
        source = _make_music_source(song.stream_url, player.volume, player.audio_filter)
    except Exception as e:
        try:
            await channel.send(embed=discord.Embed(color=C_MRED, description=f"⚠️ FFmpeg error: {e}"))
        except Exception: pass
        await _music_play_next(guild_id, channel, vc); return

    player.reset_timer()

    def _after(err):
        if err: print(f"[Music] Player error: {err}")
        if _get_player(guild_id)._changing_filter: return
        asyncio.run_coroutine_threadsafe(_music_play_next(guild_id, channel, vc), bot.loop)

    vc.play(source, after=_after)

    embed = _build_np_embed(player, vc)
    view  = NPView(player, vc)
    try:
        if player.np_msg:
            try: await player.np_msg.edit(embed=embed, view=view)
            except (discord.NotFound, discord.HTTPException):
                player.np_msg = await channel.send(embed=embed, view=view)
        else:
            player.np_msg = await channel.send(embed=embed, view=view)
    except Exception: pass

# ── Helper funcs ──────────────────────────────────────────────────────────────
def _merr(d): return discord.Embed(color=C_MRED,   description=f"❌ {d}")
def _mok(d):  return discord.Embed(color=C_MGREEN, description=f"✅ {d}")

async def _ensure_vc(ctx):
    if not ctx.author.voice:
        await ctx.send(embed=_merr("You must be in a voice channel!")); return None
    vc = ctx.voice_client
    if not vc:
        try:
            vc = await ctx.author.voice.channel.connect(self_deaf=True)
        except Exception as e:
            await ctx.send(embed=_merr(f"Couldn't connect: {e}")); return None
    elif ctx.author.voice.channel != vc.channel:
        await vc.move_to(ctx.author.voice.channel)
    return vc

async def _dj_check(ctx) -> bool:
    if ctx.author.guild_permissions.manage_guild: return True
    s     = _get_gsettings(ctx.guild.id)
    dj_id = s.get("dj_role_id")
    if dj_id:
        role = ctx.guild.get_role(int(dj_id))
        if role and role in ctx.author.roles: return True
        await ctx.send(embed=_merr(f"You need the **{role.name if role else dj_id}** DJ role!"))
        return False
    return True

# ── NP refresh loop ───────────────────────────────────────────────────────────
@tasks.loop(seconds=15)
async def _music_refresh_np():
    for gid, player in list(_music_players.items()):
        if not player.current or not player.np_msg: continue
        guild = bot.get_guild(gid)
        if not guild: continue
        vc = guild.voice_client
        if not vc or (not vc.is_playing() and not vc.is_paused()): continue
        try:
            await player.np_msg.edit(embed=_build_np_embed(player, vc))
        except (discord.NotFound, discord.HTTPException):
            player.np_msg = None
        except Exception: pass

# ══════════════════════════════════════════════════════════════════════════════
#  MUSIC COMMANDS
# ══════════════════════════════════════════════════════════════════════════════

@bot.command(name="join", aliases=["j"])
async def music_join(ctx):
    vc = await _ensure_vc(ctx)
    if vc: await ctx.send(embed=_mok(f"Joined **{vc.channel.name}**! 🎧"))


@bot.command(name="leave", aliases=["dc", "disconnect"])
async def music_leave(ctx):
    if not ctx.voice_client:
        return await ctx.send(embed=_merr("I'm not in a voice channel!"))
    if not await _dj_check(ctx): return
    player = _get_player(ctx.guild.id)
    player.queue.clear(); ctx.voice_client.stop()
    await ctx.voice_client.disconnect()
    _music_players.pop(ctx.guild.id, None)
    await ctx.send(embed=_mok("Disconnected! 👋"))


@bot.command(name="play", aliases=["p"])
async def music_play(ctx, *, query: str):
    vc = await _ensure_vc(ctx)
    if not vc: return
    player = _get_player(ctx.guild.id)
    msg    = await ctx.send(embed=discord.Embed(color=C_MUSIC, description=f"🔍 Searching for **{query}**..."))

    try:
        is_url   = query.startswith(("http://","https://"))
        platform = _detect_platform(query) if is_url else "search"

        if is_url and platform not in ("youtube","soundcloud","vimeo","direct","search"):
            await msg.edit(embed=discord.Embed(color=C_MUSIC,
                description=f"🔍 Resolving from **{_PLATFORM_ICONS.get(platform,platform)}**..."))

        # Playlist
        if is_url and ("list=" in query or "playlist" in query.lower()) and platform in ("youtube",""):
            entries = await _ydl_playlist(query, ctx.guild.id)
            if not entries: return await msg.edit(embed=_merr("Nothing found in that playlist."))
            added = 0
            for entry in entries:
                eid = entry.get("id")
                if not eid: continue
                data = {"title": entry.get("title") or "Unknown",
                        "url":   f"https://www.youtube.com/watch?v={eid}",
                        "webpage_url": f"https://www.youtube.com/watch?v={eid}",
                        "duration":  entry.get("duration", 0),
                        "thumbnail": (entry.get("thumbnail") or
                                      (entry.get("thumbnails") or [{}])[-1].get("url","")),
                        "uploader":  entry.get("uploader") or entry.get("channel","")}
                player.queue.append(Song(data, ctx.author, "youtube")); added += 1
            e = discord.Embed(color=C_MUSIC, title="📋 Playlist Added!")
            e.add_field(name="Songs",    value=str(added),             inline=True)
            e.add_field(name="In Queue", value=str(len(player.queue)), inline=True)
            await msg.edit(embed=e)

        # Single URL (any platform)
        elif is_url:
            data = await _resolve_platform(query, ctx.guild.id)
            song = Song(data, ctx.author, platform)
            player.queue.append(song)
            if vc.is_playing() or vc.is_paused():
                e = discord.Embed(color=C_MUSIC, title="➕ Added to Queue",
                                  description=f"**{song.title}**")
                e.add_field(name="Duration", value=song.dur_str, inline=True)
                e.add_field(name="Position", value=f"#{len(player.queue)}", inline=True)
                if song.thumbnail: e.set_thumbnail(url=song.thumbnail)
                await msg.edit(embed=e)
            else:
                await msg.delete()

        # Text search
        else:
            results = await _ydl_search(query, ctx.guild.id)
            if not results: return await msg.edit(embed=_merr("No results found!"))
            data = results[0]
            song = Song(data, ctx.author, "youtube")
            player.queue.append(song)
            if vc.is_playing() or vc.is_paused():
                e = discord.Embed(color=C_MUSIC, title="➕ Added to Queue",
                                  description=f"**{song.title}**")
                e.add_field(name="Duration", value=song.dur_str, inline=True)
                e.add_field(name="Position", value=f"#{len(player.queue)}", inline=True)
                if song.thumbnail: e.set_thumbnail(url=song.thumbnail)
                await msg.edit(embed=e)
            else:
                await msg.delete()

    except Exception as ex:
        return await msg.edit(embed=_merr(f"Error: {ex}"))

    if not vc.is_playing() and not vc.is_paused():
        await _music_play_next(ctx.guild.id, ctx.channel, vc)


@bot.command(name="search", aliases=["find"])
async def music_search(ctx, *, query: str):
    msg = await ctx.send(embed=discord.Embed(color=C_MUSIC, description=f"🔍 Searching **{query}**..."))
    try:
        results = (await _ydl_search(query, ctx.guild.id))[:5]
    except Exception as ex:
        return await msg.edit(embed=_merr(str(ex)))
    if not results: return await msg.edit(embed=_merr("No results found!"))

    lines = [
        f"`{i+1}.` [{r.get('title','?')}](https://youtu.be/{r.get('id','')}) "
        f"`{_fmt_dur(r.get('duration') or 0)}`"
        for i,r in enumerate(results)
    ]
    e = discord.Embed(color=C_MUSIC, title="🔍 Search Results", description="\n".join(lines))
    e.set_footer(text="Reply with a number 1–5  •  or 'cancel'")
    await msg.edit(embed=e)

    def check(m): return m.author == ctx.author and m.channel == ctx.channel
    try:
        reply = await bot.wait_for("message", check=check, timeout=30)
    except asyncio.TimeoutError:
        return await msg.edit(embed=_merr("Selection timed out."))
    try: await reply.delete()
    except Exception: pass
    if reply.content.lower() == "cancel":
        return await msg.edit(embed=_mok("Cancelled."))
    try:
        idx = int(reply.content) - 1
        if idx < 0 or idx >= len(results): raise ValueError
    except ValueError:
        return await msg.edit(embed=_merr("Invalid selection."))

    vc = await _ensure_vc(ctx)
    if not vc: return
    player = _get_player(ctx.guild.id)
    try:
        full = await _ydl_resolve(f"https://www.youtube.com/watch?v={results[idx]['id']}", ctx.guild.id)
    except Exception as ex:
        return await msg.edit(embed=_merr(str(ex)))
    song = Song(full, ctx.author, "youtube")
    player.queue.append(song)
    e2 = discord.Embed(color=C_MUSIC, title="➕ Added to Queue",
                       description=f"**[{song.title}]({song.url})**")
    e2.add_field(name="Duration", value=song.dur_str, inline=True)
    if song.thumbnail: e2.set_thumbnail(url=song.thumbnail)
    await msg.edit(embed=e2)
    if not vc.is_playing() and not vc.is_paused():
        await _music_play_next(ctx.guild.id, ctx.channel, vc)


@bot.command(name="pause", aliases=["pa"])
async def music_pause(ctx):
    vc = ctx.voice_client
    if not vc or not vc.is_playing():
        return await ctx.send(embed=_merr("Nothing is playing!"))
    if not await _dj_check(ctx): return
    player = _get_player(ctx.guild.id)
    player._elapsed_pre = player.elapsed(); player._paused_at = time.time()
    vc.pause()
    await ctx.send(embed=_mok("Paused ⏸️"))


@bot.command(name="resume", aliases=["res"])
async def music_resume(ctx):
    vc = ctx.voice_client
    if not vc or not vc.is_paused():
        return await ctx.send(embed=_merr("Nothing is paused!"))
    if not await _dj_check(ctx): return
    player = _get_player(ctx.guild.id)
    player._elapsed_pre = player.elapsed(); player._start = time.time(); player._paused_at = None
    vc.resume()
    await ctx.send(embed=_mok("Resumed ▶️"))


@bot.command(name="skip", aliases=["s"])
async def music_skip(ctx):
    vc = ctx.voice_client
    if not vc or (not vc.is_playing() and not vc.is_paused()):
        return await ctx.send(embed=_merr("Nothing is playing!"))
    player  = _get_player(ctx.guild.id)
    is_dj   = ctx.author.guild_permissions.manage_guild
    s       = _get_gsettings(ctx.guild.id)
    dj_id   = s.get("dj_role_id")
    dj_role = ctx.guild.get_role(int(dj_id)) if dj_id else None
    if is_dj or (dj_role and dj_role in ctx.author.roles):
        player.skip_votes.clear(); vc.stop()
        return await ctx.send(embed=_mok("⏭️ Skipped!"))
    vc_members = [m for m in vc.channel.members if not m.bot]
    needed     = max(1, math.ceil(len(vc_members) * 0.5))
    player.skip_votes.add(ctx.author.id)
    votes = len(player.skip_votes)
    if votes >= needed:
        player.skip_votes.clear(); vc.stop()
        await ctx.send(embed=_mok(f"⏭️ Vote passed ({votes}/{needed})! Skipped."))
    else:
        await ctx.send(embed=discord.Embed(color=C_MYELLOW,
            description=f"🗳️ Skip vote: **{votes}/{needed}** — need {needed-votes} more."))


@bot.command(name="stop")
async def music_stop(ctx):
    if not await _dj_check(ctx): return
    vc = ctx.voice_client
    if not vc: return await ctx.send(embed=_merr("I'm not in a voice channel!"))
    player = _get_player(ctx.guild.id)
    player.queue.clear(); player.loop = "off"; vc.stop()
    await ctx.send(embed=_mok("⏹️ Stopped and cleared the queue."))


@bot.command(name="nowplaying", aliases=["np"])
async def music_np(ctx):
    vc = ctx.voice_client
    if not vc: return await ctx.send(embed=_merr("I'm not in a voice channel!"))
    player = _get_player(ctx.guild.id)
    if not player.current: return await ctx.send(embed=_merr("Nothing is playing!"))
    player.np_msg = await ctx.send(embed=_build_np_embed(player, vc), view=NPView(player, vc))


@bot.command(name="again", aliases=["replay", "rewind"])
async def music_again(ctx):
    vc = ctx.voice_client
    if not vc or not vc.is_playing():
        return await ctx.send(embed=_merr("Nothing is playing!"))
    if not await _dj_check(ctx): return
    player = _get_player(ctx.guild.id)
    if not player.current: return await ctx.send(embed=_merr("Nothing is playing!"))
    player.queue.insert(0, player.current); vc.stop()
    await ctx.send(embed=_mok("🔁 Replaying from the beginning!"))


@bot.command(name="queue", aliases=["q"])
async def music_queue(ctx, page: int = 1):
    player = _get_player(ctx.guild.id)
    if not player.current and not player.queue:
        return await ctx.send(embed=discord.Embed(
            color=C_MUSIC, title="📋 Queue",
            description="Empty! Use `$play` to add songs."))
    per_page = 10
    pages    = max(1, math.ceil(len(player.queue) / per_page))
    page     = max(1, min(page, pages))
    start    = (page-1) * per_page
    chunk    = player.queue[start:start+per_page]
    desc     = ""
    if player.current:
        desc += (f"**▶️ Now Playing:**\n[{player.current.title}]({player.current.url}) "
                 f"`{player.current.dur_str}` — {player.current.requester.mention}\n\n")
    if chunk:
        desc += "**📋 Up Next:**\n"
        for i,s in enumerate(chunk, start=start+1):
            desc += f"`{i}.` [{s.title}]({s.url}) `{s.dur_str}` — {s.requester.mention}\n"
    total_dur = sum(s.duration or 0 for s in player.queue)
    loop_icon = {"off":"➡️ Off","track":"🔂 Track","queue":"🔁 Queue"}[player.loop]
    e = discord.Embed(color=C_MUSIC, title=f"📋 Queue — {len(player.queue)} song(s)", description=desc)
    e.set_footer(text=f"Page {page}/{pages}  •  Total: {_fmt_dur(total_dur)}  •  Loop: {loop_icon}")
    await ctx.send(embed=e)


@bot.command(name="remove", aliases=["rm"])
async def music_remove(ctx, index: int):
    if not await _dj_check(ctx): return
    player = _get_player(ctx.guild.id)
    if index < 1 or index > len(player.queue):
        return await ctx.send(embed=_merr(f"Invalid position. Queue has {len(player.queue)} songs."))
    removed = player.queue.pop(index-1)
    await ctx.send(embed=_mok(f"Removed **{removed.title}** from the queue."))


@bot.command(name="qclear")
async def music_qclear(ctx):
    if not await _dj_check(ctx): return
    _get_player(ctx.guild.id).queue.clear()
    await ctx.send(embed=_mok("Queue cleared! Current song continues."))


@bot.command(name="shuffle", aliases=["sh"])
async def music_shuffle(ctx):
    if not await _dj_check(ctx): return
    player = _get_player(ctx.guild.id)
    if len(player.queue) < 2:
        return await ctx.send(embed=_merr("Need at least 2 songs to shuffle."))
    random.shuffle(player.queue)
    await ctx.send(embed=_mok("🔀 Queue shuffled!"))


@bot.command(name="move", aliases=["mv"])
async def music_move(ctx, frm: int, to: int):
    if not await _dj_check(ctx): return
    player = _get_player(ctx.guild.id)
    q = player.queue
    if not (1<=frm<=len(q)) or not (1<=to<=len(q)):
        return await ctx.send(embed=_merr(f"Positions must be 1–{len(q)}."))
    song = q.pop(frm-1); q.insert(to-1, song)
    await ctx.send(embed=_mok(f"Moved **{song.title}** to position **{to}**."))


@bot.command(name="skipto")
async def music_skipto(ctx, index: int):
    if not await _dj_check(ctx): return
    vc = ctx.voice_client
    if not vc: return await ctx.send(embed=_merr("Nothing is playing!"))
    player = _get_player(ctx.guild.id)
    if index < 1 or index > len(player.queue):
        return await ctx.send(embed=_merr(f"Invalid position. Queue has {len(player.queue)} songs."))
    player.queue = player.queue[index-1:]; vc.stop()
    await ctx.send(embed=_mok(f"⏭️ Jumping to position **{index}**!"))


@bot.command(name="volume", aliases=["vol"])
async def music_volume(ctx, vol: int):
    if not await _dj_check(ctx): return
    if not 0 <= vol <= 200:
        return await ctx.send(embed=_merr("Volume must be 0–200."))
    player = _get_player(ctx.guild.id)
    player.volume = vol/100.0
    _save_gsettings(ctx.guild.id, volume=vol)
    vc = ctx.voice_client
    if vc and vc.source: vc.source.volume = player.volume
    icon = "🔇" if vol==0 else ("🔉" if vol<50 else "🔊")
    await ctx.send(embed=_mok(f"{icon} Volume set to **{vol}%**"))


@bot.command(name="loop")
async def music_loop(ctx, mode: str = None):
    if not await _dj_check(ctx): return
    player = _get_player(ctx.guild.id)
    modes  = ["off","track","queue"]
    if mode is None: mode = modes[(modes.index(player.loop)+1)%3]
    mode = mode.lower()
    if mode not in modes:
        return await ctx.send(embed=_merr("Mode must be: `off`, `track`, or `queue`"))
    player.loop = mode; _save_gsettings(ctx.guild.id, loop_mode=mode)
    icon = {"off":"➡️","track":"🔂","queue":"🔁"}[mode]
    await ctx.send(embed=_mok(f"{icon} Loop set to **{mode.capitalize()}**"))


@bot.command(name="filter", aliases=["setfilter","fx"])
async def music_filter(ctx, name: str = None):
    if not await _dj_check(ctx): return
    if name is None:
        lines = [f"`{k}` — {v['label']}" for k,v in MUSIC_FILTERS.items()]
        e = discord.Embed(color=C_MUSIC, title="🎛️ Audio Filters", description="\n".join(lines))
        e.set_footer(text="Usage: $filter <name>  •  $filter none  to reset")
        return await ctx.send(embed=e)
    name = name.lower()
    if name not in MUSIC_FILTERS:
        return await ctx.send(embed=_merr("Unknown filter! Use `$filter` to see the list."))
    player = _get_player(ctx.guild.id)
    player.audio_filter = name
    vc = ctx.voice_client
    if vc and (vc.is_playing() or vc.is_paused()) and player.current:
        was_paused = vc.is_paused(); paused_pos = player.elapsed()
        player._changing_filter = True; vc.stop()
        await asyncio.sleep(0.4)
        try:
            data = await _ydl_resolve(player.current.url, ctx.guild.id)
            player.current.stream_url = data.get("url", player.current.stream_url)
        except Exception: pass
        source = _make_music_source(player.current.stream_url, player.volume, name)
        player._elapsed_pre = 0.0; player._start = time.time()
        player._paused_at = None; player._changing_filter = False
        def _after_f(e_):
            asyncio.run_coroutine_threadsafe(_music_play_next(ctx.guild.id, ctx.channel, vc), bot.loop)
        vc.play(source, after=_after_f)
        if was_paused:
            vc.pause(); player._elapsed_pre = paused_pos; player._paused_at = time.time()
    await ctx.send(embed=_mok(f"🎛️ Filter set to **{MUSIC_FILTERS[name]['label']}**"))


@bot.command(name="247")
async def music_tfs(ctx):
    if not await _dj_check(ctx): return
    player = _get_player(ctx.guild.id)
    player.tfs = not player.tfs; _save_gsettings(ctx.guild.id, tfs=int(player.tfs))
    await ctx.send(embed=_mok(f"24/7 mode **{'enabled 🟢' if player.tfs else 'disabled 🔴'}**"))


@bot.command(name="djrole", aliases=["setdj"])
@commands.has_permissions(manage_guild=True)
async def music_djrole(ctx, role: discord.Role = None):
    if role is None:
        _save_gsettings(ctx.guild.id, dj_role_id=None)
        return await ctx.send(embed=_mok("DJ role removed. Everyone can control music."))
    _save_gsettings(ctx.guild.id, dj_role_id=role.id)
    await ctx.send(embed=_mok(f"DJ role set to {role.mention}."))


@bot.command(name="region", aliases=["setregion"])
@commands.has_permissions(manage_guild=True)
async def music_region(ctx, code: str = None):
    """Set the YouTube search region for Kurdish/regional song support.
    Usage: $region IQ  (Iraq/Kurdish Sorani)
           $region TR  (Turkey/Kurdish Kurmanji)
           $region IR  (Iran/Kurdish Sorani-Badinani)
           $region US  (default)
           $region     (show current)
    """
    valid = {"IQ": "🇮🇶 Iraq (Kurdish Sorani)",
             "TR": "🇹🇷 Turkey (Kurdish Kurmanji)",
             "IR": "🇮🇷 Iran (Kurdish Sorani/Badinani)",
             "US": "🇺🇸 United States (default)",
             "GB": "🇬🇧 United Kingdom",
             "DE": "🇩🇪 Germany",
             "FR": "🇫🇷 France",
             "SA": "🇸🇦 Saudi Arabia",
             "AE": "🇦🇪 UAE",
             "KW": "🇰🇼 Kuwait",
             "SY": "🇸🇾 Syria"}
    if code is None:
        current = _guild_regions.get(ctx.guild.id, "US")
        label   = valid.get(current, current)
        note    = "\n\n🌍 **Kurdish text is auto-detected** — if you type a Kurdish song name the bot will automatically use Iraq region for better results."
        lines   = "\n".join(f"`{k}` — {v}" for k, v in valid.items())
        e = discord.Embed(color=0x9B59B6, title="🌐 Search Region",
                          description=f"**Current:** {label}{note}\n\n**Available regions:**\n{lines}")
        e.set_footer(text="$region <code>  •  Admin only")
        return await ctx.send(embed=e)
    code = code.upper()
    if code not in valid:
        return await ctx.send(embed=_merr(f"Unknown region `{code}`. Use `$region` to see the list."))
    _guild_regions[ctx.guild.id] = code
    label = valid[code]
    await ctx.send(embed=_mok(f"Search region set to **{label}**.\nAll music searches will now use this region."))


@bot.command(name="lyrics", aliases=["ly"])
async def music_lyrics(ctx, *, song_name: str = None):
    player = _get_player(ctx.guild.id)
    if song_name is None:
        if not player.current:
            return await ctx.send(embed=_merr("Nothing is playing! Use `$lyrics song name`"))
        song_name = player.current.title
    clean = song_name
    for pat in ["(official","(lyrics","(audio","(video","(hd","[","]","ft.","feat."]:
        if pat in clean.lower(): clean = clean[:clean.lower().index(pat)].strip()
    parts = clean.split(" - ",1)
    artist, title_q = (parts[0].strip(),parts[1].strip()) if len(parts)==2 else ("",clean.strip())
    msg = await ctx.send(embed=discord.Embed(color=C_MUSIC, description=f"🔍 Fetching lyrics for **{clean}**..."))
    lyrics_text = None
    for url in [f"https://api.lyrics.ovh/v1/{artist or clean}/{title_q}",
                f"https://api.lyrics.ovh/v1/{clean}/{clean}"]:
        if lyrics_text: break
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        lyrics_text = data.get("lyrics")
        except Exception: pass
    if not lyrics_text:
        return await msg.edit(embed=_merr(f"No lyrics found for **{clean}**.\nTry: `$lyrics Artist - Song`"))
    lyrics_text = lyrics_text.replace("\r\n","\n").strip()
    chunks = [lyrics_text[i:i+3800] for i in range(0,len(lyrics_text),3800)]
    for i,chunk in enumerate(chunks):
        title = f"📜 {clean}" + (f" (Part {i+1})" if len(chunks)>1 else "")
        e = discord.Embed(color=C_MUSIC, title=title, description=chunk)
        e.set_footer(text="Powered by lyrics.ovh")
        await (msg.edit(embed=e) if i==0 else ctx.send(embed=e))


@bot.command(name="grab")
async def music_grab(ctx):
    player = _get_player(ctx.guild.id)
    if not player.current: return await ctx.send(embed=_merr("Nothing is playing!"))
    song = player.current
    e = discord.Embed(color=C_MUSIC, title="❤️ Saved Song!",
                      description=f"**[{song.title}]({song.url})**")
    e.add_field(name="Duration", value=song.dur_str, inline=True)
    e.add_field(name="Artist",   value=song.uploader, inline=True)
    if song.thumbnail: e.set_thumbnail(url=song.thumbnail)
    try:
        await ctx.author.send(embed=e)
        await ctx.send(embed=_mok("❤️ Song info sent to your DMs!"))
    except discord.Forbidden:
        await ctx.send(embed=_merr("Enable DMs from server members."))


@bot.command(name="voteskip", aliases=["vs"])
async def music_voteskip(ctx):
    await ctx.invoke(music_skip)


@bot.command(name="songhistory")
async def music_history(ctx):
    conn = _mdb()
    rows = conn.execute(
        "SELECT title,url,duration,requester FROM song_history "
        "WHERE guild_id=? ORDER BY id DESC LIMIT 10", (ctx.guild.id,)
    ).fetchall(); conn.close()
    if not rows:
        return await ctx.send(embed=discord.Embed(
            color=C_MUSIC, title="📜 History", description="No songs played yet!"))
    lines = [f"`{i+1}.` [{r['title']}]({r['url']}) `{r['duration']}`" for i,r in enumerate(rows)]
    await ctx.send(embed=discord.Embed(color=C_MUSIC, title="📜 Recently Played",
                                       description="\n".join(lines)))


