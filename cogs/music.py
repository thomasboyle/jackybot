import asyncio
import os
import re
from collections import deque
import aiohttp
import yt_dlp
import discord
from discord.ext import commands
from discord.ui import Button, View
import time
import logging
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

    async def _load_queue_info(self, queue_item, video_url):
        """Load video info in the background without blocking playback"""
        try:
            info = await self._extract_info_async(video_url)
            if info:
                # Update the queue item in-place with full info
                queue_item['title'] = info.get('title', 'Unknown Title')
                queue_item['duration'] = info.get('duration', 0)
                queue_item['thumbnail'] = info.get('thumbnail', '')
                queue_item['info_loaded'] = True
                logger.info(f"Loaded queue info for: {queue_item['title']}")
        except Exception as e:
            logger.error(f"Failed to load queue info: {e}")
            # Keep the minimal info if extraction fails
            queue_item['title'] = 'Unknown Title'
            queue_item['info_loaded'] = True

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
            # Queue immediately with minimal info to prevent stuttering
            queue_item = {
                'url': video_url,
                'title': 'Loading...',
                'duration': 0,
                'thumbnail': '',
                'info_loaded': False
            }

            queue = self.queues.setdefault(guild_id, deque())
            queue.append(queue_item)
            queue_position = len(queue)
            
            # Extract video info in the background without blocking
            asyncio.create_task(self._load_queue_info(queue_item, video_url))
            
            return await ctx.reply(f"Queued #{queue_position}")

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
            next_item = queue.popleft()
            next_url = next_item['url'] if isinstance(next_item, dict) else next_item
            await self._play_audio(ctx, next_url)
        elif ctx.voice_client and not ctx.voice_client.is_playing():
            await ctx.voice_client.disconnect()

    def _parse_artist_title(self, title):
        """Parse artist and title from YouTube video title"""
        # Clean up the title first (remove brackets but keep separators)
        cleaned = LYRICS_CLEANUP_REGEX.sub('', title)
        cleaned = LYRICS_WHITESPACE_REGEX.sub(' ', cleaned).strip()

        # Common separators for artist - title
        separators = [' - ', ' – ', ' — ', ' | ', ' : ']

        for sep in separators:
            if sep in cleaned:
                parts = cleaned.split(sep, 1)
                if len(parts) == 2:
                    # Try both orders: "Artist - Title" and "Title - Artist"
                    artist_part = parts[0].strip()
                    title_part = parts[1].strip()

                    # Better heuristics for determining artist vs title:
                    # 1. If first part contains commas (multiple artists), it's likely artist
                    # 2. If first part is under 40 chars and title is under 100, it's likely artist
                    # 3. If title part looks like a song title (shorter, no commas), it's likely title

                    has_commas = ',' in artist_part
                    artist_short = len(artist_part) < 40
                    title_reasonable = len(title_part) < 100

                    if has_commas or (artist_short and title_reasonable):
                        return artist_part, title_part
                    else:
                        # Assume title - artist order
                        return title_part, artist_part

        # If no separator found, assume the whole thing is the title and we'll try multiple approaches
        return "", cleaned

    async def get_lyrics(self, ctx, interaction):
        """Fetch lyrics using LyricsOVH API"""
        guild_id = ctx.guild.id
        if guild_id not in self.now_playing:
            logger.info(f"No song playing in guild {guild_id}")
            return await interaction.response.send_message("No song is currently playing.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        song_title = self.now_playing[guild_id]['title']
        logger.info(f"Fetching lyrics for: '{song_title}' in guild {guild_id}")

        # Parse artist and title from the song title
        artist, title = self._parse_artist_title(song_title)
        logger.info(f"Parsed artist: '{artist}', title: '{title}'")

        # URL encode the artist and title for the API
        from urllib.parse import quote
        encoded_artist = quote(artist)
        encoded_title = quote(title)

        async def try_lyrics_request(try_artist, try_title, attempt_name):
            """Try to fetch lyrics with given artist/title combination"""
            try:
                from urllib.parse import quote
                encoded_artist = quote(try_artist)
                encoded_title = quote(try_title)
                url = f"https://api.lyrics.ovh/v1/{encoded_artist}/{encoded_title}"
                logger.info(f"{attempt_name} - Making API request to: {url}")

                async with self.session.get(url) as response:
                    logger.info(f"{attempt_name} - Lyrics API response status: {response.status}")

                    if response.status == 200:
                        try:
                            data = await response.json()
                            logger.debug(f"{attempt_name} - API response data: {data}")
                            lyrics = data.get('lyrics', '').strip()

                            if lyrics:
                                # Clean up lyrics (remove extra newlines)
                                lyrics = LYRICS_NEWLINES_REGEX.sub('\n\n', lyrics)
                                logger.info(f"Successfully retrieved lyrics for '{try_artist} - {try_title}' ({len(lyrics)} characters)")

                                lyrics_content = f"{try_artist} - {try_title}\n\n{lyrics}"
                                lyrics_file = io.BytesIO(lyrics_content.encode('utf-8'))

                                embed = discord.Embed(
                                    title="📝 Lyrics",
                                    description=f"**{try_title}** by **{try_artist}**\n\nLyrics are attached as a text file above!",
                                    color=0xFF6B35
                                )

                                file = discord.File(lyrics_file, filename=f"{try_artist} - {try_title} - Lyrics.txt")
                                await interaction.followup.send(embed=embed, file=file, ephemeral=True)
                                return True  # Success
                            else:
                                logger.warning(f"{attempt_name} - No lyrics found in API response")
                        except Exception as json_error:
                            logger.error(f"{attempt_name} - Failed to parse JSON response: {json_error}")
                            response_text = await response.text()
                            logger.debug(f"{attempt_name} - Raw response: {response_text[:500]}...")
                    elif response.status == 404:
                        logger.info(f"{attempt_name} - Lyrics not found (404) for '{try_artist} - {try_title}'")
                    else:
                        logger.warning(f"{attempt_name} - Unexpected status {response.status} for '{try_artist} - {try_title}'")

                return False  # Failed

            except Exception as e:
                logger.error(f"{attempt_name} - Request failed for '{try_artist} - {try_title}': {e}")
                return False

        try:
            # First attempt: use parsed artist and title (only if we have an artist)
            if artist and artist not in ["", "Various Artists", "Unknown Artist"]:
                success = await try_lyrics_request(artist, title, "Primary attempt")
                if success:
                    return

                # If primary attempt failed and artist contains commas (multiple artists),
                # try with just the first artist
                if ',' in artist:
                    first_artist = artist.split(',')[0].strip()
                    logger.info(f"Trying with first artist only: {first_artist}")
                    success = await try_lyrics_request(first_artist, title, f"First artist '{first_artist}'")
                    if success:
                        return

            # Second attempt: try with title as artist (common for well-known songs)
            logger.info("Trying with song title as artist")
            success = await try_lyrics_request(title, title, "Title as artist")
            if success:
                return

            # Third attempt: try with common generic artists
            common_artists = ["Various Artists", "Unknown Artist", "Various", "Classic", "Popular"]
            for try_artist in common_artists:
                logger.info(f"Trying with generic artist: {try_artist}")
                success = await try_lyrics_request(try_artist, title, f"Generic artist '{try_artist}'")
                if success:
                    return

            # If all attempts failed, send error message
            logger.warning(f"All lyrics attempts failed for '{song_title}'")
            await interaction.followup.send(
                f"No lyrics found for this song. The lyrics database may not have this track, or it might be too new. Try searching for the official lyrics online.",
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Lyrics fetch failed for '{artist} - {title}': {e}")
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
        """Display queue using cached song information"""
        guild_id = ctx.guild.id
        queue = self.queues.get(guild_id)

        if not queue:
            return await ctx.reply("Queue is empty")

        embed = discord.Embed(title="🎶 Queue", color=0x0000FF)

        # Display queue items using cached info - no API calls needed
        for i, item in enumerate(queue, 1):
            if i > 10:  # Limit display to first 10 items
                embed.add_field(name=f"... and {len(queue) - 10} more", value="", inline=False)
                break

            # Handle both old format (URLs) and new format (dicts) for backwards compatibility
            if isinstance(item, dict):
                title = item.get('title', 'Unknown Title')
                duration = item.get('duration', 0)
                # Show loading status for items that haven't finished loading
                if not item.get('info_loaded', True) and title == 'Loading...':
                    title = '⏳ Loading...'
            else:
                # Fallback for old queue items that are just URLs
                title = "Unknown Title"
                duration = 0

            duration_str = self._format_time(duration) if duration > 0 else "..."
            embed.add_field(name=f"{i}. {title}", value=duration_str, inline=False)

        await ctx.reply(embed=embed)

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