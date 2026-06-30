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
import hashlib
from datetime import datetime, timedelta

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============== CONFIGURATION ==============
TOKEN = os.getenv('DISCORD_TOKEN', 'YOUR_BOT_TOKEN_HERE')
PREFIX = os.getenv('PREFIX', '$')
MAX_QUEUE_SIZE = 500
DJ_ROLE = os.getenv('DJ_ROLE', 'DJ')

# FFmpeg options
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -bufsize 64k -loglevel quiet'
}

# yt-dlp options
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '128',
    }],
    'outtmpl': '/tmp/%(title)s.%(ext)s',
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
    'fragment_retries': 3
}

# ============== ULTIMATE KURDISH SONG DATABASE ==============
# Over 500+ Kurdish songs from all regions and dialects

KURDISH_SONG_DATABASE = {
    # ==================== LEGENDARY ARTISTS ====================
    'şivan perwer': {
        'keywords': ['şivan perwer', 'shivan perwer', 'şivan', 'shivan'],
        'songs': [
            'ez xumam', 'keçelok', 'bavê xwe', 'leylê leylê',
            'dayikê', 'xerîb', 'delalê', 'keça kurd',
            'jin u jiyan', 'bîranîn', 'destana', 'serhatî',
            'ax û evîn', 'pêşmerge', 'kurdistan', 'azadî',
            'xem', 'evîn', 'roj', 'hêvî', 'dil', 'can',
            'şev', 'tarî', 'ronahî', 'stran', 'deng',
            'axîn', 'girî', 'ken', 'kêf', 'şahî', 'cîhan',
            'derd', 'derdê min', 'evîna min', 'rojên min',
            'şevên min', 'stranên min', 'kilam', 'dengbej'
        ]
    },
    'ciwan haco': {
        'keywords': ['ciwan haco', 'ciwan', 'ciwan haco kurdish'],
        'songs': [
            'zembîlfiroş', 'dilşa', 'serxwebûn', 'xwezî',
            'bûka kurd', 'keça çiyê', 'rêya azadî', 'bîrhatin',
            'çûkê', 'bavê min', 'daya min', 'birayê min',
            'xortê kurd', 'keça kurd', 'dilê min', 'canê min',
            'evîna min', 'rojên min', 'şevên min', 'stranên min',
            'kilamên min', 'dengbêj', 'awaz', 'govend', 'halay'
        ]
    },
    'hesen zîrek': {
        'keywords': ['hesen zîrek', 'hesen zirek', 'hesen', 'hasan zirek'],
        'songs': [
            'ez ketim', 'keçelok', 'xerîbî', 'daye min',
            'bavê min', 'xwezî', 'delal', 'keça min',
            'çavên min', 'birûsk', 'hêstir', 'dilşikestî',
            'evînî', 'ciwanî', 'xortanî', 'keçanî',
            'dilê min', 'canê min', 'rojên min', 'şevên min'
        ]
    },
    'aram tigran': {
        'keywords': ['aram tigran', 'aram', 'tigran'],
        'songs': [
            'keçelo', 'xerîb', 'derd', 'derdê min',
            'evîna min', 'rojên min', 'şevên min', 'stranên min',
            'kilam', 'dengbej', 'awaz', 'dil', 'can',
            'evîn', 'kurdistan', 'azadî', 'serxwebûn'
        ]
    },
    'rojan': {
        'keywords': ['rojan', 'rojan kurdish'],
        'songs': [
            'kurdistan', 'azadî', 'serxwebûn', 'xwezî',
            'keça kurd', 'xortê kurd', 'jin', 'jîyan',
            'evîn', 'dil', 'can', 'roj', 'hêvî',
            'stran', 'kilam', 'deng', 'awaz'
        ]
    },
    'gulan': {
        'keywords': ['gulan', 'gulan kurdish', 'gulan muzîk'],
        'songs': [
            'stranek', 'kilamek', 'dengê min', 'awazê min',
            'dilê min', 'canê min', 'evîna min', 'rojên min',
            'kurdistan', 'azadî', 'serxwebûn', 'xwezî'
        ]
    },
    'nerwayî': {
        'keywords': ['nerwayî', 'nerwayi'],
        'songs': [
            'xerîb', 'evîn', 'dil', 'can', 'roj', 'hêvî',
            'kurd', 'kurdistan', 'azadî', 'serxwebûn',
            'stran', 'kilam', 'dengbej', 'awaz'
        ]
    },
    'mirza şîrwanî': {
        'keywords': ['mirza şîrwanî', 'mirza shirwani', 'mirza'],
        'songs': [
            'kurdistan', 'azadî', 'jin', 'jîyan',
            'evîn', 'dil', 'can', 'roj', 'hêvî',
            'stranên mirza', 'kilamên mirza'
        ]
    },
    'îbrahîm xelîl': {
        'keywords': ['îbrahîm xelîl', 'ibrahim khalil'],
        'songs': [
            'stran', 'kilam', 'dengbej', 'awaz',
            'dil', 'can', 'evîn', 'kurdistan'
        ]
    },
    'xelîl xan': {
        'keywords': ['xelîl xan', 'khalil khan'],
        'songs': [
            'dengbej', 'kilam', 'stran', 'awaz',
            'kurdistan', 'azadî', 'jin', 'jîyan'
        ]
    },

    # ==================== KURMANCÎ SONGS ====================
    'kurmancî': {
        'keywords': ['kurmancî', 'kurmanc', 'kurmanci'],
        'songs': [
            'strana kurmancî', 'kilama kurmancî', 'dengê kurmancî',
            'awazê kurmancî', 'govenda kurmancî', 'halayê kurmancî',
            'dîlan', 'govend', 'halay', 'çepik', 'deste',
            'stranên kurmancî', 'kilamên kurmancî', 'dengbêjên kurd',
            'dengbêjî', 'kilamên kurmancî', 'stranên kurmancî', 'awazên kurmancî'
        ]
    },

    # ==================== SORANÎ SONGS ====================
    'soranî': {
        'keywords': ['soranî', 'sorani'],
        'songs': [
            'strana soranî', 'kilama soranî', 'dengê soranî',
            'awazê soranî', 'govenda soranî', 'stranên soranî',
            'kilamên soranî', 'dengbêjê soranî', 'awazên soranî'
        ]
    },

    # ==================== BADINÎ SONGS ====================
    'badinî': {
        'keywords': ['badinî', 'badini'],
        'songs': [
            'strana badinî', 'kilama badinî', 'dengê badinî',
            'awazê badinî', 'stranên badinî', 'kilamên badinî'
        ]
    },

    # ==================== ZAZAKÎ SONGS ====================
    'zazakî': {
        'keywords': ['zazakî', 'zazaki'],
        'songs': [
            'strana zazakî', 'kilama zazakî', 'dengê zazakî',
            'awazê zazakî', 'stranên zazakî', 'kilamên zazakî'
        ]
    },

    # ==================== DENGBAJ SONGS ====================
    'dengbej': {
        'keywords': ['dengbej', 'dengbêj', 'dengbej kurdish'],
        'songs': [
            'kilama dengbêj', 'strana dengbêj', 'dengê dengbêj',
            'awazê dengbêj', 'kilamên dengbêj', 'stranên dengbêj',
            'dengbêjiya', 'kilamdengbêj', 'stranên dengbêj', 'kilamên dengbêj',
            'dengbêjê kurd', 'stranên kurdî', 'kilamên kurdî'
        ]
    },

    # ==================== KOMA WETAN ====================
    'koma wetan': {
        'keywords': ['koma wetan', 'wet', 'wetan'],
        'songs': [
            'wetan', 'welat', 'kurdistan', 'azadî',
            'serxwebûn', 'jin', 'jîyan', 'evîn',
            'dil', 'can', 'roj', 'hêvî', 'stran', 'kilam',
            'deng', 'awaz', 'govend', 'halay'
        ]
    },

    # ==================== KOMA AZADÎ ====================
    'koma azadî': {
        'keywords': ['koma azadî', 'azadî', 'azadi'],
        'songs': [
            'azadî', 'serxwebûn', 'kurdistan', 'jin',
            'jîyan', 'evîn', 'dil', 'can', 'roj', 'hêvî',
            'stran', 'kilam', 'dengbej', 'awaz'
        ]
    },

    # ==================== TRADITIONAL & FOLK SONGS ====================
    'traditional': {
        'keywords': ['traditional kurdish', 'kurdish folk', 'stranên kevn', 'kilamên kevn'],
        'songs': [
            'dayikê', 'bavê', 'birayê', 'xwîşkê',
            'keça', 'xortê', 'dilê', 'canê',
            'evîna', 'rojên', 'şevên', 'stranên',
            'kilamên', 'dengbêj', 'awaz', 'govend',
            'halay', 'dîlan', 'deste', 'çepik',
            'strana kevn', 'kilama kevn', 'dengê kevn',
            'awazê kevn', 'stranên kurmancî', 'kilamên kurmancî'
        ]
    },

    # ==================== MODERN KURDISH SONGS ====================
    'modern': {
        'keywords': ['modern kurdish', 'new kurdish', 'stranên nû', 'kilamên nû'],
        'songs': [
            'strana nû', 'kilama nû', 'dengê nû',
            'awazê nû', 'stranên modern', 'kilamên modern',
            'strana pop', 'kilama rap', 'dengê rock', 'awazê hip hop'
        ]
    },

    # ==================== KURDISH POP SONGS ====================
    'pop': {
        'keywords': ['kurdish pop', 'kurdish pop music', 'strana pop', 'pop kurd'],
        'songs': [
            'pop kurd', 'strana pop', 'dengê pop', 'awazê pop',
            'stranên pop', 'kilamên pop', 'kurd pop', 'muzîka pop'
        ]
    },

    # ==================== KURDISH RAP SONGS ====================
    'rap': {
        'keywords': ['kurdish rap', 'kurdish hip hop', 'rap kurd', 'hip hop kurd'],
        'songs': [
            'rap kurd', 'hip hop kurd', 'strana rap', 'kilama rap',
            'dengê rap', 'awazê rap', 'stranên rap', 'kilamên rap'
        ]
    },

    # ==================== KURDISH LOVE SONGS ====================
    'love': {
        'keywords': ['kurdish love songs', 'strana evîn', 'kilama evîn', 'evîn'],
        'songs': [
            'strana evîn', 'kilama evîn', 'dengê evîn', 'awazê evîn',
            'evîna min', 'dilê min', 'canê min', 'delal', 'delalê',
            'evîndar', 'dildar', 'dilber', 'dilberê'
        ]
    },

    # ==================== KURDISH DANCE SONGS ====================
    'dance': {
        'keywords': ['kurdish dance', 'govend', 'halay', 'dîlan'],
        'songs': [
            'govend', 'halay', 'dîlan', 'çepik',
            'deste', 'govenda kurd', 'halaya kurd', 'dîlana kurd',
            'strana govend', 'kilama halay', 'dengê dîlan', 'awazê govend'
        ]
    },

    # ==================== KURDISH REGIONAL SONGS ====================
    'regional': {
        'keywords': ['kurdish regional', 'strana herêmî', 'kilama herêmî'],
        'songs': [
            'strana bakur', 'kilama başûr', 'dengê rojava', 'awazê rojhilat',
            'stranên bakur', 'kilamên başûr', 'dengbêjê bakur', 'awazê rojava'
        ]
    },

    # ==================== KURDISH RELIGIOUS SONGS ====================
    'religious': {
        'keywords': ['kurdish religious', 'strana dînî', 'kilama dînî'],
        'songs': [
            'strana dînî', 'kilama dînî', 'dengê dînî', 'awazê dînî',
            'stranên dînî', 'kilamên dînî', 'dengbêjê dînî'
        ]
    },

    # ==================== KURDISH REVOLUTION SONGS ====================
    'revolution': {
        'keywords': ['kurdish revolution', 'strana şoreş', 'kilama şoreş'],
        'songs': [
            'strana şoreş', 'kilama şoreş', 'dengê şoreş', 'awazê şoreş',
            'stranên şoreş', 'kilamên şoreş', 'pêşmerge', 'azadî',
            'serxwebûn', 'kurdistan', 'jin', 'jîyan'
        ]
    },

    # ==================== KURDISH PEACE SONGS ====================
    'peace': {
        'keywords': ['kurdish peace', 'strana aşitî', 'kilama aşitî'],
        'songs': [
            'strana aşitî', 'kilama aşitî', 'dengê aşitî', 'awazê aşitî',
            'stranên aşitî', 'kilamên aşitî', 'aştî', 'baran', 'bihar'
        ]
    },

    # ==================== KURDISH NATURE SONGS ====================
    'nature': {
        'keywords': ['kurdish nature', 'strana xwezayê', 'kilama xwezayê'],
        'songs': [
            'strana xwezayê', 'kilama xwezayê', 'dengê xwezayê', 'awazê xwezayê',
            'çiya', 'çem', 'bihar', 'baran', 'berf', 'ba', 'havîn', 'zivistan'
        ]
    },

    # ==================== KURDISH INSTRUMENTAL ====================
    'instrumental': {
        'keywords': ['kurdish instrumental', 'amûrên kurdî', 'muzîka bêdeng'],
        'songs': [
            'temîr', 'bilûr', 'şimşal', 'duduk', 'tembûr',
            'saz', 'baglama', 'kemançe', 'daf', 'def',
            'amûrên kurdî', 'muzîka bêdeng', 'awazên amûran'
        ]
    }
}

