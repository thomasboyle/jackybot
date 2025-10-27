import discord
from discord.ext import commands
from discord import ui
import json
import os
import aiohttp
import asyncio
from typing import Dict, List, Optional
import re


class MovieSuggestionModal(ui.Modal):
    def __init__(self, cog: 'MoviesCog'):
        super().__init__(title="Suggest a Movie")
        self.cog = cog
        self.movie_title = ui.TextInput(
            label="Movie Title",
            placeholder="Enter the movie title...",
            style=discord.TextStyle.short,
            required=True
        )
        self.add_item(self.movie_title)

    async def on_submit(self, interaction: discord.Interaction):
        """Handle movie suggestion submission"""
        movie_title = self.movie_title.value.strip()

        # Check if movie already exists in suggestions
        if any(suggestion['title'].lower() == movie_title.lower() for suggestion in self.cog.suggestions):
            await interaction.response.send_message(
                f"❌ '{movie_title}' is already in the suggestions list!",
                ephemeral=True
            )
            return

        # Add to suggestions
        suggestion = {
            'title': movie_title,
            'suggested_by': interaction.user.display_name,
            'suggested_by_id': interaction.user.id,
            'timestamp': discord.utils.utcnow().isoformat()
        }

        self.cog.suggestions.append(suggestion)
        await self.cog.save_data()

        await interaction.response.send_message(
            f"✅ Successfully added '{movie_title}' to the suggestions list!",
            ephemeral=True
        )


class MoviesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.suggestions_file = "data/movie_suggestions.json"
        self.watchlist_file = "data/movie_watchlist.json"
        self.finished_file = "data/movie_finished.json"

        # Data structures
        self.suggestions: List[Dict] = []
        self.watchlist: List[Dict] = []
        self.finished: List[Dict] = []

        self.load_data()

    def load_data(self):
        """Load data from JSON files, creating them if they don't exist"""
        # Load suggestions
        if os.path.exists(self.suggestions_file):
            with open(self.suggestions_file, 'r') as f:
                self.suggestions = json.load(f)
        else:
            self.suggestions = []
            with open(self.suggestions_file, 'w') as f:
                json.dump(self.suggestions, f, indent=4)

        # Load watchlist
        if os.path.exists(self.watchlist_file):
            with open(self.watchlist_file, 'r') as f:
                self.watchlist = json.load(f)
        else:
            self.watchlist = []
            with open(self.watchlist_file, 'w') as f:
                json.dump(self.watchlist, f, indent=4)

        # Load finished movies
        if os.path.exists(self.finished_file):
            with open(self.finished_file, 'r') as f:
                self.finished = json.load(f)
        else:
            self.finished = []
            with open(self.finished_file, 'w') as f:
                json.dump(self.finished, f, indent=4)

    async def save_data(self):
        """Save data to JSON files"""
        # Save suggestions
        with open(self.suggestions_file, 'w') as f:
            json.dump(self.suggestions, f, indent=4)

        # Save watchlist
        with open(self.watchlist_file, 'w') as f:
            json.dump(self.watchlist, f, indent=4)

        # Save finished movies
        with open(self.finished_file, 'w') as f:
            json.dump(self.finished, f, indent=4)

    async def fetch_movie_details(self, movie_title: str) -> Optional[Dict]:
        """Fetch movie details from OMDB API"""
        api_key = "6e563951"

        url = f"http://www.omdbapi.com/?t={movie_title}&apikey={api_key}"

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get('Response') == 'True':
                            return {
                                'title': data.get('Title', movie_title),
                                'year': data.get('Year', 'N/A'),
                                'poster': data.get('Poster', ''),
                                'plot': data.get('Plot', 'No plot available'),
                                'runtime': data.get('Runtime', 'N/A'),
                                'genre': data.get('Genre', 'N/A'),
                                'director': data.get('Director', 'N/A'),
                                'actors': data.get('Actors', 'N/A'),
                                'imdb_rating': data.get('imdbRating', 'N/A')
                            }
            except Exception as e:
                print(f"Error fetching movie details: {e}")

        return None

    async def show_finished_movies(self, interaction: discord.Interaction):
        """Show the list of finished/watched movies"""
        if not self.finished:
            embed = discord.Embed(
                title="✅ Finished Movies",
                description="No movies have been marked as watched yet.",
                color=0x00ff00
            )
        else:
            embed = discord.Embed(
                title="✅ Finished Movies",
                description=f"You've watched {len(self.finished)} movies!",
                color=0x00ff00
            )

            # Show movies in reverse chronological order (most recent first)
            for movie in reversed(self.finished[-10:]):  # Show last 10
                embed.add_field(
                    name=movie['title'],
                    value=f"Watched on {movie.get('watched_date', 'Unknown')}",
                    inline=False
                )

        # Add back button
        view = ui.View()
        back_button = ui.Button(label="← Back to Main", style=discord.ButtonStyle.secondary)
        back_button.callback = lambda i: self.show_main_menu(i)
        view.add_item(back_button)

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def show_watchlist(self, interaction: discord.Interaction):
        """Show the watchlist with management options"""
        if not self.watchlist:
            embed = discord.Embed(
                title="📋 Watch List",
                description="Your watchlist is empty. Add some movies from suggestions!",
                color=0xffaa00
            )
        else:
            embed = discord.Embed(
                title="📋 Watch List",
                description=f"You have {len(self.watchlist)} movies in your watchlist.",
                color=0xffaa00
            )

            for i, movie in enumerate(self.watchlist, 1):
                embed.add_field(
                    name=f"{i}. {movie['title']}",
                    value=f"Added by {movie['added_by']}",
                    inline=False
                )

        # Create watchlist view with buttons
        view = WatchlistView(self)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def show_main_menu(self, interaction: discord.Interaction):
        """Show the main movies menu"""
        embed = discord.Embed(
            title="🎬 Movie Manager",
            description="Manage your movie suggestions and watchlist!",
            color=0x00ff00
        )

        embed.add_field(
            name="📝 Suggest Movie",
            value="Add a movie to the suggestions list",
            inline=True
        )

        embed.add_field(
            name="📋 View Suggestions",
            value="Browse movie suggestions and details",
            inline=True
        )

        embed.add_field(
            name="✅ Finished",
            value="View movies you've already watched",
            inline=True
        )

        embed.add_field(
            name="🎯 Watch List",
            value="View and manage your watchlist",
            inline=True
        )

        view = MainMoviesView(self)
        await interaction.response.edit_message(embed=embed, view=view)

    async def show_suggestions(self, interaction: discord.Interaction):
        """Show movie suggestions with dropdown to view details"""
        if not self.suggestions:
            embed = discord.Embed(
                title="📋 Movie Suggestions",
                description="No movie suggestions yet. Be the first to suggest one!",
                color=0xffaa00
            )
        else:
            embed = discord.Embed(
                title="📋 Movie Suggestions",
                description=f"There are {len(self.suggestions)} movie suggestions available.",
                color=0xffaa00
            )

            # Show a few recent suggestions
            for suggestion in self.suggestions[-5:]:  # Show last 5
                embed.add_field(
                    name=suggestion['title'],
                    value=f"Suggested by {suggestion['suggested_by']}",
                    inline=False
                )

        # Create view with dropdown and back button
        view = SuggestionsView(self)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @commands.command(name='movies')
    async def movies_command(self, ctx):
        """Main movies command showing the main interface"""
        embed = discord.Embed(
            title="🎬 Movie Manager",
            description="Manage your movie suggestions and watchlist!",
            color=0x00ff00
        )

        embed.add_field(
            name="📝 Suggest Movie",
            value="Add a movie to the suggestions list",
            inline=True
        )

        embed.add_field(
            name="📋 View Suggestions",
            value="Browse movie suggestions and details",
            inline=True
        )

        embed.add_field(
            name="🎯 Watch List",
            value="View and manage your watchlist",
            inline=True
        )

        embed.add_field(
            name="✅ Finished",
            value="View movies you've already watched",
            inline=True
        )

        view = MainMoviesView(self)
        await ctx.send(embed=embed, view=view)


