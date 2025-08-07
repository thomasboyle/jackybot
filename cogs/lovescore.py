import discord
from discord.ext import commands
import aiohttp
from PIL import Image, ImageDraw, ImageFont
import os
import io
import random
import datetime
import asyncio
import functools
import weakref

class LoveCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.love_scores = {}
        self.font = None
        self.heart_image = None
        self.background = None
        self.mask = None
        # Cache for avatar images with TTL
        self.avatar_cache = weakref.WeakValueDictionary()
        
    async def cog_load(self):
        # Run heavy operations in a thread pool
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._preload_assets)

    def _preload_assets(self):
        # Preload assets in a separate thread
        self.font = ImageFont.truetype("arial.ttf", 36)
        
        # Load and optimize heart image
        heart = Image.open(os.path.join("assets", "images", "heart.png"))
        self.heart_image = heart.convert("RGBA").resize((120, 120), Image.LANCZOS)
        
        # Create background once
        self.background = Image.new('RGBA', (600, 400), color=(255, 255, 255, 255))
        draw = ImageDraw.Draw(self.background)
        draw.rounded_rectangle([0, 0, 600, 400], radius=20, fill=(255, 255, 255, 255))
        
        # Create reusable avatar mask
        avatar_size = (150, 150)
        self.mask = Image.new('L', avatar_size, 0)
        ImageDraw.Draw(self.mask).ellipse([0, 0, avatar_size[0], avatar_size[1]], fill=255)

    @commands.command()
    async def love(self, ctx, member1: discord.Member, member2: discord.Member):
        async with ctx.typing():
            # Calculate the score using a faster method
            pair_key = frozenset([member1.id, member2.id])
            current_date = datetime.date.today()
            today_str = current_date.strftime("%Y%m%d")

            if pair_key in self.love_scores and self.love_scores[pair_key][1] == today_str:
                love_score = self.love_scores[pair_key][0]
            else:
                # Generate score deterministically without resetting random seed
                seed_value = member1.id + member2.id + int(today_str)
                love_score = ((seed_value % 100) + 1)  # Simple hash function
                self.love_scores[pair_key] = (love_score, today_str)

            # Create image
            image_bytes = await self._create_love_image(member1, member2, love_score)

            # Send the image
            await ctx.reply(file=discord.File(fp=image_bytes, filename='love_match.png'))

    async def _create_love_image(self, member1, member2, love_score):
        # Process image creation in thread pool
        loop = asyncio.get_event_loop()
        
        # Fetch avatars concurrently first
        avatar_size = (150, 150)
        async with aiohttp.ClientSession() as session:
            avatar_tasks = [
                self._get_avatar(session, member1.display_avatar.url, avatar_size),
                self._get_avatar(session, member2.display_avatar.url, avatar_size)
            ]
            avatars = await asyncio.gather(*avatar_tasks)
        
        # Then do CPU-bound image processing in thread pool
        return await loop.run_in_executor(
            None, 
            functools.partial(self._render_image, avatars, love_score)
        )

    def _render_image(self, avatars, love_score):
        # Start with a copy of the preloaded background
        image = self.background.copy()
        draw = ImageDraw.Draw(image)

        # Paste avatars using the preloaded mask
        image.paste(avatars[0], (60, 50), self.mask)
        image.paste(avatars[1], (390, 50), self.mask)

        # Paste heart image
        heart_x = (600 - 120) // 2
        heart_y = 75
        image.paste(self.heart_image, (heart_x, heart_y), self.heart_image)

        # Draw love meter more efficiently
        meter_width = 400
        meter_height = 40
        meter_x = 100
        meter_y = 250
        
        # Draw background meter
        draw.rounded_rectangle(
            [meter_x, meter_y, meter_x + meter_width, meter_y + meter_height], 
            radius=10, fill=(200, 200, 200, 255)
        )
        
        # Draw filled meter portion
        fill_width = int(meter_width * love_score / 100)
        if fill_width > 0:
            draw.rounded_rectangle(
                [meter_x, meter_y, meter_x + fill_width, meter_y + meter_height], 
                radius=10, fill=(255, 105, 180, 255)
            )

        # Add text
        text = f"{love_score}% Match"
        text_width = draw.textlength(text, font=self.font)
        draw.text((300 - text_width/2, 310), text, font=self.font, fill=(0, 0, 0, 255))

        # Convert to bytes with optimized settings
        output_buffer = io.BytesIO()
        image.save(output_buffer, format='PNG', optimize=True, compress_level=6)
        output_buffer.seek(0)

        return output_buffer

    async def _get_avatar(self, session, url, size):
        # Check cache first
        if url in self.avatar_cache:
            return self.avatar_cache[url]
            
        async with session.get(url) as response:
            if response.status != 200:
                # Use a default avatar if fetch fails
                avatar = Image.new('RGBA', size, (200, 200, 200, 255))
            else:
                avatar_data = await response.read()
                loop = asyncio.get_event_loop()
                # Process image in thread pool
                avatar = await loop.run_in_executor(
                    None,
                    functools.partial(self._process_avatar, avatar_data, size)
                )
                
        # Cache the result
        self.avatar_cache[url] = avatar
        return avatar
        
    def _process_avatar(self, avatar_data, size):
        # Process avatar data in a thread
        with io.BytesIO(avatar_data) as data_buffer:
            avatar = Image.open(data_buffer).convert("RGBA")
            return avatar.resize(size, Image.LANCZOS)

async def setup(bot):
    await bot.add_cog(LoveCog(bot))