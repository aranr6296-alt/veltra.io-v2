import discord
from discord.ext import commands
from discord import FFmpegPCMAudio, Embed, Color, Activity, ActivityType
import yt_dlp
import asyncio
import os
import random
from collections import deque
from dotenv import load_dotenv
import logging
import sys
import subprocess
import hashlib
import json
import re

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============== CONFIGURATION ==============
TOKEN = os.getenv('DISCORD_TOKEN', 'YOUR_BOT_TOKEN_HERE')
PREFIX = os.getenv('PREFIX', '$')
MAX_QUEUE_SIZE = 500

# ============== KURDISH SONG DATABASE ==============
KURDISH_SONG_DATABASE = {
    'şivan perwer': ['ez xumam', 'keçelok', 'bavê xwe', 'leylê leylê', 'dayikê', 'xerîb', 'delalê', 'keça kurd'],
    'ciwan haco': ['zembîlfiroş', 'dilşa', 'serxwebûn', 'xwezî', 'bûka kurd', 'keça çiyê'],
    'hesen zîrek': ['ez ketim', 'keçelok', 'xerîbî', 'daye min', 'bavê min'],
    'aram tigran': ['keçelo', 'xerîb', 'derd', 'derdê min', 'evîna min'],
    'rojan': ['kurdistan', 'azadî', 'serxwebûn', 'xwezî', 'keça kurd'],
    'rostam sabir': ['xewn', 'evîn', 'derd', 'kurdistan', 'azadî', 'stran', 'delal', 'dil', 'rostam sabir'],
    'kurmancî': ['strana kurmancî', 'kilama kurmancî', 'dengê kurmancî'],
    'soranî': ['strana soranî', 'kilama soranî', 'dengê soranî'],
    'dengbej': ['kilama dengbêj', 'strana dengbêj', 'dengê dengbêj']
}

# Flatten the database
ALL_KURDISH_SONGS = []
for songs in KURDISH_SONG_DATABASE.values():
    ALL_KURDISH_SONGS.extend(songs)
ALL_KURDISH_SONGS = list(set(ALL_KURDISH_SONGS))

logger.info(f"📚 Loaded {len(ALL_KURDISH_SONGS)} Kurdish songs")

