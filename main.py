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
from youtube_search import YoutubeSearch
import aiohttp
import urllib.parse
from dotenv import load_dotenv
import logging
import sys

# Load environment variables
load_dotenv()

# Setup logging for debugging (minimal)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration from environment
TOKEN = os.getenv('DISCORD_TOKEN', 'YOUR_BOT_TOKEN_HERE')
PREFIX = os.getenv('PREFIX', '$')
MAX_QUEUE_SIZE = 500

# FFmpeg options for Railway - optimized for memory
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -bufsize 64k -loglevel quiet'
}

# yt-dlp options - optimized for Railway
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '128',  # Lower quality for faster downloads
    }],
    'outtmpl': '/tmp/%(title)s.%(ext)s',  # Use /tmp for Railway
    'restrictfilenames': True,
    'noplaylist': False,
    'nocheckcertificate': True,
    'ignoreerrors': True,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'extract_flat': False,
    'cookiefile': '/tmp/cookies.txt' if os.path.exists('/tmp/cookies.txt') else None,
    'socket_timeout': 30,
    'retries': 3,
    'fragment_retries': 3
}

# Language keywords for better search
LANGUAGE_KEYWORDS = {
    'kurdish': ['kurdish', 'kurdî', 'kurdi', 'kurmancî', 'soranî', 'kürdçe', 'kürtçe', 'kurdistan', 'awaz', 'dengbej', 'stran', 'kilam'],
    'arabic': ['arabic', 'عربي', 'العربية', 'music arabic', 'أغاني عربية', 'موسيقى عربية'],
    'turkish': ['turkish', 'türkçe', 'türkü', 'turkce', 'turkish music', 'türk müzik'],
    'persian': ['persian', 'فارسی', 'ایرانی', 'persian music', 'موسیقی ایرانی'],
    'english': ['english', 'pop', 'rock', 'hip hop', 'rap', 'edm', 'rnb', 'music'],
    'spanish': ['spanish', 'español', 'latin', 'reggeaton', 'bachata'],
    'french': ['french', 'français', 'chanson', 'variété française'],
    'german': ['german', 'deutsch', 'deutsche musik'],
    'hindi': ['hindi', 'बॉलीवुड', 'bollywood', 'indian music'],
    'japanese': ['japanese', '日本語', 'jpop', 'j-rock', 'anime'],
    'korean': ['korean', '한국어', 'kpop', 'k-rock', 'k-indie']
}

# Custom MusicBot class
class MusicBot(commands.Bot):
    def __init__(self):
        # Enhanced intents
        intents = discord.Intents.default()
        intents.message_content = True
        intents.voice_states = True
        intents.guilds = True
        
        super().__init__(
            command_prefix=PREFIX,
            intents=intents,
            help_command=None,
            application_id=os.getenv('APPLICATION_ID')
        )
        
        # Data storage
        self.queues = {}
        self.current_songs = {}
        self.loop = {}
        self.volume = {}
        self.music_player = None
        self.voice_clients = {}
        
        # Create temp directory for downloads
        os.makedirs('/tmp/downloads', exist_ok=True)
        
        # Lock for thread safety
        self.lock = asyncio.Lock()
        
        logger.info("Bot initialized successfully")

    async def setup_hook(self):
        """Setup hook for slash commands"""
        try:
            await self.tree.sync()
            logger.info("Slash commands synced successfully")
        except Exception as e:
            logger.error(f"Failed to sync slash commands: {e}")

    def get_queue(self, guild_id):
        """Get or create queue for a guild"""
        if guild_id not in self.queues:
            self.queues[guild_id] = deque(maxlen=MAX_QUEUE_SIZE)
        return self.queues[guild_id]

    def get_current_song(self, guild_id):
        """Get current playing song"""
        return self.current_songs.get(guild_id)

    def set_current_song(self, guild_id, song):
        """Set current playing song"""
        self.current_songs[guild_id] = song

    def get_loop(self, guild_id):
        """Get loop status"""
        return self.loop.get(guild_id, False)

    def toggle_loop(self, guild_id):
        """Toggle loop mode"""
        self.loop[guild_id] = not self.loop.get(guild_id, False)
        return self.loop[guild_id]

    def get_volume(self, guild_id):
        """Get volume level"""
        return self.volume.get(guild_id, 50)

    def set_volume(self, guild_id, vol):
        """Set volume level"""
        self.volume[guild_id] = max(0, min(200, vol))

