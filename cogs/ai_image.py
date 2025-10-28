import discord
from discord.ext import commands
import torch
from diffusers import StableDiffusionPipeline
import io
from PIL import Image
import asyncio
from concurrent.futures import ThreadPoolExecutor
import gc
import psutil
import os


class AIImageCog(commands.Cog):
    """CPU-optimized text-to-image generation cog using Tiny SD"""

    def __init__(self, bot):
        self.bot = bot
        self.executor = ThreadPoolExecutor(max_workers=1)  # Single worker for memory control
        self.model = None
        self.model_loaded = False
        self.generation_lock = asyncio.Lock()

    async def load_model(self):
        """Load Tiny SD model on first use"""
        if self.model_loaded:
            return True

        try:
            # Check available RAM before loading
            memory = psutil.virtual_memory()
            available_gb = memory.available / (1024**3)

            if available_gb < 1.0:
                raise MemoryError("Insufficient RAM (< 1GB available)")

            # Load Tiny SD model - very lightweight diffusion model optimized for CPU
            self.model = StableDiffusionPipeline.from_pretrained(
                "segmind/tiny-sd",
                torch_dtype=torch.float32,  # Use float32 for CPU compatibility
                device="cpu",
                low_cpu_mem_usage=True  # Optimize for low memory
            )

            # Enable memory efficient attention
            self.model.enable_attention_slicing(slice_size="auto")

            self.model_loaded = True
            return True

        except Exception as e:
            print(f"Failed to load Tiny SD model: {e}")
            return False

    def generate_image_sync(self, prompt: str, width: int = 512, height: int = 512):
        """Synchronous image generation function"""
        try:
            # Force garbage collection before generation
            gc.collect()

            # Generate image with TinyLDM
            with torch.no_grad():
                # Set manual seed for reproducible results
                torch.manual_seed(42)

                # Generate image
                image = self.model(
                    prompt=prompt,
                    width=width,
                    height=height,
                    num_inference_steps=10,  # Very few steps for speed
                    guidance_scale=7.5,
                    output_type="pil"
                ).images[0]

            # Convert to bytes
            img_buffer = io.BytesIO()
            image.save(img_buffer, format='PNG')
            img_buffer.seek(0)

            # Force cleanup
            del image
            gc.collect()

            return img_buffer

        except Exception as e:
            raise e

    @commands.command(name='imagine')
    async def create_image(self, ctx, *, args: str = ""):
        """Generate an image from text prompt. Usage: !imagine [prompt] 512x512"""

        # Parse arguments
        if not args.strip():
            await ctx.reply("Please provide a prompt. Usage: `!imagine [prompt] 512x512`")
            return

        # Split prompt and resolution
        parts = args.rsplit(' ', 2)
        if len(parts) >= 2 and 'x' in parts[-1]:
            prompt = ' '.join(parts[:-1])
            try:
                width, height = map(int, parts[-1].split('x'))
                if width > 1024 or height > 1024 or width < 256 or height < 256:
                    await ctx.reply("Resolution must be between 256x256 and 1024x1024")
                    return
            except ValueError:
                await ctx.reply("Invalid resolution format. Use format like `512x512`")
                return
        else:
            prompt = args
            width, height = 512, 512

        # Check prompt length
        if len(prompt) > 200:
            await ctx.reply("Prompt too long (max 200 characters)")
            return

        async with self.generation_lock:
            # Send initial message
            message = await ctx.reply("🎨 Generating image... This may take 30-60 seconds.")

            try:
                # Load model if not loaded
                if not await self.load_model():
                    await message.edit(content="❌ Failed to load AI model. Please try again later.")
                    return

                # Check memory before generation
                memory = psutil.virtual_memory()
                if memory.available / (1024**3) < 0.8:  # Less than 800MB available
                    await message.edit(content="❌ Insufficient memory available. Please try again later.")
                    return

                # Generate image in thread pool to avoid blocking
                img_buffer = await asyncio.get_event_loop().run_in_executor(
                    self.executor,
                    self.generate_image_sync,
                    prompt,
                    width,
                    height
                )

                # Send the image
                file = discord.File(img_buffer, filename=f"generated_{width}x{height}.png")
                embed = discord.Embed(
                    title="🎨 Generated Image",
                    description=f"**Prompt:** {prompt}\n**Resolution:** {width}x{height}",
                    color=0x00ff00
                )
                embed.set_image(url=f"attachment://generated_{width}x{height}.png")

                await message.edit(content=None, embed=embed, attachments=[file])

            except asyncio.TimeoutError:
                await message.edit(content="❌ Generation timed out. Please try again.")
            except MemoryError:
                await message.edit(content="❌ Insufficient memory. Please try again later.")
            except Exception as e:
                print(f"Image generation error: {e}")
                await message.edit(content="❌ Failed to generate image. Please try again.")

    @commands.command(name='model_status')
    async def model_status(self, ctx):
        """Check if the AI model is loaded and show memory usage"""
        memory = psutil.virtual_memory()
        memory_usage = f"{memory.used / (1024**3):.1f}GB / {memory.total / (1024**3):.1f}GB"

        status = "✅ Loaded" if self.model_loaded else "❌ Not loaded"
        embed = discord.Embed(
            title="🤖 AI Model Status",
            color=0x0099ff
        )
        embed.add_field(name="Model Status", value=status, inline=True)
        embed.add_field(name="Memory Usage", value=memory_usage, inline=True)
        embed.add_field(name="Available RAM", value=f"{memory.available / (1024**3):.1f}GB", inline=True)

        await ctx.reply(embed=embed)


async def setup(bot):
    await bot.add_cog(AIImageCog(bot))