# ============== FAST SEARCH HELPER ==============
class FastSearch:
    def __init__(self):
        self.cache = {}
        self.ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'default_search': 'ytsearch',
            'max_downloads': 1,
            'socket_timeout': 10,
            'format': 'bestaudio/best'
        }
        self.download_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': '/tmp/audio_%(id)s.%(ext)s',
            'restrictfilenames': True,
            'nocheckcertificate': True,
            'ignoreerrors': True,
            'quiet': True,
            'no_warnings': True,
            'socket_timeout': 30,
            'retries': 3,
            'fragment_retries': 3,
            'noplaylist': True,
        }

    def get_cache_key(self, query):
        return hashlib.md5(query.lower().encode()).hexdigest()

    async def search(self, query):
        """ULTRA-FAST search using yt-dlp"""
        cache_key = self.get_cache_key(query)
        
        # Check cache
        if cache_key in self.cache:
            logger.info(f"⚡ Cache hit for: {query}")
            return self.cache[cache_key]
        
        try:
            # Try multiple search strategies FAST
            search_terms = [
                query,
                f"{query} audio",
                f"{query} song"
            ]
            
            # If Kurdish, add Kurdish keywords
            if any(word in query.lower() for word in ['kurd', 'kurdish', 'kurdî', 'rostam']):
                search_terms.insert(0, f"{query} kurdish")
                search_terms.insert(0, f"kurdish {query}")
            
            for search_term in search_terms[:3]:  # Only try 3 max for speed
                try:
                    with yt_dlp.YoutubeDL(self.ydl_opts) as ydl:
                        result = await asyncio.to_thread(
                            ydl.extract_info,
                            f"ytsearch1:{search_term}",
                            download=False
                        )
                        
                        if result and 'entries' in result and result['entries']:
                            entry = result['entries'][0]
                            if entry:
                                video_url = entry.get('webpage_url') or entry.get('url')
                                if video_url:
                                    song_data = {
                                        'title': entry.get('title', 'Unknown')[:80],
                                        'url': video_url,
                                        'duration': self.format_duration(entry.get('duration', 0)),
                                        'thumbnail': entry.get('thumbnail', ''),
                                        'channel': entry.get('channel', entry.get('uploader', 'Unknown'))
                                    }
                                    # Cache it
                                    self.cache[cache_key] = song_data
                                    logger.info(f"✅ Found: {song_data['title'][:30]}...")
                                    return song_data
                except Exception as e:
                    continue
            
            return None
            
        except Exception as e:
            logger.error(f"Search error: {e}")
            return None

    def format_duration(self, seconds):
        if not seconds or seconds <= 0:
            return 'N/A'
        try:
            minutes = int(seconds // 60)
            seconds = int(seconds % 60)
            if minutes >= 60:
                hours = minutes // 60
                minutes = minutes % 60
                return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            return f"{minutes:02d}:{seconds:02d}"
        except:
            return 'N/A'

    async def download(self, url):
        """FAST download with caching"""
        try:
            url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
            filename = f"/tmp/audio_{url_hash}.mp3"
            
            # Check if already downloaded
            if os.path.exists(filename) and os.path.getsize(filename) > 100000:
                return filename
            
            # Download
            with yt_dlp.YoutubeDL(self.download_opts) as ydl:
                await asyncio.to_thread(ydl.extract_info, url, download=True)
            
            # Find the downloaded file
            for ext in ['.mp3', '.webm', '.m4a', '.opus']:
                check_file = f"/tmp/audio_{url_hash}{ext}"
                if os.path.exists(check_file) and os.path.getsize(check_file) > 100000:
                    if not check_file.endswith('.mp3'):
                        new_file = f"/tmp/audio_{url_hash}.mp3"
                        try:
                            cmd = ['ffmpeg', '-i', check_file, '-acodec', 'libmp3lame', '-q:a', '2', new_file, '-y', '-loglevel', 'quiet']
                            await asyncio.to_thread(subprocess.run, cmd, capture_output=True, timeout=30)
                            if os.path.exists(new_file):
                                os.remove(check_file)
                                return new_file
                        except:
                            return check_file
                    return check_file
            
            # Try to find any file
            for file in os.listdir('/tmp'):
                if file.startswith(f"audio_{url_hash}") and os.path.getsize(f"/tmp/{file}") > 100000:
                    return f"/tmp/{file}"
            
            return None
            
        except Exception as e:
            logger.error(f"Download error: {e}")
            return None

# ============== BOT CLASS ==============
class MusicBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        
        super().__init__(
            command_prefix=PREFIX,
            intents=intents,
            help_command=None
        )
        
        self.queues = {}
        self.current_songs = {}
        self.loop = {}
        self.volume = {}
        self.fast_search = FastSearch()
        
        os.makedirs('/tmp/downloads', exist_ok=True)
        
        logger.info("🤖 Bot initialized with FAST search")

    async def setup_hook(self):
        try:
            await self.tree.sync()
            logger.info("✅ Slash commands synced")
        except Exception as e:
            logger.error(f"Slash sync error: {e}")

    def get_queue(self, guild_id):
        if guild_id not in self.queues:
            self.queues[guild_id] = deque(maxlen=MAX_QUEUE_SIZE)
        return self.queues[guild_id]

    def get_current_song(self, guild_id):
        return self.current_songs.get(guild_id)

    def set_current_song(self, guild_id, song):
        self.current_songs[guild_id] = song

    def get_loop(self, guild_id):
        return self.loop.get(guild_id, False)

    def toggle_loop(self, guild_id):
        self.loop[guild_id] = not self.loop.get(guild_id, False)
        return self.loop[guild_id]

    def get_volume(self, guild_id):
        return self.volume.get(guild_id, 50)

    def set_volume(self, guild_id, vol):
        self.volume[guild_id] = max(0, min(200, vol))

# ========== MUSIC PLAYER ==========
class MusicPlayer:
    def __init__(self, bot):
        self.bot = bot

    async def play_song(self, ctx, query):
        """Play a song - FAST VERSION"""
        try:
            # Check voice channel
            if not ctx.author.voice:
                await ctx.send("❌ You need to be in a voice channel!")
                return None
            
            # Join voice channel FAST
            voice_channel = ctx.author.voice.channel
            if ctx.voice_client is None:
                await voice_channel.connect(timeout=5.0)
                logger.info(f"✅ Joined: {voice_channel.name}")
            elif ctx.voice_client.channel != voice_channel:
                await ctx.voice_client.move_to(voice_channel)
            
            # Search FAST
            song = await self.bot.fast_search.search(query)
            if not song:
                await ctx.send(f"❌ No results for: **{query}**")
                return None
            
            # Add to queue
            queue = self.bot.get_queue(ctx.guild.id)
            queue.append(song)
            
            if not ctx.voice_client.is_playing():
                await self.play_next(ctx)
            else:
                await ctx.send(f"📝 Added: **{song['title']}** (Position: {len(queue)})")
            
            return song
            
        except Exception as e:
            logger.error(f"Play error: {e}")
            await ctx.send(f"❌ Error: {str(e)[:100]}")
            return None

    async def play_next(self, ctx):
        """Play next song - FAST VERSION"""
        try:
            queue = self.bot.get_queue(ctx.guild.id)
            
            if not queue:
                self.bot.set_current_song(ctx.guild.id, None)
                if ctx.voice_client:
                    await ctx.voice_client.disconnect()
                    await ctx.send("⏹️ Queue empty. Disconnected.")
                return
            
            # Check loop
            if self.bot.get_loop(ctx.guild.id):
                current = self.bot.get_current_song(ctx.guild.id)
                if current:
                    queue.appendleft(current)
            
            song = queue.popleft()
            self.bot.set_current_song(ctx.guild.id, song)
            
            logger.info(f"🎯 Playing: {song.get('title', 'Unknown')}")
            
            # Download audio FAST
            audio_file = await self.bot.fast_search.download(song['url'])
            if not audio_file:
                await ctx.send(f"❌ Failed to download: {song.get('title', 'Unknown')}")
                await self.play_next(ctx)
                return
            
            # Create audio source
            volume = self.bot.get_volume(ctx.guild.id) / 100
            
            audio = FFmpegPCMAudio(
                audio_file,
                before_options='-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                options=f'-vn -bufsize 64k -loglevel quiet -af "volume={volume}"'
            )
            
            def after_playing(error):
                if error:
                    logger.error(f"Playback error: {error}")
                try:
                    if os.path.exists(audio_file):
                        os.remove(audio_file)
                except:
                    pass
                asyncio.run_coroutine_threadsafe(self.play_next(ctx), self.bot.loop)
            
            ctx.voice_client.play(audio, after=after_playing)
            
            # Send now playing embed
            embed = Embed(
                title="🎵 Now Playing",
                description=f"**{song.get('title', 'Unknown')}**",
                color=Color.green()
            )
            if song.get('thumbnail'):
                embed.set_thumbnail(url=song['thumbnail'])
            
            embed.add_field(name="⏱️ Duration", value=song.get('duration', 'N/A'), inline=True)
            embed.add_field(name="👤 Channel", value=song.get('channel', 'Unknown'), inline=True)
            embed.add_field(name="🔊 Volume", value=f"{self.bot.get_volume(ctx.guild.id)}%", inline=True)
            embed.add_field(
                name="📋 Queue",
                value=f"{len(queue)} songs remaining" if queue else "Queue is empty",
                inline=False
            )
            embed.set_footer(text="🎶 Kurdish Music Bot")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Play next error: {e}")
            await ctx.send(f"❌ Playback error, skipping...")
            await self.play_next(ctx)

# ========== INITIALIZE BOT ==========
bot = MusicBot()
player = MusicPlayer(bot)

# ========== EVENTS ==========

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    if message.content.startswith(PREFIX):
        logger.info(f"📝 Command: {message.content} from {message.author.name}")
    
    await bot.process_commands(message)

# ========== COMMANDS ==========

@bot.command(name='test', aliases=['t'])
async def test_command(ctx):
    await ctx.send("✅ Bot is responding! Prefix: `$`")

@bot.command(name='ping')
async def ping(ctx):
    latency = round(bot.latency * 1000)
    await ctx.send(f"🏓 Pong! Latency: {latency}ms")

@bot.command(name='play', aliases=['p'])
async def play(ctx, *, query):
    """Play ANY song - FAST!"""
    if not query:
        await ctx.send("❌ Please provide a song name!\nExample: `$play rostam sabir`")
        return
    
    await ctx.send(f"🔍 Searching for: **{query}**...")
    logger.info(f"🎵 Play: {query} by {ctx.author.name}")
    
    try:
        result = await player.play_song(ctx, query)
        if result:
            await ctx.send(f"🎵 Added: **{result.get('title', 'Song')}**")
        else:
            await ctx.send(f"❌ Could not find: **{query}**")
    except Exception as e:
        logger.error(f"Play error: {e}")
        await ctx.send(f"❌ Error: {str(e)[:100]}")

@bot.command(name='kurdish')
async def kurdish(ctx, *, query=None):
    """Search for Kurdish songs"""
    if not query:
        random_song = random.choice(ALL_KURDISH_SONGS)
        await ctx.send(f"🎵 Try this Kurdish song: **{random_song}**\n💡 Use `$play {random_song}` to play it!")
        return
    
    matched = [song for song in ALL_KURDISH_SONGS if query.lower() in song.lower()]
    if matched:
        embed = Embed(
            title="🇰🇲 Kurdish Songs Found",
            description=f"Found {len(matched)} Kurdish songs!",
            color=Color.gold()
        )
        song_list = []
        for i, song in enumerate(matched[:20], 1):
            song_list.append(f"`{i}.` **{song}**")
        embed.add_field(name="📝 Songs", value="\n".join(song_list), inline=False)
        embed.set_footer(text="💡 Use $play <song name> to play any of these!")
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"❌ No Kurdish songs found for: **{query}**")

