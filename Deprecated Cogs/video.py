import discord
from discord.ext import commands
import torch
from diffusers import AnimateDiffPipeline, MotionAdapter, EulerDiscreteScheduler
from diffusers.utils import export_to_gif
from huggingface_hub import hf_hub_download
from safetensors.torch import load_file
import io
import asyncio
import functools

class VideoGenerationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.device = "cuda"
        self.dtype = torch.float16
        self.step = 4
        self.repo = "ByteDance/AnimateDiff-Lightning"
        self.ckpt = f"animatediff_lightning_{self.step}step_diffusers.safetensors"
        self.base = "emilianJR/epiCRealism"

        # Initialize the pipeline
        self.initialize_pipeline()

    def initialize_pipeline(self):
        adapter = MotionAdapter().to(self.device, self.dtype)
        adapter.load_state_dict(load_file(hf_hub_download(self.repo, self.ckpt), device=self.device))
        
        self.pipe = AnimateDiffPipeline.from_pretrained(
            self.base, 
            motion_adapter=adapter, 
            torch_dtype=self.dtype
        ).to(self.device)
        
        self.pipe.scheduler = EulerDiscreteScheduler.from_config(
            self.pipe.scheduler.config, 
            timestep_spacing="trailing", 
            beta_schedule="linear"
        )

    def generate_video(self, prompt):
        with torch.inference_mode():
            output = self.pipe(
                prompt=prompt,
                guidance_scale=1.0,
                num_inference_steps=self.step
            )

        # Convert frames to GIF
        gif_bytes = io.BytesIO()
        export_to_gif(output.frames[0], gif_bytes)
        gif_bytes.seek(0)

        # Clear CUDA cache to optimize memory usage
        torch.cuda.empty_cache()

        return gif_bytes

    @commands.command()
    async def video(self, ctx, *, prompt: str):
        await ctx.send("Generating video, please wait...")

        # Run the generation in a separate thread
        loop = asyncio.get_event_loop()
        gif_bytes = await loop.run_in_executor(None, functools.partial(self.generate_video, prompt))

        # Send the GIF as a reply
        await ctx.send(file=discord.File(gif_bytes, filename="animation.gif"))

async def setup(bot):
    await bot.add_cog(VideoGenerationCog(bot))