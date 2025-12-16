import discord
from discord.ext import commands, tasks
import random
import asyncio
from datetime import datetime
from PIL import Image
import aiohttp
import io
import math
import json
import os
import groq

TWO_PI = 2 * math.pi

class AuraCommands(commands.Cog):
    __slots__ = ('bot', 'groq_client', 'data_file', 'daily_info', 'used_values',
                 'last_reset', 'initial_size', 'final_size', 'frame_count',
                 'frame_duration', 'zoom_factors', 'paste_offsets', 'session', 'aura_categories',
                 '_save_pending')

    def __init__(self, bot):
        self.bot = bot
        self.groq_client = groq.Groq()
        self.data_file = 'data/aura_data.json'
        self.daily_info = {}
        self.used_values = {}
        self.last_reset = None
        self._save_pending = False

        self.initial_size = 512
        self.final_size = 128
        self.frame_count = 48
        self.frame_duration = 42

        self.zoom_factors = []
        self.paste_offsets = []
        for i in range(self.frame_count):
            zoom = 1 + 0.1 * math.sin(TWO_PI * i / self.frame_count)
            zoomed_size = int(self.initial_size * zoom)
            paste_pos = (self.initial_size - zoomed_size) >> 1
            self.zoom_factors.append(zoomed_size)
            self.paste_offsets.append(paste_pos)

        self.session = None
        self.aura_categories = ('todays_crush', 'fattest_user', 'horniness_level',
                               'penis_length', 'weight_amount', 'height_amount', 'aura_reading')
        self.load_data()

    async def cog_load(self):
        self.session = aiohttp.ClientSession()
        self.refresh_daily_info.start()

    def cog_unload(self):
        self.refresh_daily_info.cancel()
        self._save_data_sync()
        if self.session:
            asyncio.create_task(self.session.close())

    def load_data(self):
        if os.path.exists(self.data_file):
            with open(self.data_file, 'r') as f:
                data = json.load(f)
                self.daily_info = {int(k): {int(uk): uv for uk, uv in v.items()} for k, v in data.get('daily_info', {}).items()}
                self.used_values = {int(k): {kk: set(vv) for kk, vv in v.items()} for k, v in data.get('used_values', {}).items()}
                self.last_reset = datetime.fromisoformat(data['last_reset']) if data.get('last_reset') else None

    def _save_data_sync(self):
        data = {
            'daily_info': {str(k): {str(uk): uv for uk, uv in v.items()} for k, v in self.daily_info.items()},
            'used_values': {str(k): {kk: list(vv) for kk, vv in v.items()} for k, v in self.used_values.items()},
            'last_reset': self.last_reset.isoformat() if self.last_reset else None
        }
        with open(self.data_file, 'w') as f:
            json.dump(data, f, separators=(',', ':'))

    async def save_data(self):
        if self._save_pending:
            return
        self._save_pending = True
        await asyncio.sleep(1)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._save_data_sync)
        self._save_pending = False

    @tasks.loop(minutes=1)
    async def refresh_daily_info(self):
        await self.bot.wait_until_ready()
        now = datetime.now()
        if self.last_reset is None or now.date() > self.last_reset.date():
            self.daily_info.clear()
            self.used_values.clear()
            self.last_reset = now
            await self.save_data()

    def get_unique_value(self, guild_id, key, value_generator):
        if guild_id not in self.used_values:
            self.used_values[guild_id] = {k: set() for k in self.aura_categories}

        used_set = self.used_values[guild_id][key]
        for _ in range(1000):
            value = value_generator()
            if value not in used_set:
                used_set.add(value)
                return value
        return value_generator()

    def generate_aura_reading_sync(self):
        response = self.groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a mystical aura reader. Provide brief, insightful readings."},
                {"role": "user", "content": "Generate a coherant daily aura reading in 15 words. Do so in one line. Don't use speech marks.-:"}
            ],
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            max_tokens=20
        )
        return response.choices[0].message.content

    async def generate_aura_reading(self):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.generate_aura_reading_sync)

    async def get_user_info(self, guild_id, user_id):
        if guild_id not in self.daily_info:
            self.daily_info[guild_id] = {}

        if user_id not in self.daily_info[guild_id]:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                return None

            if not guild.chunked:
                await guild.chunk()

            members = list(guild.members)

            if len(members) < 2:
                todays_crush = fattest_user = None
            else:
                todays_crush = self.get_unique_value(guild_id, 'todays_crush', lambda: random.choice(members).id)
                available_members = [m for m in members if m.id != todays_crush]
                fattest_user = self.get_unique_value(guild_id, 'fattest_user', lambda: random.choice(available_members).id)

            aura_reading = await self.generate_aura_reading()

            self.daily_info[guild_id][user_id] = {
                "todays_crush": todays_crush,
                "fattest_user": fattest_user,
                "horniness_level": self.get_unique_value(guild_id, 'horniness_level', lambda: round(random.uniform(0, 110), 1)),
                "penis_length": self.get_unique_value(guild_id, 'penis_length', lambda: round(random.uniform(0.1, 20), 1)),
                "weight_amount": self.get_unique_value(guild_id, 'weight_amount', lambda: round(random.uniform(40, 120), 1)),
                "height_amount": self.get_unique_value(guild_id, 'height_amount', lambda: f"{random.randint(3, 8)}'{random.randint(0, 11)}\""),
                "aura_reading": aura_reading
            }
            asyncio.create_task(self.save_data())

        return self.daily_info[guild_id][user_id]

    async def create_animated_avatar(self, avatar_url):
        async with self.session.get(avatar_url) as resp:
            if resp.status != 200:
                return None
            data = await resp.read()

        avatar = Image.open(io.BytesIO(data)).resize((self.initial_size, self.initial_size), Image.LANCZOS)
        frames = []

        for i in range(self.frame_count):
            zoomed_size = self.zoom_factors[i]
            paste_pos = self.paste_offsets[i]

            zoomed = avatar.resize((zoomed_size, zoomed_size), Image.LANCZOS)
            frame = Image.new('RGBA', (self.initial_size, self.initial_size), (0, 0, 0, 0))
            frame.paste(zoomed, (paste_pos, paste_pos))
            frames.append(frame.resize((self.final_size, self.final_size), Image.LANCZOS))

        output = io.BytesIO()
        frames[0].save(output, format='GIF', save_all=True, append_images=frames[1:],
                      duration=self.frame_duration, loop=0)
        output.seek(0)
        return discord.File(output, filename="animated_avatar.gif")

    @commands.command(name='aura')
    async def today(self, ctx):
        user_info = await self.get_user_info(ctx.guild.id, ctx.author.id)
        if not user_info:
            await ctx.reply("Unable to retrieve guild information. Please try again later.")
            return

        embed = discord.Embed(
            title="Your Aura Today...",
            description="Here's your daily aura reading",
            color=0x0099FF
        )

        todays_crush = ctx.guild.get_member(user_info["todays_crush"])
        fattest_user = ctx.guild.get_member(user_info["fattest_user"])

        embed.add_field(name="Today's Crush", value=todays_crush.mention if todays_crush else "N/A", inline=False)
        embed.add_field(name="Fattest User", value=fattest_user.mention if fattest_user else "N/A", inline=False)
        embed.add_field(name="Horniness", value=f"`{user_info['horniness_level']}%`", inline=True)
        embed.add_field(name="Penis Length", value=f"`{user_info['penis_length']} inches`", inline=True)
        embed.add_field(name="Height Today", value=f"`{user_info['height_amount']}`", inline=True)
        embed.add_field(name="Weight Today", value=f"`{user_info['weight_amount']} kg`", inline=True)

        if 'aura_reading' not in user_info:
            user_info['aura_reading'] = await self.generate_aura_reading()
            asyncio.create_task(self.save_data())

        embed.add_field(name="Daily Aura Reading", value=f"`{user_info['aura_reading']}`", inline=False)
        embed.set_footer(text=f"Requested by {ctx.author.name} | Refreshes at midnight")

        animated_avatar = await self.create_animated_avatar(ctx.author.display_avatar.url)
        if animated_avatar:
            embed.set_thumbnail(url="attachment://animated_avatar.gif")
            await ctx.reply(embed=embed, file=animated_avatar)
        else:
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            await ctx.reply(embed=embed)

async def setup(bot):
    await bot.add_cog(AuraCommands(bot))