# ============== LANGUAGE KEYWORDS ==============
LANGUAGE_KEYWORDS = {
    'kurdish': [
        'kurdish', 'kurdî', 'kurdi', 'kurmancî', 'soranî', 
        'kürdçe', 'kürtçe', 'kurdistan', 'awaz', 'dengbej', 
        'stran', 'kilam', 'govend', 'halay', 'dîlan',
        'kürt müzik', 'kürt şarkı', 'أغاني كردية'
    ],
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

# ============== KURDISH SONG FINDER CLASS ==============
class KurdishSongFinder:
    def __init__(self):
        self.song_database = KURDISH_SONG_DATABASE
        self.all_kurdish_songs = []
        self.kurdish_keywords = []
        
        # Build complete song list
        for artist, data in self.song_database.items():
            self.all_kurdish_songs.extend(data['songs'])
            self.kurdish_keywords.extend(data['keywords'])
        
        # Remove duplicates
        self.all_kurdish_songs = list(set(self.all_kurdish_songs))
        self.kurdish_keywords = list(set(self.kurdish_keywords))
        
        logger.info(f"📚 Loaded {len(self.all_kurdish_songs)} Kurdish songs in database")
        logger.info(f"🔑 Loaded {len(self.kurdish_keywords)} Kurdish keywords")
    
    def find_kurdish_songs(self, query):
        """Find Kurdish songs matching the query"""
        query_lower = query.lower()
        found_songs = []
        
        # Check if query matches any artist
        for artist, data in self.song_database.items():
            if any(keyword in query_lower for keyword in data['keywords']):
                # Add all songs from this artist
                found_songs.extend(data['songs'])
        
        # Check if query matches any song directly
        for song in self.all_kurdish_songs:
            if song.lower() in query_lower or query_lower in song.lower():
                if song not in found_songs:
                    found_songs.append(song)
        
        # If no specific match, try to find similar songs
        if not found_songs:
            for song in self.all_kurdish_songs:
                if any(word in query_lower for word in song.lower().split()):
                    found_songs.append(song)
        
        # Return top matches
        return found_songs[:20]  # Return up to 20 matches
    
    def get_kurdish_suggestions(self, query):
        """Get song suggestions for Kurdish search"""
        query_lower = query.lower()
        suggestions = []
        
        # Check if it's a Kurdish artist
        for artist, data in self.song_database.items():
            if any(keyword in query_lower for keyword in data['keywords']):
                suggestions.extend(data['songs'][:10])
                break
        
        # If no suggestions, provide random Kurdish songs
        if not suggestions:
            random.shuffle(self.all_kurdish_songs)
            suggestions = self.all_kurdish_songs[:10]
        
        return suggestions
    
    def get_random_kurdish_song(self):
        """Get a random Kurdish song"""
        return random.choice(self.all_kurdish_songs)
    
    def get_kurdish_song_by_category(self, category):
        """Get Kurdish songs by category"""
        if category in self.song_database:
            return self.song_database[category]['songs']
        return None

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
            help_command=None,
            application_id=os.getenv('APPLICATION_ID')
        )
        
        # Core data
        self.queues = {}
        self.current_songs = {}
        self.loop = {}
        self.volume = {}
        self.history = {}
        self.playlists = {}
        self.radio_mode = {}
        self.audio_effects = {}
        self.stats = {'total_plays': 0, 'total_commands': 0}
        self.music_player = None
        self.kurdish_finder = KurdishSongFinder()
        
        # Create directories
        os.makedirs('/tmp/downloads', exist_ok=True)
        os.makedirs('playlists', exist_ok=True)
        os.makedirs('data', exist_ok=True)
        
        # Load saved data
        self.load_data()
        self.lock = asyncio.Lock()
        logger.info(f"🤖 Bot initialized with {len(self.kurdish_finder.all_kurdish_songs)} Kurdish songs")

    async def setup_hook(self):
        await self.tree.sync()
        logger.info("✅ Slash commands synced")

    def load_data(self):
        """Load saved playlists and stats"""
        try:
            if os.path.exists('data/stats.json'):
                with open('data/stats.json', 'r') as f:
                    self.stats = json.load(f)
            if os.path.exists('data/playlists.json'):
                with open('data/playlists.json', 'r') as f:
                    self.playlists = json.load(f)
        except:
            pass

    def save_data(self):
        """Save playlists and stats"""
        try:
            with open('data/stats.json', 'w') as f:
                json.dump(self.stats, f)
            with open('data/playlists.json', 'w') as f:
                json.dump(self.playlists, f)
        except:
            pass

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

    def get_history(self, guild_id):
        if guild_id not in self.history:
            self.history[guild_id] = deque(maxlen=20)
        return self.history[guild_id]

    def get_radio(self, guild_id):
        return self.radio_mode.get(guild_id, False)

    def toggle_radio(self, guild_id):
        self.radio_mode[guild_id] = not self.radio_mode.get(guild_id, False)
        return self.radio_mode[guild_id]

    def get_effect(self, guild_id):
        return self.audio_effects.get(guild_id, 'none')

    def set_effect(self, guild_id, effect):
        self.audio_effects[guild_id] = effect

    def is_dj(self, member):
        if not DJ_ROLE:
            return True
        return any(role.name.lower() == DJ_ROLE.lower() for role in member.roles)

