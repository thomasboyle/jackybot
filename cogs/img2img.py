import discord
from discord.ext import commands
import torch
import asyncio
import io
import time
import requests
from PIL import Image
from .model_manager import model_manager

class Img2Img(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.generation_lock = asyncio.Lock()
        
        # Pre-calculate common values
        self.default_negative_prompt = "blurry, bad quality, distorted, deformed, low resolution, watermark, text, signature"
        self.image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp'}
        
        # Initialize the shared model manager
        asyncio.create_task(self._ensure_model_loaded())
        
    def cog_unload(self):
        """Clean up resources when cog is unloaded."""
        # Note: We don't cleanup the shared model manager here as other cogs might be using it
        pass
    
    async def _ensure_model_loaded(self):
        """Ensure the shared model manager is initialized."""
        await model_manager.initialize_models()
    
    async def download_image(self, url: str) -> Image.Image:
        """Download image from URL and return PIL Image."""
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return Image.open(io.BytesIO(response.content)).convert('RGB')
        except Exception as e:
            raise Exception(f"Failed to download image: {e}")
    
    def edit_image_sync(self, image: Image.Image, prompt: str, negative_prompt: str = None, 
                       strength: float = 0.75, num_inference_steps: int = 20, 
                       guidance_scale: float = 8) -> bytes:
        """Synchronous image editing function."""
        pipeline = model_manager.get_img2img_pipeline()
        if not pipeline:
            raise Exception("Model not loaded")
        
        negative_prompt = negative_prompt or self.default_negative_prompt
        
        # Optimized image resizing - single pass calculation
        w, h = image.size
        if w > 512 or h > 512:
            ratio = min(512 / w, 512 / h)
            # Bitwise operations for 8-alignment (faster than modulo)
            new_w = int(w * ratio) & ~7
            new_h = int(h * ratio) & ~7
            image = image.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        with torch.inference_mode():
            result = pipeline(
                prompt=prompt,
                image=image,
                negative_prompt=negative_prompt,
                strength=strength,
                num_inference_steps=num_inference_steps,
                guidance_scale=guidance_scale,
                generator=torch.Generator(device=model_manager.device).manual_seed(int(time.time()))
            )
            
            # Direct bytes conversion without intermediate storage
            img_bytes = io.BytesIO()
            result.images[0].save(img_bytes, format='PNG', optimize=True)
            return img_bytes.getvalue()
    
    def _create_embed(self, title: str, description: str, color: int) -> discord.Embed:
        """Create standardized embed."""
        return discord.Embed(title=title, description=description, color=color)
    
    def _validate_image_attachment(self, ctx) -> str:
        """Validate and return image URL from attachments."""
        if not ctx.message.attachments:
            return None
        
        attachment = ctx.message.attachments[0]
        filename_lower = attachment.filename.lower()
        return attachment.url if any(filename_lower.endswith(ext) for ext in self.image_extensions) else None
    
    async def _process_image_edit(self, ctx, prompt: str, image_url: str, strength: float = 0.75, 
                                 steps: int = 20, guidance: float = 8, advanced_params: str = ""):
        """Consolidated image processing logic."""
        desc = f"**Prompt:** {prompt}{advanced_params}\n\n🔄 AI is working on your image...\n⏱️ This may take 30-60 seconds"
        processing_msg = await ctx.reply(embed=self._create_embed("🎨 Editing Your Image", desc, 0x0099ff))
        
        try:
            input_image = await self.download_image(image_url)
        except Exception as e:
            await processing_msg.edit(embed=self._create_embed("❌ Error", f"Failed to download image: {str(e)}", 0xff0000))
            return
        
        try:
            image_bytes = await asyncio.get_event_loop().run_in_executor(
                model_manager.executor, self.edit_image_sync, input_image, prompt, None, strength, steps, guidance
            )
            
            desc = f"**Prompt:** {prompt}{advanced_params}\n**Edited by:** {ctx.author.display_name}"
            result_embed = self._create_embed("✅ Image Edited Successfully", desc, 0x00ff00)
            result_embed.set_footer(text="Powered by Stable Diffusion • DreamShaper v8")
            edited_file = discord.File(io.BytesIO(image_bytes), filename="edited_image.png")
            await processing_msg.edit(embed=result_embed, attachments=[edited_file])
            
        except Exception as e:
            await processing_msg.edit(embed=self._create_embed(
                "❌ Generation Failed", 
                f"Error during image editing: {str(e)}\n\nPlease try again or contact support.",
                0xff0000
            ))
    
    @commands.command(name='edit')
    @commands.cooldown(1, 45, commands.BucketType.user)
    async def edit_image(self, ctx, *, prompt: str):
        """Edit an image using AI with Stable Diffusion img2img.
        
        Usage: !edit [your prompt here]
        Attach an image to your message (upload or paste)
        
        Example: !edit make this photo look like a painting
        """
        if not model_manager.is_model_loaded():
            await ctx.reply("🔄 AI img2img model is still loading, please wait a moment and try again.")
            return
        
        prompt = prompt.strip()
        if not prompt:
            await ctx.reply("❌ Please provide a prompt for image editing.\nExample: `!edit make this photo look like a painting`")
            return
        
        if len(prompt) > 500:
            await ctx.reply("❌ Prompt is too long. Please keep it under 500 characters.")
            return
        
        image_url = self._validate_image_attachment(ctx)
        if not image_url:
            await ctx.reply("❌ Please attach a valid image file (PNG, JPG, JPEG, GIF, BMP, or WebP).")
            return
        
        if self.generation_lock.locked():
            desc = f"**Your prompt:** {prompt}\n\n🔄 Another image is currently being edited. Your request has been added to the queue.\n\n⏱️ Please wait for the current generation to complete..."
            await ctx.reply(embed=self._create_embed("⏳ Image Editing Queue", desc, 0xffaa00))
        
        async with self.generation_lock:
            await self._process_image_edit(ctx, prompt, image_url)
    
    @commands.command(name='edit_advanced')
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def edit_image_advanced(self, ctx, *, params: str):
        """Advanced image editing with custom parameters.
        
        Usage: !edit_advanced [prompt] --strength [0.1-1.0] --steps [10-50] --guidance [1-20]
        Attach an image to your message
        
        Parameters:
        - strength: How much to change the image (0.1=subtle, 1.0=major changes)
        - steps: Number of denoising steps (more = higher quality, slower)
        - guidance: How closely to follow the prompt (higher = more adherence)
        
        Example: !edit_advanced turn into a oil painting --strength 0.8 --steps 30 --guidance 10
        """
        if not model_manager.is_model_loaded():
            await ctx.reply("🔄 AI img2img model is still loading, please wait a moment and try again.")
            return
        
        # Optimized parameter parsing - single pass
        parts = params.split('--')
        prompt = parts[0].strip()
        
        if not prompt:
            await ctx.reply("❌ Please provide a prompt for image editing.")
            return
        
        # Default values
        strength, steps, guidance = 0.75, 20, 8
        
        # Single-pass parameter parsing with optimized validation
        param_processors = {
            'strength': (lambda x: max(0.1, min(1.0, float(x))), 'strength'),
            'steps': (lambda x: max(10, min(50, int(x))), 'steps'),
            'guidance': (lambda x: max(1, min(20, float(x))), 'guidance')
        }
        
        for part in parts[1:]:
            tokens = part.strip().split(None, 1)
            if len(tokens) >= 2:
                param, value_str = tokens[0], tokens[1].split()[0]
                if param in param_processors:
                    try:
                        processor, _ = param_processors[param]
                        locals()[param] = processor(value_str)
                    except ValueError:
                        await ctx.reply(f"❌ Invalid {param} value. Use --{param} [valid range]")
                        return
        
        image_url = self._validate_image_attachment(ctx)
        if not image_url:
            await ctx.reply("❌ Please attach a valid image file (PNG, JPG, JPEG, GIF, BMP, or WebP).")
            return
        
        if self.generation_lock.locked():
            desc = f"**Your prompt:** {prompt}\n**Settings:** Strength: {strength}, Steps: {steps}, Guidance: {guidance}\n\n🔄 Another image is currently being edited. Your request has been added to the queue."
            await ctx.reply(embed=self._create_embed("⏳ Advanced Image Editing Queue", desc, 0xffaa00))
        
        advanced_params = f"\n**Strength:** {strength}\n**Steps:** {steps}\n**Guidance:** {guidance}"
        
        async with self.generation_lock:
            await self._process_image_edit(ctx, prompt, image_url, strength, steps, guidance, advanced_params)
    
    @commands.command(name='img2img_status')
    async def img2img_status(self, ctx):
        """Check the status of the img2img model."""
        if model_manager.is_model_loaded():
            model_info = model_manager.get_model_info()
            desc = f"✅ **Status:** Ready\n🤖 **Model:** {model_info['model_name']}\n💾 **Device:** {model_info['device_name']}"
            embed = self._create_embed("🎨 Img2Img Model Status", desc, 0x00ff00)
        else:
            embed = self._create_embed("🎨 Img2Img Model Status", "❌ **Status:** Not loaded or loading...", 0xff0000)
        
        await ctx.reply(embed=embed)

async def setup(bot):
    await bot.add_cog(Img2Img(bot)) 