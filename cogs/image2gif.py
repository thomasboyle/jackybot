import discord
from discord.ext import commands
import aiohttp
import os
import asyncio
from typing import Optional
import io

class Image2Gif(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.hf_token = os.environ.get("HF_TOKEN")
        self.session = None
        self.processing = set()
        
    async def cog_load(self):
        self.session = aiohttp.ClientSession()
        if not self.hf_token:
            print("Warning: HF_TOKEN not set. image2gif command will not work.")
    
    async def cog_unload(self):
        if self.session:
            await self.session.close()
    
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user or not message.guild:
            return
        
        if self.bot.user.mention in message.content and "gif that" in message.content.lower():
            await self.handle_gif_that(message)
    
    async def handle_gif_that(self, message: discord.Message):
        if message.author.id in self.processing:
            await message.reply("Already generating. Please wait.")
            return
        
        async with message.channel.typing():
            try:
                self.processing.add(message.author.id)
                image_url = await self._get_last_image(message.channel)
                
                if not image_url:
                    return await message.reply("No images found in this channel.")
                
                await message.reply("Generating GIF... This may take a moment.")
                
                gif_file = await self._generate_gif(image_url)
                
                if gif_file:
                    await message.reply(file=gif_file)
                else:
                    await message.reply("Failed to generate GIF.")
                    
            except Exception as e:
                print(f"image2gif error: {e}")
                await message.reply(f"Error: {str(e)[:100]}")
            finally:
                self.processing.discard(message.author.id)
    
    async def _get_last_image(self, channel):
        async for msg in channel.history(limit=50):
            if msg.attachments:
                for attachment in msg.attachments:
                    if attachment.content_type and attachment.content_type.startswith('image/'):
                        return attachment.url
            if msg.embeds:
                for embed in msg.embeds:
                    if embed.image:
                        return embed.image.url
        return None
    
    async def _generate_gif(self, image_url: str) -> Optional[discord.File]:
        headers = {
            "Authorization": f"Bearer {self.hf_token}"
        }
        
        payload = {
            "inputs": image_url
        }
        
        try:
            async with self.session.post(
                "https://api-inference.huggingface.co/models/cerspense/zeroscope_v2_576w",
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=300)
            ) as response:
                if response.status == 200:
                    video_data = await response.read()
                    return discord.File(
                        fp=io.BytesIO(video_data),
                        filename="generated.gif"
                    )
                else:
                    error_text = await response.text()
                    print(f"HF API error {response.status}: {error_text}")
                    return None
        except asyncio.TimeoutError:
            print("HF API request timeout")
            return None
        except Exception as e:
            print(f"Error calling HF API: {e}")
            return None

async def setup(bot):
    await bot.add_cog(Image2Gif(bot))
