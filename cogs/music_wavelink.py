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
        player = payload.player
        track = payload.track

        # Store track start time for elapsed tracking
        player.track_start_time = time.time()

        # Create embed for now playing
        embed = self._create_now_playing_embed(track, player)
        view = self._create_controls(player)

        # Get the channel to send message to
        channel = getattr(player, 'text_channel', None)
        if channel:
            message = await channel.send(embed=embed, view=view)
            player.current_message = message

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        """Handle track end event"""
        player = payload.player

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
        if not player.queue.is_empty and payload.reason != 'stopped':
            next_track = player.queue.get()
            await player.play(next_track)
        elif player.queue.is_empty and payload.reason == 'finished':
            # Auto-disconnect when queue is empty
            await player.disconnect()

    def _create_now_playing_embed(self, track: wavelink.Playable, player: wavelink.Player, show_progress: bool = False) -> discord.Embed:
        """Create now playing embed with optional progress tracking"""
        embed = discord.Embed(title="🎵 Now Playing", color=0x00FF00)

        # Track info
        embed.add_field(
            name="Title",
            value=f"[{track.title}]({track.uri})",
            inline=False
        )

        # Duration
        if track.duration:
            duration_str = self._format_duration(track.duration)
            embed.add_field(name="Duration", value=duration_str, inline=True)

        # Loop status
        loop_mode = getattr(player, 'loop_mode', False)
        embed.add_field(name="Loop", value="On" if loop_mode else "Off", inline=True)

        # Show elapsed and remaining time if requested
        if show_progress and track.duration:
            elapsed_ms = self._get_elapsed_time(player)
            if elapsed_ms > 0:
                elapsed_str = self._format_duration(elapsed_ms)
                remaining_ms = max(0, track.duration - elapsed_ms)
                remaining_str = self._format_duration(remaining_ms)
                embed.add_field(name="Elapsed", value=elapsed_str, inline=True)
                embed.add_field(name="Remaining", value=remaining_str, inline=True)

        # Thumbnail
        if track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)

        # Requester info
        requester = getattr(player, 'last_requester', getattr(track, 'requester', None))
        if requester:
            requester_name = requester.display_name if hasattr(requester, 'display_name') else str(requester)
            embed.set_footer(text=f"Requested by {requester_name}")

        return embed

    def _create_controls(self, player: wavelink.Player) -> View:
        """Create control buttons"""
        view = View(timeout=None)

        async def control_callback(interaction: discord.Interaction, action: str):
            """Unified control callback"""
            if not player.connected:
                return await interaction.response.send_message("Not connected to voice.", ephemeral=True)

            try:
                if action == 'pause':
                    if player.paused:
                        await player.resume()
                        await interaction.response.send_message("Resumed playback.", ephemeral=True)
                    else:
                        await player.pause()
                        await interaction.response.send_message("Paused playback.", ephemeral=True)

                    await self._update_embed(player)

                elif action == 'skip':
                    await player.skip()
                    await interaction.response.send_message(f"{interaction.user.name} skipped", ephemeral=True)

                elif action == 'loop':
                    loop_mode = getattr(player, 'loop_mode', False)
                    player.loop_mode = not loop_mode
                    status = 'on' if player.loop_mode else 'off'
                    await interaction.response.send_message(f"Loop {status}", ephemeral=True)
                    await self._update_embed(player)

                elif action in ('fwd', 'back'):
                    seconds = 10 if action == 'fwd' else -10
                    await self.seek_player(player, seconds)
                    await interaction.response.defer()

                elif action == 'lyrics':
                    await self.get_lyrics(interaction, player)

            except Exception as e:
                logger.error(f"Control action {action} failed: {e}")
                if not interaction.response.is_done():
                    await interaction.response.send_message("Action failed.", ephemeral=True)

        # Create buttons
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
            button.callback = lambda i, a=action: control_callback(i, a)
            view.add_item(button)

        return view

    async def _update_embed(self, player: wavelink.Player):
        """Update the now playing embed with current progress"""
        if not hasattr(player, 'current_message') or not player.current_track:
            return

        try:
            embed = self._create_now_playing_embed(player.current_track, player, show_progress=True)
            await player.current_message.edit(embed=embed)
        except Exception as e:
            logger.error(f"Failed to update embed: {e}")

    def _get_elapsed_time(self, player: wavelink.Player) -> int:
        """Get elapsed time in milliseconds for current track"""
        if not player.current_track:
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
        if not player.current_track:
            return

        current_pos = player.position
        new_pos = max(0, min(current_pos + (seconds * 1000), player.current_track.duration))

        await player.seek(new_pos)

        time_display = self._format_duration(new_pos)
        
        # Send feedback message to text channel
        text_channel = getattr(player, 'text_channel', None)
        if text_channel:
            try:
                await text_channel.send(f"Seeked to {time_display}.")
            except:
                pass

    def _get_search_query(self, search: str) -> str:
        """Process search query with YouTube-specific prefixes"""
        if search.startswith(('http://', 'https://')):
            return search
        
        if not any(search.startswith(prefix) for prefix in ['ytsearch:', 'ytmsearch:', 'scsearch:', 'spsearch:']):
            return f'ytsearch:{search}'
        
        return search

    @commands.command()
    async def play(self, ctx: commands.Context, *, search: str):
        """Play music from YouTube or other sources"""
        if not ctx.author.voice:
            return await ctx.send("Join a voice channel first.")

        # Get or create player
        player = ctx.voice_client
        if not player:
            try:
                player = await ctx.author.voice.channel.connect(cls=wavelink.Player)
            except Exception as e:
                logger.error(f"Failed to connect to voice: {e}")
                return await ctx.send("Failed to connect to voice channel.")

        # Store text channel for messages
        player.text_channel = ctx.channel

        # Move to user's channel if different
        if player.channel != ctx.author.voice.channel:
            await player.move_to(ctx.author.voice.channel)

        # Process search query with YouTube prefix
        search_query = self._get_search_query(search)
        
        # Search for tracks
        tracks = await wavelink.Playable.search(search_query)
        if not tracks:
            return await ctx.send("No results found.")

        # Handle single track or playlist
        if isinstance(tracks, wavelink.Playlist):
            # Add all tracks from playlist
            for track in tracks:
                track.requester = ctx.author
                player.queue.put(track)

            await ctx.send(f"Queued playlist: {tracks.name} ({len(tracks)} tracks)")
        else:
            # Single track
            track = tracks[0]
            track.requester = ctx.author

            if player.playing:
                player.queue.put(track)
                position = player.queue.count + 1
                await ctx.reply(f"Queued #{position}: {track.title}")
            else:
                await player.play(track)
                player.last_requester = ctx.author

    @commands.command()
    async def queue(self, ctx: commands.Context):
        """Display current queue"""
        player = ctx.voice_client
        if not player or player.queue.is_empty:
            return await ctx.reply("Queue is empty")

        embed = discord.Embed(title="🎶 Queue", color=0x0000FF)

        # Show up to 10 tracks
        queue_list = list(player.queue)
        for i, track in enumerate(queue_list[:10], 1):
            duration_str = self._format_duration(track.duration) if track.duration else "..."
            embed.add_field(
                name=f"{i}. {track.title}",
                value=duration_str,
                inline=False
            )

        if len(queue_list) > 10:
            embed.add_field(
                name=f"... and {len(queue_list) - 10} more",
                value="",
                inline=False
            )

        await ctx.reply(embed=embed)

    @commands.command(aliases=["nowplaying"])
    async def np(self, ctx: commands.Context):
        """Show currently playing track with progress"""
        player = ctx.voice_client
        if not player or not player.current_track:
            return await ctx.send("Nothing playing")

        # Show embed with progress tracking
        embed = self._create_now_playing_embed(player.current_track, player, show_progress=True)
        view = self._create_controls(player)
        await ctx.send(embed=embed, view=view)

    @commands.command()
    async def ytplay(self, ctx: commands.Context, *, search: str):
        """Play music specifically from YouTube"""
        if not search.startswith(('http://', 'https://')):
            search = f'ytsearch:{search}'
        
        # Ensure player has text channel stored
        if ctx.voice_client:
            ctx.voice_client.text_channel = ctx.channel
        
        await self.play(ctx, search=search)

    @commands.command()
    async def ytmusic(self, ctx: commands.Context, *, search: str):
        """Play music from YouTube Music"""
        if not search.startswith(('http://', 'https://')):
            search = f'ytmsearch:{search}'
        
        # Ensure player has text channel stored
        if ctx.voice_client:
            ctx.voice_client.text_channel = ctx.channel
        
        await self.play(ctx, search=search)

    @commands.command()
    async def pause(self, ctx: commands.Context):
        """Pause or resume the current track"""
        player = ctx.voice_client
        if not player:
            return await ctx.send("Not connected to voice.")
        
        # Ensure text channel is set
        player.text_channel = ctx.channel
        
        if player.paused:
            await player.resume()
            await ctx.send("Resumed playback.")
            await self._update_embed(player)
        else:
            await player.pause()
            await ctx.send("Paused playback.")
            await self._update_embed(player)

    @commands.command()
    async def skip(self, ctx: commands.Context):
        """Skip the current track"""
        player = ctx.voice_client
        if not player:
            return await ctx.send("Not connected to voice.")
        
        if player.current_track:
            await player.skip(force=True)
            await ctx.send(f"{ctx.author.name} skipped")
        else:
            await ctx.send("Nothing to skip.")

    @commands.command(name='stopmusic', aliases=['musicstop'])
    async def stop_music(self, ctx: commands.Context):
        """Stop playback and clear the queue"""
        player = ctx.voice_client
        if not player:
            return await ctx.send("Not connected to voice.")
        
        player.queue.clear()
        await player.stop()
        await ctx.send("Stopped playback and cleared queue.")

    @commands.command()
    async def volume(self, ctx: commands.Context, level: int):
        """Set playback volume (0-100)"""
        player = ctx.voice_client
        if not player:
            return await ctx.send("Not connected to voice.")
        
        if not 0 <= level <= 100:
            return await ctx.send("Volume must be between 0 and 100.")
        
        await player.set_volume(level)
        await ctx.send(f"Volume set to {level}%.")

    @commands.command()
    async def disconnect(self, ctx: commands.Context):
        """Disconnect the bot from voice"""
        player = ctx.voice_client
        if not player:
            return await ctx.send("Not connected to voice.")
        
        await player.disconnect()
        await ctx.send("Disconnected from voice channel.")

    @commands.command()
    async def loop(self, ctx: commands.Context):
        """Toggle loop mode for current track"""
        player = ctx.voice_client
        if not player:
            return await ctx.send("Not connected to voice.")
        
        loop_mode = getattr(player, 'loop_mode', False)
        player.loop_mode = not loop_mode
        status = 'enabled' if player.loop_mode else 'disabled'
        await ctx.send(f"Loop {status}.")

    @commands.command()
    async def clear(self, ctx: commands.Context):
        """Clear the queue"""
        player = ctx.voice_client
        if not player:
            return await ctx.send("Not connected to voice.")
        
        player.queue.clear()
        await ctx.send("Queue cleared.")

    @commands.command()
    async def shuffle(self, ctx: commands.Context):
        """Shuffle the queue"""
        player = ctx.voice_client
        if not player or player.queue.is_empty:
            return await ctx.send("Queue is empty.")
        
        player.queue.shuffle()
        await ctx.send("Queue shuffled.")

    @commands.command()
    async def remove(self, ctx: commands.Context, index: int):
        """Remove a track from the queue by position"""
        player = ctx.voice_client
        if not player or player.queue.is_empty:
            return await ctx.send("Queue is empty.")
        
        if index < 1 or index > player.queue.count:
            return await ctx.send(f"Invalid position. Queue has {player.queue.count} tracks.")
        
        queue_list = list(player.queue)
        removed_track = queue_list[index - 1]
        
        player.queue.clear()
        for i, track in enumerate(queue_list):
            if i != index - 1:
                player.queue.put(track)
        
        await ctx.send(f"Removed: {removed_track.title}")

    @commands.command()
    async def seek(self, ctx: commands.Context, seconds: int):
        """Seek forward or backward by specified seconds"""
        player = ctx.voice_client
        if not player or not player.current_track:
            return await ctx.send("Nothing is playing to seek.")
        
        await self.seek_player(player, seconds)

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

    async def get_lyrics(self, interaction: discord.Interaction, player: wavelink.Player):
        """Fetch lyrics for current track"""
        if not player.current_track:
            return await interaction.response.send_message("No song is currently playing.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        track_title = player.current_track.title
        logger.info(f"Fetching lyrics for: '{track_title}'")

        # Parse artist and title
        artist, title = self._parse_artist_title(track_title)
        logger.info(f"Parsed artist: '{artist}', title: '{title}'")

        async def try_lyrics_request(try_artist: str, try_title: str, attempt_name: str) -> bool:
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
                                return True
                        except Exception as json_error:
                            logger.error(f"{attempt_name} - Failed to parse JSON response: {json_error}")
                    elif response.status == 404:
                        logger.info(f"{attempt_name} - Lyrics not found (404) for '{try_artist} - {try_title}'")

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
            logger.warning(f"All lyrics attempts failed for '{track_title}'")
            await interaction.followup.send(
                f"No lyrics found for this song. The lyrics database may not have this track, or it might be too new. Try searching for the official lyrics online.",
                ephemeral=True
            )

        except Exception as e:
            logger.error(f"Lyrics fetch failed for '{artist} - {title}': {e}")
            await interaction.followup.send("Failed to fetch lyrics. Please try again later.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(MusicWavelinkCog(bot))
