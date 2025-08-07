import discord
from discord.ext import commands
from PIL import Image
import imageio
import io
import aiohttp
import random

class TriggeredCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

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

        async with aiohttp.ClientSession() as session:
            async with session.get(attachment.url) as resp:
                if resp.status != 200:
                    await ctx.send("Failed to download the image.")
                    return
                image_data = await resp.read()

        # Process the image
        img = Image.open(io.BytesIO(image_data)).convert("RGBA")
        
        # Zoom in by 10%
        zoom_factor = 1.1
        original_width, original_height = img.size
        zoomed_width = int(original_width * zoom_factor)
        zoomed_height = int(original_height * zoom_factor)
        
        img = img.resize((zoomed_width, zoomed_height), Image.LANCZOS)
        
        # Crop to original size from the center
        left = (zoomed_width - original_width) // 2
        top = (zoomed_height - original_height) // 2
        right = left + original_width
        bottom = top + original_height
        img = img.crop((left, top, right, bottom))
        
        # Resize to 512x512
        img = img.resize((512, 512), Image.LANCZOS)

        # Load the triggered overlay
        overlay = Image.open("triggered.png").convert("RGBA")
        overlay_height = int(512 * 0.2)  # 20% of the image height
        overlay = overlay.resize((512, overlay_height))

        # Create frames for the shaking effect
        frames = []
        frame_count = 24  # 1 second of animation at 24 fps
        for _ in range(frame_count):
            frame = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
            
            # Dynamic shaking
            offset_x = random.randint(-15, 15)
            offset_y = random.randint(-15, 15)
            frame.paste(img, (offset_x, offset_y))
            
            # Shake the overlay too, but less than the main image
            overlay_offset_x = random.randint(-5, 5)
            frame.paste(overlay, (overlay_offset_x, 512 - overlay_height), overlay)
            
            frames.append(frame)

        # Save as animated GIF
        output = io.BytesIO()
        imageio.mimsave(output, frames, format='GIF', duration=1/72, loop=0)  # 48 fps animation (2x speed)
        output.seek(0)

        # Send the result
        await ctx.send(file=discord.File(output, filename="triggered.gif"))

async def setup(bot):
    await bot.add_cog(TriggeredCog(bot))