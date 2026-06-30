import discord
from discord.ext import commands
from discord import FFmpegPCMAudio, Embed, Color, Activity, ActivityType
import yt_dlp
import asyncio
import os
import re
from collections import deque
import random
import time
import json
import urllib.parse
from dotenv import load_dotenv
import logging
import sys
import subprocess

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============== CONFIGURATION ==============
TOKEN = os.getenv('DISCORD_TOKEN', 'YOUR_BOT_TOKEN_HERE')
PREFIX = os.getenv('PREFIX', '$')
MAX_QUEUE_SIZE = 500

# Check if ffmpeg is available
try:
    subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
    logger.info("✅ FFmpeg is available")
except:
    logger.warning("⚠️ FFmpeg not found, using fallback")

# FFmpeg options for Railway
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -bufsize 64k -loglevel quiet'
}

# yt-dlp options - OPTIMIZED FOR RAILWAY
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '128',
    }],
    'outtmpl': '/tmp/audio_%(title)s_%(id)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': False,
    'nocheckcertificate': True,
    'ignoreerrors': True,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'socket_timeout': 30,
    'retries': 3,
    'fragment_retries': 3,
    'extract_flat': False
}

# ============== KURDISH SONG DATABASE ==============
KURDISH_SONG_DATABASE = {
    'şivan perwer': {
        'keywords': ['şivan perwer', 'shivan perwer', 'şivan', 'shivan'],
        'songs': [
            'ez xumam', 'keçelok', 'bavê xwe', 'leylê leylê',
            'dayikê', 'xerîb', 'delalê', 'keça kurd',
            'jin u jiyan', 'bîranîn', 'destana', 'serhatî',
            'ax û evîn', 'pêşmerge', 'kurdistan', 'azadî',
            'xem', 'evîn', 'roj', 'hêvî', 'dil', 'can'
        ]
    },
    'ciwan haco': {
        'keywords': ['ciwan haco', 'ciwan', 'ciwan haco kurdish'],
        'songs': [
            'zembîlfiroş', 'dilşa', 'serxwebûn', 'xwezî',
            'bûka kurd', 'keça çiyê', 'rêya azadî', 'bîrhatin',
            'çûkê', 'bavê min', 'daya min', 'birayê min'
        ]
    },
    'hesen zîrek': {
        'keywords': ['hesen zîrek', 'hesen zirek', 'hesen', 'hasan zirek'],
        'songs': [
            'ez ketim', 'keçelok', 'xerîbî', 'daye min',
            'bavê min', 'xwezî', 'delal', 'keça min'
        ]
    },
    'aram tigran': {
        'keywords': ['aram tigran', 'aram', 'tigran'],
        'songs': [
            'keçelo', 'xerîb', 'derd', 'derdê min',
            'evîna min', 'rojên min', 'şevên min'
        ]
    },
    'rojan': {
        'keywords': ['rojan', 'rojan kurdish'],
        'songs': [
            'kurdistan', 'azadî', 'serxwebûn', 'xwezî',
            'keça kurd', 'xortê kurd', 'jin', 'jîyan'
        ]
    },
    'gulan': {
        'keywords': ['gulan', 'gulan kurdish'],
        'songs': [
            'stranek', 'kilamek', 'dengê min', 'awazê min',
            'dilê min', 'canê min', 'evîna min'
        ]
    },
    'kurmancî': {
        'keywords': ['kurmancî', 'kurmanc', 'kurmanci'],
        'songs': [
            'strana kurmancî', 'kilama kurmancî', 'dengê kurmancî',
            'awazê kurmancî', 'govenda kurmancî', 'halayê kurmancî'
        ]
    },
    'soranî': {
        'keywords': ['soranî', 'sorani'],
        'songs': [
            'strana soranî', 'kilama soranî', 'dengê soranî',
            'awazê soranî', 'govenda soranî'
        ]
    },
    'dengbej': {
        'keywords': ['dengbej', 'dengbêj', 'dengbej kurdish'],
        'songs': [
            'kilama dengbêj', 'strana dengbêj', 'dengê dengbêj',
            'awazê dengbêj', 'kilamên dengbêj'
        ]
    }
}

