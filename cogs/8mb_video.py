import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button


class VideoCompression(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="compress")
    async def compress_command(self, ctx):
        """Compress MP4 or MOV videos to under 8MB and 60 seconds max"""
        try:
            compress_url = "https://jackybot.xyz/compress"

            embed = discord.Embed(
                title="🎥 Video Compression Tool",
                description="**Compress your videos to under 8MB and 60 seconds!**\n\n"
                           f"**[Click here to access the compression tool]({compress_url})**\n\n"
                           "Upload any MP4 or MOV file (any size)\n"
                           "Choose between AV1 or AVIF format\n"
                           "Get a compressed version under 8MB and 60 seconds\n"
                           "Perfect for Discord uploads and sharing",
                color=0x4169e1,
                url=compress_url
            )

            embed.add_field(
                name="📤 Supported Formats",
                value="• MP4\n• MOV",
                inline=True
            )

            embed.add_field(
                name="🎯 Output Formats",
                value="• AV1 (recommended)\n• AVIF",
                inline=True
            )

            embed.add_field(
                name="⚡ Features",
                value="• Auto-resize to under 8MB\n• Trim to 60 seconds max\n• Local hardware processing\n• Fast compression",
                inline=False
            )

            embed.set_footer(text="Powered by JackyBot | Free to use", icon_url=self.bot.user.avatar.url if self.bot.user.avatar else None)
            embed.set_thumbnail(url=self.bot.user.avatar.url if self.bot.user.avatar else None)

            view = View()
            view.add_item(Button(label="Open Compression Tool", url=compress_url, style=discord.ButtonStyle.link, emoji="🎥"))

            await ctx.send(embed=embed, view=view)

            if ctx.guild:
                print(f'Command: compress | Server: {ctx.guild.name} | User: {ctx.author}')

        except Exception as e:
            print(f"Compress command error: {e}")
            await ctx.send("An error occurred. Please visit https://jackybot.xyz/compress to access the video compression tool.")

    @app_commands.command(name="compress", description="Compress videos to under 8MB and 60 seconds max")
    async def slash_compress(self, interaction: discord.Interaction):
        """Slash command version of compress"""
        try:
            compress_url = "https://jackybot.xyz/compress"

            embed = discord.Embed(
                title="🎥 Video Compression Tool",
                description="**Compress your videos to under 8MB and 60 seconds!**\n\n"
                           f"**[Click here to access the compression tool]({compress_url})**\n\n"
                           "Upload any MP4 or MOV file (any size)\n"
                           "Choose between AV1 or AVIF format\n"
                           "Get a compressed version under 8MB and 60 seconds\n"
                           "Perfect for Discord uploads and sharing",
                color=0x4169e1,
                url=compress_url
            )

            embed.add_field(
                name="📤 Supported Formats",
                value="• MP4\n• MOV",
                inline=True
            )

            embed.add_field(
                name="🎯 Output Formats",
                value="• AV1 (recommended)\n• AVIF",
                inline=True
            )

            embed.add_field(
                name="⚡ Features",
                value="• Auto-resize to under 8MB\n• Trim to 60 seconds max\n• Local hardware processing\n• Fast compression",
                inline=False
            )

            embed.set_footer(text="Powered by JackyBot | Free to use", icon_url=self.bot.user.avatar.url if self.bot.user.avatar else None)
            embed.set_thumbnail(url=self.bot.user.avatar.url if self.bot.user.avatar else None)

            view = View()
            view.add_item(Button(label="Open Compression Tool", url=compress_url, style=discord.ButtonStyle.link, emoji="🎥"))

            await interaction.response.send_message(embed=embed, view=view)

            if interaction.guild:
                print(f'Command: /compress | Server: {interaction.guild.name} | User: {interaction.author}')

        except Exception as e:
            print(f"Compress slash command error: {e}")
            await interaction.response.send_message("An error occurred. Please visit https://jackybot.xyz/compress to access the video compression tool.")


async def setup(bot):
    await bot.add_cog(VideoCompression(bot))