@bot.command(name='kurdish-random')
async def kurdish_random(ctx):
    random_song = random.choice(ALL_KURDISH_SONGS)
    await ctx.send(f"🎵 Playing random Kurdish song: **{random_song}** 🇰🇲")
    await play(ctx, query=random_song)

@bot.command(name='search')
async def search(ctx, *, query):
    if not query:
        await ctx.send("❌ Please provide a search query!")
        return
    
    try:
        song = await bot.fast_search.search(query)
        if not song:
            await ctx.send(f"❌ No results for: **{query}**")
            return
        
        embed = Embed(
            title="🔍 Search Result",
            description=f"**{song['title']}**",
            color=Color.blue()
        )
        embed.add_field(name="⏱️ Duration", value=song.get('duration', 'N/A'), inline=True)
        embed.add_field(name="👤 Channel", value=song.get('channel', 'Unknown'), inline=True)
        embed.set_footer(text="💡 Use $play <song name> to play it!")
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)[:100]}")

@bot.command(name='queue', aliases=['q'])
async def show_queue(ctx):
    try:
        queue = bot.get_queue(ctx.guild.id)
        current = bot.get_current_song(ctx.guild.id)
        
        if not queue and not current:
            await ctx.send("📭 The queue is empty!")
            return
        
        embed = Embed(title="📋 Music Queue", color=Color.blue())
        
        if current:
            embed.add_field(
                name="🎵 Now Playing",
                value=f"**{current.get('title', 'Unknown')}**\n⏱️ {current.get('duration', 'N/A')}",
                inline=False
            )
        
        if queue:
            queue_list = []
            for i, song in enumerate(list(queue)[:10], 1):
                title = song.get('title', 'Unknown')[:45]
                duration = song.get('duration', 'N/A')
                queue_list.append(f"`{i}.` **{title}...** `{duration}`")
            
            embed.add_field(
                name=f"📝 Next Songs ({len(queue)} total)",
                value="\n".join(queue_list) if queue_list else "No upcoming songs",
                inline=False
            )
        
        embed.set_footer(text=f"🔄 Loop: {'✅' if bot.get_loop(ctx.guild.id) else '❌'} | 🔊 Volume: {bot.get_volume(ctx.guild.id)}%")
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)[:100]}")

@bot.command(name='skip', aliases=['s'])
async def skip(ctx):
    if not ctx.voice_client or not ctx.voice_client.is_playing():
        await ctx.send("❌ No song is currently playing!")
        return
    
    current = bot.get_current_song(ctx.guild.id)
    if current:
        await ctx.send(f"⏭️ Skipped: **{current.get('title', 'Song')}**")
    ctx.voice_client.stop()

@bot.command(name='stop')
async def stop(ctx):
    try:
        queue = bot.get_queue(ctx.guild.id)
        queue.clear()
        bot.set_current_song(ctx.guild.id, None)
        
        if ctx.voice_client:
            await ctx.voice_client.disconnect()
            await ctx.send("⏹️ Stopped and disconnected. Queue cleared.")
        else:
            await ctx.send("❌ Not in a voice channel!")
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)[:100]}")

@bot.command(name='pause')
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸️ Paused")
    else:
        await ctx.send("❌ No song playing!")

@bot.command(name='resume')
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶️ Resumed")
    else:
        await ctx.send("❌ No song paused!")