# ============== LANGUAGE KEYWORDS ==============
LANGUAGE_KEYWORDS = {
    'kurdish': [
        'kurdish', 'kurdî', 'kurdi', 'kurmancî', 'soranî',
        'kürdçe', 'kürtçe', 'kurdistan', 'awaz', 'dengbej',
        'stran', 'kilam', 'govend', 'halay'
    ],
    'arabic': ['arabic', 'عربي', 'العربية', 'أغاني عربية'],
    'turkish': ['turkish', 'türkçe', 'türkü', 'turkce'],
    'persian': ['persian', 'فارسی', 'ایرانی'],
    'english': ['english', 'pop', 'rock', 'hip hop', 'rap', 'edm']
}

# ============== KURDISH SONG FINDER ==============
class KurdishSongFinder:
    def __init__(self):
        self.song_database = KURDISH_SONG_DATABASE
        self.all_kurdish_songs = []
        self.kurdish_keywords = []
        
        for artist, data in self.song_database.items():
            self.all_kurdish_songs.extend(data['songs'])
            self.kurdish_keywords.extend(data['keywords'])
        
        self.all_kurdish_songs = list(set(self.all_kurdish_songs))
        self.kurdish_keywords = list(set(self.kurdish_keywords))
        
        logger.info(f"📚 Loaded {len(self.all_kurdish_songs)} Kurdish songs")
    
    def find_kurdish_songs(self, query):
        query_lower = query.lower()
        found_songs = []
        
        for artist, data in self.song_database.items():
            if any(keyword in query_lower for keyword in data['keywords']):
                found_songs.extend(data['songs'])
        
        for song in self.all_kurdish_songs:
            if song.lower() in query_lower or query_lower in song.lower():
                if song not in found_songs:
                    found_songs.append(song)
        
        return found_songs[:20]
    
    def get_random_kurdish_song(self):
        return random.choice(self.all_kurdish_songs)

