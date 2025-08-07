import discord
from discord.ext import commands
from discord.ui import View, Button

class PaginatedHelpCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.commands_per_page = 5

    def get_commands(self):
        return {
            "!create [prompt]": "AI generated image",
            "!3d [prompt]": "AI generated 3D Model",
            "!video [prompt]": "AI generated video (Currently Unavailable)",
            "@JackyBot [prompt]": "ChatGPT",
            "!aura": "Daily Aura Reading",
            "!quote": "Reply to a message to create a meme quote",
            "!love @user @user": "Check connection between users",
            "!avatar @user": "Fullscreen user avatar",
            "!play URL/song title": "Play music in voice channel",
            "!skip": "Skip current song",
            "!lyrics [song name]": "Display lyrics of song",
            "!triggered": "Reply to an image with this command to trigger",
            "!ping": "Check bot connection to Discord",
            "!tts": "Text to speech message",
            "!leave": "Kick bot from voice channel",
            "!help": "Show bot commands",
            "!image": "Search for image online",
            "!queue": "Show all items in music queue",
            "!deaf": "Bot will TTS every message in chat",
            "!trivia": "Start trivia game",
            "!info @user": "Request user info",
            "!scrape [number of days]d": "Save chat messages to a spreadsheet",
            "!like [message]": "Punisher meme template",
            "!alright [message]": "Homelander meme template",
            "!hot @user": "Walking Dead meme template",
            "!karma @user": "Jojo Siwa meme template"
        }

    def get_embed_pages(self):
        commands = self.get_commands()
        pages = []
        for i in range(0, len(commands), self.commands_per_page):
            embed = discord.Embed(title="Bot Commands", color=0x00ff00)
            for command, description in list(commands.items())[i:i+self.commands_per_page]:
                embed.add_field(name=f"`{command}`", value=description, inline=False)
            pages.append(embed)

        for i, page in enumerate(pages):
            page.set_footer(text=f"Page {i+1}/{len(pages)}")

        return pages

    class HelpView(View):
        def __init__(self, pages, timeout=60):
            super().__init__(timeout=timeout)
            self.pages = pages
            self.current_page = 0

        @discord.ui.button(label="Previous", style=discord.ButtonStyle.grey, disabled=True)
        async def previous_button(self, interaction: discord.Interaction, button: Button):
            self.current_page = max(0, self.current_page - 1)
            await self.update_view(interaction)

        @discord.ui.button(label="Next", style=discord.ButtonStyle.grey)
        async def next_button(self, interaction: discord.Interaction, button: Button):
            self.current_page = min(len(self.pages) - 1, self.current_page + 1)
            await self.update_view(interaction)

        async def update_view(self, interaction: discord.Interaction):
            self.previous_button.disabled = (self.current_page == 0)
            self.next_button.disabled = (self.current_page == len(self.pages) - 1)
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

    @commands.command()
    async def help(self, ctx):
        server = ctx.guild.name
        print(f'Command: help | Server: {server}')

        pages = self.get_embed_pages()
        view = self.HelpView(pages)
        await ctx.send(embed=pages[0], view=view)

async def setup(bot):
    await bot.add_cog(PaginatedHelpCommand(bot))