@bot.command(name='loop')
async def loop(ctx):
    if not bot.get_current_song(ctx.guild.id):
        await ctx.send("❌ No song playing!")
        return
    
    loop_status = bot.toggle_loop(ctx.guild.id)
    await ctx.send(f"🔄 Loop: {'✅ Enabled' if loop_status else '❌ Disabled'}")

@bot.command(name='volume', aliases=['vol'])
async def volume(ctx, level: int = None):
    if level is None:
        await ctx.send(f"🔊 Volume: **{bot.get_volume(ctx.guild.id)}%**")
        return
    
    if level < 0 or level > 200:
        await ctx.send("❌ Volume must be between 0-200!")
        return
    
    bot.set_volume(ctx.guild.id, level)
    await ctx.send(f"🔊 Volume set to: **{level}%**")

@bot.command(name='remove')
async def remove_from_queue(ctx, position: int):
    queue = bot.get_queue(ctx.guild.id)
    if position < 1 or position > len(queue):
        await ctx.send(f"❌ Position must be between 1-{len(queue)}")
        return
    
    try:
        removed = list(queue)[position - 1]
        queue.remove(removed)
        await ctx.send(f"🗑️ Removed: **{removed.get('title', 'Song')}**")
    except:
        await ctx.send("❌ Could not remove!")

@bot.command(name='clear')
async def clear_queue(ctx):
    queue = bot.get_queue(ctx.guild.id)
    count = len(queue)
    queue.clear()
    await ctx.send(f"🗑️ Cleared **{count}** songs!")

@bot.command(name='shuffle')
async def shuffle_queue(ctx):
    queue = bot.get_queue(ctx.guild.id)
    if len(queue) < 2:
        await ctx.send("❌ Need at least 2 songs!")
        return
    
    queue_list = list(queue)
    random.shuffle(queue_list)
    queue.clear()
    queue.extend(queue_list)
    await ctx.send("🔀 Queue shuffled!")

@bot.command(name='nowplaying', aliases=['np'])
async def now_playing(ctx):
    current = bot.get_current_song(ctx.guild.id)
    if not current:
        await ctx.send("❌ No song playing!")
        return
    
    embed = Embed(
        title="🎵 Now Playing",
        description=f"**{current.get('title', 'Unknown')}**",
        color=Color.green()
    )
    
    if current.get('thumbnail'):
        embed.set_thumbnail(url=current['thumbnail'])
    
    embed.add_field(name="⏱️ Duration", value=current.get('duration', 'N/A'), inline=True)
    embed.add_field(name="👤 Channel", value=current.get('channel', 'Unknown'), inline=True)
    embed.add_field(name="🔊 Volume", value=f"{bot.get_volume(ctx.guild.id)}%", inline=True)
    embed.add_field(name="🔄 Loop", value="✅" if bot.get_loop(ctx.guild.id) else "❌", inline=True)
    
    queue = bot.get_queue(ctx.guild.id)
    embed.add_field(name="📋 Queue", value=f"{len(queue)} songs", inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name='help', aliases=['h'])
