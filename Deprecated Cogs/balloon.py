import discord
from discord.ext import commands, tasks
import asyncio
import random
import json
from datetime import datetime, timedelta

class ChannelInputModal(discord.ui.Modal, title="Enter Channel Name"):
    channel_name = discord.ui.TextInput(label="Channel Name", placeholder="Enter the channel name here")

    async def on_submit(self, interaction: discord.Interaction):
        self.interaction = interaction
        self.stop()

class ConfigView(discord.ui.View):
    def __init__(self, ctx, config, cog):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.config = config
        self.cog = cog
        self.channel_name = discord.utils.get(ctx.guild.channels, id=config.get('channel_id')).name if config and 'channel_id' in config else None
        self.frequency = config.get('frequency')

    @discord.ui.button(label="Set Channel", style=discord.ButtonStyle.primary, emoji="📝", row=0)
    async def set_channel_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("You're not authorized to use this button.", ephemeral=True)
            return

        modal = ChannelInputModal()
        await interaction.response.send_modal(modal)
        await modal.wait()
        self.channel_name = modal.channel_name.value
        
        # Save channel data
        channel = discord.utils.get(self.ctx.guild.text_channels, name=self.channel_name)
        if channel:
            self.config['channel_id'] = channel.id
            self.cog.save_config(self.ctx.guild.id, self.config)
        
        await self.update_embed(modal.interaction)

    @discord.ui.select(
        placeholder="Select frequency",
        options=[discord.SelectOption(label=f"{i} times per day", value=str(i)) for i in range(1, 9)],
        row=1
    )
    async def select_frequency(self, interaction: discord.Interaction, select: discord.ui.Select):
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("You're not authorized to use this dropdown.", ephemeral=True)
            return

        self.frequency = int(select.values[0])
        
        # Save frequency data
        self.config['frequency'] = self.frequency
        self.cog.save_config(self.ctx.guild.id, self.config)
        
        await self.update_embed(interaction)

    async def update_embed(self, interaction: discord.Interaction):
        embed = self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    def create_embed(self):
        embed = discord.Embed(
            title="🎈 Balloon Game Configuration 🎈",
            description="Manage your Balloon Game settings here!",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="📋 Instructions",
            value="1. Click 'Set Channel' to choose where balloons will appear\n2. Use the dropdown to select how often balloons should pop up",
            inline=False
        )
        embed.add_field(
            name="🏷️ Channel",
            value=self.channel_name or "Not set",
            inline=True
        )
        embed.add_field(
            name="🕒 Frequency",
            value=f"{self.frequency} times per day" if self.frequency else "Not set",
            inline=True
        )
        embed.set_footer(text="Configuration will timeout after 5 minutes of inactivity")
        return embed