# ============== MAIN BOT CLASS ==============
class MusicBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        intents.guilds = True
        
        super().__init__(
            command_prefix=PREFIX,
            intents=intents,
            help_command=None
        )
        
        self.queues = {}
        self.current_songs = {}
        self.loop = {}
        self.volume = {}
        self.history = {}
        self.kurdish_finder = KurdishSongFinder()
        self.music_player = None
        self.stats = {'total_plays': 0}
        
        os.makedirs('/tmp/downloads', exist_ok=True)
        os.makedirs('data', exist_ok=True)
        
        logger.info(f"🤖 Bot initialized with {len(self.kurdish_finder.all_kurdish_songs)} Kurdish songs")

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
        self.downloading = {}

    def detect_language(self, query):
        query_lower = query.lower()
        for keyword in self.bot.kurdish_finder.kurdish_keywords:
            if keyword in query_lower:
                return 'kurdish'
        for language, keywords in LANGUAGE_KEYWORDS.items():
            if any(keyword in query_lower for keyword in keywords):
                return language
        return None

    def format_duration(self, seconds):
        if not seconds or seconds <= 0:
            return 'Live'
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

    async def search_song(self, query, limit=5):
        """Search for songs using yt-dlp - NO external libraries needed!"""
        try:
            results = []
            
            # Try direct search with yt-dlp
            try:
                ydl_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': True,
                    'default_search': 'ytsearch',
                    'max_downloads': limit * 2,
                    'socket_timeout': 30
                }
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    search_results = await asyncio.to_thread(
                        ydl.extract_info, 
                        f"ytsearch{limit*2}:{query}", 
                        download=False
                    )
                    
                    if search_results and 'entries' in search_results:
                        for entry in search_results['entries']:
                            if entry:
                                results.append(entry)
            except Exception as e:
                logger.warning(f"Search error: {e}")

            # If no results, try with language detection
            if not results:
                language = self.detect_language(query)
                if language == 'kurdish':
                    try:
                        ydl_opts = {
                            'quiet': True,
                            'no_warnings': True,
                            'extract_flat': True,
                            'default_search': 'ytsearch',
                            'max_downloads': limit,
                            'socket_timeout': 30
                        }
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            search_results = await asyncio.to_thread(
                                ydl.extract_info,
                                f"ytsearch{limit}:{query} kurdish",
                                download=False
                            )
                            if search_results and 'entries' in search_results:
                                for entry in search_results['entries']:
                                    if entry:
                                        results.append(entry)
                    except:
                        pass

            # Format results
            formatted_results = []
            seen_urls = set()
            
            for result in results:
                try:
                    url = result.get('url', result.get('webpage_url', ''))
                    if not url or url in seen_urls:
                        continue
                    
                    seen_urls.add(url)
                    duration = result.get('duration', 0)
                    
                    formatted_results.append({
                        'title': result.get('title', 'Unknown')[:100],
                        'url': url,
                        'duration': self.format_duration(duration),
                        'thumbnail': result.get('thumbnail', ''),
                        'channel': result.get('channel', result.get('uploader', 'Unknown')),
                        'views': f"{result.get('view_count', 0):,}" if result.get('view_count') else 'N/A'
                    })
                    
                    if len(formatted_results) >= limit:
                        break
                except:
                    continue

            return formatted_results[:limit]

        except Exception as e:
            logger.error(f"Search error: {e}")
            return []

    async def download_audio(self, url):
        """Download audio with retry logic"""
        try:
            ydl_opts = {
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '128',
                }],
                'outtmpl': '/tmp/audio_%(title)s_%(id)s.%(ext)s',
                'restrictfilenames': True,
                'nocheckcertificate': True,
                'ignoreerrors': True,
                'quiet': True,
                'no_warnings': True,
                'socket_timeout': 30,
                'retries': 3,
                'noplaylist': True
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    info = await asyncio.to_thread(ydl.extract_info, url, download=True)
                    if info:
                        filename = ydl.prepare_filename(info)
                        for ext in ['mp3', 'webm', 'm4a', 'opus']:
                            check_file = filename.rsplit('.', 1)[0] + '.' + ext
                            if os.path.exists(check_file):
                                filename = check_file
                                break
                        if os.path.exists(filename):
                            return filename
                except Exception as e:
                    logger.error(f"Download error: {e}")
            
            return None
            
        except Exception as e:
            logger.error(f"Download error: {e}")
            return None

    async def get_song_info(self, url):
        """Get detailed song information"""
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': True,
                'force_generic_extractor': False,
                'socket_timeout': 10,
                'retries': 2
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    info = await asyncio.to_thread(ydl.extract_info, url, download=False)
                except:
                    return None
                
                if not info:
                    return None
                
                if 'entries' in info and info['entries']:
                    songs = []
                    for entry in info['entries'][:10]:
                        if entry:
                            songs.append({
                                'title': entry.get('title', 'Unknown')[:100],
                                'url': entry.get('url', entry.get('webpage_url', url)),
                                'duration': self.format_duration(entry.get('duration', 0)),
                                'thumbnail': entry.get('thumbnail', ''),
                                'channel': entry.get('channel', info.get('channel', 'Unknown')),
                                'views': f"{entry.get('view_count', 0):,}" if entry.get('view_count') else 'N/A'
                            })
                    return songs
                
                return {
                    'title': info.get('title', 'Unknown')[:100],
                    'url': url,
                    'duration': self.format_duration(info.get('duration', 0)),
                    'thumbnail': info.get('thumbnail', ''),
                    'channel': info.get('channel', 'Unknown'),
                    'views': f"{info.get('view_count', 0):,}" if info.get('view_count') else 'N/A'
                }
                
        except Exception as e:
            logger.error(f"Info error: {e}")
            return None

    async def play_song(self, ctx, query):
        """Main play function - supports ALL languages!"""
        try:
            if not ctx.author.voice:
                await ctx.send("❌ You need to be in a voice channel!")
                return None
            
            voice_channel = ctx.author.voice.channel
            if ctx.voice_client is None:
                await voice_channel.connect(timeout=10.0)
            elif ctx.voice_client.channel != voice_channel:
                await ctx.voice_client.move_to(voice_channel)
            
            # Check if it's a URL
            is_url = query.startswith(('http://', 'https://', 'www.'))
            
            if is_url:
                song_info = await self.get_song_info(query)
                if not song_info:
                    await ctx.send("❌ Could not get song information!")
                    return None
                
                if isinstance(song_info, list):
                    queue = self.bot.get_queue(ctx.guild.id)
                    for song in song_info:
                        if song:
                            queue.append(song)
                    await ctx.send(f"📝 Added **{len(song_info)}** songs from playlist!")
                    if not ctx.voice_client.is_playing():
                        await self.play_next(ctx)
                    return song_info
                
                queue = self.bot.get_queue(ctx.guild.id)
                queue.append(song_info)
                
                if not ctx.voice_client.is_playing():
                    await self.play_next(ctx)
                else:
                    await ctx.send(f"📝 Added: **{song_info['title']}** (Position: {len(queue)})")
                return song_info
            
            # Check Kurdish database first
            kurdish_songs = self.bot.kurdish_finder.find_kurdish_songs(query)
            if kurdish_songs:
                for song in kurdish_songs[:3]:
                    search_query = f"{song} kurdish"
                    results = await self.search_song(search_query, limit=1)
                    if results:
                        song_data = results[0]
                        queue = self.bot.get_queue(ctx.guild.id)
                        queue.append(song_data)
                        
                        if not ctx.voice_client.is_playing():
                            await self.play_next(ctx)
                        else:
                            await ctx.send(f"📝 Added Kurdish song: **{song_data['title']}** (Position: {len(queue)})")
                        return song_data
            
            # Regular search
            results = await self.search_song(query, limit=3)
            if not results:
                # Try with Kurdish keyword as last resort
                try:
                    kurdish_search = await self.search_song(f"{query} kurdish", limit=3)
                    if kurdish_search:
                        results = kurdish_search
                except:
                    pass
                
                if not results:
                    await ctx.send(f"❌ No results found for: **{query}**")
                    return None
            
            song = results[0]
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
        """Play the next song in queue"""
        try:
            queue = self.bot.get_queue(ctx.guild.id)
            
            if not queue:
                self.bot.set_current_song(ctx.guild.id, None)
                if ctx.voice_client:
                    await ctx.voice_client.disconnect()
                    await ctx.send("⏹️ Queue empty. Disconnected.")
                    await self.bot.change_presence(
                        activity=Activity(type=ActivityType.listening, name=f"{PREFIX}help")
                    )
                return
            
            if self.bot.get_loop(ctx.guild.id):
                current = self.bot.get_current_song(ctx.guild.id)
                if current:
                    queue.appendleft(current)
            
            try:
                song = queue.popleft()
            except:
                await self.play_next(ctx)
                return
            
            self.bot.set_current_song(ctx.guild.id, song)
            
            # Download audio
            audio_file = await self.download_audio(song['url'])
            if not audio_file or not os.path.exists(audio_file):
                await ctx.send(f"❌ Failed to download: {song.get('title', 'Unknown')}")
                await self.play_next(ctx)
                return
            
            # Create audio source
            volume = self.bot.get_volume(ctx.guild.id) / 100
            volume_filter = f"volume={volume}" if volume != 1.0 else ""
            
            audio = FFmpegPCMAudio(
                audio_file,
                before_options='-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                options=f'-vn -bufsize 64k -loglevel quiet -af "{volume_filter}"' if volume_filter else '-vn -bufsize 64k -loglevel quiet'
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
            embed.set_footer(text="🎶 Universal Music Bot | 🇰🇲 Kurdish Songs Available")
            
            await ctx.send(embed=embed)
            
            # Update status
            song_title = song.get('title', 'Music')[:50]
            await self.bot.change_presence(
                activity=Activity(type=ActivityType.listening, name=song_title)
            )
            
        except Exception as e:
            logger.error(f"Play next error: {e}")
            await ctx.send(f"❌ Playback error, skipping...")
            await self.play_next(ctx)

# ========== INITIALIZE BOT ==========
bot = MusicBot()
bot.music_player = MusicPlayer(bot)

# ========== TEXT COMMANDS ==========

@bot.command(name='play', aliases=['p'])
async def play(ctx, *, query):
    """Play ANY song - including Kurdish songs!"""
    if not query:
        await ctx.send("❌ Please provide a song name!")
        return
    
    await ctx.send("🔍 Searching...")
    try:
        result = await bot.music_player.play_song(ctx, query)
        if result:
            if isinstance(result, list):
                await ctx.send(f"✅ Added playlist with {len(result)} songs!")
            else:
                await ctx.send(f"🎵 Added: **{result.get('title', 'Song')}**")
    except Exception as e:
        logger.error(f"Play error: {e}")
        await ctx.send(f"❌ Error: {str(e)[:100]}")

@bot.command(name='kurdish', aliases=['kurd'])
async def kurdish_songs(ctx, *, query=None):
    """Search for Kurdish songs from the database"""
    if not query:
        random_song = bot.kurdish_finder.get_random_kurdish_song()
        await ctx.send(f"🎵 Try this Kurdish song: **{random_song}**\n💡 Use `$play {random_song}` to play it!")
        return
    
    songs = bot.kurdish_finder.find_kurdish_songs(query)
    if songs:
        embed = Embed(
            title="🇰🇲 Kurdish Songs Found",
            description=f"Found {len(songs)} Kurdish songs!",
            color=Color.gold()
        )
        
        song_list = []
        for i, song in enumerate(songs[:20], 1):
            song_list.append(f"`{i}.` **{song}**")
        
        embed.add_field(
            name="📝 Songs",
            value="\n".join(song_list) if song_list else "No songs found",
            inline=False
        )
        embed.set_footer(text="💡 Use $play <song name> to play any of these!")
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"❌ No Kurdish songs found for: **{query}**")

