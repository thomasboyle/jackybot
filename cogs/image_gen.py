import discord
from discord.ext import commands
import torch
import asyncio
import io
import gc
import time
from .model_manager import model_manager

class ImageGeneration(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.generation_lock = asyncio.Lock()
        
        # Initialize the shared model manager
        asyncio.create_task(self._ensure_model_loaded())
        
    def cog_unload(self):
        """Clean up resources when cog is unloaded."""
        # Note: We don't cleanup the shared model manager here as other cogs might be using it
        pass
    
    async def _ensure_model_loaded(self):
        """Ensure the shared model manager is initialized."""
        await model_manager.initialize_models()
    
    def generate_image_sync(self, prompt: str, negative_prompt: str = None, 
                          width: int = 512, height: int = 512, 
                          num_inference_steps: int = 20, guidance_scale: float = 8) -> bytes:
        """Synchronous image generation function."""
        pipeline = model_manager.get_txt2img_pipeline()
        if not pipeline:
            raise Exception("Model not loaded")
        
        if negative_prompt is None:
            negative_prompt = "blurry, bad quality, distorted, deformed, low resolution, watermark, text, signature"
        
        with torch.inference_mode():
            result = pipeline(
                prompt=prompt,
                negative_prompt=negative_prompt,
                width=width,
                height=height,
                num_inference_steps=num_inference_steps,
                guidance_scale=guidance_scale,
                generator=torch.Generator(device=model_manager.device).manual_seed(int(time.time()))
            )
            
            image = result.images[0]
            
            img_bytes = io.BytesIO()
            image.save(img_bytes, format='PNG', optimize=True)
            img_bytes.seek(0)
            
            return img_bytes.getvalue()
    
    @commands.command(name='create')
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def create_image(self, ctx, *, prompt: str):
        """Generate an AI image using Stable Diffusion 1.5.
        
        Usage: !create [your prompt here]
        Example: !create a beautiful sunset over mountains
        """
        if not model_manager.is_model_loaded():
            await ctx.reply("🔄 AI model is still loading, please wait a moment and try again.")
            return
        
        prompt = prompt.strip()
        if not prompt:
            await ctx.reply("❌ Please provide a prompt for image generation.\nExample: `!create a beautiful sunset over mountains`")
            return
        
        if len(prompt) > 500:
            await ctx.reply("❌ Prompt is too long. Please keep it under 500 characters.")
            return
        
        if self.generation_lock.locked():
            queue_embed = discord.Embed(
                title="⏳ Generation Queue",
                description=f"**Your prompt:** {prompt}\n\n🔄 Another image is currently being generated. Your request has been added to the queue.\n\n⏱️ Please wait for the current generation to complete...",
                color=0xffaa00
            )
            queue_embed.set_footer(text="You'll be notified when generation starts")
            await ctx.reply(embed=queue_embed)
        
        async with self.generation_lock:
            try:
                embed = discord.Embed(
                    title="🎨 Generating Image...",
                    description=f"**Prompt:** {prompt}\n\n⏳ This may take 30-60 seconds...",
                    color=0x00ff00
                )
                embed.set_footer(text="Powered by Stable Diffusion 1.5")
                
                status_msg = await ctx.reply(embed=embed)
                
                start_time = time.time()
                image_bytes = await asyncio.get_event_loop().run_in_executor(
                    model_manager.executor, 
                    self.generate_image_sync, 
                    prompt
                )
                generation_time = time.time() - start_time
                
                file = discord.File(
                    io.BytesIO(image_bytes), 
                    filename=f"generated_image_{int(time.time())}.png"
                )
                
                success_embed = discord.Embed(
                    title="✅ Image Generated Successfully!",
                    description=f"**Prompt:** {prompt}",
                    color=0x00ff00
                )
                success_embed.set_footer(text=f"Generated in {generation_time:.1f}s • Stable Diffusion 1.5")
                
                try:
                    await status_msg.delete()
                except:
                    pass
                
                await ctx.reply(embed=success_embed, file=file)
                
            except Exception as e:
                error_embed = discord.Embed(
                    title="❌ Generation Failed",
                    description=f"**Error:** {str(e)}\n\nPlease try again in a moment.",
                    color=0xff0000
                )
                
                try:
                    await status_msg.delete()
                    await ctx.reply(embed=error_embed)
                except:
                    try:
                        await status_msg.edit(embed=error_embed)
                    except:
                        await ctx.reply(embed=error_embed)
                
                print(f"Image generation error: {e}")
                
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    gc.collect()
    
    @commands.command(name='create_advanced')
    @commands.cooldown(1, 45, commands.BucketType.user)
    async def create_image_advanced(self, ctx, *, params: str):
        """Advanced image generation with custom parameters.
        
        Usage: !create_advanced prompt="your prompt" negative="negative prompt" steps=25 guidance=7.5 size=512x512
        
        Parameters:
        - prompt: Your image description (required)
        - negative: What to avoid in the image (optional)
        - steps: Number of inference steps (10-50, default: 20)
        - guidance: Guidance scale (1-20, default: 7.5)
        - size: Image size - 512x512, 512x768, 768x512 (default: 512x512)
        """
        if not model_manager.is_model_loaded():
            await ctx.reply("🔄 AI model is still loading, please wait a moment and try again.")
            return
        
        try:
            import re
            
            prompt_match = re.search(r'prompt="([^"]*)"', params) or re.search(r'prompt=(\S+)', params)
            if not prompt_match:
                await ctx.reply("❌ Please specify a prompt.\nExample: `!create_advanced prompt=\"a beautiful sunset\"`")
                return
            
            prompt = prompt_match.group(1)
            
            negative_match = re.search(r'negative="([^"]*)"', params)
            negative_prompt = negative_match.group(1) if negative_match else None
            
            steps_match = re.search(r'steps=(\d+)', params)
            steps = max(10, min(50, int(steps_match.group(1)) if steps_match else 20))
            
            guidance_match = re.search(r'guidance=([\d.]+)', params)
            guidance = max(1.0, min(20.0, float(guidance_match.group(1)) if guidance_match else 7.5))
            
            size_match = re.search(r'size=(\d+)x(\d+)', params)
            if size_match:
                width, height = int(size_match.group(1)), int(size_match.group(2))
                allowed_sizes = [(512, 512), (512, 768), (768, 512), (640, 640)]
                if (width, height) not in allowed_sizes:
                    width, height = 512, 512
            else:
                width, height = 512, 512
            
        except Exception as e:
            await ctx.reply(f"❌ Error parsing parameters: {str(e)}\nExample: `!create_advanced prompt=\"a cat\" steps=25 guidance=8.0`")
            return
        
        if self.generation_lock.locked():
            queue_embed = discord.Embed(
                title="⏳ Advanced Generation Queue",
                description=f"**Your prompt:** {prompt}\n**Settings:** Steps: {steps} | Guidance: {guidance} | Size: {width}x{height}\n\n🔄 Another image is currently being generated. Your advanced request has been added to the queue.\n\n⏱️ Please wait for the current generation to complete...",
                color=0xffaa00
            )
            if negative_prompt:
                queue_embed.add_field(name="Negative Prompt", value=negative_prompt, inline=False)
            queue_embed.set_footer(text="Advanced generation will start once queue is clear")
            await ctx.reply(embed=queue_embed)
        
        async with self.generation_lock:
            try:
                embed = discord.Embed(
                    title="🎨 Generating Advanced Image...",
                    description=f"**Prompt:** {prompt}\n**Steps:** {steps}\n**Guidance:** {guidance}\n**Size:** {width}x{height}",
                    color=0x00ff00
                )
                if negative_prompt:
                    embed.add_field(name="Negative Prompt", value=negative_prompt, inline=False)
                embed.set_footer(text="This may take longer with advanced settings...")
                
                status_msg = await ctx.reply(embed=embed)
                
                start_time = time.time()
                image_bytes = await asyncio.get_event_loop().run_in_executor(
                    model_manager.executor,
                    self.generate_image_sync,
                    prompt, negative_prompt, width, height, steps, guidance
                )
                generation_time = time.time() - start_time
                
                file = discord.File(
                    io.BytesIO(image_bytes),
                    filename=f"advanced_generated_{int(time.time())}.png"
                )
                
                success_embed = discord.Embed(
                    title="✅ Advanced Image Generated!",
                    description=f"**Prompt:** {prompt}",
                    color=0x00ff00
                )
                success_embed.add_field(name="Settings", 
                                      value=f"Steps: {steps} | Guidance: {guidance} | Size: {width}x{height}", 
                                      inline=False)
                success_embed.set_footer(text=f"Generated in {generation_time:.1f}s • Stable Diffusion 1.5")
                
                try:
                    await status_msg.delete()
                except:
                    pass
                
                await ctx.reply(embed=success_embed, file=file)
                
            except Exception as e:
                error_embed = discord.Embed(
                    title="❌ Advanced Generation Failed",
                    description=f"**Error:** {str(e)}",
                    color=0xff0000
                )
                
                try:
                    await status_msg.delete()
                    await ctx.reply(embed=error_embed)
                except:
                    try:
                        await status_msg.edit(embed=error_embed)
                    except:
                        await ctx.reply(embed=error_embed)
                
                print(f"Advanced image generation error: {e}")
                
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    gc.collect()
    
    @commands.command(name='model_status')
    async def model_status(self, ctx):
        """Check the status of the AI image generation model."""
        if model_manager.is_model_loaded():
            model_info = model_manager.get_model_info()
            embed = discord.Embed(
                title="🟢 Model Status: Ready",
                description=f"{model_info['model_name']} is loaded and ready for image generation!",
                color=0x00ff00
            )
            
            if torch.cuda.is_available():
                try:
                    vram_allocated = torch.cuda.memory_allocated() / 1024**3
                    vram_cached = torch.cuda.memory_reserved() / 1024**3
                    embed.add_field(name="VRAM Usage", 
                                  value=f"Allocated: {vram_allocated:.1f}GB\nCached: {vram_cached:.1f}GB", 
                                  inline=True)
                except:
                    pass
            
            embed.add_field(name="Device", value=model_info['device_name'], inline=True)
            embed.add_field(name="Model", value=model_info['model_name'], inline=True)
            embed.add_field(name="Commands", value="`!create` - Basic generation\n`!create_advanced` - Advanced options", inline=False)
        else:
            embed = discord.Embed(
                title="🟡 Model Status: Loading",
                description="The AI model is still loading. Please wait a moment before generating images.",
                color=0xffff00
            )
        
        await ctx.reply(embed=embed)

async def setup(bot):
    await bot.add_cog(ImageGeneration(bot))
