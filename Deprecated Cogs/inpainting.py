import discord
from discord.ext import commands
import PIL
import aiohttp
import torch
from diffusers import StableDiffusionInstructPix2PixPipeline, EulerAncestralDiscreteScheduler
import io
import asyncio
from functools import partial

class PaintCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.model_id = "timbrooks/instruct-pix2pix"
        self.pipe = None
        self.session = None
        self.last_use_time = 0
        self.inactivity_threshold = 300  # 5 minutes

    async def cog_load(self):
        self.session = aiohttp.ClientSession()

    async def cog_unload(self):
        if self.session:
            await self.session.close()
        self.unload_model()

    def load_model(self):
        if self.pipe is None:
            torch.cuda.empty_cache()
            
            self.pipe = StableDiffusionInstructPix2PixPipeline.from_pretrained(
                self.model_id,
                torch_dtype=torch.float16,
                safety_checker=None,
                use_safetensors=True,
                low_cpu_mem_usage=True,
                device_map="auto"
            )
            self.pipe.scheduler = EulerAncestralDiscreteScheduler.from_config(self.pipe.scheduler.config)
            self.pipe.enable_xformers_memory_efficient_attention()

    def unload_model(self):
        if self.pipe is not None:
            del self.pipe
            self.pipe = None
            torch.cuda.empty_cache()

    def check_vram_usage(self):
        if torch.cuda.is_available():
            return torch.cuda.memory_allocated() / torch.cuda.max_memory_allocated()
        return 0

    async def download_image(self, url):
        if not self.session:
            self.session = aiohttp.ClientSession()
        async with self.session.get(url) as response:
            if response.status != 200:
                raise ValueError(f"Failed to download image: HTTP status {response.status}")
            image_data = await response.read()
            image = PIL.Image.open(io.BytesIO(image_data))
            image = PIL.ImageOps.exif_transpose(image)
            
            max_size = 768  # Stable Diffusion works best with images around this size
            if max(image.size) > max_size:
                ratio = max_size / max(image.size)
                new_size = tuple(int(dim * ratio) for dim in image.size)
                image = image.resize(new_size, PIL.Image.LANCZOS)
            
            return image.convert("RGB")

    async def generate_image(self, prompt, image):
        if self.pipe is None:
            self.load_model()
        
        loop = asyncio.get_running_loop()
        try:
            with torch.inference_mode(), torch.cuda.amp.autocast():
                images = await loop.run_in_executor(
                    None,
                    partial(
                        self.pipe,
                        prompt,
                        image=image,
                        num_inference_steps=20,
                        image_guidance_scale=1,
                        guidance_scale=6,
                        generator=torch.Generator("cuda").manual_seed(42)
                    )
                )
            return images.images[0]
        finally:
            self.last_use_time = asyncio.get_event_loop().time()
            
            if torch.cuda.memory_allocated() / torch.cuda.get_device_properties(0).total_memory > 0.9:
                self.unload_model()

    async def cleanup_memory(self):
        """Aggressive memory cleanup function"""
        if self.pipe is not None:
            self.unload_model()
        torch.cuda.empty_cache()
        import gc
        gc.collect()

    @commands.command(name='paint')
    async def paint_command(self, ctx, *, prompt):
        if not ctx.message.attachments:
            await ctx.send("Please attach an image to edit.")
            return

        await ctx.send("Processing your image. This may take a moment...")

        try:
            # Download the attached image
            image_url = ctx.message.attachments[0].url
            image = await self.download_image(image_url)

            # Generate the image asynchronously
            result_image = await self.generate_image(prompt, image)

            # Convert PIL image to bytes and send
            image_binary = io.BytesIO()
            result_image.save(image_binary, format='PNG')
            image_binary.seek(0)
            
            await ctx.send(file=discord.File(fp=image_binary, filename='result.png'))
        except Exception as e:
            await ctx.send(f"An error occurred: {str(e)}")
            await self.cleanup_memory()
        finally:
            current_time = asyncio.get_event_loop().time()
            if current_time - self.last_use_time > self.inactivity_threshold:
                await self.cleanup_memory()

async def setup(bot):
    await bot.add_cog(PaintCog(bot))