async def help_command(ctx):
    embed = Embed(
        title="🎵 Kurdish Music Bot - Help",
        description="🇰🇲 **Kurdish songs built-in!**\n🌍 Supports ALL languages!\n⚡ **ULTRA-FAST** search!",
        color=Color.gold()
    )
    
    embed.add_field(
        name="🎶 Music Commands",
        value=(
            "`$play <song>` - Play ANY song (FAST!)\n"
            "`$search <query>` - Search for songs\n"
            "`$queue` - Show current queue\n"
            "`$skip` - Skip current song\n"
            "`$stop` - Stop and clear queue\n"
            "`$pause` - Pause playback\n"
            "`$resume` - Resume playback\n"
            "`$loop` - Toggle loop mode\n"
            "`$volume <0-200>` - Adjust volume\n"
            "`$nowplaying` - Show current song"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🇰🇲 Kurdish Commands",
        value=(
            "`$kurdish <song>` - Search Kurdish songs\n"
            "`$kurdish-random` - Play random Kurdish song"
        ),
        inline=False
    )
    
    embed.add_field(
        name="📋 Queue Management",
        value=(
            "`$remove <position>` - Remove song\n"
            "`$clear` - Clear queue\n"
            "`$shuffle` - Shuffle queue"
        ),
        inline=False
    )
    
    embed.set_footer(text=f"🎵 Prefix: {PREFIX} | ⚡ FASTEST Kurdish Bot")
    await ctx.send(embed=embed)

# ========== EVENTS ==========

@bot.event
async def on_ready():
    logger.info(f'✅ Logged in as {bot.user.name}')
    logger.info(f'📊 Connected to {len(bot.guilds)} servers')
    logger.info(f'🇰🇲 Loaded {len(ALL_KURDISH_SONGS)} Kurdish songs!')
    logger.info(f'⚡ ULTRA-FAST search enabled!')
    logger.info(f'📝 Prefix: {PREFIX}')
    logger.info(f'💡 Try: $play rostam sabir')
    
    await bot.change_presence(
        activity=Activity(
            type=ActivityType.listening,
            name=f"⚡ FAST | {PREFIX}play"
        ),
        status=discord.Status.online
    )
    
    try:
        await bot.tree.sync()
        logger.info("✅ Slash commands synced!")
    except Exception as e:
        logger.error(f"Slash sync error: {e}")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    else:
        logger.error(f"Command error: {error}")
        await ctx.send(f"❌ Error: {str(error)[:100]}")

# ========== START BOT ==========

if __name__ == "__main__":
    if not TOKEN or TOKEN == 'YOUR_BOT_TOKEN_HERE':
        logger.error("❌ No bot token found!")
        sys.exit(1)
    
    try:
        logger.info("Starting ULTRA-FAST bot... ⚡")
        bot.run(TOKEN, reconnect=True)
    except discord.LoginFailure:
        logger.error("❌ Invalid bot token!")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Failed to start: {e}")
        sys.exit(1)        
        os.makedirs('/tmp/downloads', exist_ok=True)
        
        logger.info("🤖 Bot initialized")

    async def setup_hook(self):
        try:
            await self.tree.sync()
            logger.info("✅ Slash commands synced")
        except Exception as e:
            logger.error(f"Slash sync error: {e}")

    def get_queue(self, guild_id):
        if guild_id not in self.queues:
            self.queues[guild_id] = deque(maxlen=MAX_QUEUE_SIZE)
        return self.queues[guild_id]

    def get_current_song(self, guild_id):
        return self.current_songs.get(guild_id)

    def set_current_song(self, guild_id, song):
        self.current_songs[guild_id] = song

    def get_loop(self, guild_id):
        return self.loop.get(guild_id, False)

    def toggle_loop(self, guild_id):
        self.loop[guild_id] = not self.loop.get(guild_id, False)
        return self.loop[guild_id]

    def get_volume(self, guild_id):
        return self.volume.get(guild_id, 50)

    def set_volume(self, guild_id, vol):
        self.volume[guild_id] = max(0, min(200, vol))

# ========== MUSIC PLAYER CLASS ==========
class MusicPlayer:
    def __init__(self, bot):
        self.bot = bot

    def format_duration(self, seconds):
        if not seconds or seconds <= 0:
            return 'N/A'
        try:
            minutes = int(seconds // 60)
            seconds = int(seconds % 60)
            if minutes >= 60:
                hours = minutes // 60
                minutes = minutes % 60
                return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            return f"{minutes:02d}:{seconds:02d}"
        except:
            return 'N/A'

    async def search_song(self, query):
        """Search for a song using yt-dlp - FIXED VERSION"""
        try:
            # Updated yt-dlp options for better compatibility
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'default_search': 'ytsearch',
                'max_downloads': 3,
                'socket_timeout': 30,
                'format': 'bestaudio/best',
                'extract_audio': True,
                'audio_format': 'mp3',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            }
            
            # Try different search queries
            search_queries = [
                query,
                f"{query} music",
                f"{query} song"
            ]
            
            # If it's Kurdish, add Kurdish keywords
            if any(word in query.lower() for word in ['kurd', 'kurdish', 'kurdî', 'kurmancî', 'soranî', 'rostam']):
                search_queries.extend([
                    f"{query} kurdish",
                    f"{query} kurdî",
                    f"kurdish {query}"
                ])
            
            for search_query in search_queries:
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        search_results = await asyncio.to_thread(
                            ydl.extract_info, 
                            f"ytsearch3:{search_query}", 
                            download=False
                        )
                        
                        if search_results and 'entries' in search_results:
                            for entry in search_results['entries']:
                                if entry and entry.get('url'):
                                    # Get full video info
                                    try:
                                        full_info = await asyncio.to_thread(
                                            ydl.extract_info,
                                            entry.get('url', entry.get('webpage_url', '')),
                                            download=False
                                        )
                                        if full_info:
                                            return {
                                                'title': full_info.get('title', 'Unknown')[:100],
                                                'url': entry.get('url', entry.get('webpage_url', '')),
                                                'duration': self.format_duration(full_info.get('duration', 0)),
                                                'thumbnail': full_info.get('thumbnail', ''),
                                                'channel': full_info.get('channel', full_info.get('uploader', 'Unknown')),
                                                'full_info': full_info
                                            }
                                    except:
                                        # If we can't get full info, use the entry
                                        return {
                                            'title': entry.get('title', 'Unknown')[:100],
                                            'url': entry.get('url', entry.get('webpage_url', '')),
                                            'duration': self.format_duration(entry.get('duration', 0)),
                                            'thumbnail': entry.get('thumbnail', ''),
                                            'channel': entry.get('channel', entry.get('uploader', 'Unknown'))
                                        }
                except Exception as e:
                    logger.warning(f"Search attempt failed: {e}")
                    continue
            
            return None
            
        except Exception as e:
            logger.error(f"Search error: {e}")
            return None

    async def download_audio(self, url):
        """Download audio from YouTube - FIXED VERSION"""
        try:
            url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
            filename = f"/tmp/audio_{url_hash}.mp3"
            
            # Check cache
            if os.path.exists(filename) and os.path.getsize(filename) > 50000:
                logger.info(f"✅ Using cached audio: {filename}")
                return filename
            
            # Updated yt-dlp options for better audio download
            ydl_opts = {
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'outtmpl': f"/tmp/audio_{url_hash}",
                'restrictfilenames': True,
                'nocheckcertificate': True,
                'ignoreerrors': True,
                'quiet': True,
                'no_warnings': True,
                'socket_timeout': 60,
                'retries': 10,
                'fragment_retries': 10,
                'noplaylist': True,
                'extract_audio': True,
                'audio_format': 'mp3',
                'audio_quality': 0,
                'writeinfojson': False,
                'writethumbnail': False,
                'writesubtitles': False,
                'writeautomaticsub': False,
            }
            
            logger.info(f"⬇️ Downloading audio from: {url[:50]}...")
            
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    await asyncio.to_thread(ydl.extract_info, url, download=True)
                
                # Check for downloaded file
                for ext in ['.mp3', '.webm', '.m4a', '.opus']:
                    check_file = f"/tmp/audio_{url_hash}{ext}"
                    if os.path.exists(check_file) and os.path.getsize(check_file) > 50000:
                        # If it's not mp3, convert it to mp3
                        if not check_file.endswith('.mp3'):
                            new_file = f"/tmp/audio_{url_hash}.mp3"
                            try:
                                cmd = ['ffmpeg', '-i', check_file, '-acodec', 'libmp3lame', '-q:a', '2', new_file, '-y', '-loglevel', 'quiet']
                                await asyncio.to_thread(subprocess.run, cmd, capture_output=True, timeout=60)
                                if os.path.exists(new_file) and os.path.getsize(new_file) > 50000:
                                    os.remove(check_file)
                                    logger.info(f"✅ Converted to MP3: {new_file}")
                                    return new_file
                            except:
                                return check_file
                        return check_file
                
                # Try to find any file with the base name
                for file in os.listdir('/tmp'):
                    if file.startswith(f"audio_{url_hash}") and os.path.getsize(f"/tmp/{file}") > 50000:
                        logger.info(f"✅ Found audio: /tmp/{file}")
                        return f"/tmp/{file}"
                
                logger.error("❌ No audio file found after download")
                return None
                
            except Exception as e:
                logger.error(f"Download error: {e}")
                return None
            
        except Exception as e:
            logger.error(f"Download error: {e}")
            return None

    async def play_song(self, ctx, query):
        """Play a song - FIXED VERSION"""
        try:
            # Check voice channel
            if not ctx.author.voice:
                await ctx.send("❌ You need to be in a voice channel!")
                return None
            
            # Join voice channel
            voice_channel = ctx.author.voice.channel
            if ctx.voice_client is None:
                await voice_channel.connect(timeout=10.0)
                logger.info(f"✅ Joined: {voice_channel.name}")
            elif ctx.voice_client.channel != voice_channel:
                await ctx.voice_client.move_to(voice_channel)
            
            # Search for the song
            song = await self.search_song(query)
            if not song:
                await ctx.send(f"❌ No results found for: **{query}**")
                return None
            
            # Add to queue
            queue = self.bot.get_queue(ctx.guild.id)
            queue.append(song)
            
            if not ctx.voice_client.is_playing():
                await self.play_next(ctx)
            else:
                await ctx.send(f"📝 Added: **{song['title']}** (Position: {len(queue)})")
            
            return song
            
        except Exception as e:
            logger.error(f"Play error: {e}")
            await ctx.send(f"❌ Error: {str(e)[:100]}")
            return None

    async def play_next(self, ctx):
        """Play next song in queue - FIXED VERSION"""
        try:
            queue = self.bot.get_queue(ctx.guild.id)
            
            if not queue:
                self.bot.set_current_song(ctx.guild.id, None)
                if ctx.voice_client:
                    await ctx.voice_client.disconnect()
                    await ctx.send("⏹️ Queue empty. Disconnected.")
                return
            
            # Check loop
            if self.bot.get_loop(ctx.guild.id):
                current = self.bot.get_current_song(ctx.guild.id)
                if current:
                    queue.appendleft(current)
            
            song = queue.popleft()
            self.bot.set_current_song(ctx.guild.id, song)
            
            logger.info(f"🎯 Playing: {song.get('title', 'Unknown')}")
            
            # Download audio with retry
            audio_file = None
            for attempt in range(3):
                audio_file = await self.download_audio(song['url'])
                if audio_file:
                    break
                logger.warning(f"Download attempt {attempt + 1} failed, retrying...")
                await asyncio.sleep(2)
            
            if not audio_file:
                await ctx.send(f"❌ Failed to download: {song.get('title', 'Unknown')}")
                await self.play_next(ctx)
                return
            
            # Verify file
            if not os.path.exists(audio_file) or os.path.getsize(audio_file) < 50000:
                await ctx.send(f"❌ Invalid audio file: {song.get('title', 'Unknown')}")
                await self.play_next(ctx)
                return
            
            # Create audio source with proper settings
            volume = self.bot.get_volume(ctx.guild.id) / 100
            
            audio = FFmpegPCMAudio(
                audio_file,
                before_options='-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                options=f'-vn -bufsize 64k -loglevel quiet -af "volume={volume}"'
            )
            
            def after_playing(error):
                if error:
                    logger.error(f"Playback error: {error}")
                try:
                    if os.path.exists(audio_file):
                        os.remove(audio_file)
                        logger.info(f"🗑️ Removed: {audio_file}")
                except:
                    pass
                asyncio.run_coroutine_threadsafe(self.play_next(ctx), self.bot.loop)
            
            # Play the audio
            try:
                ctx.voice_client.play(audio, after=after_playing)
            except Exception as e:
                logger.error(f"FFmpeg play error: {e}")
                await ctx.send(f"❌ FFmpeg error: {str(e)[:100]}")
                await self.play_next(ctx)
                return
            
            # Send now playing embed
            embed = Embed(
                title="🎵 Now Playing",
                description=f"**{song.get('title', 'Unknown')}**",
                color=Color.green()
            )
            if song.get('thumbnail'):
                embed.set_thumbnail(url=song['thumbnail'])
            
            embed.add_field(name="⏱️ Duration", value=song.get('duration', 'N/A'), inline=True)
            embed.add_field(name="👤 Channel", value=song.get('channel', 'Unknown'), inline=True)
            embed.add_field(name="🔊 Volume", value=f"{self.bot.get_volume(ctx.guild.id)}%", inline=True)
            embed.add_field(
                name="📋 Queue",
                value=f"{len(queue)} songs remaining" if queue else "Queue is empty",
                inline=False
            )
            embed.set_footer(text="🎶 Kurdish Music Bot")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Play next error: {e}")
            await ctx.send(f"❌ Playback error, skipping...")
            await self.play_next(ctx)

# ========== INITIALIZE BOT ==========
bot = MusicBot()
player = MusicPlayer(bot)

# ========== DIAGNOSTIC COMMANDS ==========

@bot.event
async def on_message(message):
    """Process messages with diagnostic logging"""
    if message.author.bot:
        return
    
    if message.content.startswith(PREFIX):
        logger.info(f"📝 Command received: {message.content} from {message.author.name}")
    
    await bot.process_commands(message)

@bot.command(name='test', aliases=['t'])
async def test_command(ctx):
    await ctx.send("✅ Bot is responding! Your prefix is `$`")

@bot.command(name='ping')
async def ping(ctx):
    latency = round(bot.latency * 1000)
    await ctx.send(f"🏓 Pong! Latency: {latency}ms")

# ========== TEXT COMMANDS ==========

@bot.command(name='play', aliases=['p'])
async def play(ctx, *, query):
    """Play ANY song - including Kurdish songs!"""
    if not query:
        await ctx.send("❌ Please provide a song name!\nExample: `$play rostam sabir`")
        return
    
    await ctx.send(f"🔍 Searching for: **{query}**...")
    logger.info(f"🎵 Play command: {query} by {ctx.author.name}")
    
    try:
        result = await player.play_song(ctx, query)
        if result:
            await ctx.send(f"🎵 Added: **{result.get('title', 'Song')}**")
        else:
            await ctx.send(f"❌ Could not find: **{query}**")
    except Exception as e:
        logger.error(f"Play error: {e}")
        await ctx.send(f"❌ Error: {str(e)[:100]}")

@bot.command(name='kurdish')
async def kurdish(ctx, *, query=None):
    """Search for Kurdish songs"""
    if not query:
        random_song = random.choice(ALL_KURDISH_SONGS)
        await ctx.send(f"🎵 Try this Kurdish song: **{random_song}**\n💡 Use `$play {random_song}` to play it!")
        return
    
    matched = [song for song in ALL_KURDISH_SONGS if query.lower() in song.lower()]
    if matched:
        embed = Embed(
            title="🇰🇲 Kurdish Songs Found",
            description=f"Found {len(matched)} Kurdish songs!",
            color=Color.gold()
        )
        song_list = []
        for i, song in enumerate(matched[:20], 1):
            song_list.append(f"`{i}.` **{song}**")
        embed.add_field(name="📝 Songs", value="\n".join(song_list), inline=False)
        embed.set_footer(text="💡 Use $play <song name> to play any of these!")
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"❌ No Kurdish songs found for: **{query}**")

