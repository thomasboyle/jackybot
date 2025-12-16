import discord
from discord.ext import commands
from PIL import Image
import imageio
import io
import aiohttp
import os
import numpy as np

class TriggeredCog(commands.Cog):
    __slots__ = ('bot', 'overlay', 'overlay_height', 'session')

    def __init__(self, bot):
        self.bot = bot
        self.overlay_height = 102
        overlay_path = os.path.join("assets", "images", "triggered.png")
        overlay = Image.open(overlay_path).convert("RGBA")
        self.overlay = overlay.resize((512, self.overlay_height))
        self.session = None

    async def cog_load(self):
        self.session = aiohttp.ClientSession()

    async def cog_unload(self):
        if self.session:
            await self.session.close()

    @commands.command()
    async def triggered(self, ctx):
        if not ctx.message.reference:
            await ctx.send("Please use this command as a reply to a message with an image.")
            return

        referenced_msg = await ctx.channel.fetch_message(ctx.message.reference.message_id)

        if not referenced_msg.attachments:
            await ctx.send("The referenced message doesn't contain an image.")
            return

        attachment = referenced_msg.attachments[0]
        if not attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
            await ctx.send("The attachment is not a supported image format.")
            return

        session = self.session or aiohttp.ClientSession()
        try:
            async with session.get(attachment.url) as resp:
                if resp.status != 200:
                    await ctx.send("Failed to download the image.")
                    return
                image_data = await resp.read()
        finally:
            if not self.session:
                await session.close()

        img = Image.open(io.BytesIO(image_data)).convert("RGBA")

        zoom_factor = 1.1
        original_width, original_height = img.size
        zoomed_width = int(original_width * zoom_factor)
        zoomed_height = int(original_height * zoom_factor)

        img = img.resize((zoomed_width, zoomed_height), Image.LANCZOS)

        left = (zoomed_width - original_width) >> 1
        top = (zoomed_height - original_height) >> 1
        img = img.crop((left, top, left + original_width, top + original_height))
        img = img.resize((512, 512), Image.LANCZOS)

        img_array = np.array(img)
        overlay_array = np.array(self.overlay)
        overlay_y = 512 - self.overlay_height

        rng = np.random.default_rng()
        offsets = rng.integers(-15, 16, size=(24, 2))
        overlay_offsets = rng.integers(-5, 6, size=24)

        frames = []
        for i in range(24):
            frame = np.zeros((512, 512, 4), dtype=np.uint8)

            ox, oy = int(offsets[i, 0]), int(offsets[i, 1])
            src_x1 = max(0, -ox)
            src_y1 = max(0, -oy)
            src_x2 = min(512, 512 - ox)
            src_y2 = min(512, 512 - oy)
            dst_x1 = max(0, ox)
            dst_y1 = max(0, oy)
            dst_x2 = dst_x1 + (src_x2 - src_x1)
            dst_y2 = dst_y1 + (src_y2 - src_y1)

            frame[dst_y1:dst_y2, dst_x1:dst_x2] = img_array[src_y1:src_y2, src_x1:src_x2]

            oox = int(overlay_offsets[i])
            ov_src_x1 = max(0, -oox)
            ov_src_x2 = min(512, 512 - oox)
            ov_dst_x1 = max(0, oox)
            ov_dst_x2 = ov_dst_x1 + (ov_src_x2 - ov_src_x1)

            overlay_slice = overlay_array[:, ov_src_x1:ov_src_x2]
            alpha = overlay_slice[:, :, 3:4].astype(np.float32) / 255.0
            bg = frame[overlay_y:, ov_dst_x1:ov_dst_x2]
            blended = (overlay_slice[:, :, :3] * alpha + bg[:, :, :3] * (1 - alpha)).astype(np.uint8)
            frame[overlay_y:, ov_dst_x1:ov_dst_x2, :3] = blended
            frame[overlay_y:, ov_dst_x1:ov_dst_x2, 3] = np.maximum(bg[:, :, 3], overlay_slice[:, :, 3])

            frames.append(Image.fromarray(frame))

        output = io.BytesIO()
        imageio.mimsave(output, frames, format='GIF', duration=1/72, loop=0)
        output.seek(0)

        await ctx.send(file=discord.File(output, filename="triggered.gif"))

async def setup(bot):
    await bot.add_cog(TriggeredCog(bot))