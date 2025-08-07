import asyncio
import re
from collections import deque
import aiohttp
import yt_dlp
import discord
from discord.ext import commands
from discord.ui import Button, View
import time
import logging
import lyricsgenius
from functools import partial, lru_cache
import io

# Pre-compiled regex patterns for better performance
YOUTUBE_VIDEO_REGEX = re.compile(r"watch\?v=(\S{11})")
LYRICS_CLEANUP_REGEX = re.compile(r'[\[\(\{].*?[\]\)\}]')
LYRICS_SEPARATOR_REGEX = re.compile(r'[-_]')
LYRICS_WHITESPACE_REGEX = re.compile(r'\s+')
LYRICS_TAGS_REGEX = re.compile(r'\[.*?\]')
LYRICS_NEWLINES_REGEX = re.compile(r'\n{3,}')

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger('MusicBot')

class MusicBotCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queues = {}
        self.now_playing = {}
        self.play_start_time = {}
        self.loop_mode = {}
        self.lock = asyncio.Lock()
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))
        self.genius = lyricsgenius.Genius("m4hOO0xFpuYL4Ch5diTkVSnou8QleEpb8Sd8akHbbiayNTZblrZiv4M7GVE9cW0e", timeout=5)
        
        # Optimized yt_dlp options - single instance, reused
        self.ydl = yt_dlp.YoutubeDL({
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'default_search': 'auto',
            'source_address': '0.0.0.0',
            'extract_flat': False,
            'cachedir': False  # Disable caching to save disk space
        })
        
        # Pre-defined FFmpeg options to avoid recreation
        self.ffmpeg_base_opts = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 
            'options': '-vn'
        }
        
        # Cache for video info to reduce API calls
        self._video_info_cache = {}

    async def cog_unload(self):
        """Cleanup resources on cog unload"""
        await self.session.close()
        # Clear all caches
        self._video_info_cache.clear()

    async def get_video_url(self, search_query):
        """Optimized video URL retrieval with better error handling"""
        try:
            search_url = f"https://www.youtube.com/results?search_query={search_query.replace(' ', '+')}"
            async with self.session.get(search_url) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    match = YOUTUBE_VIDEO_REGEX.search(text)
                    return f"https://www.youtube.com/watch?v={match.group(1)}" if match else None
        except (asyncio.TimeoutError, aiohttp.ClientError):
            logger.warning(f"Failed to search for: {search_query}")
        return None

    async def _extract_info_async(self, url):
        """Async wrapper for yt-dlp info extraction with caching"""
        if url in self._video_info_cache:
            return self._video_info_cache[url]
            
        try:
            info = await asyncio.get_running_loop().run_in_executor(
                None, partial(self.ydl.extract_info, url, download=False)
            )
            info = info.get('entries', [info])[0]
            
            # Cache the result to avoid repeated API calls
            self._video_info_cache[url] = info
            return info
        except Exception as e:
            logger.error(f"Failed to extract info for {url}: {e}")
            return None

    @commands.command()
    async def play(self, ctx, *, search):
        """Optimized play command with better validation"""
        if not ctx.author.voice:
            return await ctx.send("Join a voice channel first.")

        video_url = await self.get_video_url(search)
        if not video_url:
            return await ctx.send("No results found.")

        voice_client = ctx.voice_client or await ctx.author.voice.channel.connect()
        if voice_client.channel != ctx.author.voice.channel:
            await voice_client.move_to(ctx.author.voice.channel)

        guild_id = ctx.guild.id
        if voice_client.is_playing():
            queue = self.queues.setdefault(guild_id, deque())
            queue.append(video_url)
            return await ctx.reply(f"Queued #{len(queue)}")

        await self._play_audio(ctx, video_url, voice_client)

    async def _play_audio(self, ctx, url, voice_client=None):
        """Optimized audio playback with better error handling"""
        guild_id = ctx.guild.id
        info = await self._extract_info_async(url)
        
        if not info:
            return await ctx.send("Failed to extract video information.")
        
        try:
            song_data = {
                'url': info['url'],
                'title': info['title'],
                'webpage_url': url,
                'thumbnail': info.get('thumbnail', ''),
                'duration': info.get('duration', 0),
                'start_time': 0
            }
            self.now_playing[guild_id] = song_data

            embed = self._create_embed(song_data, guild_id, url)
            view = self._create_controls(ctx)
            song_data['message'] = await ctx.send(embed=embed, view=view)

            source = discord.FFmpegPCMAudio(song_data['url'], **self.ffmpeg_base_opts)
            voice_client = voice_client or ctx.voice_client
            voice_client.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(self._play_next(ctx), self.bot.loop))
            self.play_start_time[guild_id] = time.time()
            
        except Exception as e:
            logger.error(f"Playback failed for {url}: {e}")
            await ctx.send("Playback failed.")

    def _create_embed(self, song_data, guild_id, url, elapsed=0):
        """Optimized embed creation with cached calculations"""
        embed = discord.Embed(title="🎵 Now Playing", color=0x00FF00)
        embed.add_field(name="Title", value=f"[{song_data['title']}]({url})", inline=False)
        
        duration_str = self._format_time(song_data['duration'])
        embed.add_field(name="Duration", value=duration_str, inline=True)
        embed.add_field(name="Loop", value="On" if self.loop_mode.get(guild_id, False) else "Off", inline=True)
        
        if elapsed:
            elapsed_str = self._format_time(elapsed)
            remaining_str = self._format_time(song_data['duration'] - elapsed)
            embed.add_field(name="Elapsed", value=elapsed_str, inline=True)
            embed.add_field(name="Remaining", value=remaining_str, inline=True)
        
        if song_data['thumbnail']:
            embed.set_thumbnail(url=song_data['thumbnail'])
        return embed

    def _create_controls(self, ctx):
        """Optimized control creation with single callback handler"""
        view = View(timeout=None)
        guild_id = ctx.guild.id

        async def unified_control_callback(interaction, action):
            """Single callback handler for all control actions"""
            vc = ctx.voice_client
            if not vc:
                return await interaction.response.send_message("Not connected to voice.", ephemeral=True)

            try:
                if action == 'pause':
                    if vc.is_paused():
                        vc.resume()
                        self.play_start_time[guild_id] = time.time() - self.get_current_time(guild_id)
                        await interaction.response.send_message("Resumed playback.", ephemeral=True)
                    else:
                        vc.pause()
                        self.now_playing[guild_id]['start_time'] = self.get_current_time(guild_id)
                        await interaction.response.send_message("Paused playback.", ephemeral=True)
                    await self._update_embed(ctx)
                    
                elif action == 'skip':
                    vc.stop()
                    await interaction.response.send_message(f"{interaction.user.name} skipped")
                    
                elif action == 'loop':
                    self.loop_mode[guild_id] = not self.loop_mode.get(guild_id, False)
                    status = 'on' if self.loop_mode[guild_id] else 'off'
                    await interaction.response.send_message(f"Loop {status}", ephemeral=True)
                    await self._update_embed(ctx)
                    
                elif action in ('fwd', 'back'):
                    await self.seek_relative(ctx, 10 if action == 'fwd' else -10)
                    await interaction.response.defer()
                    
                elif action == 'lyrics':
                    await self.get_lyrics(ctx, interaction)
                    
            except Exception as e:
                logger.error(f"Control action {action} failed: {e}")
                if not interaction.response.is_done():
                    await interaction.response.send_message("Action failed.", ephemeral=True)

        # Create buttons with unified callback
        buttons_config = [
            ("⏪", 'back', discord.ButtonStyle.grey),
            ("⏯️", 'pause', discord.ButtonStyle.blurple),
            ("⏩", 'fwd', discord.ButtonStyle.grey),
            ("⏭️", 'skip', discord.ButtonStyle.grey),
            ("🔁", 'loop', discord.ButtonStyle.grey),
            ("📝", 'lyrics', discord.ButtonStyle.grey)
        ]
        
        for emoji, action, style in buttons_config:
            button = Button(style=style, emoji=emoji)
            button.callback = lambda i, a=action: unified_control_callback(i, a)
            view.add_item(button)
            
        return view

    def get_current_time(self, guild_id):
        """Optimized current time calculation"""
        if guild_id not in self.now_playing:
            return 0
        
        start_time = self.play_start_time.get(guild_id, 0)
        if start_time == 0:
            return 0
            
        elapsed = time.time() - start_time
        current_time = int(elapsed) + self.now_playing[guild_id].get('start_time', 0)
        max_duration = self.now_playing[guild_id].get('duration', 0)
        
        return min(current_time, max_duration)

    async def seek_relative(self, ctx, seconds):
        """Optimized seeking with better error handling"""
        vc = ctx.voice_client
        if not vc or not vc.is_playing():
            return await ctx.send("Nothing is playing to seek.")

        guild_id = ctx.guild.id
        current_time = self.get_current_time(guild_id)
        duration = self.now_playing[guild_id].get('duration', 0)
        new_time = max(0, min(current_time + seconds, duration))

        try:
            vc.pause()
            seek_opts = self.ffmpeg_base_opts.copy()
            time_str = time.strftime("%H:%M:%S", time.gmtime(new_time))
            seek_opts['before_options'] = f'-ss {time_str} {seek_opts["before_options"]}'
            
            source = discord.FFmpegPCMAudio(self.now_playing[guild_id]['url'], **seek_opts)
            vc.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(self._play_next(ctx), self.bot.loop))
            
            self.play_start_time[guild_id] = time.time()
            self.now_playing[guild_id]['start_time'] = new_time
            
            time_display = time.strftime('%H:%M:%S', time.gmtime(new_time))
            await ctx.send(f"Seeked to {time_display}.")
            
        except Exception as e:
            logger.error(f"Seek failed: {e}")
            await ctx.send("Seek failed.")

    async def _play_next(self, ctx):
        """Optimized next track handling"""
        guild_id = ctx.guild.id
        
        # Handle loop mode
        if self.loop_mode.get(guild_id, False) and guild_id in self.now_playing:
            return await self._play_audio(ctx, self.now_playing[guild_id]['webpage_url'])

        # Clean up current song data
        self.now_playing.pop(guild_id, None)
        self.play_start_time.pop(guild_id, None)

        # Play next in queue or disconnect
        queue = self.queues.get(guild_id)
        if queue:
            next_url = queue.popleft()
            await self._play_audio(ctx, next_url)
        elif ctx.voice_client and not ctx.voice_client.is_playing():
            await ctx.voice_client.disconnect()

    async def get_lyrics(self, ctx, interaction):
        """Optimized lyrics fetching with better cleanup"""
        guild_id = ctx.guild.id
        if guild_id not in self.now_playing:
            return await interaction.response.send_message("No song is currently playing.", ephemeral=True)
        
        await interaction.response.defer(ephemeral=True)
        
        song_title = self.now_playing[guild_id]['title']
        
        # Optimized lyrics cleaning using pre-compiled regex
        cleaned_title = LYRICS_CLEANUP_REGEX.sub('', song_title)
        cleaned_title = LYRICS_SEPARATOR_REGEX.sub(' ', cleaned_title)
        cleaned_title = LYRICS_WHITESPACE_REGEX.sub(' ', cleaned_title).strip()
        
        try:
            song = await asyncio.get_running_loop().run_in_executor(
                None, 
                lambda: self.genius.search_song(cleaned_title, get_full_info=False)
            )
            
            if not song or not song.lyrics:
                return await interaction.followup.send("No lyrics found for this song.", ephemeral=True)
            
            # Optimized lyrics cleanup
            lyrics = LYRICS_TAGS_REGEX.sub('', song.lyrics).strip()
            lyrics = LYRICS_NEWLINES_REGEX.sub('\n\n', lyrics)
            
            lyrics_content = f"{song_title} - {song.artist}\n\n{lyrics}"
            lyrics_file = io.BytesIO(lyrics_content.encode('utf-8'))
            
            embed = discord.Embed(
                title="📝 Lyrics",
                description=f"**{song_title}** by **{song.artist}**\n\nLyrics are attached as a text file above!",
                color=0xFF6B35
            )
            
            file = discord.File(lyrics_file, filename=f"{song_title} - {song.artist} - Lyrics.txt")
            await interaction.followup.send(embed=embed, file=file, ephemeral=True)
                
        except Exception as e:
            logger.error(f"Lyrics fetch failed: {e}")
            await interaction.followup.send("Failed to fetch lyrics. Please try again later.", ephemeral=True)

    async def _update_embed(self, ctx):
        """Optimized embed updating"""
        guild_id = ctx.guild.id
        song_info = self.now_playing.get(guild_id)
        
        if not song_info or 'message' not in song_info:
            return

        try:
            elapsed = self.get_current_time(guild_id)
            embed = self._create_embed(song_info, guild_id, song_info['webpage_url'], elapsed)
            await song_info['message'].edit(embed=embed)
        except Exception as e:
            logger.error(f"Failed to update embed: {e}")

    @lru_cache(maxsize=128)
    def _format_time(self, seconds):
        """Cached time formatting for better performance"""
        if not seconds:
            return "00:00"
        
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

    @commands.command()
    async def queue(self, ctx):
        """Optimized queue display with async info extraction"""
        guild_id = ctx.guild.id
        queue = self.queues.get(guild_id)
        
        if not queue:
            return await ctx.send("Queue is empty")

        embed = discord.Embed(title="🎶 Queue", color=0x0000FF)
        
        # Process queue items asynchronously for better performance
        tasks = []
        for i, url in enumerate(queue, 1):
            if i > 10:  # Limit display to first 10 items
                embed.add_field(name=f"... and {len(queue) - 10} more", value="", inline=False)
                break
            tasks.append(self._extract_info_async(url))
        
        try:
            infos = await asyncio.gather(*tasks, return_exceptions=True)
            
            for i, (url, info) in enumerate(zip(list(queue)[:10], infos), 1):
                if isinstance(info, Exception) or not info:
                    title = "Unknown Title"
                    duration = 0
                else:
                    title = info.get('title', 'Unknown Title')
                    duration = info.get('duration', 0)
                
                duration_str = self._format_time(duration)
                embed.add_field(name=f"{i}. {title}", value=duration_str, inline=False)
                
        except Exception as e:
            logger.error(f"Queue display failed: {e}")
            return await ctx.send("Failed to display queue.")
            
        await ctx.send(embed=embed)

    @commands.command(aliases=["nowplaying"])
    async def np(self, ctx):
        """Optimized now playing display"""
        guild_id = ctx.guild.id
        if guild_id not in self.now_playing:
            return await ctx.send("Nothing playing")

        await self._update_embed(ctx)
        song_info = self.now_playing[guild_id]
        message = song_info.get('message')
        
        if message and message.embeds:
            await ctx.send(embed=message.embeds[0], view=self._create_controls(ctx))
        else:
            await ctx.send("Unable to display current song information.")

async def setup(bot):
    await bot.add_cog(MusicBotCog(bot))