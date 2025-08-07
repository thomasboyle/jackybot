import discord
from discord.ext import commands, tasks
import aiohttp
import json
import asyncio

class TwitchAPI:
    def __init__(self, client_id):
        self.client_id = client_id
        self.headers = {
            'Client-ID': self.client_id,
            'Accept': 'application/vnd.twitchtv.v5+json'
        }

    async def get_streams(self, usernames):
        url = 'https://api.twitch.tv/helix/streams'
        params = [('user_login', username) for username in usernames]

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=self.headers, params=params) as resp:
                return await resp.json()

class TwitchNotifier(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        with open('config.json', 'r') as config_file:
            self.config = json.load(config_file)
        self.twitch_api = TwitchAPI(self.config['twitch_client_id'])
        self.live_streamers = set()
        self.check_twitch_streams.start()

    def cog_unload(self):
        self.check_twitch_streams.cancel()

    @tasks.loop(minutes=5)
    async def check_twitch_streams(self):
        data = await self.twitch_api.get_streams(self.config['twitch_usernames'])
        
        for stream in data.get('data', []):
            username = stream['user_name']
            if username not in self.live_streamers:
                self.live_streamers.add(username)
                channel = self.bot.get_channel(self.config['discord_channel_id'])
                
                embed = discord.Embed(
                    title=f"{username} is now live on Twitch!",
                    url=f"https://twitch.tv/{username}",
                    color=discord.Color.purple()
                )
                embed.add_field(name="Game", value=stream['game_name'], inline=True)
                embed.add_field(name="Viewers", value=stream['viewer_count'], inline=True)
                embed.set_thumbnail(url=stream['thumbnail_url'].replace('{width}', '320').replace('{height}', '180'))
                embed.set_footer(text="Join the stream now!")
                
                await channel.send(embed=embed)

        ended_streams = self.live_streamers - {stream['user_name'] for stream in data.get('data', [])}
        for username in ended_streams:
            self.live_streamers.remove(username)

    @check_twitch_streams.before_loop
    async def before_check_twitch_streams(self):
        await self.bot.wait_until_ready()

    @commands.command(name="checkstreams")
    async def check_streams_command(self, ctx):
        """Manually check for live streams"""
        await ctx.send("Checking for live streams...")
        await self.check_twitch_streams()
        await ctx.send("Stream check complete!")

async def setup(bot):
    await bot.add_cog(TwitchNotifier(bot))