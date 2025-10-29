import asyncio
import os
import re
import io
import time
import logging
from typing import Optional, Dict, Any
import aiohttp
import discord
from discord.ext import commands
from discord.ui import Button, View
import wavelink
from functools import lru_cache

# Pre-compiled regex patterns for better performance
LYRICS_CLEANUP_REGEX = re.compile(r'[\[\(\{].*?[\]\)\}]')
LYRICS_SEPARATOR_REGEX = re.compile(r'[-_]')
LYRICS_WHITESPACE_REGEX = re.compile(r'\s+')
LYRICS_TAGS_REGEX = re.compile(r'\[.*?\]')
LYRICS_NEWLINES_REGEX = re.compile(r'\n{3,}')

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger('WavelinkMusicBot')


class MusicWavelinkCog(commands.Cog):
    """Wavelink-based music cog with YouTube support via lavalink-devs/youtube-source
    
    Features:
    - YouTube search and playback using ytsearch: prefix
    - YouTube Music support using ytmsearch: prefix
    - Direct YouTube URL playback
    - Playlist support
    - Queue management with shuffle, clear, remove
    - Playback controls: pause, skip, stopmusic, loop
    - Volume control
    - Lyrics fetching
    
    Requires:
    - Lavalink server with youtube-plugin.jar
    - Configured application.yml with YouTube clients
    """

    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10))

        # Wavelink setup
        self.bot.loop.create_task(self.connect_nodes())

    async def connect_nodes(self):
        """Connect to Lavalink node"""
        await self.bot.wait_until_ready()

        try:
            # Get Lavalink credentials from environment
            host = os.getenv('LAVALINK_HOST', '127.0.0.1')
            port = int(os.getenv('LAVALINK_PORT', '2333'))
            password = os.getenv('LAVALINK_PASSWORD', 'youshallnotpass')

            node = wavelink.Node(
                uri=f'http://{host}:{port}',
                password=password,
                identifier='JackyBot',
                retries=3
            )

            await wavelink.Pool.connect(client=self.bot, nodes=[node])
            logger.info(f"Connected to Lavalink node at {host}:{port}")

        except Exception as e:
            logger.error(f"Failed to connect to Lavalink: {e}")
            raise

    async def _start_idle_timer(self, player: wavelink.Player):
        """Start idle disconnect timer"""
        # Cancel any existing timer
        await self._cancel_idle_timer(player)

        async def idle_disconnect():
            try:
                await asyncio.sleep(30)  # Wait 30 seconds
                if player.connected and not player.playing and len(player.queue) == 0:
                    await player.disconnect()
                    logger.info("Bot disconnected due to idle timeout")
            except Exception as e:
                logger.error(f"Idle disconnect failed: {e}")

        player.idle_timer = asyncio.create_task(idle_disconnect())

    async def _cancel_idle_timer(self, player: wavelink.Player):
        """Cancel idle disconnect timer if it exists"""
        if hasattr(player, 'idle_timer') and not player.idle_timer.done():
            player.idle_timer.cancel()
            try:
                await player.idle_timer
            except asyncio.CancelledError:
                pass

    async def cog_unload(self):
        """Cleanup resources on cog unload"""
        await self.session.close()


    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        """Handle node ready event"""
        logger.info(f"Wavelink node '{payload.node.identifier}' is ready")

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload):
        """Handle track start event"""
        try:
            player = payload.player
            track = payload.track

            # Cancel idle timer since we're starting playback
            await self._cancel_idle_timer(player)

            # Stop any existing periodic updates
            await self._stop_periodic_updates(player)

            # Store track start time for elapsed tracking
            player.track_start_time = time.time()

            # Get the channel to send message to
            channel = getattr(player, 'text_channel', None)
            if not channel:
                return

            await self._send_now_playing(channel, player)
        except Exception as e:
            logger.error(f"Error in on_wavelink_track_start: {e}", exc_info=True)

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        """Handle track end event"""
        try:
            player = payload.player

            # Stop periodic updates
            await self._stop_periodic_updates(player)

            # Clear current message
            if hasattr(player, 'current_message'):
                try:
                    await player.current_message.delete()
                except:
                    pass
                delattr(player, 'current_message')

            # Check if loop mode is enabled
            loop_mode = getattr(player, 'loop_mode', False)
            if loop_mode and payload.track and payload.reason == 'finished':
                await player.play(payload.track)
                return

            # Auto-play next track if not stopped manually
            if len(player.queue) > 0 and payload.reason != 'stopped':
                next_track = player.queue.get()
                await player.play(next_track)
            elif len(player.queue) == 0 and payload.reason == 'finished':
                # Start idle timer instead of immediate disconnect
                await self._start_idle_timer(player)
        except Exception as e:
            logger.error(f"Error in on_wavelink_track_end: {e}", exc_info=True)

    def _create_now_playing_embed(self, track: wavelink.Playable, player: wavelink.Player, show_progress: bool = False) -> discord.Embed:
        """Create now playing embed with new structure and progress tracking"""
        # Dynamic color based on player state
        if not player.playing:
            color = 0x5865F2  # Blue when idle
        elif getattr(player, 'paused', False):
            color = 0xFEE75C  # Orange when paused
        else:
            color = 0x57F287  # Green when playing

        embed = discord.Embed(title="Now Playing", color=color, timestamp=discord.utils.utcnow())

        # Try to get artist from track attributes first
        artist = getattr(track, 'author', None) or getattr(track, 'artist', None)

        if not artist:
            # Fallback to parsing the title for artist/title separation
            artist, title = self._parse_artist_title(track.title)
        else:
            title = track.title

        # Clean up artist/title if needed
        if not artist or artist in ["", "Various Artists", "Unknown Artist"]:
            artist = "Unknown Artist"
        if not title:
            title = track.title

        # Main description: Artist and title with labels, reduced gap
        embed.description = f"**Artist:** {artist}\n**Title:** {title}"

        # Get duration and elapsed time
        duration_ms = getattr(track, 'duration', None) or getattr(track, 'length', None) or getattr(track, 'duration_ms', None)
        current_ms = self._get_elapsed_time(player) if show_progress else 0

        # Fields
        if duration_ms:
            current_time_str = self._format_duration(current_ms) if current_ms > 0 else "0:00"
            total_time_str = self._format_duration(duration_ms)
            embed.add_field(name="⏰ Duration", value=f"{current_time_str} / {total_time_str}", inline=True)

        # Status field
        status_icon = "⏸️" if getattr(player, 'paused', False) else "▶️"
        status_text = "Paused" if getattr(player, 'paused', False) else "Playing"
        embed.add_field(name="Status", value=f"{status_icon} {status_text}", inline=True)

        # Loop field
        loop_mode = getattr(player, 'loop_mode', False)
        loop_status = "On" if loop_mode else "Off"
        embed.add_field(name="🔁 Loop", value=loop_status, inline=True)


        # Progress bar field
        if show_progress and duration_ms and duration_ms > 0:
            progress_bar = self._create_progress_bar(current_ms, duration_ms)
            embed.add_field(name="Progress", value=progress_bar, inline=False)

        # Thumbnail - try multiple sources for YouTube thumbnails
        thumbnail = getattr(track, 'thumbnail', None) or getattr(track, 'artwork_url', None)

        if not thumbnail:
            # Try to extract YouTube thumbnail from URL
            track_uri = getattr(track, 'uri', None)
            if track_uri and ('youtube.com' in track_uri or 'youtu.be' in track_uri):
                thumbnail = self._get_youtube_thumbnail(track_uri)

        if thumbnail:
            embed.set_image(url=thumbnail)

        # Footer with requester info and avatar
        requester = getattr(player, 'last_requester', getattr(track, 'requester', None))
        if requester:
            requester_name = requester.display_name if hasattr(requester, 'display_name') else str(requester)
            embed.set_footer(text=f"Requested by {requester_name}", icon_url=requester.avatar.url if hasattr(requester, 'avatar') and requester.avatar else None)

        return embed

    def _create_controls(self, player: wavelink.Player) -> View:
        """Create control buttons with new 2-row layout"""
        view = View(timeout=None)

        async def control_callback(interaction: discord.Interaction, action: str):
            """Unified control callback"""
            if not player.connected:
                return await interaction.response.send_message("Not connected to voice.", ephemeral=True)

            try:
                if action == 'pause':
                    if getattr(player, 'paused', False):
                        await player.resume()
                        message = "Resumed playback."
                    else:
                        await player.pause()
                        message = "Paused playback."

                    await interaction.response.send_message(message, ephemeral=True)
                    await self._update_embed(player)

                elif action == 'skip':
                    if not player.current:
                        return await interaction.response.send_message("No song is currently playing.", ephemeral=True)
                    await player.skip()
                    await interaction.response.send_message(f"{interaction.user.name} skipped", ephemeral=True)

                elif action == 'loop':
                    loop_mode = getattr(player, 'loop_mode', False)
                    player.loop_mode = not loop_mode
                    status = 'on' if player.loop_mode else 'off'
                    await interaction.response.send_message(f"Loop {status}", ephemeral=True)
                    await self._update_embed(player)

                elif action in ('fwd', 'back'):
                    if not player.current:
                        return await interaction.response.send_message("No song is currently playing.", ephemeral=True)
                    seconds = 10 if action == 'fwd' else -10
                    logger.info(f"Seeking {seconds} seconds")
                    try:
                        await self.seek_player(player, seconds)
                        await interaction.response.send_message(f"Seeked {seconds:+d} seconds", ephemeral=True)
                        logger.info("Seek successful")
                    except Exception as seek_error:
                        logger.error(f"Seek failed: {seek_error}", exc_info=True)
                        await interaction.response.send_message(f"Seek failed: {seek_error}", ephemeral=True)

                elif action == 'lyrics':
                    await self.get_lyrics(interaction, player)

                elif action == 'spotify':
                    await self.get_spotify_link(interaction, player)

                elif action == 'youtube':
                    await self.get_youtube_link(interaction, player)

                elif action == 'queue':
                    await self.show_queue(interaction, player)

            except Exception as e:
                logger.error(f"Control action {action} failed: {e}")
                if not interaction.response.is_done():
                    await interaction.response.send_message("Action failed.", ephemeral=True)

        # Row 1 - Playback Controls
        row1_buttons = [
            ("⏪", 'back', discord.ButtonStyle.secondary, player.current is not None),  # Seek back -10s
            ("⏯️", 'pause', discord.ButtonStyle.secondary, True),  # Play/Pause
            ("⏩", 'fwd', discord.ButtonStyle.secondary, player.current is not None),   # Seek forward +10s
            ("⏭️", 'skip', discord.ButtonStyle.secondary, True),  # Skip (always enabled)
            ("🔁", 'loop', discord.ButtonStyle.secondary, True),  # Loop
        ]

        # Row 2 - Utility Features
        row2_buttons = [
            ("📜", 'lyrics', discord.ButtonStyle.secondary, True),    # Lyrics (scroll emoji)
            ("💚", 'spotify', discord.ButtonStyle.secondary, True),     # Spotify
            ("❤️", 'youtube', discord.ButtonStyle.secondary, True),     # YouTube
            ("📋", 'queue', discord.ButtonStyle.secondary, True),     # Queue
        ]

        # Add buttons to view
        for emoji, action, style, enabled in row1_buttons + row2_buttons:
            button = Button(style=style, emoji=emoji, disabled=not enabled)
            button.callback = lambda i, a=action: control_callback(i, a)
            view.add_item(button)

        return view

    async def _start_periodic_updates(self, player: wavelink.Player):
        """Start periodic embed updates every 10 seconds"""
        # Cancel any existing update task
        await self._stop_periodic_updates(player)

        async def periodic_update():
            try:
                while player.connected and player.current and hasattr(player, 'current_message'):
                    await asyncio.sleep(10)  # Update every 10 seconds

                    # Only update if player is still active and has a current message
                    if not player.connected or not player.current or not hasattr(player, 'current_message'):
                        break

                    try:
                        embed = self._create_now_playing_embed(player.current, player, show_progress=True)
                        view = self._create_controls(player)  # Recreate controls to update button states
                        await player.current_message.edit(embed=embed, view=view)
                    except Exception as e:
                        logger.error(f"Failed to update embed periodically: {e}")
                        break  # Stop updating if there's an error

            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"Periodic update task failed: {e}")

        player.update_task = asyncio.create_task(periodic_update())

    async def _stop_periodic_updates(self, player: wavelink.Player):
        """Stop periodic embed updates"""
        if hasattr(player, 'update_task') and not player.update_task.done():
            player.update_task.cancel()
            try:
                await player.update_task
            except asyncio.CancelledError:
                pass

    async def _update_embed(self, player: wavelink.Player):
        """Update the now playing embed with current progress"""
        if not hasattr(player, 'current_message') or not player.current:
            return

        try:
            embed = self._create_now_playing_embed(player.current, player, show_progress=True)
            view = self._create_controls(player)  # Recreate controls to update button states
            await player.current_message.edit(embed=embed, view=view)
        except Exception as e:
            logger.error(f"Failed to update embed: {e}")

    async def _send_now_playing(self, ctx_or_channel, player: wavelink.Player):
        """Send now playing embed with controls to context or channel"""
        embed = self._create_now_playing_embed(player.current, player, show_progress=True)
        view = self._create_controls(player)

        # Use reply() if available (for command contexts), otherwise use send() (for channels)
        if hasattr(ctx_or_channel, 'reply'):
            message = await ctx_or_channel.reply(embed=embed, view=view)
        else:
            message = await ctx_or_channel.send(embed=embed, view=view)

        player.current_message = message

        # Start periodic updates
        await self._start_periodic_updates(player)

    def _get_elapsed_time(self, player: wavelink.Player) -> int:
        """Get elapsed time in milliseconds for current track"""
        if not player.current:
            return 0
        
        # Use player.position if available (more accurate)
        if hasattr(player, 'position') and player.position:
            return player.position
        
        # Fallback to calculating from track start time
        track_start_time = getattr(player, 'track_start_time', None)
        if track_start_time:
            elapsed_seconds = time.time() - track_start_time
            return int(elapsed_seconds * 1000)
        
        return 0

    @lru_cache(maxsize=128)
    def _format_duration(self, milliseconds: int) -> str:
        """Format duration from milliseconds"""
        if not milliseconds:
            return "00:00"

        total_seconds = milliseconds // 1000
        m, s = divmod(total_seconds, 60)
        h, m = divmod(m, 60)

        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        else:
            return f"{m:02d}:{s:02d}"

    async def seek_player(self, player: wavelink.Player, seconds: int):
        """Seek the player by relative seconds"""
        if not player.current:
            return

        # Get current position safely
        current_pos = getattr(player, 'position', 0) or 0

        # Get track duration safely
        track_duration = getattr(player.current, 'duration', None) or \
                        getattr(player.current, 'length', None) or \
                        getattr(player.current, 'duration_ms', None)

        if track_duration:
            new_pos = max(0, min(current_pos + (seconds * 1000), track_duration))
        else:
            new_pos = max(0, current_pos + (seconds * 1000))

        await player.seek(new_pos)

    def _get_search_query(self, search: str) -> str:
        """Process search query with YouTube-specific prefixes"""
        if search.startswith(('http://', 'https://')):
            return search

        if not any(search.startswith(prefix) for prefix in ['ytsearch:', 'ytmsearch:', 'scsearch:', 'spsearch:']):
            return f'ytsearch:{search}'

        return search

    async def _ensure_player(self, ctx: commands.Context) -> wavelink.Player:
        """Get or create player and ensure proper setup"""
        if not ctx.author.voice:
            raise commands.CommandError("Join a voice channel first.")

        player = ctx.voice_client
        if not player:
            try:
                player = await ctx.author.voice.channel.connect(cls=wavelink.Player)
            except Exception:
                raise commands.CommandError("Failed to connect to voice channel.")

        # Store text channel for messages
        player.text_channel = ctx.channel

        # Move to user's channel if different
        if player.channel != ctx.author.voice.channel:
            await player.move_to(ctx.author.voice.channel)

        return player

    def _get_player(self, ctx: commands.Context) -> wavelink.Player:
        """Get existing player or raise error"""
        player = ctx.voice_client
        if not player:
            raise commands.CommandError("Not connected to voice.")
        return player

    def _remove_from_queue(self, player: wavelink.Player, index: int) -> wavelink.Playable:
        """Remove track from queue by index (1-based) and return removed track"""
        queue_list = list(player.queue)
        if index < 1 or index > len(queue_list):
            raise ValueError("Invalid index")

        removed_track = queue_list.pop(index - 1)
        player.queue.clear()
        for track in queue_list:
            player.queue.put(track)

        return removed_track

    @commands.command()
    async def play(self, ctx: commands.Context, *, search: str):
        """Play music from YouTube or other sources"""
        try:
            player = await self._ensure_player(ctx)
        except commands.CommandError as e:
            return await ctx.reply(str(e))

        # Cancel idle timer since we're adding tracks
        await self._cancel_idle_timer(player)

        # Process search query with YouTube prefix
        search_query = self._get_search_query(search)

        # Search for tracks
        tracks = await wavelink.Playable.search(search_query)
        if not tracks:
            return await ctx.reply("No results found.")

        # Handle single track or playlist
        if isinstance(tracks, wavelink.Playlist):
            # Add all tracks from playlist
            for track in tracks:
                track.requester = ctx.author
                player.queue.put(track)

            await ctx.reply(f"Queued playlist: {tracks.name} ({len(tracks)} tracks)")
        else:
            # Single track
            track = tracks[0]
            track.requester = ctx.author

            if player.playing:
                player.queue.put(track)
                position = player.queue.count + 1
                await ctx.reply(f"Queued #{position}: {track.title}")
            else:
                player.last_requester = ctx.author
                await player.play(track)


    @commands.command()
    async def skip(self, ctx: commands.Context):
        """Skip the current track"""
        try:
            player = self._get_player(ctx)
            player.text_channel = ctx.channel
        except commands.CommandError as e:
            return await ctx.send(str(e))

        if not player.current:
            return await ctx.send("Nothing to skip.")

        await player.skip(force=True)
        await ctx.send(f"{ctx.author.name} skipped")


    def _parse_artist_title(self, title: str) -> tuple[str, str]:
        """Parse artist and title from track title"""
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

        # If no separator found, assume the whole thing is the title
        return "", cleaned

    def _get_youtube_thumbnail(self, url: str) -> Optional[str]:
        """Extract YouTube video ID and return high-quality thumbnail URL"""
        import re

        # YouTube URL patterns
        patterns = [
            r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})',  # Standard and short URLs
            r'youtube\.com\/embed\/([a-zA-Z0-9_-]{11})',  # Embed URLs
            r'youtube\.com\/v\/([a-zA-Z0-9_-]{11})'  # Old embed format
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                video_id = match.group(1)
                # Return high-quality thumbnail, fallback to medium quality if needed
                return f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"

        return None

    def _create_progress_bar(self, current_ms: int, total_ms: int, length: int = 20) -> str:
        """Create a Unicode progress bar with percentage"""
        if total_ms <= 0:
            return "░░░░░░░░░░░░░░░░░░░░ 0%"

        progress = min(current_ms / total_ms, 1.0)
        filled = int(progress * length)
        empty = length - filled

        bar = "▓" * filled + "░" * empty
        percentage = int(progress * 100)

        return f"{bar} {percentage}%"

    async def get_youtube_link(self, interaction: discord.Interaction, player: wavelink.Player):
        """Get YouTube link for current track"""
        if not player.current:
            return await interaction.response.send_message("No song is currently playing.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        # Use the same artist/title extraction logic as the embed
        artist = getattr(player.current, 'author', None) or getattr(player.current, 'artist', None)
        track_title = player.current.title

        if not artist:
            # Fallback to parsing the title for artist/title separation
            artist, parsed_title = self._parse_artist_title(track_title)
            title = parsed_title
        else:
            title = track_title

        # Clean up artist/title if needed (same as embed)
        if not artist or artist in ["", "Various Artists", "Unknown Artist"]:
            artist = "Unknown Artist"
        if not title:
            title = track_title

        # Create search query using the exact same values shown in embed
        search_query = f"{artist} {title}"

        # URL encode the search query
        from urllib.parse import quote
        encoded_query = quote(search_query)

        # Create YouTube search URL
        youtube_url = f"https://www.youtube.com/search?q={encoded_query}"

        await interaction.followup.send(f"🔍 **YouTube Search:** {youtube_url}", ephemeral=True)

    async def get_lyrics(self, interaction: discord.Interaction, player: wavelink.Player):
        """Fetch lyrics for current track"""
        if not player.current:
            return await interaction.response.send_message("No song is currently playing.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        track_title = player.current.title

        # Parse artist and title
        artist, title = self._parse_artist_title(track_title)

        async def try_lyrics_request(try_artist: str, try_title: str, attempt_name: str) -> bool:
            """Try to fetch lyrics with given artist/title combination"""
            try:
                from urllib.parse import quote
                encoded_artist = quote(try_artist)
                encoded_title = quote(try_title)
                url = f"https://api.lyrics.ovh/v1/{encoded_artist}/{encoded_title}"

                async with self.session.get(url) as response:
                    if response.status == 200:
                        try:
                            data = await response.json()
                            lyrics = data.get('lyrics', '').strip()

                            if lyrics:
                                # Clean up lyrics (remove extra newlines)
                                lyrics = LYRICS_NEWLINES_REGEX.sub('\n\n', lyrics)

                                lyrics_content = f"{try_artist} - {try_title}\n\n{lyrics}"
                                lyrics_file = io.BytesIO(lyrics_content.encode('utf-8'))

                                embed = discord.Embed(
                                    title="📝 Lyrics",
                                    description=f"**{try_title}** by **{try_artist}**\n\nLyrics are attached as a text file above!",
                                    color=0xFF6B35
                                )

                                file = discord.File(lyrics_file, filename=f"{try_artist} - {try_title} - Lyrics.txt")
                                await interaction.followup.send(embed=embed, file=file, ephemeral=True)
                                return True
                        except Exception as json_error:
                            logger.error(f"Failed to parse lyrics response: {json_error}")
                    elif response.status == 404:
                        pass

                return False

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
                    if await try_lyrics_request(first_artist, title, f"First artist '{first_artist}'"):
                        return

            # Second attempt: try with title as artist (common for well-known songs)
            if await try_lyrics_request(title, title, "Title as artist"):
                return

            # Third attempt: try with common generic artists
            common_artists = ["Various Artists", "Unknown Artist", "Various", "Classic", "Popular"]
            for try_artist in common_artists:
                if await try_lyrics_request(try_artist, title, f"Generic artist '{try_artist}'"):
                    return
            await interaction.followup.send(
                f"No lyrics found for this song. The lyrics database may not have this track, or it might be too new. Try searching for the official lyrics online.",
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Lyrics fetch failed for '{artist} - {title}': {e}")
            await interaction.followup.send("Failed to fetch lyrics. Please try again later.", ephemeral=True)

    async def get_spotify_link(self, interaction: discord.Interaction, player: wavelink.Player):
        """Get Spotify link for current track"""
        if not player.current:
            return await interaction.response.send_message("No song is currently playing.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        # Use the same artist/title extraction logic as the embed
        artist = getattr(player.current, 'author', None) or getattr(player.current, 'artist', None)
        track_title = player.current.title

        if not artist:
            # Fallback to parsing the title for artist/title separation
            artist, parsed_title = self._parse_artist_title(track_title)
            title = parsed_title
        else:
            title = track_title

        # Clean up artist/title if needed (same as embed)
        if not artist or artist in ["", "Various Artists", "Unknown Artist"]:
            artist = "Unknown Artist"
        if not title:
            title = track_title

        # Create search query using the exact same values shown in embed
        search_query = f"{artist} {title}"

        # URL encode the search query
        from urllib.parse import quote
        encoded_query = quote(search_query)

        # Create Spotify search URL
        spotify_url = f"https://open.spotify.com/search/{encoded_query}"

        await interaction.followup.send(f"🔍 **Spotify Search:** {spotify_url}", ephemeral=True)

    async def show_queue(self, interaction: discord.Interaction, player: wavelink.Player):
        """Display the current queue"""
        await interaction.response.defer(ephemeral=True)
        
        if len(player.queue) == 0:
            return await interaction.followup.send("📋 **Queue is empty**", ephemeral=True)
        
        embed = discord.Embed(
            title="📋 Queue",
            color=0x5865F2,
            timestamp=discord.utils.utcnow()
        )
        
        queue_list = list(player.queue)
        total_tracks = len(queue_list)
        
        tracks_per_page = 10
        queue_text = []
        
        for idx, track in enumerate(queue_list[:tracks_per_page], start=1):
            artist = getattr(track, 'author', None) or getattr(track, 'artist', None)
            
            if not artist:
                artist, title = self._parse_artist_title(track.title)
            else:
                title = track.title
            
            if not artist or artist in ["", "Various Artists", "Unknown Artist"]:
                artist = "Unknown Artist"
            if not title:
                title = track.title
            
            duration_ms = getattr(track, 'duration', None) or getattr(track, 'length', None)
            duration_str = self._format_duration(duration_ms) if duration_ms else "?"
            
            queue_text.append(f"**{idx}.** {artist} - {title} `[{duration_str}]`")
        
        embed.description = "\n".join(queue_text)
        
        if total_tracks > tracks_per_page:
            embed.set_footer(text=f"Showing 10 of {total_tracks} tracks")
        else:
            embed.set_footer(text=f"{total_tracks} track{'s' if total_tracks != 1 else ''} in queue")
        
        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(MusicWavelinkCog(bot))
