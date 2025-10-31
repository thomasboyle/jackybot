import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button, Select
from functools import lru_cache

class CustomHelpCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Remove built-in help command
        bot.remove_command('help')

    @commands.command(name='create')
    async def create_disabled(self, ctx, *, prompt: str = None):
        """Disabled AI image generation command."""
        embed = discord.Embed(
            title="🎨 AI Image Generation Temporarily Disabled",
            description="The AI image generation feature has been temporarily disabled due to maintenance.\n\n"
                       "This feature will return in a future update.",
            color=0xff6b6b
        )
        embed.add_field(
            name="Alternative",
            value="Try `!music` for AI-generated music instead!",
            inline=False
        )
        embed.set_footer(text="We apologize for the inconvenience")
        await ctx.reply(embed=embed)

    @lru_cache(maxsize=1)
    def get_commands_by_category(self):
        """Organize commands by category with emojis"""
        return {
            "🔧 General": {
                "!help": "Show bot commands",
                "!roles": "Manage server roles quickly",
                "!ping": "Check bot connection to Discord",
                "!stats": "Display bot statistics",
                "!botinfo": "Display basic bot info"
            },
            "🎨 Media": {
                "@JackyBot": "ChatGPT",
                "!music": "AI Music Generation (MusicGen)",
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
            },
            "💡 Suggestions": {
                "!suggestions": "Create a suggestion request (Admin only)",
                "!clear_suggestions": "Clear suggestion data (Admin only)"
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
        """Custom help command directing users to web UI"""
        try:
            web_ui_url = "https://jackybot.xyz"
            
            embed = discord.Embed(
                title="🌟 JackyBot Commands & Configuration",
                description=f"**Visit our web interface to view all commands and configure the bot!**\n\n"
                           f"**[Click here to access the Web UI]({web_ui_url})**\n\n"
                           f"Browse all available commands\n"
                           f"Configure bot settings and preferences\n"
                           f"View bot statistics and information",
                color=0x4169e1,
                url=web_ui_url
            )
            
            embed.add_field(
                name="🔗 Quick Access",
                value=f"[**Open Web Interface**]({web_ui_url})",
                inline=False
            )
            
            embed.add_field(
                name="💡 Tip",
                value="The web interface provides a complete command reference and allows you to customize bot settings for your server.",
                inline=False
            )
            
            embed.set_footer(text="For support, visit jackybot.xyz", icon_url=self.bot.user.avatar.url if self.bot.user.avatar else None)
            embed.set_thumbnail(url=self.bot.user.avatar.url if self.bot.user.avatar else None)
            
            view = View()
            view.add_item(Button(label="Open Web UI", url=web_ui_url, style=discord.ButtonStyle.link, emoji="🌐"))
            
            await ctx.send(embed=embed, view=view)
            
            if ctx.guild:
                print(f'Command: help | Server: {ctx.guild.name}')
                
        except Exception as e:
            print(f"Help command error: {e}")
            await ctx.send(f"An error occurred displaying help. Please visit https://jackybot.xyz for command information.")

    @app_commands.command(name="help", description="Show bot commands and access the web UI")
    async def slash_help(self, interaction: discord.Interaction):
        """Slash command version of help"""
        try:
            web_ui_url = "https://jackybot.xyz"

            embed = discord.Embed(
                title="🌟 JackyBot Commands & Configuration",
                description=f"**Visit our web interface to view all commands and configure the bot!**\n\n"
                           f"**[Click here to access the Web UI]({web_ui_url})**\n\n"
                           f"Browse all available commands\n"
                           f"Configure bot settings and preferences\n"
                           f"View bot statistics and information",
                color=0x4169e1,
                url=web_ui_url
            )

            embed.add_field(
                name="🔗 Quick Access",
                value=f"[**Open Web Interface**]({web_ui_url})",
                inline=False
            )

            embed.add_field(
                name="💡 Tip",
                value="The web interface provides a complete command reference and allows you to customize bot settings for your server.",
                inline=False
            )

            embed.set_footer(text="For support, visit jackybot.xyz", icon_url=self.bot.user.avatar.url if self.bot.user.avatar else None)
            embed.set_thumbnail(url=self.bot.user.avatar.url if self.bot.user.avatar else None)

            view = View()
            view.add_item(Button(label="Open Web UI", url=web_ui_url, style=discord.ButtonStyle.link, emoji="🌐"))

            await interaction.response.send_message(embed=embed, view=view)

            if interaction.guild:
                print(f'Command: /help | Server: {interaction.guild.name}')

        except Exception as e:
            print(f"Help slash command error: {e}")
            await interaction.response.send_message(f"An error occurred displaying help. Please visit https://jackybot.xyz for command information.")

    @commands.command(name="botinfo", aliases=["info"])
    async def botinfo(self, ctx):
        """Display basic bot info"""
        try:
            guild_count = len(self.bot.guilds)
            user_count = sum(guild.member_count for guild in self.bot.guilds)
            uptime = discord.utils.utcnow() - self.bot.start_time if hasattr(self.bot, 'start_time') else "Unknown"
            
            embed = discord.Embed(
                title="Bot Info",
                color=0x2b2d31,
                description="Current bot performance and usage summary"
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