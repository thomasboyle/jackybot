import discord
from discord.ext import commands
import aiohttp
import os
import io
from huggingface_hub import InferenceClient
import asyncio

class ImageToVideoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.hf_client = None
        self.model = "Lightricks/LTX-Video-0.9.8-13B-distilled"

    async def cog_load(self):
        if not (api_key := os.environ.get("HF_TOKEN")):
            raise ValueError("HF_TOKEN environment variable not set.")
        self.hf_client = InferenceClient(
            provider="fal-ai",
            api_key=api_key,
        )

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user:
            return

        if self.bot.user.mentioned_in(message) and "gif that" in message.content.lower():
            async with message.channel.typing():
                last_image = await self._get_last_image(message.channel)
                
                if not last_image:
                    await message.reply("No image found in recent messages.")
                    return

                video_data = await self._convert_image_to_video(last_image)
                
                if not video_data:
                    await message.reply("Failed to convert image to video.")
                    return

                await message.reply(
                    file=discord.File(
                        fp=io.BytesIO(video_data),
                        filename="generated_video.mp4"
                    )
                )

    async def _get_last_image(self, channel):
        try:
            async for msg in channel.history(limit=50):
                if msg.attachments:
                    for attachment in msg.attachments:
                        if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')):
                            return attachment
        except discord.Forbidden:
            return None
        return None

    async def _convert_image_to_video(self, attachment):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(attachment.url) as resp:
                    if resp.status != 200:
                        return None
                    image_data = await resp.read()

            loop = asyncio.get_event_loop()
            video = await loop.run_in_executor(
                None,
                self._generate_video,
                image_data
            )

            if not video:
                return None

            if isinstance(video, bytes):
                return video
            elif hasattr(video, 'read'):
                return video.read()
            else:
                return bytes(video)

        except Exception as e:
            print(f"Error converting image to video: {e}")
            return None

    def _generate_video(self, image_data):
        try:
            video = self.hf_client.image_to_video(
                image_data,
                prompt="Dynamic and creative animation",
                model=self.model,
            )
            return video
        except Exception as e:
            print(f"Error in image_to_video API call: {e}")
            return None

async def setup(bot):
    await bot.add_cog(ImageToVideoCog(bot))
