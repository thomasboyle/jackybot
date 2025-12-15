import discord
from discord.ext import commands, tasks
import datetime
import aiohttp
import json
import os
import aiofiles
from collections import defaultdict
import logging

class EpicGamesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_games = defaultdict(dict)  # {guild_id: {game_id: game_data}}
        self.announced_games = defaultdict(dict)  # {guild_id: {game_id: timestamp}}
        self.announced_games_file = r"C:\Users\thoma\Documents\Python Programs\JackyBot\JackyBot March 2025\JackyBot\json\announced_games.json"
        self.epic_api_url = "https://store-site-backend-static-ipv4.ak.epicgames.com/freeGamesPromotions?locale=en-US&country=US&allowCountries=US"
        self.epic_store_base = "https://store.epicgames.com/en-US/p/"
        self.epic_free_games_url = "https://store.epicgames.com/en-US/free-games"
        # Don't start the task here - let it start after the bot is ready

    async def cog_load(self):
        """Called when the cog is loaded"""
        await self.load_announced_games()
        # Task will start automatically via before_loop when bot is ready

    async def cog_unload(self):
        if self.check_free_games.is_running():
            self.check_free_games.cancel()
        await self.save_announced_games()

    async def cog_load(self):
        """Called when the cog is loaded"""
        # Task will start automatically via before_loop when bot is ready
        pass

    async def load_announced_games(self):
        try:
            async with aiofiles.open(self.announced_games_file, 'r') as f:
                content = await f.read()
                if content.strip():
                    data = json.loads(content)
                    # Convert string keys back to defaultdict structure
                    for guild_id, games in data.items():
                        self.announced_games[guild_id] = games
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    async def save_announced_games(self):
        try:
            os.makedirs(os.path.dirname(self.announced_games_file), exist_ok=True)
            async with aiofiles.open(self.announced_games_file, 'w') as f:
                await f.write(json.dumps(dict(self.announced_games), separators=(',', ':')))
        except Exception as e:
            print(f"Error saving announced games: {e}")

    async def populate_active_games_on_startup(self):
        """Populate active_games on startup without sending announcements"""
        print("Populating active games on startup...")
        games = await self.get_epic_free_games()
        
        if not games:
            print("No games found during startup")
            return
        
        # Populate active_games for all guilds with current free games
        for guild in self.bot.guilds:
            guild_id = str(guild.id)
            for game in games:
                self.active_games[guild_id][game['id']] = game
        
        print(f"Populated {len(games)} active games for {len(self.bot.guilds)} guilds")

    async def get_epic_free_games(self):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.epic_api_url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status != 200:
                        print(f"Epic API returned status {response.status}")
                        return []
                    
                    data = await response.json()
                    current_time = datetime.datetime.now(datetime.timezone.utc)
                    
                    free_games = []
                    for element in data['data']['Catalog']['searchStore']['elements']:
                        promotions = element.get('promotions')
                        if not (promotions and promotions.get('promotionalOffers')):
                            continue
                        
                        # Check if there are active promotional offers
                        if not promotions['promotionalOffers']:
                            continue
                            
                        promo = promotions['promotionalOffers'][0]['promotionalOffers'][0]
                        
                        # Parse dates more safely
                        try:
                            start_date = promo['startDate'].replace('Z', '+00:00')
                            end_date = promo['endDate'].replace('Z', '+00:00')
                            start_time = datetime.datetime.fromisoformat(start_date)
                            end_time = datetime.datetime.fromisoformat(end_date)
                        except (ValueError, KeyError) as e:
                            print(f"Error parsing dates for {element.get('title', 'Unknown')}: {e}")
                            continue
                        
                        # Check if the offer is currently active
                        if start_time <= current_time <= end_time:
                            mappings = element.get('catalogNs', {}).get('mappings', [])
                            link = f"{self.epic_store_base}{mappings[0]['pageSlug']}" if mappings else self.epic_free_games_url
                            thumbnail = next((img['url'] for img in element.get('keyImages', []) if img['type'] == 'Thumbnail'), None)
                            
                            free_games.append({
                                'id': element['id'],
                                'title': element['title'],
                                'start_time': start_time,
                                'end_time': end_time,
                                'link': link,
                                'thumbnail': thumbnail
                            })
                    
                    return free_games
        except Exception as e:
            print(f"Error fetching Epic Games data: {e}")
            return []

    def to_uk_time(self, utc_time):
        """Convert UTC to UK time (GMT/BST)"""
        # More accurate BST calculation
        now = datetime.datetime.now()
        # BST runs from last Sunday in March to last Sunday in October
        is_bst = (now.month > 3 and now.month < 10) or \
                 (now.month == 3 and now.day >= 25) or \
                 (now.month == 10 and now.day < 25)
        return utc_time + datetime.timedelta(hours=1 if is_bst else 0)

    async def process_free_games(self):
        print(f"Checking free games at {datetime.datetime.now()}")
        games = await self.get_epic_free_games()
        
        if not games:
            print("No games found or API error")
            return
            
        print(f"Found {len(games)} free games")
        utc_time = datetime.datetime.now(datetime.timezone.utc)
        changes = False

        for guild in self.bot.guilds:
            channel = discord.utils.get(guild.text_channels, name='free-games')
            if not channel:
                continue

            guild_id = str(guild.id)
            active_games = self.active_games[guild_id]
            announced_games = self.announced_games[guild_id]

            # Handle expired games
            expired_games = [game_id for game_id, game in active_games.items() if game['end_time'] <= utc_time]
            for game_id in expired_games:
                game = active_games.pop(game_id)
                embed = discord.Embed(
                    title=game['title'],
                    description="This free game offer has now ended.",
                    color=discord.Color.red()
                )
                try:
                    await channel.send(embed=embed)
                    print(f"Announced end of {game['title']} in {guild.name}")
                except discord.errors.Forbidden:
                    print(f"No permission to send message in {guild.name}")
                except Exception as e:
                    print(f"Error sending expiry message: {e}")
                changes = True

            # Announce new games
            for game in games:
                game_id = game['id']
                if game_id not in active_games and game_id not in announced_games:
                    embed = discord.Embed(
                        title=game['title'],
                        description="**Now FREE on Epic Games Store!** 🎉",
                        color=discord.Color.green()
                    ).add_field(
                        name="Claim", value=f"[Click here]({game['link']})", inline=False
                    ).add_field(
                        name="Available until", value=self.to_uk_time(game['end_time']).strftime("%Y-%m-%d %H:%M"), inline=False
                    )
                    if game['thumbnail']:
                        embed.set_thumbnail(url=game['thumbnail'])
                    
                    try:
                        await channel.send(embed=embed)
                        print(f"Announced new game {game['title']} in {guild.name}")
                        active_games[game_id] = game
                        announced_games[game_id] = utc_time.isoformat()
                        changes = True
                    except discord.errors.Forbidden:
                        print(f"No permission to send message in {guild.name}")
                    except Exception as e:
                        print(f"Error sending new game message: {e}")

        if changes:
            await self.save_announced_games()

    @tasks.loop(hours=1)
    async def check_free_games(self):
        try:
            await self.process_free_games()
        except Exception as e:
            print(f"Error in check_free_games: {e}")

    @check_free_games.before_loop
    async def before_check_free_games(self):
        await self.bot.wait_until_ready()
        print("Epic Games task started")
        # Populate active_games on startup to prevent duplicate announcements
        await self.populate_active_games_on_startup()

    @check_free_games.error
    async def check_free_games_error(self, error):
        print(f"Task error: {error}")
        # Restart the task if it fails
        if not self.check_free_games.is_running():
            print("Restarting Epic Games task...")
            self.check_free_games.restart()

    @commands.command(name='freegames')
    async def list_free_games(self, ctx):
        guild_id = str(ctx.guild.id)
        active_games = self.active_games[guild_id]
        
        if not active_games:
            # Try to fetch current games if none are stored
            games = await self.get_epic_free_games()
            if not games:
                await ctx.send("No free games available on Epic Games Store right now!")
                return
            
            # Store the games for this guild
            for game in games:
                active_games[game['id']] = game

        embed = discord.Embed(title="Current Free Epic Games Store Titles", color=discord.Color.blue())
        first_game = None
        
        for game in active_games.values():
            if not first_game:
                first_game = game
            embed.add_field(
                name=game['title'],
                value=f"🎉 **FREE!**\n[Claim Here]({game['link']})\nEnds: {self.to_uk_time(game['end_time']).strftime('%Y-%m-%d %H:%M')}",
                inline=False
            )
        
        if first_game and first_game['thumbnail']:
            embed.set_thumbnail(url=first_game['thumbnail'])
        
        await ctx.send(embed=embed)

    @commands.command(name='checkgames')
    @commands.has_permissions(administrator=True)
    async def manual_check(self, ctx):
        """Manual trigger for checking games (admin only)"""
        await ctx.send("Checking for free games...")
        await self.process_free_games()
        await ctx.send("Check complete!")

    @commands.command(name='taskstatus')
    @commands.has_permissions(administrator=True)
    async def task_status(self, ctx):
        """Check if the task is running (admin only)"""
        status = "running" if self.check_free_games.is_running() else "stopped"
        next_run = self.check_free_games.next_iteration
        await ctx.send(f"Epic Games task is currently: **{status}**\nNext run: {next_run}")

async def setup(bot):
    await bot.add_cog(EpicGamesCog(bot))