@bot.command(name='kurdish-random', aliases=['krandom'])
async def kurdish_random(ctx):
    """Play a random Kurdish song"""
    random_song = bot.kurdish_finder.get_random_kurdish_song()
    await ctx.send(f"🎵 Playing random Kurdish song: **{random_song}** 🇰🇲")
    await play(ctx, query=random_song)

@bot.command(name='search', aliases=['find'])
async def search(ctx, *, query):
    """Search for songs"""
    if not query:
        await ctx.send("❌ Please provide a search query!")
        return
    
    try:
        results = await bot.music_player.search_song(query, limit=10)
        if not results:
            await ctx.send(f"❌ No results for: **{query}**")
            return
        
        embed = Embed(
            title="🔍 Search Results",
            description=f"Found {len(results)} results for: **{query[:50]}**",
            color=Color.blue()
        )
        
        for i, result in enumerate(results[:10], 1):
            embed.add_field(
                name=f"{i}. {result['title'][:50]}...",
                value=f"⏱️ {result.get('duration', 'N/A')} | 👤 {result.get('channel', 'Unknown')}",
                inline=False
            )
        
        embed.set_footer(text="💡 Use $play <number> or $play <song name>")
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)[:100]}")

@bot.command(name='queue', aliases=['q'])
async def show_queue(ctx):
    """Show current queue"""
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
        
        embed.set_footer(
            text=f"🔄 Loop: {'✅' if bot.get_loop(ctx.guild.id) else '❌'} | "
                 f"🔊 Volume: {bot.get_volume(ctx.guild.id)}%"
        )
        await ctx.send(embed=embed)
        
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)[:100]}")

