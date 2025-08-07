import discord
from discord.ext import commands
from PIL import Image, ImageDraw
import io
import aiohttp
import json
import os
from datetime import datetime, timedelta
import random
import asyncio

class DailyRandomAvatar(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.user_avatars = {}
        self.json_file = 'user_avatars.json'
        self.background_images = ['v1.png', 'v2.png', 'v3.png', 'v4.png', 'v5.png', 'v6.png']
        
        # Pre-load background images into memory
        self.backgrounds = {name: Image.open(name) for name in self.background_images}
        
        # Precompute constants and masks
        self.avatar_size = 300
        self.border_size = 6
        self.total_size = 312  # avatar_size + 2 * border_size
        self.avatar_pos = (304, 84)  # Pre-calculated position
        
        # Precompute masks once
        self.border_mask = Image.new('L', (self.total_size, self.total_size), 0)
        draw = ImageDraw.Draw(self.border_mask)
        draw.ellipse((0, 0, self.total_size, self.total_size), fill=255)
        
        self.avatar_mask = Image.new('L', (self.avatar_size, self.avatar_size), 0)
        draw = ImageDraw.Draw(self.avatar_mask)
        draw.ellipse((0, 0, self.avatar_size, self.avatar_size), fill=255)
        
        # Pre-generate compliments list
        self.compliments = [
            "You're looking extra thicc today! 👀",
            "That GYAT is on fire! 🔥",
            "Serving looks and booty, honey! 💖",
            "You can't handle this jelly! 🍑",
            "Bringing that cake to the party! 🎂"
        ]
        
        # Single session for all HTTP requests
        self.session = aiohttp.ClientSession()
        
        self.load_user_avatars()
        self.bot.loop.create_task(self.daily_reset())

    def load_user_avatars(self):
        if os.path.exists(self.json_file):
            with open(self.json_file, 'r') as f:
                self.user_avatars = json.load(f)

    def save_user_avatars(self):
        with open(self.json_file, 'w') as f:
            json.dump(self.user_avatars, f)

    def get_user_background(self, user_id):
        today = datetime.now().date().isoformat()
        user_data = self.user_avatars.get(user_id)
        if not user_data or user_data['date'] != today:
            self.user_avatars[user_id] = {
                'background': random.choice(self.background_images),
                'date': today
            }
            self.save_user_avatars()
        return self.user_avatars[user_id]['background']

    async def daily_reset(self):
        while True:
            now = datetime.now()
            next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            await asyncio.sleep((next_midnight - now).total_seconds())
            self.user_avatars.clear()
            self.save_user_avatars()

    @commands.command(name="gyat")
    async def gyat(self, ctx):
        await self.send_gyat_image(ctx)

    async def send_gyat_image(self, ctx):
        user = ctx.author
        user_id = str(user.id)
        background_key = self.get_user_background(user_id)
        img = self.backgrounds[background_key].copy()

        # Download and process avatar
        avatar_url = user.avatar.with_size(512).url
        async with self.session.get(avatar_url) as resp:
            avatar_data = await resp.read()
            avatar = Image.open(io.BytesIO(avatar_data)).resize((self.avatar_size, self.avatar_size))

        # Create bordered avatar in one operation
        bordered_avatar = Image.new('RGBA', (self.total_size, self.total_size), (0, 0, 0, 255))
        bordered_avatar.paste(avatar, (self.border_size, self.border_size), self.avatar_mask)
        
        # Apply mask and composite directly
        output = Image.new('RGBA', (self.total_size, self.total_size), (0, 0, 0, 0))
        output.paste(bordered_avatar, mask=self.border_mask)
        img.paste(output, self.avatar_pos, output)

        # Optimize image saving
        buffer = io.BytesIO()
        img.save(buffer, format='PNG', optimize=True, compress_level=1)
        buffer.seek(0)

        # Create embed with pre-selected compliment
        embed = discord.Embed(
            title="🍑 Today's GYAT 🍑",
            description=f"Oh {user.mention}, check out that fabulous body! 💃🕺",
            color=0xFF69B4  # Direct hex color instead of discord.Color.from_rgb
        )
        embed.set_image(url="attachment://daily_avatar.png")
        embed.set_footer(text="🔄 Daily Reset. Come back tomorrow for a new look!")
        embed.add_field(name="Our thoughts...", value=random.choice(self.compliments), inline=True)

        await ctx.reply(file=discord.File(buffer, filename="daily_avatar.png"), embed=embed)

    def cog_unload(self):
        asyncio.create_task(self.session.close())

async def setup(bot):
    await bot.add_cog(DailyRandomAvatar(bot))