class BalloonGame(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = {}
        self.load_config()
        self.balloon_task.start()

    def load_config(self):
        config_file = 'balloon_config.json'
        try:
            with open(config_file, 'r') as f:
                self.config = json.load(f)
        except FileNotFoundError:
            print(f"Configuration file {config_file} not found. Creating a new one.")
            self.config = {}
        except json.JSONDecodeError:
            print(f"Error decoding {config_file}. Starting with an empty configuration.")
            self.config = {}
        self.validate_config()
        print(f"Loaded configuration: {self.config}")  # Debug print

    def validate_config(self):
        for guild_id, data in list(self.config.items()):
            if not isinstance(data, dict) or 'channel_id' not in data or 'frequency' not in data:
                print(f"Invalid configuration for guild {guild_id}. Removing it.")
                del self.config[guild_id]
        self.save_config()

    def save_config(self, guild_id=None, guild_config=None):
        if guild_id and guild_config:
            self.config[str(guild_id)] = guild_config
        with open('balloon_config.json', 'w') as f:
            json.dump(self.config, f, indent=4)
        print(f"Saved configuration: {self.config}")  # Debug print

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def balloonconfig(self, ctx):
        guild_id = str(ctx.guild.id)
        config = self.config.get(guild_id, {})
        view = ConfigView(ctx, config, self)
        embed = view.create_embed()
        config_message = await ctx.send(embed=embed, view=view)

        timeout = await view.wait()
        if timeout:
            await config_message.edit(content="Configuration timed out.", embed=None, view=None)
            return

        success_embed = discord.Embed(
            title="🎉 Balloon Game Configuration Updated! 🎉",
            description="The configuration has been saved.",
            color=discord.Color.green()
        )
        await config_message.edit(embed=success_embed, view=None)

    @balloonconfig.error
    async def balloonconfig_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            embed = discord.Embed(
                title="❌ Permission Denied",
                description="You need administrator permissions to use this command.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def balloontest(self, ctx):
        guild_id = str(ctx.guild.id)
        print(f"Current config: {self.config}")  # Debug print
        if guild_id not in self.config:
            await ctx.send("Balloon game is not configured for this server. Use `!balloonconfig` to set it up.")
            return

        channel_id = self.config[guild_id]['channel_id']
        channel = self.bot.get_channel(channel_id)
        if not channel:
            await ctx.send("The configured channel for the balloon game no longer exists. Please use `!balloonconfig` to set a new channel.")
            return

        await self.send_balloon(channel)
        await ctx.send(f"A test balloon has been sent to {channel.mention}!")

    @tasks.loop(minutes=1)
    async def balloon_task(self):
        now = datetime.utcnow()
        for guild_id, data in list(self.config.items()):
            if 'channel_id' not in data or 'frequency' not in data:
                print(f"Invalid configuration for guild {guild_id}. Skipping.")
                continue
            
            channel = self.bot.get_channel(data['channel_id'])
            if channel:
                last_balloon = data.get('last_balloon')
                if last_balloon:
                    last_balloon = datetime.fromisoformat(last_balloon)
                    if now - last_balloon < timedelta(minutes=30):
                        continue

                if random.random() < data['frequency'] / (24 * 60):
                    await self.send_balloon(channel)
                    self.config[guild_id]['last_balloon'] = now.isoformat()
                    self.save_config()
            else:
                print(f"Channel not found for guild {guild_id}. Removing configuration.")
                del self.config[guild_id]
                self.save_config()

    async def send_balloon(self, channel):
        message = await channel.send("🎈")
        await message.add_reaction("✂️")

        def check(reaction, user):
            return user != self.bot.user and str(reaction.emoji) == "✂️" and reaction.message.id == message.id

        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=300.0, check=check)
            await self.add_coins(user.id, 100)
            await channel.send(f"{user.mention} popped the balloon and collected 100 coins! Use !bank to check your new balance.")
        except asyncio.TimeoutError:
            await message.delete()


    async def add_coins(self, user_id, amount):
        user_id = str(user_id)
        if 'bank' not in self.config:
            self.config['bank'] = {}
        if user_id not in self.config['bank']:
            self.config['bank'][user_id] = 0
        self.config['bank'][user_id] += amount
        self.save_config()

    @commands.command()
    async def bank(self, ctx):
        user_id = str(ctx.author.id)
        balance = self.config.get('bank', {}).get(user_id, 0)
        
        # Calculate level and progress
        level = balance // 1000
        progress = (balance % 1000) / 10  # Convert to percentage
        
        embed = discord.Embed(
            title="🎈 Balloon Bank 🏦",
            description=f"Welcome to your personal Balloon Bank, {ctx.author.mention}!",
            color=discord.Color.gold()
        )

        # Balance field with emoji
        embed.add_field(
            name="💰 Your Balance",
            value=f"**{balance:,}** coins",
            inline=False
        )

        # Level field
        embed.add_field(
            name="🏅 Balloon Popper Level",
            value=f"Level **{level}**",
            inline=True
        )

        # Coins to next level field
        coins_to_next_level = 1000 - (balance % 1000)
        embed.add_field(
            name="🎯 Next Level",
            value=f"**{coins_to_next_level:,}** coins to Level {level + 1}",
            inline=True
        )

        # Progress bar
        progress_bar = self.create_progress_bar(progress)
        embed.add_field(
            name="📊 Progress to Next Level",
            value=progress_bar,
            inline=False
        )

        # Fun fact or tip
        facts = [
            "Did you know? The record for most balloons popped in one minute is 107!",
            "Tip: Keep an eye out for special golden balloons for bonus coins!",
            "Fun Fact: The largest balloon ever made was 100 feet in diameter!",
            "Tip: Invite friends to join the Balloon Game for more popping fun!",
        ]
        embed.add_field(
            name="💡 Balloon Byte",
            value=random.choice(facts),
            inline=False
        )

        embed.set_footer(text="Keep popping those balloons to earn more coins and level up!")
        
        await ctx.send(embed=embed)

    def create_progress_bar(self, percent):
        filled = int(10 * percent // 100)
        return f"[{'🟩' * filled}{'⬜' * (10 - filled)}] {percent:.1f}%"

async def setup(bot):
    await bot.add_cog(BalloonGame(bot))