@bot.command(name='kurdish-random')
async def kurdish_random(ctx):
    random_song = random.choice(ALL_KURDISH_SONGS)
    await ctx.send(f"🎵 Playing random Kurdish song: **{random_song}** 🇰🇲")
    await play(ctx, query=random_song)

@bot.command(name='search')
async def search(ctx, *, query):
    if not query:
        await ctx.send("❌ Please provide a search query!")
        return
    
    try:
        song = await player.search_song(query)
        if not song:
            await ctx.send(f"❌ No results for: **{query}**")
            return
        
        embed = Embed(
            title="🔍 Search Result",
            description=f"**{song['title']}**",
            color=Color.blue()
        )
        embed.add_field(name="⏱️ Duration", value=song.get('duration', 'N/A'), inline=True)
        embed.add_field(name="👤 Channel", value=song.get('channel', 'Unknown'), inline=True)
        embed.set_footer(text="💡 Use $play <song name> to play it!")
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)[:100]}")

@bot.command(name='queue', aliases=['q'])
async def show_queue(ctx):
    try:
        queue = bot.get_queue(ctx.guild.id)
        current = bot.get_current_song(ctx.guild.id)
        
        if not queue and not current:
            await ctx.send("📭 The queue is empty!")
            return
        
        embed = Embed(title="📋 Music Queue", color=Color.blue())
        
        if current:
            embed.add_field(
                name="🎵 Now Playing",
                value=f"**{current.get('title', 'Unknown')}**\n⏱️ {current.get('duration', 'N/A')}",
                inline=False
            )
        
        if queue:
            queue_list = []
            for i, song in enumerate(list(queue)[:10], 1):
                title = song.get('title', 'Unknown')[:45]
                duration = song.get('duration', 'N/A')
                queue_list.append(f"`{i}.` **{title}...** `{duration}`")
            
            embed.add_field(
                name=f"📝 Next Songs ({len(queue)} total)",
                value="\n".join(queue_list) if queue_list else "No upcoming songs",
                inline=False
            )
        
        embed.set_footer(text=f"🔄 Loop: {'✅' if bot.get_loop(ctx.guild.id) else '❌'} | 🔊 Volume: {bot.get_volume(ctx.guild.id)}%")
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)[:100]}")

