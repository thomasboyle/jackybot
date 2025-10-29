import asyncio
import os
import re
import io
import time
from typing import Optional
import aiohttp
import discord
from discord.ext import commands
from discord.ui import Button, View
import wavelink
from functools import lru_cache

LYRICS_CLEANUP_REGEX = re.compile(r'[\[\(\{].*?[\]\)\}]')
LYRICS_WHITESPACE_REGEX = re.compile(r'\s+')
LYRICS_NEWLINES_REGEX = re.compile(r'\n{3,}')


class MusicWavelinkCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = None
        self.bot.loop.create_task(self.connect_nodes())

    async def connect_nodes(self):
        await self.bot.wait_until_ready()
        
        connector = aiohttp.TCPConnector(
            limit=100,
            limit_per_host=10,
            ttl_dns_cache=300,
            enable_cleanup_closed=True,
            force_close=False
        )
        
        timeout = aiohttp.ClientTimeout(
            total=10,
            connect=3,
            sock_read=5
        )
        
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={'User-Agent': 'JackyBot-MusicPlayer/1.0'}
        )
        
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

    async def _start_idle_timer(self, player: wavelink.Player):
        await self._cancel_idle_timer(player)
        async def idle_disconnect():
            try:
                await asyncio.sleep(30)
                if player.connected and not player.playing and len(player.queue) == 0:
                    await player.disconnect()
            except Exception:
                pass
        player.idle_timer = asyncio.create_task(idle_disconnect())

    async def _cancel_idle_timer(self, player: wavelink.Player):
        if hasattr(player, 'idle_timer') and not player.idle_timer.done():
            player.idle_timer.cancel()
            try:
                await player.idle_timer
            except asyncio.CancelledError:
                pass

    async def cog_unload(self):
        if self.session:
            await self.session.close()


    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        pass

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload):
        try:
            player = payload.player
            await self._cancel_idle_timer(player)
            await self._stop_periodic_updates(player)
            player.track_start_time = time.time()
            channel = getattr(player, 'text_channel', None)
            if channel:
                await self._send_now_playing(channel, player)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        try:
            player = payload.player
            await self._stop_periodic_updates(player)
            if hasattr(player, 'current_message'):
                try:
                    await player.current_message.delete()
                except:
                    pass
                delattr(player, 'current_message')
            if getattr(player, 'loop_mode', False) and payload.track and payload.reason == 'finished':
                await player.play(payload.track)
                return
            if len(player.queue) > 0 and payload.reason not in ('replaced', 'loadFailed'):
                await player.play(player.queue.get())
            elif len(player.queue) == 0 and payload.reason in ('finished', 'stopped'):
                await self._start_idle_timer(player)
        except Exception:
            pass

    def _extract_artist_title(self, track: wavelink.Playable) -> tuple[str, str]:
        artist = getattr(track, 'author', None) or getattr(track, 'artist', None)
        track_title = str(track.title) if track.title else "Unknown Title"
        
        if not artist:
            artist, title = self._parse_artist_title(track_title)
        else:
            title = track_title
            artist = str(artist)
        
        if not artist or artist in ["", "Various Artists", "Unknown Artist"]:
            artist = "Unknown Artist"
        if not title:
            title = track_title
        
        return artist, title

    def _create_now_playing_embed(self, track: wavelink.Playable, player: wavelink.Player, show_progress: bool = False) -> discord.Embed:
        color = 0x5865F2 if not player.playing else (0xFEE75C if getattr(player, 'paused', False) else 0x57F287)
        embed = discord.Embed(title="Now Playing", color=color, timestamp=discord.utils.utcnow())
        
        artist, title = self._extract_artist_title(track)
        embed.description = f"**Artist:** {artist}\n**Title:** {title}"
        
        duration_ms = getattr(track, 'duration', None) or getattr(track, 'length', None) or getattr(track, 'duration_ms', None)
        current_ms = self._get_elapsed_time(player) if show_progress else 0
        
        if duration_ms:
            current_time_str = self._format_duration(current_ms) if current_ms > 0 else "0:00"
            embed.add_field(name="⏰ Duration", value=f"{current_time_str} / {self._format_duration(duration_ms)}", inline=True)
        
        paused = getattr(player, 'paused', False)
        embed.add_field(name="Status", value=f"{'⏸️ Paused' if paused else '▶️ Playing'}", inline=True)
        embed.add_field(name="🔁 Loop", value="On" if getattr(player, 'loop_mode', False) else "Off", inline=True)
        
        if show_progress and duration_ms and duration_ms > 0:
            embed.add_field(name="Progress", value=self._create_progress_bar(current_ms, duration_ms), inline=False)
        
        thumbnail = getattr(track, 'thumbnail', None) or getattr(track, 'artwork_url', None)
        if not thumbnail:
            track_uri = getattr(track, 'uri', None)
            if track_uri and ('youtube.com' in track_uri or 'youtu.be' in track_uri):
                thumbnail = self._get_youtube_thumbnail(track_uri)
        if thumbnail:
            embed.set_image(url=thumbnail)
        
        requester = getattr(player, 'last_requester', getattr(track, 'requester', None))
        if requester:
            requester_name = requester.display_name if hasattr(requester, 'display_name') else str(requester)
            embed.set_footer(text=f"Requested by {requester_name}", icon_url=requester.avatar.url if hasattr(requester, 'avatar') and requester.avatar else None)
        
        return embed

    def _create_controls(self, player: wavelink.Player) -> View:
        view = View(timeout=None)
        
        async def control_callback(interaction: discord.Interaction, action: str):
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
                    player.loop_mode = not getattr(player, 'loop_mode', False)
                    await interaction.response.send_message(f"Loop {'on' if player.loop_mode else 'off'}", ephemeral=True)
                    await self._update_embed(player)
                elif action in ('fwd', 'back'):
                    if not player.current:
                        return await interaction.response.send_message("No song is currently playing.", ephemeral=True)
                    seconds = 10 if action == 'fwd' else -10
                    try:
                        await self.seek_player(player, seconds)
                        await interaction.response.send_message(f"Seeked {seconds:+d} seconds", ephemeral=True)
                    except Exception as e:
                        await interaction.response.send_message(f"Seek failed: {e}", ephemeral=True)
                elif action == 'lyrics':
                    await self.get_lyrics(interaction, player)
                elif action == 'spotify':
                    await self.get_spotify_link(interaction, player)
                elif action == 'youtube':
                    await self.get_youtube_link(interaction, player)
                elif action == 'queue':
                    await self.show_queue(interaction, player)
            except Exception:
                if not interaction.response.is_done():
                    await interaction.response.send_message("Action failed.", ephemeral=True)
        
        buttons = [
            ("⏪", 'back', player.current is not None),
            ("⏯️", 'pause', True),
            ("⏩", 'fwd', player.current is not None),
            ("⏭️", 'skip', True),
            ("🔁", 'loop', True),
            ("📜", 'lyrics', True),
            ("💚", 'spotify', True),
            ("❤️", 'youtube', True),
            ("📋", 'queue', True),
        ]
        
        for emoji, action, enabled in buttons:
            button = Button(style=discord.ButtonStyle.secondary, emoji=emoji, disabled=not enabled)
            button.callback = lambda i, a=action: control_callback(i, a)
            view.add_item(button)
        
        return view

    async def _start_periodic_updates(self, player: wavelink.Player):
        await self._stop_periodic_updates(player)
        
        UPDATE_INTERVAL = 30
        MAX_CONSECUTIVE_ERRORS = 3
        
        async def periodic_update():
            error_count = 0
            try:
                while player.connected and player.current and hasattr(player, 'current_message'):
                    await asyncio.sleep(UPDATE_INTERVAL)
                    
                    if not player.connected or not player.current or not hasattr(player, 'current_message'):
                        break
                    
                    if not getattr(player, 'paused', False):
                        try:
                            embed = self._create_now_playing_embed(player.current, player, show_progress=True)
                            view = self._create_controls(player)
                            await player.current_message.edit(embed=embed, view=view)
                            error_count = 0
                        except discord.NotFound:
                            break
                        except discord.HTTPException as e:
                            error_count += 1
                            if error_count >= MAX_CONSECUTIVE_ERRORS:
                                break
                            if e.status == 429:
                                await asyncio.sleep(60)
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
            finally:
                if hasattr(player, 'update_task'):
                    delattr(player, 'update_task')
        
        player.update_task = asyncio.create_task(periodic_update())

    async def _stop_periodic_updates(self, player: wavelink.Player):
        if hasattr(player, 'update_task') and not player.update_task.done():
            player.update_task.cancel()
            try:
                await player.update_task
            except asyncio.CancelledError:
                pass

    async def _update_embed(self, player: wavelink.Player):
        if hasattr(player, 'current_message') and player.current:
            try:
                embed = self._create_now_playing_embed(player.current, player, show_progress=True)
                view = self._create_controls(player)
                await player.current_message.edit(embed=embed, view=view)
            except Exception:
                pass

    async def _send_now_playing(self, ctx_or_channel, player: wavelink.Player):
        embed = self._create_now_playing_embed(player.current, player, show_progress=True)
        view = self._create_controls(player)
        message = await (ctx_or_channel.reply(embed=embed, view=view) if hasattr(ctx_or_channel, 'reply') else ctx_or_channel.send(embed=embed, view=view))
        player.current_message = message
        await self._start_periodic_updates(player)

    def _get_elapsed_time(self, player: wavelink.Player) -> int:
        if not player.current:
            return 0
        if hasattr(player, 'position') and player.position:
            return player.position
        track_start_time = getattr(player, 'track_start_time', None)
        if track_start_time:
            return int((time.time() - track_start_time) * 1000)
        return 0

    @lru_cache(maxsize=128)
    def _format_duration(self, milliseconds: int) -> str:
        if not milliseconds:
            return "00:00"
        total_seconds = milliseconds // 1000
        m, s = divmod(total_seconds, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"

    async def seek_player(self, player: wavelink.Player, seconds: int):
        if not player.current:
            return
        current_pos = getattr(player, 'position', 0) or 0
        track_duration = getattr(player.current, 'duration', None) or getattr(player.current, 'length', None) or getattr(player.current, 'duration_ms', None)
        new_pos = max(0, min(current_pos + (seconds * 1000), track_duration) if track_duration else current_pos + (seconds * 1000))
        await player.seek(new_pos)

    def _get_search_query(self, search: str) -> str:
        if search.startswith(('http://', 'https://')):
            return search
        if not any(search.startswith(prefix) for prefix in ['ytsearch:', 'ytmsearch:', 'scsearch:', 'spsearch:']):
            return f'ytsearch:{search}'
        return search

    async def _ensure_player(self, ctx: commands.Context) -> wavelink.Player:
        if not ctx.author.voice:
            raise commands.CommandError("Join a voice channel first.")
        player = ctx.voice_client
        if not player:
            try:
                player = await ctx.author.voice.channel.connect(cls=wavelink.Player)
            except Exception:
                raise commands.CommandError("Failed to connect to voice channel.")
        player.text_channel = ctx.channel
        if player.channel != ctx.author.voice.channel:
            await player.move_to(ctx.author.voice.channel)
        return player

    def _get_player(self, ctx: commands.Context) -> wavelink.Player:
        player = ctx.voice_client
        if not player:
            raise commands.CommandError("Not connected to voice.")
        return player

    def _remove_from_queue(self, player: wavelink.Player, index: int) -> wavelink.Playable:
        if index < 1 or index > player.queue.count:
            raise ValueError("Invalid index")
        
        queue_list = list(player.queue)
        removed_track = queue_list[index - 1]
        
        player.queue.clear()
        for i, track in enumerate(queue_list):
            if i != index - 1:
                player.queue.put(track)
        
        return removed_track

    @commands.command()
    async def play(self, ctx: commands.Context, *, search: str):
        try:
            player = await self._ensure_player(ctx)
        except commands.CommandError as e:
            return await ctx.reply(str(e))
        
        await self._cancel_idle_timer(player)
        tracks = await wavelink.Playable.search(self._get_search_query(search))
        if not tracks:
            return await ctx.reply("No results found.")
        
        if isinstance(tracks, wavelink.Playlist):
            for track in tracks:
                track.requester = ctx.author
                player.queue.put(track)
            await ctx.reply(f"Queued playlist: {tracks.name} ({len(tracks)} tracks)")
        else:
            track = tracks[0]
            track.requester = ctx.author
            if player.playing:
                player.queue.put(track)
                await ctx.reply(f"Queued #{player.queue.count + 1}: {track.title or 'Unknown Title'}")
            else:
                player.last_requester = ctx.author
                await player.play(track)

    @commands.command()
    async def skip(self, ctx: commands.Context):
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
        cleaned = LYRICS_WHITESPACE_REGEX.sub(' ', LYRICS_CLEANUP_REGEX.sub('', title)).strip()
        for sep in [' - ', ' – ', ' — ', ' | ', ' : ']:
            if sep in cleaned:
                parts = cleaned.split(sep, 1)
                if len(parts) == 2:
                    artist_part, title_part = parts[0].strip(), parts[1].strip()
                    if ',' in artist_part or (len(artist_part) < 40 and len(title_part) < 100):
                        return artist_part, title_part
                    else:
                        return title_part, artist_part
        return "", cleaned

    def _get_youtube_thumbnail(self, url: str) -> Optional[str]:
        for pattern in [r'(?:youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})', r'youtube\.com\/embed\/([a-zA-Z0-9_-]{11})', r'youtube\.com\/v\/([a-zA-Z0-9_-]{11})']:
            match = re.search(pattern, url)
            if match:
                return f"https://img.youtube.com/vi/{match.group(1)}/maxresdefault.jpg"
        return None

    def _create_progress_bar(self, current_ms: int, total_ms: int, length: int = 20) -> str:
        if total_ms <= 0:
            return "░░░░░░░░░░░░░░░░░░░░ 0%"
        progress = min(current_ms / total_ms, 1.0)
        filled = int(progress * length)
        return f"{'▓' * filled}{'░' * (length - filled)} {int(progress * 100)}%"

    async def get_youtube_link(self, interaction: discord.Interaction, player: wavelink.Player):
        if not player.current:
            return await interaction.response.send_message("No song is currently playing.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        artist, title = self._extract_artist_title(player.current)
        from urllib.parse import quote
        youtube_url = f"https://www.youtube.com/search?q={quote(f'{artist} {title}')}"
        await interaction.followup.send(f"🔍 **YouTube Search:** {youtube_url}", ephemeral=True)

    async def get_lyrics(self, interaction: discord.Interaction, player: wavelink.Player):
        if not player.current:
            return await interaction.response.send_message("No song is currently playing.", ephemeral=True)
        if not self.session:
            return await interaction.response.send_message("Bot is still initializing. Please try again in a moment.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        artist, title = self._extract_artist_title(player.current)
        
        async def try_lyrics(try_artist: str, try_title: str) -> str:
            try:
                from urllib.parse import quote
                url = f"https://api.lyrics.ovh/v1/{quote(try_artist)}/{quote(try_title)}"
                async with self.session.get(url) as response:
                    if response.status == 200:
                        try:
                            lyrics = (await response.json()).get('lyrics', '').strip()
                            if lyrics:
                                lyrics = LYRICS_NEWLINES_REGEX.sub('\n\n', lyrics)
                                lyrics_file = io.BytesIO(f"{try_artist} - {try_title}\n\n{lyrics}".encode('utf-8'))
                                embed = discord.Embed(title="📝 Lyrics", description=f"**{try_title}** by **{try_artist}**\n\nLyrics are attached as a text file above!", color=0xFF6B35)
                                await interaction.followup.send(embed=embed, file=discord.File(lyrics_file, filename=f"{try_artist} - {try_title} - Lyrics.txt"), ephemeral=True)
                                return 'success'
                        except Exception:
                            return 'server_error'
                    return 'not_found' if response.status == 404 else ('server_error' if response.status >= 500 else 'not_found')
            except Exception:
                return 'network_error'
        
        try:
            server_errors = 0
            attempts = [
                (artist, title),
                (artist.split(',')[0].strip(), title) if ',' in artist else None,
                (title, title),
                *[(a, title) for a in ["Various Artists", "Various", "Classic", "Popular"] if a != artist]
            ]
            
            for attempt in filter(None, attempts):
                result = await try_lyrics(*attempt)
                if result == 'success':
                    return
                elif result in ('server_error', 'network_error'):
                    server_errors += 1
            
            msg = "The lyrics service is temporarily unavailable. Please try again later." if server_errors > 0 else "No lyrics found for this song. The lyrics database may not have this track, or it might be too new. Try searching for the official lyrics online."
            await interaction.followup.send(msg, ephemeral=True)
        except Exception:
            await interaction.followup.send("Failed to fetch lyrics. Please try again later.", ephemeral=True)

    async def get_spotify_link(self, interaction: discord.Interaction, player: wavelink.Player):
        if not player.current:
            return await interaction.response.send_message("No song is currently playing.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        artist, title = self._extract_artist_title(player.current)
        from urllib.parse import quote
        spotify_url = f"https://open.spotify.com/search/{quote(f'{artist} {title}')}"
        await interaction.followup.send(f"🔍 **Spotify Search:** {spotify_url}", ephemeral=True)

    async def show_queue(self, interaction: discord.Interaction, player: wavelink.Player):
        await interaction.response.defer(ephemeral=True)
        if len(player.queue) == 0:
            return await interaction.followup.send("📋 **Queue is empty**", ephemeral=True)
        
        queue_list = list(player.queue)
        total_tracks = len(queue_list)
        tracks_per_page = 10
        
        queue_text = []
        for idx, track in enumerate(queue_list[:tracks_per_page], start=1):
            artist, title = self._extract_artist_title(track)
            duration_ms = getattr(track, 'duration', None) or getattr(track, 'length', None)
            duration_str = self._format_duration(duration_ms) if duration_ms else "?"
            queue_text.append(f"**{idx}.** {artist} - {title} `[{duration_str}]`")
        
        embed = discord.Embed(title="📋 Queue", color=0x5865F2, timestamp=discord.utils.utcnow(), description="\n".join(queue_text))
        embed.set_footer(text=f"Showing 10 of {total_tracks} tracks" if total_tracks > tracks_per_page else f"{total_tracks} track{'s' if total_tracks != 1 else ''} in queue")
        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(MusicWavelinkCog(bot))
