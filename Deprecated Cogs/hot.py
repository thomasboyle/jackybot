import discord
from discord.ext import commands
import moviepy.editor as mp
from PIL import Image
import numpy as np
import cv2
import os
import asyncio
import aiohttp
from io import BytesIO
from functools import partial

class HotDog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self.video = mp.VideoFileClip("hotdiggitydog.mp4")
        self.green_lower, self.green_upper = self._get_green_range()

    def cog_unload(self):
        asyncio.create_task(self.session.close())
        self.video.close()

    @commands.command()
    async def hot(self, ctx, user: discord.Member = None):
        user = user or ctx.author
        async with ctx.typing():
            try:
                avatar = await self._get_avatar(user)
                output_path = await self._process_video(avatar, user.id)
                await ctx.reply(f"Here's the hot diggity dog video for {user.mention}!", file=discord.File(output_path))
                os.remove(output_path)
            except Exception as e:
                await ctx.send(f"An error occurred: {str(e)}")

    async def _get_avatar(self, user):
        async with self.session.get(str(user.avatar.url)) as response:
            return Image.open(BytesIO(await response.read())).convert("RGBA")

    async def _process_video(self, avatar, user_id):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(self._video_processing, avatar, user_id))

    def _video_processing(self, avatar, user_id):
        output_path = f"walking_dead_{user_id}.mp4"
        processed_clip = self.video.fl_image(partial(self._process_frame, avatar))
        processed_clip.write_videofile(output_path, codec="libx264", audio_codec="aac", threads=4)
        return output_path

    def _process_frame(self, avatar, frame):
        frame_pil = Image.fromarray(frame)
        avatar_resized = self._resize_avatar(avatar, frame_pil.size)
        green_mask = self._create_green_mask(frame)
        return np.array(Image.composite(avatar_resized, frame_pil, Image.fromarray(green_mask)))

    @staticmethod
    def _resize_avatar(avatar, frame_size):
        avatar_ratio = avatar.width / avatar.height
        frame_ratio = frame_size[0] / frame_size[1]
        if avatar_ratio > frame_ratio:
            new_height = frame_size[1]
            new_width = int(new_height * avatar_ratio)
        else:
            new_width = frame_size[0]
            new_height = int(new_width / avatar_ratio)
        avatar_resized = avatar.resize((new_width, new_height), Image.LANCZOS)
        left = (avatar_resized.width - frame_size[0]) // 2
        top = (avatar_resized.height - frame_size[1]) // 2
        return avatar_resized.crop((left, top, left + frame_size[0], top + frame_size[1]))

    def _create_green_mask(self, frame):
        hsv = cv2.cvtColor(frame, cv2.COLOR_RGB2HSV)
        mask = cv2.inRange(hsv, self.green_lower, self.green_upper)
        kernel = np.ones((3,3), np.uint8)
        mask = cv2.erode(mask, kernel, iterations=1)
        return cv2.dilate(mask, kernel, iterations=2)

    @staticmethod
    def _get_green_range():
        green_rgb = np.uint8([[[63, 249, 0]]])
        hue = cv2.cvtColor(green_rgb, cv2.COLOR_RGB2HSV)[0][0][0]
        return np.array([hue - 10, 100, 100]), np.array([hue + 10, 255, 255])

async def setup(bot):
    await bot.add_cog(HotDog(bot))