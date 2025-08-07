import discord
from discord.ext import commands
from discord.ui import View, Button, Select
from functools import lru_cache

class CustomHelpCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Remove built-in help command
        bot.remove_command('help')
        
    @lru_cache(maxsize=1)
    def get_commands_by_category(self):
        """Organize commands by category with emojis"""
        return {
            "🔧 General": {
                "!help": "Show bot commands",
                "!roles": "Manage server roles quickly",
                "!ping": "Check bot connection to Discord",
                "!stats": "Display bot statistics"
            },
            "🎨 Media": {
                "@JackyBot": "ChatGPT",
                "!create": "AI Image Generation",
                "!quote": "Reply to a message to create a meme quote",
                "!avatar": "Fullscreen user avatar"
            },
            "🎵 Music": {
                "!play": "Play music in voice channel",
                "!skip": "Skip current song",
                "!leave": "Kick bot from voice channel",
                "!queue": "Show all items in music queue"
            },
            "📋 Playlist": {
                "!playlist delete": "Delete a playlist",
                "!pl create [name]": "Create a new playlist",
                "!pl list": "Show all playlists",
                "!pl view [name]": "View a playlist",
                "!pl delete [name]": "Delete a playlist"
            },
            "🎮 Fun and Games": {
                "!gyat": "Check how your body is looking today",
                "!aura": "Daily Aura Reading",
                "!love": "Check connection between users",
                "!triggered": "Reply to an image with this command to trigger",
                "!tts": "Text to speech message",
                "!deaf": "Bot will TTS every message in chat",
                "!trivia": "Start trivia game",
                "!steamos_latest": "Get latest SteamOS info"
            },
            "😂 Meme Templates": {
                "!punisher": "Punisher meme template",
                "!homelander": "Homelander meme template"
            }
        }
    
    def create_category_embed(self, category, commands_dict):
        """Create an embed for a specific category"""
        embed = discord.Embed(
            title=f"{category} Commands", 
            color=0x2b2d31,
            description="Select a category from the dropdown menu to view commands."
        )
        
        for command, description in commands_dict.items():
            embed.add_field(name=f"`{command}`", value=description, inline=False)
            
        embed.set_footer(text="Navigate between categories using the dropdown menu")
        return embed
    
    class HelpView(View):
        def __init__(self, help_cog, timeout=60):
            super().__init__(timeout=timeout)
            self.help_cog = help_cog
            self.commands_by_category = help_cog.get_commands_by_category()
            
            # Add category selector
            self.add_category_selector()
            
        def add_category_selector(self):
            options = [
                discord.SelectOption(label=category.split(" ", 1)[1], emoji=category.split(" ", 1)[0], value=category)
                for category in self.commands_by_category.keys()
            ]
            
            select = Select(
                placeholder="Select command category",
                options=options,
                custom_id="category_select"
            )
            
            select.callback = self.category_callback
            self.add_item(select)
            
        async def category_callback(self, interaction: discord.Interaction):
            selected_category = interaction.data["values"][0]
            category_commands = self.commands_by_category[selected_category]
            embed = self.help_cog.create_category_embed(selected_category, category_commands)
            await interaction.response.edit_message(embed=embed, view=self)
    
    @commands.command(name="help")
    async def custom_help(self, ctx, command=None):
        """Custom help command with category support"""
        try:
            commands_by_category = self.get_commands_by_category()
            
            if command:
                # Find the command in any category
                for category, commands in commands_by_category.items():
                    for cmd, desc in commands.items():
                        # Match without the prefix
                        if command.lower() == cmd.lower() or command.lower() == cmd.lower().strip('!'):
                            embed = discord.Embed(
                                title=f"Command: {cmd}",
                                description=desc,
                                color=0x2b2d31
                            )
                            await ctx.send(embed=embed)
                            return
                
                # If command not found
                await ctx.send(f"Command `{command}` not found. Use `!help` to see all commands.")
                return
            
            # Default overview embed when no specific command is requested
            overview_embed = discord.Embed(
                title="Bot Commands",
                description="Select a category from the dropdown menu below to view commands.",
                color=0x2b2d31
            )
            
            # Add a field for each category showing command count
            for category, commands in commands_by_category.items():
                overview_embed.add_field(
                    name=category,
                    value=f"{len(commands)} commands",
                    inline=True
                )
                
            overview_embed.set_footer(text="Use !help [command] for detailed information about a specific command")
            
            # Create and send the view with the overview embed
            view = self.HelpView(self)
            await ctx.send(embed=overview_embed, view=view)
            
            # Optional logging
            if ctx.guild:
                print(f'Command: help | Server: {ctx.guild.name}')
                
        except Exception as e:
            # Add error handling to prevent crashes
            print(f"Help command error: {e}")
            await ctx.send("An error occurred displaying help. Please try again later.")
    
    @commands.command(name="stats")
    async def stats(self, ctx):
        """Display bot statistics"""
        try:
            guild_count = len(self.bot.guilds)
            user_count = sum(guild.member_count for guild in self.bot.guilds)
            uptime = discord.utils.utcnow() - self.bot.start_time if hasattr(self.bot, 'start_time') else "Unknown"
            
            embed = discord.Embed(
                title="Bot Statistics",
                color=0x2b2d31,
                description="Current bot performance and usage statistics"
            )
            
            embed.add_field(name="Servers", value=str(guild_count), inline=True)
            embed.add_field(name="Users", value=str(user_count), inline=True)
            embed.add_field(name="Commands", value=str(len(self.bot.commands)), inline=True)
            embed.add_field(name="Uptime", value=str(uptime).split('.')[0], inline=True)
            embed.add_field(name="Latency", value=f"{round(self.bot.latency * 1000)}ms", inline=True)
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            print(f"Stats command error: {e}")
            await ctx.send("An error occurred displaying statistics. Please try again later.")

async def setup(bot):
    # Store the bot start time for the stats command
    if not hasattr(bot, 'start_time'):
        bot.start_time = discord.utils.utcnow()
    await bot.add_cog(CustomHelpCommand(bot))