class SuggestionsView(ui.View):
    def __init__(self, cog: MoviesCog):
        super().__init__(timeout=300)  # 5 minute timeout
        self.cog = cog

        # Create select menu with current suggestions only if suggestions exist
        if self.cog.suggestions:
            options = [
                discord.SelectOption(
                    label=suggestion['title'][:100],
                    value=str(i),
                    description=f"By {suggestion['suggested_by']}"
                )
                for i, suggestion in enumerate(self.cog.suggestions)
            ][:25]  # Discord limit

            self.select_movie = ui.Select(
                placeholder="Choose a movie to view details...",
                options=options,
                custom_id="movie_select"
            )
            self.select_movie.callback = self.select_movie_callback
            self.add_item(self.select_movie)

        # Add back button below the dropdown
        back_button = ui.Button(label="← Back", style=discord.ButtonStyle.secondary)
        back_button.callback = self.back_to_main
        self.add_item(back_button)

    async def select_movie_callback(self, interaction: discord.Interaction):
        """Handle movie selection from dropdown"""
        if not hasattr(self, 'select_movie') or not self.select_movie.values:
            return

        index = int(self.select_movie.values[0])
        if index >= len(self.cog.suggestions):
            await interaction.response.send_message("❌ Movie not found!", ephemeral=True)
            return

        suggestion = self.cog.suggestions[index]
        movie_details = await self.cog.fetch_movie_details(suggestion['title'])

        embed = discord.Embed(
            title=f"🎬 {suggestion['title']}",
            color=0x3498db
        )

        if movie_details:
            embed.add_field(name="📅 Year", value=movie_details.get('year', 'N/A'), inline=True)
            embed.add_field(name="⏱️ Runtime", value=movie_details.get('runtime', 'N/A'), inline=True)
            embed.add_field(name="⭐ IMDB Rating", value=movie_details.get('imdb_rating', 'N/A'), inline=True)
            embed.add_field(name="🎭 Genre", value=movie_details.get('genre', 'N/A'), inline=False)
            embed.add_field(name="🎬 Director", value=movie_details.get('director', 'N/A'), inline=True)
            embed.add_field(name="🎪 Actors", value=movie_details.get('actors', 'N/A'), inline=True)
            embed.add_field(name="📖 Plot", value=movie_details.get('plot', 'No plot available')[:500] + "..." if len(movie_details.get('plot', '')) > 500 else movie_details.get('plot', 'No plot available'), inline=False)

            if movie_details.get('poster') and movie_details['poster'] != 'N/A':
                embed.set_image(url=movie_details['poster'])
        else:
            embed.add_field(name="ℹ️ Info", value="Could not fetch movie details. Please check the title spelling.", inline=False)

        embed.set_footer(text=f"Suggested by {suggestion['suggested_by']}")

        # Update the view to show details
        view = ui.View()
        back_button = ui.Button(label="← Back to Suggestions", style=discord.ButtonStyle.secondary)

        async def back_callback(interaction: discord.Interaction):
            await self.cog.show_suggestions(interaction)

        back_button.callback = back_callback
        view.add_item(back_button)

        await interaction.response.edit_message(embed=embed, view=view)

    async def back_to_main(self, interaction: discord.Interaction):
        """Go back to main menu"""
        await self.cog.show_main_menu(interaction)


class MainMoviesView(ui.View):
    def __init__(self, cog: MoviesCog):
        super().__init__(timeout=None)
        self.cog = cog

    @ui.button(label="Suggest Movie", style=discord.ButtonStyle.green, emoji="📝")
    async def suggest_movie(self, interaction: discord.Interaction, button: ui.Button):
        """Handle suggest movie button"""
        modal = MovieSuggestionModal(self.cog)
        await interaction.response.send_modal(modal)

    @ui.button(label="View Suggestions", style=discord.ButtonStyle.blurple, emoji="📋")
    async def view_suggestions(self, interaction: discord.Interaction, button: ui.Button):
        """Handle view suggestions button"""
        await self.cog.show_suggestions(interaction)

    @ui.button(label="Watch List", style=discord.ButtonStyle.primary, emoji="🎯")
    async def show_watchlist(self, interaction: discord.Interaction, button: ui.Button):
        """Handle watchlist button"""
        await self.cog.show_watchlist(interaction)

    @ui.button(label="Finished", style=discord.ButtonStyle.primary, emoji="✅")
    async def show_finished(self, interaction: discord.Interaction, button: ui.Button):
        """Handle finished movies button"""
        await self.cog.show_finished_movies(interaction)


