import discord
from discord.ext import commands
from discord import ui
import json
import os
from typing import Dict, List
import aiohttp
import re
import yt_dlp
import asyncio
import logging

logger = logging.getLogger(__name__)

class AddToPlaylistModal(ui.Modal):
    def __init__(self, playlist_name: str):
        super().__init__(title=f"Add Song to {playlist_name}")
        self.playlist_name = playlist_name
        
        self.song_input = ui.TextInput(
            label="Song Name or URL",
            placeholder="Enter song name or YouTube URL...",
            style=discord.TextStyle.short,
            required=True
        )
        self.add_item(self.song_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # Get the playlist manager from the cog
        playlist_manager = interaction.client.get_cog("PlaylistManager")
        if not playlist_manager:
            await interaction.followup.send("Playlist system is currently unavailable.", ephemeral=True)
            return
            
        # Add the song to the playlist
        success = await playlist_manager.add_song_to_playlist(
            interaction.user.id,
            self.playlist_name,
            self.song_input.value
        )
        
        if success:
            await interaction.followup.send(f"Added '{self.song_input.value}' to playlist '{self.playlist_name}'", ephemeral=True)
        else:
            await interaction.followup.send("Failed to add song to playlist. Please check the song name/URL.", ephemeral=True)

class PlaylistView(ui.View):
    def __init__(self, playlist_name: str, songs: List[str], owner_id: int):
        super().__init__(timeout=180)
        self.playlist_name = playlist_name
        self.songs = songs
        self.owner_id = owner_id
        self.page = 0
        self.songs_per_page = 5
        self.message = None

    async def on_timeout(self):
        """Disable all buttons when the view times out"""
        if self.message:
            for item in self.children:
                item.disabled = True
            await self.message.edit(view=self)

    @ui.button(label="▶️ Play", style=discord.ButtonStyle.green)
    async def play_playlist(self, interaction: discord.Interaction, button: ui.Button):
        if not self.songs:
            await interaction.response.send_message("This playlist is empty!", ephemeral=True)
            return
            
        # Check if user is in a voice channel
        if not interaction.user.voice:
            await interaction.response.send_message("You need to be in a voice channel to play music!", ephemeral=True)
            return
            
        music_cog = interaction.client.get_cog("MusicBotCog")
        if not music_cog:
            await interaction.response.send_message("Music system is currently unavailable.", ephemeral=True)
            return
            
        # Connect to the voice channel if not already connected
        voice_client = interaction.guild.voice_client
        if not voice_client:
            voice_client = await interaction.user.voice.channel.connect()
        elif voice_client.channel != interaction.user.voice.channel:
            await voice_client.move_to(interaction.user.voice.channel)
            
        # Queue up all songs in the playlist
        await interaction.response.send_message(f"Adding {len(self.songs)} songs from playlist '{self.playlist_name}' to the queue...")
        
        # Create a minimal context with just what we need
        ctx = await interaction.client.get_context(interaction.message)
        ctx.author = interaction.user
        
        # Instead of setting voice_client directly, we'll let the play command handle it
        # since the voice client is now properly connected to the right channel
        
        # Play the first song
        await music_cog.play(ctx, search=self.songs[0])
        
        # Queue the remaining songs
        for song in self.songs[1:]:
            music_cog.queues.setdefault(interaction.guild.id, []).append(song)

    @ui.button(label="➕ Add Song", style=discord.ButtonStyle.blurple)
    async def add_song(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Only the playlist owner can add songs!", ephemeral=True)
            return
            
        modal = AddToPlaylistModal(self.playlist_name)
        await interaction.response.send_modal(modal)

    @ui.button(label="🗑️ Remove Song", style=discord.ButtonStyle.red)
    async def remove_song(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("Only the playlist owner can remove songs!", ephemeral=True)
            return
            
        # Create a select menu with the songs
        options = [
            discord.SelectOption(label=f"{i+1}. {song[:50]}...", value=str(i))
            for i, song in enumerate(self.songs)
        ]
        
        select = ui.Select(placeholder="Choose a song to remove...", options=options)
        
        async def select_callback(interaction: discord.Interaction):
            index = int(select.values[0])
            removed_song = self.songs.pop(index)
            
            playlist_manager = interaction.client.get_cog("PlaylistManager")
            await playlist_manager.save_playlists()
            
            await interaction.response.send_message(f"Removed '{removed_song}' from the playlist.", ephemeral=True)
            
        select.callback = select_callback
        view = ui.View()
        view.add_item(select)
        await interaction.response.send_message("Select a song to remove:", view=view, ephemeral=True)

class PlaylistManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.playlists_file = "data/playlists.json"
        self.playlists: Dict[str, Dict] = {}
        self.load_playlists()

    def load_playlists(self):
        if os.path.exists(self.playlists_file):
            with open(self.playlists_file, 'r') as f:
                self.playlists = json.load(f)

    async def save_playlists(self):
        with open(self.playlists_file, 'w') as f:
            json.dump(self.playlists, f, indent=4)

    async def add_song_to_playlist(self, user_id: int, playlist_name: str, song: str) -> bool:
        user_id = str(user_id)
        if user_id not in self.playlists:
            return False
        
        if playlist_name not in self.playlists[user_id]:
            return False
            
        # If it's not a URL, try to get the YouTube URL
        if not song.startswith(('http://', 'https://')):
            music_cog = self.bot.get_cog("MusicBotCog")
            if music_cog:
                song = await music_cog.get_video_url(song)
                if not song:
                    return False

        self.playlists[user_id][playlist_name].append(song)
        await self.save_playlists()
        return True

    async def get_song_titles_batch(self, urls: List[str]) -> List[str]:
        """Fetch multiple song titles concurrently"""
        async def fetch_single_title(url: str) -> str:
            try:
                music_cog = self.bot.get_cog("MusicBotCog")
                if not music_cog:
                    return url
                    
                ydl_opts = {
                    'format': 'bestaudio/best',
                    'noplaylist': True,
                    'nocheckcertificate': True,
                    'ignoreerrors': False,
                    'quiet': True,
                    'no_warnings': True,
                    'extract_flat': True,
                }
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = await asyncio.to_thread(ydl.extract_info, url, download=False)
                    return info.get('title', url)
            except Exception as e:
                logger.error(f"Error getting song title: {e}")
                return url

        # Fetch all titles concurrently
        tasks = [fetch_single_title(url) for url in urls]
        titles = await asyncio.gather(*tasks)
        return titles

    @commands.group(
        name="playlist",
        aliases=["playlists", "pl", "playlist help", "playlisthelp"],
        invoke_without_command=True
    )
    async def playlist(self, ctx):
        """Manage your playlists"""
        # Check if the command was invoked with just the name or with "help"
        command = ctx.message.content.lower().strip()
        if command not in ["!playlist", "!playlists", "!pl", "!playlist help", "!playlisthelp"]:
            # If it doesn't match any of our expected formats, show a more specific error
            embed = discord.Embed(
                title="❌ Invalid Playlist Command",
                description=f"Hey {ctx.author.mention}, that doesn't look quite right.",
                color=discord.Color.red()
            )
            embed.add_field(
                name="Did you mean?",
                value="Try one of these commands instead:\n"
                "You can use `!pl` as a shortcut for any command!",
                inline=False
            )
            embed.add_field(
                name="Create a playlist",
                value="```!playlist create <name>\n!pl create <name>```",
                inline=False
            )
            embed.add_field(
                name="View your playlists",
                value="```!playlist list\n!pl list```",
                inline=False
            )
            await ctx.reply(embed=embed, mention_author=True)
            return

        # Standard help embed
        embed = discord.Embed(
            title="🎵 Playlist Commands Help",
            description=f"Hey {ctx.author.mention}, here's how to manage your music playlists:",
            color=discord.Color.blue()
        )

        embed.add_field(
            name="Create a Playlist",
            value="```!playlist create <name>```"
            "Creates a new empty playlist with the given name\n"
            "Example: `!playlist create My Favorites`",
            inline=False
        )

        embed.add_field(
            name="View Your Playlists",
            value="```!playlist list```"
            "Shows all your playlists and how many songs are in each one",
            inline=False
        )

        embed.add_field(
            name="View Playlist Contents",
            value="```!playlist view <name>```"
            "Shows all songs in the specified playlist and provides playback controls\n"
            "Example: `!playlist view My Favorites`",
            inline=False
        )

        embed.add_field(
            name="Delete a Playlist",
            value="```!playlist delete <name>```"
            "Permanently deletes the specified playlist\n"
            "Example: `!playlist delete My Favorites`",
            inline=False
        )

        embed.add_field(
            name="💡 Tips",
            value="• When viewing a playlist, you can:\n"
            "  - ▶️ Play the entire playlist\n"
            "  - ➕ Add new songs\n"
            "  - 🗑️ Remove songs\n"
            "• You can add songs using either YouTube URLs or search terms\n"
            "• Each user can have multiple playlists\n"
            "• Quick Commands:\n"
            "  - `!pl` instead of `!playlist`\n"
            "  - `!pl create` for create\n"
            "  - `!pl list` for list\n"
            "  - `!pl view` for view\n"
            "  - `!pl delete` for delete",
            inline=False
        )

        await ctx.reply(embed=embed, mention_author=True)

    @playlist.command(name="create")
    async def create_playlist(self, ctx, *, name: str):
        """Create a new playlist"""
        user_id = str(ctx.author.id)
        
        if user_id not in self.playlists:
            self.playlists[user_id] = {}
            
        if name in self.playlists[user_id]:
            await ctx.send("You already have a playlist with that name!")
            return
            
        self.playlists[user_id][name] = []
        await self.save_playlists()
        await ctx.send(f"Created playlist '{name}'!")

    @playlist.command(name="list")
    async def list_playlists(self, ctx):
        """List all your playlists"""
        user_id = str(ctx.author.id)
        
        if user_id not in self.playlists or not self.playlists[user_id]:
            await ctx.send("You don't have any playlists!")
            return
            
        embed = discord.Embed(title="Your Playlists", color=discord.Color.blue())
        for name, songs in self.playlists[user_id].items():
            embed.add_field(name=name, value=f"{len(songs)} songs", inline=False)
            
        await ctx.send(embed=embed)

    @playlist.command(name="view")
    async def view_playlist(self, ctx, *, name: str):
        """View songs in a playlist"""
        user_id = str(ctx.author.id)
        
        if user_id not in self.playlists or name not in self.playlists[user_id]:
            await ctx.send("Playlist not found!")
            return
            
        songs = self.playlists[user_id][name].copy()
        if not songs:
            embed = discord.Embed(
                title=f"Playlist: {name}", 
                description="This playlist is empty!",
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)
            return

        # Send initial loading message
        embed = discord.Embed(
            title=f"Playlist: {name}",
            description="Loading songs...",
            color=discord.Color.blue()
        )
        message = await ctx.send(embed=embed)

        # Fetch all titles concurrently
        titles = await self.get_song_titles_batch(songs)

        # Create the final embed
        embed = discord.Embed(title=f"Playlist: {name}", color=discord.Color.blue())
        
        # Add all songs to the embed
        for i, (title, url) in enumerate(zip(titles, songs), 1):
            embed.add_field(
                name=f"Song {i}", 
                value=f"[{title}]({url})", 
                inline=False
            )

        # Create and send the view
        view = PlaylistView(name, songs, int(user_id))
        view.message = message
        await message.edit(embed=embed, view=view)

    @playlist.command(name="delete")
    async def delete_playlist(self, ctx, *, name: str):
        """Delete a playlist"""
        user_id = str(ctx.author.id)
        
        if user_id not in self.playlists or name not in self.playlists[user_id]:
            await ctx.send("Playlist not found!")
            return
            
        del self.playlists[user_id][name]
        await self.save_playlists()
        await ctx.send(f"Deleted playlist '{name}'!")

async def setup(bot):
    await bot.add_cog(PlaylistManager(bot))