# Music Player class
class MusicPlayer:
    def __init__(self, bot):
        self.bot = bot
        self.ffmpeg_options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn -bufsize 64k -loglevel quiet'
        }
        self.downloading = {}
        logger.info("MusicPlayer initialized")

    def detect_language(self, query):
        """Detect language from query"""
        query_lower = query.lower()
        for language, keywords in LANGUAGE_KEYWORDS.items():
            if any(keyword in query_lower for keyword in keywords):
                return language
        return None

    def format_duration(self, seconds):
        """Format duration to HH:MM:SS"""
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
        """Search for songs with language support"""
        try:
            results = []
            
            # Try direct YouTube search
            try:
                search_results = YoutubeSearch(query, max_results=limit * 2).to_dict()
                if search_results:
                    results.extend(search_results)
            except Exception as e:
                logger.warning(f"Primary search failed: {e}")

            # If no results, try with language keywords
            if not results:
                language = self.detect_language(query)
                if language and language in LANGUAGE_KEYWORDS:
                    keywords = LANGUAGE_KEYWORDS[language]
                    for keyword in keywords[:3]:
                        try:
                            enhanced_query = f"{query} {keyword}"
                            search_results = YoutubeSearch(enhanced_query, max_results=limit).to_dict()
                            if search_results:
                                results.extend(search_results)
                                break
                        except:
                            continue

            # If still no results, try broad search
            if not results:
                try:
                    broad_results = YoutubeSearch(f"{query} music", max_results=limit).to_dict()
                    if broad_results:
                        results.extend(broad_results)
                except:
                    pass

            # Format and deduplicate results
            formatted_results = []
            seen_urls = set()
            
            for result in results:
                try:
                    url = f"https://www.youtube.com/watch?v={result.get('id', '')}"
                    if url in seen_urls or not result.get('id'):
                        continue
                    
                    seen_urls.add(url)
                    duration = result.get('duration', 'N/A')
                    if duration == 'N/A' and result.get('duration_seconds'):
                        duration = self.format_duration(result.get('duration_seconds'))
                    
                    formatted_results.append({
                        'title': result.get('title', 'Unknown Title')[:100],
                        'url': url,
                        'duration': duration if duration else 'N/A',
                        'thumbnail': f"https://i.ytimg.com/vi/{result['id']}/hqdefault.jpg",
                        'channel': result.get('channel', 'Unknown'),
                        'views': result.get('views', 'N/A')
                    })
                    
                    if len(formatted_results) >= limit:
                        break
                except Exception as e:
                    logger.warning(f"Error formatting result: {e}")
                    continue

            return formatted_results[:limit]

        except Exception as e:
            logger.error(f"Search error: {e}")
            return []

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
                except Exception as e:
                    logger.error(f"yt-dlp extract error: {e}")
                    return None
                
                if not info:
                    return None
                
                # Handle playlists
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
                
                # Single song
                return {
                    'title': info.get('title', 'Unknown')[:100],
                    'url': url,
                    'duration': self.format_duration(info.get('duration', 0)),
                    'thumbnail': info.get('thumbnail', ''),
                    'channel': info.get('channel', 'Unknown'),
                    'views': f"{info.get('view_count', 0):,}" if info.get('view_count') else 'N/A',
                    'upload_date': info.get('upload_date', 'Unknown')
                }
                
        except Exception as e:
            logger.error(f"Error getting song info: {e}")
            return None

    async def play_song(self, ctx, query):
        """Main play function - handles both URL and search queries"""
        try:
            # Check if user is in voice channel
            if not ctx.author.voice:
                await ctx.send("❌ You need to be in a voice channel!")
                return None
            
            # Join voice channel
            voice_channel = ctx.author.voice.channel
            if ctx.voice_client is None:
                await voice_channel.connect(timeout=10.0)
                logger.info(f"Connected to voice channel: {voice_channel.name}")
            elif ctx.voice_client.channel != voice_channel:
                await ctx.voice_client.move_to(voice_channel)
            
            # Determine if it's a URL or search
            is_url = query.startswith(('http://', 'https://', 'www.'))
            
            if is_url:
                # Handle URL
                song_info = await self.get_song_info(query)
                if not song_info:
                    await ctx.send("❌ Could not get song information!")
                    return None
                
                # Handle playlist
                if isinstance(song_info, list):
                    queue = self.bot.get_queue(ctx.guild.id)
                    for song in song_info:
                        if song:
                            queue.append(song)
                    await ctx.send(f"📝 Added **{len(song_info)}** songs from playlist to queue!")
                    if not ctx.voice_client.is_playing():
                        await self.play_next(ctx)
                    return song_info
                
                # Single song
                queue = self.bot.get_queue(ctx.guild.id)
                queue.append(song_info)
                
                if not ctx.voice_client.is_playing():
                    await self.play_next(ctx)
                else:
                    await ctx.send(f"📝 Added to queue: **{song_info['title']}** (Position: {len(queue)})")
                return song_info
            
            else:
                # Search for song
                results = await self.search_song(query, limit=3)
                if not results:
                    await ctx.send(f"❌ No results found for: **{query}**")
                    return None
                
                # Use first result
                song = results[0]
                queue = self.bot.get_queue(ctx.guild.id)
                queue.append(song)
                
                if not ctx.voice_client.is_playing():
                    await self.play_next(ctx)
                else:
                    await ctx.send(f"📝 Added to queue: **{song['title']}** (Position: {len(queue)})")
                return song
                
        except discord.errors.ClientException as e:
            logger.error(f"Discord client error: {e}")
            await ctx.send("❌ Failed to connect to voice channel. Please try again.")
            return None
        except Exception as e:
            logger.error(f"Play song error: {e}")
            await ctx.send(f"❌ An error occurred: {str(e)[:100]}")
            return None

    async def play_next(self, ctx):
        """Play the next song in queue"""
        try:
            queue = self.bot.get_queue(ctx.guild.id)
            
            # Check if queue is empty
            if not queue:
                self.bot.set_current_song(ctx.guild.id, None)
                if ctx.voice_client:
                    await ctx.voice_client.disconnect()
                    await ctx.send("⏹️ Queue is empty. Disconnected.")
                    await self.bot.change_presence(
                        activity=Activity(type=ActivityType.listening, name=f"{PREFIX}help for commands")
                    )
                return
            
            # Check loop
            if self.bot.get_loop(ctx.guild.id):
                current = self.bot.get_current_song(ctx.guild.id)
                if current:
                    queue.appendleft(current)
            
            # Get next song
            try:
                song = queue.popleft()
            except IndexError:
                await self.play_next(ctx)
                return
            
            self.bot.set_current_song(ctx.guild.id, song)
            
            try:
                # Download audio with retry
                audio_file = await self.download_audio(song['url'])
                if not audio_file or not os.path.exists(audio_file):
                    logger.error(f"Failed to download audio for: {song['title']}")
                    await self.play_next(ctx)
                    return
                
                # Create audio source
                volume = self.bot.get_volume(ctx.guild.id) / 100
                volume_filter = f"volume={volume}" if volume != 1.0 else ""
                
                audio = FFmpegPCMAudio(
                    audio_file,
                    before_options='-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                    options=f'-vn -bufsize 64k -loglevel quiet {volume_filter}'
                )
                
                def after_playing(error):
                    if error:
                        logger.error(f"Playback error: {error}")
                    try:
                        # Clean up downloaded file
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
                embed.set_footer(text="🎶 Universal Music Bot | 🌍 Supports ALL Languages")
                
                await ctx.send(embed=embed)
                
                # Update bot status
                song_title = song.get('title', 'Music')[:50]
                await self.bot.change_presence(
                    activity=Activity(type=ActivityType.listening, name=song_title)
                )
                
            except Exception as e:
                logger.error(f"Error playing song: {e}")
                await ctx.send(f"❌ Error playing song, skipping...")
                await self.play_next(ctx)
                
        except Exception as e:
            logger.error(f"Play next error: {e}")
            await ctx.send(f"❌ Playback error: {str(e)[:100]}")

    async def download_audio(self, url):
        """Download audio with retry logic"""
        try:
            filename = None
            
            # Create ydl options with temporary file path
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
                'fragment_retries': 3,
                'noplaylist': True
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    info = await asyncio.to_thread(ydl.extract_info, url, download=True)
                    if info:
                        filename = ydl.prepare_filename(info)
                        # Check for different extensions
          ions
          