@bot.command(name='skip', aliases=['s'])
async def skip(ctx):
    """Skip current song"""
    if not ctx.voice_client or not ctx.voice_client.is_playing():
        await ctx.send("❌ No song is currently playing!")
        return
    
    current = bot.get_current_song(ctx.guild.id)
    if current:
        await ctx.send(f"⏭️ Skipped: **{current.get('title', 'Song')}**")
    ctx.voice_client.stop()

@bot.command(name='stop', aliases=['leave'])
async def stop(ctx):
    """Stop playback and clear queue"""
    try:
        queue = bot.get_queue(ctx.guild.id)
        queue.clear()
        bot.set_current_song(ctx.guild.id, None)
        
        if ctx.voice_client:
            await ctx.voice_client.disconnect()
            await ctx.send("⏹️ Stopped and disconnected. Queue cleared.")
            await bot.change_presence(
                activity=Activity(type=ActivityType.listening, name=f"{PREFIX}help")
            )
        else:
            await ctx.send("❌ Not in a voice channel!")
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)[:100]}")

@bot.command(name='pause')
async def pause(ctx):
    """Pause current song"""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.pause()
        await ctx.send("⏸️ Paused")
    else:
        await ctx.send("❌ No song playing!")

@bot.command(name='resume')
async def resume(ctx):
    """Resume paused song"""
    if ctx.voice_client and ctx.voice_client.is_paused():
        ctx.voice_client.resume()
        await ctx.send("▶️ Resumed")
    else:
        await ctx.send("❌ No song paused!")