class WatchlistView(ui.View):
    def __init__(self, cog: MoviesCog):
        super().__init__(timeout=300)  # 5 minute timeout
        self.cog = cog

    @ui.button(label="Add", style=discord.ButtonStyle.green, emoji="➕")
    async def add_movie(self, interaction: discord.Interaction, button: ui.Button):
        """Add a movie from suggestions to watchlist"""
        if not self.cog.suggestions:
            await interaction.response.send_message(
                "❌ No movie suggestions available to add!",
                ephemeral=True
            )
            return

        # Create dropdown with suggestions
        options = []
        for i, suggestion in enumerate(self.cog.suggestions):
            # Skip if already in watchlist
            if not any(w['title'].lower() == suggestion['title'].lower() for w in self.cog.watchlist):
                options.append(
                    discord.SelectOption(
                        label=suggestion['title'][:100],  # Discord limit
                        value=str(i),
                        description=f"Suggested by {suggestion['suggested_by']}"
                    )
                )

        if not options:
            await interaction.response.send_message(
                "❌ All suggestions are already in your watchlist!",
                ephemeral=True
            )
            return

        select = ui.Select(placeholder="Choose a movie to add...", options=options[:25])  # Discord limit

        async def select_callback(interaction: discord.Interaction):
            index = int(select.values[0])
            suggestion = self.cog.suggestions[index]

            # Check if already in watchlist (double check)
            if any(w['title'].lower() == suggestion['title'].lower() for w in self.cog.watchlist):
                await interaction.response.send_message(
                    "❌ This movie is already in your watchlist!",
                    ephemeral=True
                )
                return

            # Add to watchlist
            watchlist_item = {
                'title': suggestion['title'],
                'added_by': interaction.user.display_name,
                'added_by_id': interaction.user.id,
                'timestamp': discord.utils.utcnow().isoformat()
            }

            self.cog.watchlist.append(watchlist_item)

            # Remove from suggestions
            self.cog.suggestions.pop(index)

            await self.cog.save_data()

            await interaction.response.send_message(
                f"✅ Added '{suggestion['title']}' to your watchlist!",
                ephemeral=True
            )

        select.callback = select_callback
        view = ui.View()
        view.add_item(select)
        await interaction.response.send_message("Select a movie to add to your watchlist:", view=view, ephemeral=True)

    @ui.button(label="Remove", style=discord.ButtonStyle.red, emoji="🗑️")
    async def remove_movie(self, interaction: discord.Interaction, button: ui.Button):
        """Remove a movie from watchlist"""
        if not self.cog.watchlist:
            await interaction.response.send_message(
                "❌ Your watchlist is empty!",
                ephemeral=True
            )
            return

        # Create dropdown with watchlist movies
        options = [
            discord.SelectOption(
                label=movie['title'][:100],
                value=str(i),
                description=f"Added by {movie['added_by']}"
            )
            for i, movie in enumerate(self.cog.watchlist)
        ]

        select = ui.Select(placeholder="Choose a movie to remove...", options=options[:25])

        async def select_callback(interaction: discord.Interaction):
            index = int(select.values[0])
            removed_movie = self.cog.watchlist.pop(index)
            await self.cog.save_data()

            await interaction.response.send_message(
                f"✅ Removed '{removed_movie['title']}' from your watchlist!",
                ephemeral=True
            )

        select.callback = select_callback
        view = ui.View()
        view.add_item(select)
        await interaction.response.send_message("Select a movie to remove from your watchlist:", view=view, ephemeral=True)

    @ui.button(label="Watched", style=discord.ButtonStyle.primary, emoji="✅")
    async def mark_watched(self, interaction: discord.Interaction, button: ui.Button):
        """Mark a movie as watched (move from watchlist to finished)"""
        if not self.cog.watchlist:
            await interaction.response.send_message(
                "❌ Your watchlist is empty!",
                ephemeral=True
            )
            return

        # Create dropdown with watchlist movies
        options = [
            discord.SelectOption(
                label=movie['title'][:100],
                value=str(i),
                description=f"Added by {movie['added_by']}"
            )
            for i, movie in enumerate(self.cog.watchlist)
        ]

        select = ui.Select(placeholder="Choose a movie you watched...", options=options[:25])

        async def select_callback(interaction: discord.Interaction):
            index = int(select.values[0])
            watched_movie = self.cog.watchlist.pop(index)

            # Add to finished list
            finished_item = {
                'title': watched_movie['title'],
                'watched_by': interaction.user.display_name,
                'watched_by_id': interaction.user.id,
                'watched_date': discord.utils.utcnow().strftime('%Y-%m-%d'),
                'timestamp': discord.utils.utcnow().isoformat()
            }

            self.cog.finished.append(finished_item)
            await self.cog.save_data()

            await interaction.response.send_message(
                f"✅ Marked '{watched_movie['title']}' as watched! Moved to finished list.",
                ephemeral=True
            )

        select.callback = select_callback
        view = ui.View()
        view.add_item(select)
        await interaction.response.send_message("Select a movie you just watched:", view=view, ephemeral=True)

    @ui.button(label="← Back", style=discord.ButtonStyle.secondary)
    async def back_to_main(self, interaction: discord.Interaction, button: ui.Button):
        """Go back to main menu"""
        await self.cog.show_main_menu(interaction)


async def setup(bot):
    await bot.add_cog(MoviesCog(bot))
