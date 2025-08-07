import json
import os
from discord.ext import commands
import discord
import matplotlib.pyplot as plt
import seaborn as sns
import io
import time
from datetime import datetime

class StatTrackingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.start_time = time.time()  # Track bot session start time
        self.command_stats = self.load_stats('command_stats.json')
        self.server_stats = self.load_stats('server_command_stats.json')
        self.user_stats = self.load_stats('user_stats.json')  # New: Track user-specific stats
        self.error_stats = self.load_stats('error_stats.json')  # New: Track command errors

    def load_stats(self, filename):
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                return json.load(f)
        return {}

    def save_stats(self, data, filename):
        with open(filename, 'w') as f:
            json.dump(data, f)

    @commands.Cog.listener()
    async def on_command_completion(self, ctx):
        # Update command stats
        command_name = ctx.command.name
        prefix = ctx.prefix
        key = f"{prefix}{command_name}"
        self.command_stats[key] = self.command_stats.get(key, 0) + 1
        self.save_stats(self.command_stats, 'command_stats.json')

        # Update server stats
        server_id = str(ctx.guild.id) if ctx.guild else 'DM'
        server_name = ctx.guild.name if ctx.guild else 'Direct Messages'
        if server_id not in self.server_stats:
            self.server_stats[server_id] = {"name": server_name, "count": 0, "last_used": ""}
        self.server_stats[server_id]["count"] += 1
        self.server_stats[server_id]["last_used"] = datetime.now().isoformat()
        self.save_stats(self.server_stats, 'server_command_stats.json')

        # Update user stats
        user_id = str(ctx.author.id)
        if user_id not in self.user_stats:
            self.user_stats[user_id] = {"name": str(ctx.author), "count": 0}
        self.user_stats[user_id]["count"] += 1
        self.save_stats(self.user_stats, 'user_stats.json')

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        # Track command errors
        error_type = type(error).__name__
        self.error_stats[error_type] = self.error_stats.get(error_type, 0) + 1
        self.save_stats(self.error_stats, 'error_stats.json')

    def get_uptime(self):
        """Calculate bot uptime in a human-readable format."""
        uptime_seconds = int(time.time() - self.start_time)
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}h {minutes}m {seconds}s"

    def create_command_pie(self, top_commands):
        """Create a pie chart for command distribution."""
        commands, counts = zip(*top_commands)
        plt.figure(figsize=(8, 8))
        plt.pie(counts, labels=commands, autopct='%1.1f%%', startangle=90, colors=sns.color_palette("viridis", len(commands)))
        plt.title("Command Usage Distribution", fontsize=14, fontweight='bold')
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=300)
        buf.seek(0)
        plt.close()
        return buf

    @commands.command(name="stats")
    async def stats(self, ctx):
        """Display bot stats including uptime, top commands, and top users."""
        embed = discord.Embed(title="Bot Statistics", color=discord.Color.blue())
        embed.add_field(name="Uptime", value=self.get_uptime(), inline=True)
        embed.add_field(name="Latency", value=f"{round(self.bot.latency * 1000)}ms", inline=True)

        # Top Commands
        top_commands = sorted(self.command_stats.items(), key=lambda x: x[1], reverse=True)[:5]
        if top_commands:
            command_str = "\n".join(f"{cmd}: {count}" for cmd, count in top_commands)
            embed.add_field(name="Top Commands", value=f"```\n{command_str}\n```", inline=False)
            graph_buf = self.create_command_pie(top_commands)
            graph_file = discord.File(graph_buf, filename="command_stats.png")
            embed.set_image(url="attachment://command_stats.png")
        else:
            embed.add_field(name="Top Commands", value="No commands used yet!", inline=False)

        # Top Users
        top_users = sorted(self.user_stats.items(), key=lambda x: x[1]["count"], reverse=True)[:3]
        if top_users:
            user_str = "\n".join(f"{data['name']}: {data['count']}" for _, data in top_users)
            embed.add_field(name="Top Users", value=f"```\n{user_str}\n```", inline=False)

        # Errors
        if self.error_stats:
            top_error = max(self.error_stats.items(), key=lambda x: x[1])
            embed.add_field(name="Most Common Error", value=f"{top_error[0]} ({top_error[1]} times)", inline=False)

        await ctx.reply(embed=embed, file=graph_file if top_commands else None)

    @commands.command(name="serverstats")
    async def serverstats(self, ctx):
        """Display server-specific command usage stats."""
        top_servers = sorted(self.server_stats.values(), key=lambda x: x["count"], reverse=True)[:5]
        embed = discord.Embed(title="Server Command Stats", color=discord.Color.green())

        if top_servers:
            server_str = "\n".join(f"{s['name']}: {s['count']} (Last: {s['last_used'][:10]})" for s in top_servers)
            embed.add_field(name="Top Servers", value=f"```\n{server_str}\n```", inline=False)
        else:
            embed.add_field(name="Top Servers", value="No server activity yet!", inline=False)

        await ctx.reply(embed=embed)

async def setup(bot):
    await bot.add_cog(StatTrackingCog(bot))