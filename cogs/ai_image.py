import discord
from discord.ext import commands
import torch
from diffusers import StableDiffusionPipeline
import io
import asyncio
from concurrent.futures import ThreadPoolExecutor
import gc
import psutil

class AIImageCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.model = None
        self.lock = asyncio.Lock()

    def generate_image_sync(self, prompt, width=512, height=512):
        gc.collect()
        with torch.no_grad():
            torch.manual_seed(42)
            image = self.model(
                prompt=prompt, width=width, height=height,
                num_inference_steps=10, guidance_scale=7.5,
                output_type="pil", generator=torch.Generator("cpu").manual_seed(42)
            ).images[0]
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        buffer.seek(0)
        del image
        gc.collect()
        return buffer

    @commands.command(name='imagine')
    async def create_image(self, ctx, *, args=""):
        if not args.strip():
            return await ctx.reply("Usage: `!imagine [prompt] 512x512`")

        parts = args.rsplit(' ', 2)
        if len(parts) >= 2 and 'x' in parts[-1]:
            prompt = ' '.join(parts[:-1])
            try:
                width, height = map(int, parts[-1].split('x'))
                if not (256 <= width <= 1024 and 256 <= height <= 1024):
                    return await ctx.reply("Resolution must be 256x256 to 1024x1024")
            except ValueError:
                return await ctx.reply("Invalid resolution format")
        else:
            prompt = args
            width, height = 512, 512

        if len(prompt) > 200:
            return await ctx.reply("Prompt too long (max 200 chars)")

        async with self.lock:
            message = await ctx.reply("Generating image... (30-60s)")
            try:
                if not self.model:
                    memory = psutil.virtual_memory()
                    if memory.available / (1024**3) < 0.5:
                        return await message.edit(content="Low memory")
                    self.model = StableDiffusionPipeline.from_pretrained(
                        "segmind/tiny-sd", torch_dtype=torch.float16,
                        device="cpu", low_cpu_mem_usage=True
                    ).to("cpu")
                    self.model.enable_attention_slicing(slice_size="max")
                    self.model.enable_vae_slicing()

                memory = psutil.virtual_memory()
                if memory.available / (1024**3) < 0.3:
                    return await message.edit(content="Low memory")

                buffer = await asyncio.get_event_loop().run_in_executor(
                    self.executor, self.generate_image_sync, prompt, width, height
                )

                file = discord.File(buffer, f"generated_{width}x{height}.png")
                embed = discord.Embed(
                    title="Generated Image",
                    description=f"**Prompt:** {prompt}\n**Size:** {width}x{height}",
                    color=0x00ff00
                )
                embed.set_image(url=f"attachment://generated_{width}x{height}.png")
                await message.edit(content=None, embed=embed, attachments=[file])

            except Exception as e:
                print(f"Error: {e}")
                await message.edit(content="Generation failed")

async def setup(bot):
    await bot.add_cog(AIImageCog(bot))