@bot.command(name='loop', aliases=['repeat'])
async def loop(ctx):
    """Toggle loop mode"""
    if not bot.get_current_song(ctx.guild.id):
        await ctx.send("❌ No song playing!")
        return
    
    loop_status = bot.toggle_loop(ctx.guild.id)
    await ctx.send(f"🔄 Loop: {'✅ Enabled' if loop_status else '❌ Disabled'}")

@bot.command(name='volume', aliases=['vol'])
async def volume(ctx, level: int = None):
    """Set volume (0-200%)"""
    if level is None:
        await ctx.send(f"🔊 Volume: **{bot.get_volume(ctx.guild.id)}%**")
        return
    
    if level < 0 or level > 200:
        await ctx.send("❌ Volume must be between 0-200!")
        return
    
    bot.set_volume(ctx.guild.id, level)
    await ctx.send(f"🔊 Volume set to: **{level}%**")

@bot.command(name='remove', aliases=['rm'])
async def remove_from_queue(ctx, position: int):
    """Remove song from queue"""
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

@bot.command(name='clear', aliases=['clearqueue'])
async def clear_queue(ctx):
    """Clear all songs from queue"""
    queue = bot.get_queue(ctx.guild.id)
    count = len(queue)
    queue.clear()
    await ctx.send(f"🗑️ Cleared **{count}** songs!")

@bot.command(name='shuffle')
async def shuffle_queue(ctx):
    """Shuffle the queue"""
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
    """Show currently playing song"""
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
    embed.set_footer(text="🎶 Universal Music Bot")
    
    await ctx.send(embed=embed)

@bot.command(name='help', aliases=['h'])
async def help_command(ctx):
    """Show help menu"""
    embed = Embed(
        title="🎵 Universal Music Bot - Help",
        description="**🌍 Supports ALL Languages!**\n🇰🇲 **Kurdish songs built-in!**",
        color=Color.gold()
    )
    
    embed.add_field(
        name="🎶 Music Commands",
        value=(
            "`$play <song>` - Play ANY song from ANY language\n"
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
        name="🌍 Language Support",
        value=(
            "🇰🇲 Kurdish • 🇸🇦 Arabic • 🇹🇷 Turkish\n"
            "🇮🇷 Persian • 🇬🇧 English • 🇪🇸 Spanish\n"
            "🇫🇷 French • 🇩🇪 German • 🇮🇳 Hindi"
        ),
        inline=False
    )
    
    embed.set_footer(text=f"🎵 Prefix: {PREFIX} | 🇰🇲 Kurdish Music Included")
    await ctx.send(embed=embed)

# ========== SLASH COMMANDS ==========

@bot.tree.command(name="play", description="Play a song from any language")
async def slash_play(interaction: discord.Interaction, query: str):
    await interaction.response.defer()
    ctx = await bot.get_context(interaction)
    try:
        result = await bot.music_player.play_song(ctx, query)
        if result:
            await interaction.followup.send(f"🎵 Added: **{result.get('title', 'Song')}**")
        else:
            await interaction.followup.send(f"❌ Could not find: **{query}**")
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)[:100]}")

@bot.tree.command(name="search", description="Search for songs")
async def slash_search(interaction: discord.Interaction, query: str):
    await interaction.response.defer()
    try:
        results = await bot.music_player.search_song(query, limit=10)
        if not results:
            await interaction.followup.send(f"❌ No results for: **{query}**")
            return
        
        embed = Embed(
            title="🔍 Search Results",
            description=f"Found {len(results)} results",
            color=Color.blue()
        )
        
        for i, result in enumerate(results[:10], 1):
            embed.add_field(
                name=f"{i}. {result['title'][:50]}...",
                value=f"⏱️ {result.get('duration', 'N/A')}",
                inline=False
            )
        
        await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)[:100]}")

@bot.tree.command(name="kurdish", description="Search for Kurdish songs")
async def slash_kurdish(interaction: discord.Interaction, query: str):
    await interaction.response.defer()
    
    songs = bot.kurdish_finder.find_kurdish_songs(query)
    if songs:
        embed = Embed(
            title="🇰🇲 Kurdish Songs Found",
            description=f"Found {len(songs)} Kurdish songs!",
            color=Color.gold()
        )
        
        song_list = []
        for i, song in enumerate(songs[:20], 1):
            song_list.append(f"`{i}.` **{song}**")
        
        embed.add_field(
            name="📝 Songs",
            value="\n".join(song_list) if song_list else "No songs found",
            inline=False
        )
        await interaction.followup.send(embed=embed)
    else:
        await interaction.followup.send(f"❌ No Kurdish songs found for: **{query}**")