@bot.command(name='skip', aliases=['s'])
async def skip(ctx):
    if not ctx.voice_client or not ctx.voice_client.is_playing():
        await ctx.send("❌ No song is currently playing!")
        return
    
    current = bot.get_current_song(ctx.guild.id)
    if current:
        await ctx.send(f"⏭️ Skipped: **{current.get('title', 'Song')}**")
    ctx.voice_client.stop()

@bot.command(name='stop')
async def stop(ctx):
    try:
        queue = bot.get_queue(ctx.guild.id)
        queue.clear()
        bot.set_current_song(ctx.guild.id, None)
        
        if ctx.voice_client:
            await ctx.voice_client.disconnect()
            await ctx.send("⏹️ Stopped and disconnected. Queue cleared.")
        else:
            await ctx.send("❌ Not in a voice channel!")
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)[:100]}")

@bot.command(name='pause')
async def pause(ctx):
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸️ Paused")
    else:
        await ctx.send("❌ No song playing!")

@bot.command(name='resume')
async def resume(ctx):
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶️ Resumed")
    else:
        await ctx.send("❌ No song paused!")

@bot.command(name='loop')
async def loop(ctx):
    if not bot.get_current_song(ctx.guild.id):
        await ctx.send("❌ No song playing!")
        return
    
    loop_status = bot.toggle_loop(ctx.guild.id)
    await ctx.send(f"🔄 Loop: {'✅ Enabled' if loop_status else '❌ Disabled'}")