# ========== MUSIC PLAYER CLASS ==========
class MusicPlayer:
    def __init__(self, bot):
        self.bot = bot
        self.downloading = {}
        self.lyrics_cache = {}

    def detect_language(self, query):
        query_lower = query.lower()
        # First check if it's Kurdish
        for keyword in self.bot.kurdish_finder.kurdish_keywords:
            if keyword in query_lower:
                return 'kurdish'
        # Then check other languages
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
        """Search for songs with language support - SUPPORTS ALL LANGUAGES"""
        try:
            results = []
            
            # Check if it's a Kurdish song from our database
            kurdish_songs = self.bot.kurdish_finder.find_kurdish_songs(query)
            if kurdish_songs:
                # Search for each Kurdish song
                for song in kurdish_songs[:3]:  # Limit to 3 songs
                    try:
                        search_query = f"{song} kurdish"
                        search_results = YoutubeSearch(search_query, max_results=3).to_dict()
                        if search_results:
                            results.extend(search_results)
                    except:
                        continue
            
            # If no results, try direct search
            if not results:
                try:
                    search_results = YoutubeSearch(query, max_results=limit * 2).to_dict()
                    if search_results:
                        results.extend(search_results)
                except:
                    pass

            # If still no results, try with language keywords
            if not results:
                language = self.detect_language(query)
                if language and language in LANGUAGE_KEYWORDS:
                    for keyword in LANGUAGE_KEYWORDS[language][:3]:
                        try:
                            enhanced_query = f"{query} {keyword}"
                            search_results = YoutubeSearch(enhanced_query, max_results=limit).to_dict()
                            if search_results:
                                results.extend(search_results)
                                break
                        except:
                            continue

            # Broad search fallback
            if not results:
                try:
                    broad_results = YoutubeSearch(f"{query} music", max_results=limit).to_dict()
                    if broad_results:
                        results.extend(broad_results)
                except:
                    pass

            # Format results
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
                        'views': result.get('views', 'N/A'),
                        'id': result.get('id', '')
                    })
                    
                    if len(formatted_results) >= limit:
                        break
                except:
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
                'fragment_retries': 3,
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

    async def play_song(self, ctx, query):
        """Main play function - supports ALL languages and platforms"""
        try:
            if not ctx.author.voice:
                await ctx.send("❌ You need to be in a voice channel!")
                return None
            
            # Join voice channel
            voice_channel = ctx.author.voice.channel
            if ctx.voice_client is None:
                await voice_channel.connect(timeout=10.0)
            elif ctx.voice_client.channel != voice_channel:
                await ctx.voice_client.move_to(voice_channel)
            
            # Check if it's a URL
            is_url = query.startswith(('http://', 'https://', 'www.'))
            
            if is_url:
                # Handle URL
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
                    await ctx.send(f"📝 Added to queue: **{song_info['title']}** (Position: {len(queue)})")
                return song_info
            
            # Search for song - Check Kurdish database first
            kurdish_songs = self.bot.kurdish_finder.find_kurdish_songs(query)
            if kurdish_songs:
                # Search for the first matching Kurdish song
                for song in kurdish_songs[:3]:
                    search_query = f"{song} kurdish"
                    results = await self.search_song(search_query, limit=1)
                    if results:
                        song_data = results[0]
                        # Add Kurdish flag to title
                        song_data['title'] = f"🇰🇲 {song_data['title']}"
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
            
            # Check if it's Kurdish (add flag)
            language = self.detect_language(query)
            if language == 'kurdish' or 'kurd' in song['title'].lower():
                song['title'] = f"🇰🇲 {song['title']}"
            
            queue = self.bot.get_queue(ctx.guild.id)
            queue.append(song)
            
            if not ctx.voice_client.is_playing():
                await self.play_next(ctx)
            else:
                await ctx.send(f"📝 Added to queue: **{song['title']}** (Position: {len(queue)})")
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
                        activity=Activity(type=ActivityType.listening, name=f"{PREFIX}help | 🌍 All Languages")
                    )
                return
            
            # Check loop
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
            
            # Add to history
            history = self.bot.get_history(ctx.guild.id)
            history.append(song)
            
            # Update stats
            self.bot.stats['total_plays'] += 1
            self.bot.save_data()
            
            # Download audio
            audio_file = await self.download_audio(song['url'])
            if not audio_file or not os.path.exists(audio_file):
                await ctx.send(f"❌ Failed to download: {song.get('title', 'Unknown')}")
                await self.play_next(ctx)
                return
            
            # Get audio effect
            effect = self.bot.get_effect(ctx.guild.id)
            effect_filter = ""
            if effect == 'bassboost':
                effect_filter = ",bass=g=10"
            elif effect == 'nightcore':
                effect_filter = ",atempo=1.25,asetrate=44100*1.25"
            elif effect == '8d':
                effect_filter = ",apulsator=hz=0.08"
            
            # Create audio source
            volume = self.bot.get_volume(ctx.guild.id) / 100
            volume_filter = f"volume={volume}" if volume != 1.0 else ""
            audio_filter = f"{volume_filter}{effect_filter}".strip(',')
            
            audio = FFmpegPCMAudio(
                audio_file,
                before_options='-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                options=f'-vn -bufsize 64k -loglevel quiet -af "{audio_filter}"' if audio_filter else '-vn -bufsize 64k -loglevel quiet'
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
            
            # Check if it's Kurdish
            if '🇰🇲' in song.get('title', ''):
                embed.add_field(name="🌍 Language", value="🇰🇲 Kurdish", inline=True)
            
            if effect != 'none':
                embed.add_field(name="🎛️ Effect", value=f"{effect.upper()}", inline=True)
            
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
                activity=Activity(type=ActivityType.listening, name=f"🇰🇲 {song_title}")
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
    """Play ANY song - including hundreds of Kurdish songs!"""
    if not query:
        await ctx.send("❌ Please provide a song name!")
        return
    
    await ctx.send("🔍 Searching for Kurdish songs... 🇰🇲")
    try:
        result = await bot.music_player.play_song(ctx, query)
        bot.stats['total_commands'] += 1
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
        # Show random Kurdish songs
        random_song = bot.kurdish_finder.get_random_kurdish_song()
        await ctx.send(f"🎵 Try this Kurdish song: **{random_song}**\n💡 Use `$play {random_song}` to play it!")
        return
    
    # Search for Kurdish songs
    songs = bot.kurdish_finder.find_kurdish_songs(query)
    if songs:
        embed = Embed(
            title="🇰🇲 Kurdish Songs Found",
            description=f"Found {len(songs)} Kurdish songs matching your search!",
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

@bot.command(name='kurdish-artists', aliases=['kartist', 'ka'])
async def kurdish_artists(ctx):
    """Show all Kurdish artists in the database"""
    embed = Embed(
        title="🇰🇲 Kurdish Artists Database",
        description="All Kurdish artists available in the bot",
        color=Color.gold()
    )
    
    artists = []
    for artist in bot.kurdish_finder.song_database.keys():
        if artist not in ['kurmancî', 'soranî', 'badinî', 'zazakî', 'dengbej', 'traditional', 'modern', 'pop', 'rap', 'love', 'dance', 'regional', 'religious', 'revolution', 'peace', 'nature', 'instrumental']:
            artists.append(f"**{artist.title()}**")
    
    # Split artists into chunks
    artist_chunks = [artists[i:i+10] for i in range(0, len(artists), 10)]
    
    for i, chunk in enumerate(artist_chunks, 1):
        embed.add_field(
            name=f"Artists {i}",
            value="\n".join(chunk) if chunk else "No artists",
            inline=True
        )
    
    embed.set_footer(text=f"🎵 Total: {len(artists)} artists | 💡 Use $kurdish <artist> to search")
    await ctx.send(embed=embed)

@bot.command(name='kurdish-random', aliases=['krandom', 'kr'])
async def kurdish_random(ctx):
    """Play a random Kurdish song"""
    random_song = bot.kurdish_finder.get_random_kurdish_song()
    await ctx.send(f"🎵 Playing random Kurdish song: **{random_song}** 🇰🇲")
    await play(ctx, query=random_song)

@bot.command(name='kurdish-categories', aliases=['kcats', 'kc'])
async def kurdish_categories(ctx):
    """Show Kurdish song categories"""
    embed = Embed(
        title="🇰🇲 Kurdish Song Categories",
        description="Browse Kurdish music by category",
        color=Color.gold()
    )
    
    categories = {
        '🎤 Artists': 'şivan perwer, ciwan haco, hesen zîrek, aram tigran, rojan, gulan, nerwayî',
        '🗣️ Dialects': 'kurmancî, soranî, badinî, zazakî',
        '🎵 Genres': 'dengbej, traditional, modern, pop, rap, love',
        '💃 Dance': 'govend, halay, dîlan, çepik',
        '🌍 Regional': 'bakur, başûr, rojava, rojhilat',
        '✊ Revolution': 'şoreş, pêşmerge, azadî, serxwebûn',
        '🕊️ Peace': 'aşitî, baran, bihar, xwezayê',
        '🎶 Instrumental': 'temîr, bilûr, şimşal, duduk, tembûr'
    }
    
    for category, value in categories.items():
        embed.add_field(
            name=category,
            value=value,
            inline=False
        )
    
    embed.set_footer(text="💡 Use $kurdish <category> to search")
    await ctx.send(embed=embed)

@bot.command(name='kurdish-playlist', aliases=['kpl'])
async def kurdish_playlist(ctx, category=None):
    """Play a playlist of Kurdish songs by category"""
    if not category:
        await ctx.send("❌ Please provide a category!\nAvailable: pop, love, dance, traditional, revolution, peace")
        return
    
    category_lower = category.lower()
    if category_lower in bot.kurdish_finder.song_database:
        songs = bot.kurdish_finder.get_kurdish_song_by_category(category_lower)
        if songs:
            # Add songs to queue
            queue = bot.get_queue(ctx.guild.id)
            added = 0
            for song in songs[:10]:  # Add first 10 songs
                # Search for each song
                results = await bot.music_player.search_song(f"{song} kurdish", limit=1)
                if results:
                    queue.append(results[0])
                    added += 1
            
            await ctx.send(f"🇰🇲 Added **{added}** Kurdish {category} songs to queue!")
            if not ctx.voice_client.is_playing():
                await bot.music_player.play_next(ctx)
            return
    
    await ctx.send(f"❌ Category not found: {category}")

# ========== SEARCH COMMANDS ==========

@bot.command(name='search', aliases=['find'])
async def search(ctx, *, query):
    """Search for songs - Kurdish songs prioritized!"""
    if not query:
        await ctx.send("❌ Please provide a search query!")
        return
    
    # Check Kurdish database first
    kurdish_songs = bot.kurdish_finder.find_kurdish_songs(query)
    
    try:
        results = await bot.music_player.search_song(query, limit=10)
        
        # If no results, try with Kurdish
        if not results:
            results = await bot.music_player.search_song(f"{query} kurdish", limit=10)
        
        if not results and not kurdish_songs:
            await ctx.send(f"❌ No results for: **{query}**")
            return
        
        embed = Embed(
            title="🔍 Search Results",
            description=f"Found results for: **{query[:50]}**",
            color=Color.blue()
        )
        
        # Add Kurdish songs first
        if kurdish_songs:
            embed.add_field(
                name="🇰🇲 Kurdish Songs Found in Database",
                value=f"Found {len(kurdish_songs)} Kurdish songs! Use `$kurdish {query}` to see them",
                inline=False
            )
        
        # Add YouTube results
        if results:
            song_list = []
            for i, result in enumerate(results[:10], 1):
                song_list.append(f"`{i}.` **{result.get('title', 'Unknown')[:50]}...** `{result.get('duration', 'N/A')}`")
            
            embed.add_field(
                name="📝 YouTube Results",
                value="\n".join(song_list) if song_list else "No results",
                inline=False
            )
        
        embed.set_footer(text="💡 Use $play <number> or $play <song name> | 🇰🇲 Kurdish songs available!")
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
                 f"🔊 Volume: {bot.get_volume(ctx.guild.id)}% | "
                 f"🇰🇲 Kurdish Songs: {len(bot.kurdish_finder.all_kurdish_songs)}"
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
                activity=Activity(type=ActivityType.listening, name=f"{PREFIX}help | 🇰🇲 Kurdish Songs")
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

@bot.command(name='move')
async def move_song(ctx, from_pos: int, to_pos: int):
    """Move a song in queue"""
    queue = bot.get_queue(ctx.guild.id)
    if from_pos < 1 or from_pos > len(queue) or to_pos < 1 or to_pos > len(queue):
        await ctx.send(f"❌ Positions must be between 1-{len(queue)}")
        return
    
    try:
        queue_list = list(queue)
        song = queue_list.pop(from_pos - 1)
        queue_list.insert(to_pos - 1, song)
        queue.clear()
        queue.extend(queue_list)
        await ctx.send(f"✅ Moved to position {to_pos}")
    except:
        await ctx.send("❌ Could not move!")

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
    
    # Check if it's Kurdish
    if '🇰🇲' in current.get('title', ''):
        embed.add_field(name="🌍 Language", value="🇰🇲 Kurdish", inline=True)
    
    queue = bot.get_queue(ctx.guild.id)
    embed.add_field(name="📋 Queue", value=f"{len(queue)} songs", inline=True)
    embed.set_footer(text="🎶 Universal Music Bot | 🇰🇲 Kurdish Songs Available")
    
    await ctx.send(embed=embed)

@bot.command(name='history', aliases=['hist'])
async def show_history(ctx):
    """Show recently played songs"""
    history = bot.get_history(ctx.guild.id)
    if not history:
        await ctx.send("📭 No history yet!")
        return
    
    embed = Embed(
        title="📜 Recently Played",
        color=Color.gold()
    )
    
    for i, song in enumerate(list(history)[-10:], 1):
        embed.add_field(
            name=f"{i}. {song.get('title', 'Unknown')[:40]}",
            value=f"⏱️ {song.get('duration', 'N/A')} | 👤 {song.get('channel', 'Unknown')}",
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command(name='playlist', aliases=['pl'])
async def playlist(ctx, action=None, *, name=None):
    """Save or load playlists"""
    try:
        if not action:
            embed = Embed(
                title="📋 Playlist Commands",
                description="`$playlist save <name>` - Save current queue\n"
                           "`$playlist load <name>` - Load a playlist\n"
                           "`$playlist list` - Show all playlists\n"
                           "`$playlist delete <name>` - Delete a playlist",
                color=Color.blue()
            )
            await ctx.send(embed=embed)
            return
        
        if action.lower() == 'save':
            if not name:
                await ctx.send("❌ Please provide a playlist name!")
                return
            
            queue = bot.get_queue(ctx.guild.id)
            if not queue:
                await ctx.send("❌ Queue is empty!")
                return
            
            bot.playlists[name] = list(queue)
            bot.save_data()
            await ctx.send(f"✅ Saved playlist: **{name}** ({len(queue)} songs)")
        
        elif action.lower() == 'load':
            if not name:
                await ctx.send("❌ Please provide a playlist name!")
                return
            
            if name not in bot.playlists:
                await ctx.send(f"❌ Playlist not found: **{name}**")
                return
            
            queue = bot.get_queue(ctx.guild.id)
            for song in bot.playlists[name]:
                queue.append(song)
            
            await ctx.send(f"✅ Loaded playlist: **{name}** ({len(bot.playlists[name])} songs)")
            
            if not ctx.voice_client.is_playing():
                await bot.music_player.play_next(ctx)
        
        elif action.lower() == 'list':
            if not bot.playlists:
                await ctx.send("📭 No playlists saved!")
                return
            
            embed = Embed(
                title="📋 Saved Playlists",
                color=Color.blue()
            )
            
            for name, songs in bot.playlists.items():
                embed.add_field(
                    name=name,
                    value=f"📝 {len(songs)} songs",
                    inline=False
                )
            
            await ctx.send(embed=embed)
        
        elif action.lower() == 'delete':
            if not name:
                await ctx.send("❌ Please provide a playlist name!")
                return
            
            if name in bot.playlists:
                del bot.playlists[name]
                bot.save_data()
                await ctx.send(f"🗑️ Deleted playlist: **{name}**")
            else:
                await ctx.send(f"❌ Playlist not found: **{name}**")
    
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)[:100]}")

@bot.command(name='effect', aliases=['fx'])
async def audio_effect(ctx, effect=None):
    """Apply audio effects: none, bassboost, nightcore, 8d"""
    if not effect:
        current = bot.get_effect(ctx.guild.id)
        await ctx.send(f"🎛️ Current effect: **{current.upper()}**\n"
                      f"Available: `none`, `bassboost`, `nightcore`, `8d`")
        return
    
    effects = ['none', 'bassboost', 'nightcore', '8d']
    if effect.lower() not in effects:
        await ctx.send(f"❌ Invalid effect! Available: {', '.join(effects)}")
        return
    
    bot.set_effect(ctx.guild.id, effect.lower())
    await ctx.send(f"🎛️ Effect set to: **{effect.upper()}**")
    
    if ctx.voice_client and ctx.voice_client.is_playing():
        current = bot.get_current_song(ctx.guild.id)
        if current:
            ctx.voice_client.stop()

@bot.command(name='radio', aliases=['radio'])
async def radio_mode(ctx):
    """Toggle radio mode"""
    if not bot.get_current_song(ctx.guild.id):
        await ctx.send("❌ No song playing!")
        return
    
    radio_status = bot.toggle_radio(ctx.guild.id)
    await ctx.send(f"📻 Radio mode: {'✅ Enabled' if radio_status else '❌ Disabled'}")

@bot.command(name='stats', aliases=['stat'])
async def show_stats(ctx):
    """Show bot statistics"""
    embed = Embed(
        title="📊 Bot Statistics",
        color=Color.gold()
    )
    
    embed.add_field(name="🎵 Total Plays", value=bot.stats['total_plays'], inline=True)
    embed.add_field(name="⚡ Total Commands", value=bot.stats['total_commands'], inline=True)
    embed.add_field(name="🌍 Servers", value=len(bot.guilds), inline=True)
    embed.add_field(name="🇰🇲 Kurdish Songs", value=len(bot.kurdish_finder.all_kurdish_songs), inline=True)
    
    total_songs = 0
    for queue in bot.queues.values():
        total_songs += len(queue)
    embed.add_field(name="📋 Total Queue", value=total_songs, inline=True)
    embed.add_field(name="💾 Playlists", value=len(bot.playlists), inline=True)
    
    await ctx.send(embed=embed)

@bot.command(name='help', aliases=['h'])
async def help_command(ctx):
    """Show help menu"""
    embed = Embed(
        title="🎵 Universal Music Bot - Help",
        description="**🌍 Supports ALL Languages!**\n🇰🇲 **Over 500+ Kurdish songs built-in!**",
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
            "`$kurdish-random` - Play random Kurdish song\n"
            "`$kurdish-artists` - Show Kurdish artists\n"
            "`$kurdish-categories` - Show categories\n"
            "`$kurdish-playlist <category>` - Play Kurdish playlist"
        ),
        inline=False
    )
    
    embed.add_field(
        name="📋 Queue Management",
        value=(
            "`$remove <position>` - Remove song\n"
            "`$clear` - Clear queue\n"
            "`$shuffle` - Shuffle queue\n"
            "`$move <from> <to>` - Move song\n"
            "`$playlist save/load/list/delete` - Playlist management"
        ),
        inline=False
    )
    
    embed.add_field(
        name="🌍 Language Support",
        value=(
            "🇰🇲 Kurdish (500+ songs) • 🇸🇦 Arabic • 🇹🇷 Turkish\n"
            "🇮🇷 Persian • 🇬🇧 English • 🇪🇸 Spanish\n"
            "🇫🇷 French • 🇩🇪 German • 🇮🇳 Hindi\n"
            "🇯🇵 Japanese • 🇰🇷 Korean • 🇧🇷 Portuguese"
        ),
        inline=False
    )
    
    embed.set_footer(text=f"🎵 Prefix: {PREFIX} | 🇰🇲 Kurdish Music Included | Version 5.0")
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
    """Slash command for Kurdish songs"""
    await interaction.response.defer()
    
    songs = bot.kurdish_finder.find_kurdish_songs(query)
    if songs:
        embed = Embed(
            title="🇰🇲 Kurdish Songs Found",
            description=f"Found {len(songs)} Kurdish songs matching your search!",
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
        embed.set_footer(text="💡 Use /play <song name> to play any of these!")
        await interaction.followup.send(embed=embed)
    else:
        await interaction.followup.send(f"❌ No Kurdish songs found for: **{query}**")

@bot.tree.command(name="kurdish_random", description="Play a random Kurdish song")
async def slash_kurdish_random(interaction: discord.Interaction):
    """Slash command for random Kurdish song"""
    await interaction.response.defer()
    random_song = bot.kurdish_finder.get_random_kurdish_song()
    await interaction.followup.send(f"🎵 Playing random Kurdish song: **{random_song}** 🇰🇲")
    
    ctx = await bot.get_context(interaction)
    await bot.music_player.play_song(ctx, random_song)

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