@bot.tree.command(name="queue", description="Show current queue")
async def slash_queue(interaction: discord.Interaction):
    try:
        queue = bot.get_queue(interaction.guild.id)
        current = bot.get_current_song(interaction.guild.id)
        
        if not queue and not current:
            await interaction.response.send_message("📭 The queue is empty!")
            return
        
        embed = Embed(title="📋 Music Queue", color=Color.blue())
        
        if current:
            embed.add_field(
                name="🎵 Now Playing",
                value=f"**{current.get('title', 'Unknown')}**",
                inline=False
            )
        
        if queue:
            queue_list = []
            for i, song in enumerate(list(queue)[:10], 1):
                title = song.get('title', 'Unknown')[:45]
                queue_list.append(f"`{i}.` **{title}...**")
            
            embed.add_field(
                name=f"📝 Next Songs ({len(queue)} total)",
                value="\n".join(queue_list) if queue_list else "No upcoming songs",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {str(e)[:100]}")

@bot.tree.command(name="skip", description="Skip current song")
async def slash_skip(interaction: discord.Interaction):
    if not interaction.guild.voice_client or not interaction.guild.voice_client.is_playing():
        await interaction.response.send_message("❌ No song playing!")
        return
    
    current = bot.get_current_song(interaction.guild.id)
    interaction.guild.voice_client.stop()
    await interaction.response.send_message(f"⏭️ Skipped: **{current.get('title', 'Song')}**")

@bot.tree.command(name="stop", description="Stop playback")
async def slash_stop(interaction: discord.Interaction):
    try:
        queue = bot.get_queue(interaction.guild.id)
        queue.clear()
        bot.set_current_song(interaction.guild.id, None)
        
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.disconnect()
            await interaction.response.send_message("⏹️ Stopped and disconnected.")
        else:
            await interaction.response.send_message("❌ Not in a voice channel!")
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {str(e)[:100]}")

@bot.tree.command(name="loop", description="Toggle loop mode")
async def slash_loop(interaction: discord.Interaction):
    if not bot.get_current_song(interaction.guild.id):
        await interaction.response.send_message("❌ No song playing!")
        return
    
    loop_status = bot.toggle_loop(interaction.guild.id)
    await interaction.response.send_message(f"🔄 Loop: {'✅ Enabled' if loop_status else '❌ Disabled'}")

@bot.tree.command(name="volume", description="Set volume (0-200%)")
async def slash_volume(interaction: discord.Interaction, level: int):
    if level < 0 or level > 200:
        await interaction.response.send_message("❌ Volume must be 0-200!")
        return
    
    bot.set_volume(interaction.guild.id, level)
    await interaction.response.send_message(f"🔊 Volume: **{level}%**")

@bot.tree.command(name="nowplaying", description="Show currently playing song")
async def slash_nowplaying(interaction: discord.Interaction):
    current = bot.get_current_song(interaction.guild.id)
    if not current:
        await interaction.response.send_message("❌ No song playing!")
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
    embed.add_field(name="🔊 Volume", value=f"{bot.get_volume(interaction.guild.id)}%", inline=True)
    
    await interaction.response.send_message(embed=embed)

# ========== EVENTS ==========

@bot.event
async def on_ready():
    logger.info(f'✅ Logged in as {bot.user.name}')
    logger.info(f'📊 Connected to {len(bot.guilds)} servers')
    logger.info(f'🇰🇲 Loaded {len(bot.kurdish_finder.all_kurdish_songs)} Kurdish songs!')
    logger.info(f'🎵 Universal Music Bot is ready!')
    
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

@bot.event
async def on_error(event, *args, **kwargs):
    logger.error(f"Event error: {event}")

# ========== START BOT ==========

if __name__ == "__main__":
    if not TOKEN or TOKEN == 'YOUR_BOT_TOKEN_HERE':
        logger.error("❌ No bot token found!")
        sys.exit(1)
    
    try:
        logger.info("Starting bot with Kurdish song database... 🇰🇲")
        bot.run(TOKEN, reconnect=True)
    except discord.LoginFailure:
        logger.error("❌ Invalid bot token!")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Failed to start: {e}")
        sys.exit(1)