@bot.command(name='volume', aliases=['vol'])
async def volume(ctx, level: int = None):
    if level is None:
        await ctx.send(f"🔊 Volume: **{bot.get_volume(ctx.guild.id)}%**")
        return
    
    if level < 0 or level > 200:
        await ctx.send("❌ Volume must be between 0-200!")
        return
    
    bot.set_volume(ctx.guild.id, level)
    await ctx.send(f"🔊 Volume set to: **{level}%**")

@bot.command(name='remove')
async def remove_from_queue(ctx, position: int):
    queue = bot.get_queue(ctx.guild.id)
    if position < 1 or position > len(queue):
        await ctx.send(f"❌ Position must be between 1-{len(queue)}")
        return
    
    try:
        removed = list(queue)[position - 1]
        queue.remove(removed)
        await ctx.send(f"🗑️ Removed: **{removed.get('title', 'Song')}**")
    except:
        await ctx.send("❌ Could not remove!")

@bot.command(name='clear')
async def clear_queue(ctx):
    queue = bot.get_queue(ctx.guild.id)
    count = len(queue)
    queue.clear()
    await ctx.send(f"🗑️ Cleared **{count}** songs!")

@bot.command(name='shuffle')
async def shuffle_queue(ctx):
    queue = bot.get_queue(ctx.guild.id)
    if len(queue) < 2:
        await ctx.send("❌ Need at least 2 songs!")
        return
    
    queue_list = list(queue)
    random.shuffle(queue_list)
    queue.clear()
    queue.extend(queue_list)
    await ctx.send("🔀 Queue shuffled!")

@bot.command(name='nowplaying', aliases=['np'])
async def now_playing(ctx):
    current = bot.get_current_song(ctx.guild.id)
    if not current:
        await ctx.send("❌ No song playing!")
        return
    
    embed = Embed(
        title="🎵 Now Playing",
        description=f"**{current.get('title', 'Unknown')}**",
        color=Color.green()
    )
    
    if current.get('thumbnail'):
        embed.set_thumbnail(url=current['thumbnail'])
    
    embed.add_field(name="⏱️ Duration", value=current.get('duration', 'N/A'), inline=True)
    embed.add_field(name="👤 Channel", value=current.get('channel', 'Unknown'), inline=True)
    embed.add_field(name="🔊 Volume", value=f"{bot.get_volume(ctx.guild.id)}%", inline=True)
    embed.add_field(name="🔄 Loop", value="✅" if bot.get_loop(ctx.guild.id) else "❌", inline=True)
    
    queue = bot.get_queue(ctx.guild.id)
    embed.add_field(name="📋 Queue", value=f"{len(queue)} songs", inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name='help', aliases=['h'])
async def help_command(ctx):
    embed = Embed(
        title="🎵 Kurdish Music Bot - Help",
        description="🇰🇲 **Kurdish songs built-in!**\n🌍 Supports ALL languages!",
        color=Color.gold()
    )
    
    embed.add_field(
        name="🎶 Music Commands",
        value=(
            "`$play <song>` - Play ANY song\n"
            "`$search <query>` - Search for songs\n"
            "`$queue` - Show current queue\n"
            "`$skip` - Skip current song\n"
            "`$stop` - Stop and clear queue\n"
            "`$pause` - Pause playback\n"
            "`$resume` - Resume playback\n"
            "`$loop` - Toggle loop mode\n"
            "`$volume <0-200>` - Adjust volume\n"
            "`$nowplaying` - Show current song"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🇰🇲 Kurdish Commands",
        value=(
            "`$kurdish <song>` - Search Kurdish songs\n"
            "`$kurdish-random` - Play random Kurdish song"
        ),
        inline=False
    )
    
    embed.add_field(
        name="📋 Queue Management",
        value=(
            "`$remove <position>` - Remove song\n"
            "`$clear` - Clear queue\n"
            "`$shuffle` - Shuffle queue"
        ),
        inline=False
    )
    
    embed.set_footer(text=f"🎵 Prefix: {PREFIX} | 🇰🇲 Kurdish Music Bot")
    await ctx.send(embed=embed)

# ========== EVENTS ==========

@bot.event
async def on_ready():
    logger.info(f'✅ Logged in as {bot.user.name}')
    logger.info(f'📊 Connected to {len(bot.guilds)} servers')
    logger.info(f'🇰🇲 Loaded {len(ALL_KURDISH_SONGS)} Kurdish songs!')
    logger.info(f'📝 Prefix: {PREFIX}')
    logger.info(f'💡 Try: $test to see if bot responds!')
    
    await bot.change_presence(
        activity=Activity(
            type=ActivityType.listening,
            name=f"🇰🇲 Kurdish Songs | {PREFIX}help"
        ),
        status=discord.Status.online
    )
    
    try:
        await bot.tree.sync()
        logger.info("✅ Slash commands synced!")
    except Exception as e:
        logger.error(f"Slash sync error: {e}")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission!")
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send("❌ I don't have permission!")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing required argument: {error.param.name}")
    else:
        logger.error(f"Command error: {error}")
        await ctx.send(f"❌ Error: {str(error)[:100]}")

@bot.event
async def on_voice_state_update(member, before, after):
    if member.id == bot.user.id:
        if not after.channel:
            guild_id = member.guild.id
            queue = bot.get_queue(guild_id)
            queue.clear()
            bot.set_current_song(guild_id, None)
            logger.info(f"Bot disconnected from {member.guild.name}")

# ========== START BOT ==========

if __name__ == "__main__":
    if not TOKEN or TOKEN == 'YOUR_BOT_TOKEN_HERE':
        logger.error("❌ No bot token found! Set DISCORD_TOKEN in .env file")
        sys.exit(1)
    
    try:
        logger.info("Starting bot... 🇰🇲")
        bot.run(TOKEN, reconnect=True)
    except discord.LoginFailure:
        logger.error("❌ Invalid bot token!")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Failed to start: {e}")
        sys.exit(1)
