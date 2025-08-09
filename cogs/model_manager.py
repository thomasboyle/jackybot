import torch
from diffusers import StableDiffusionPipeline, StableDiffusionImg2ImgPipeline, DPMSolverMultistepScheduler
from safetensors.torch import load_file
import asyncio
import os
import gc
from concurrent.futures import ThreadPoolExecutor
import discord
from discord.ext import commands

class SharedModelManager:
    """Shared model manager to load the model once and provide both pipelines."""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self.txt2img_pipeline = None
        self.img2img_pipeline = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model_loaded = False
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.initialization_lock = asyncio.Lock()
        
        self.custom_model_path = r"C:\Users\thoma\Documents\Python Programs\JackyBot\JackyBot March 2025\JackyBot\safetensors\dreamshaper_8.safetensors"
        self.custom_model_exists = os.path.exists(self.custom_model_path)
        
        self.torch_dtype = torch.float16 if self.device == "cuda" else torch.float32
        
        self._initialized = True
    
    async def initialize_models(self):
        """Initialize both pipelines with shared model weights."""
        if self.model_loaded:
            return
            
        async with self.initialization_lock:
            if self.model_loaded:  # Double-check after acquiring lock
                return
                
            try:
                print("Loading shared DreamShaper v8 model...")
                
                if not self.custom_model_exists:
                    print(f"Custom model not found at: {self.custom_model_path}")
                    print("Falling back to Stable Diffusion 1.5...")
                    await self._load_default_models()
                    return
                
                def load_models():
                    try:
                        print("Loading base model...")
                        base_pipeline = StableDiffusionPipeline.from_single_file(
                            self.custom_model_path,
                            torch_dtype=self.torch_dtype,
                            safety_checker=None,
                            requires_safety_checker=False,
                            use_safetensors=True
                        )
                        print("Custom DreamShaper v8 base model loaded successfully!")
                        
                    except Exception as e:
                        print(f"Error loading custom model directly: {e}")
                        print("Trying alternative loading method...")
                        
                        base_pipeline = StableDiffusionPipeline.from_pretrained(
                            "runwayml/stable-diffusion-v1-5",
                            torch_dtype=self.torch_dtype,
                            safety_checker=None,
                            requires_safety_checker=False,
                            use_safetensors=True
                        )
                        
                        custom_weights = load_file(self.custom_model_path)
                        base_pipeline.unet.load_state_dict(custom_weights, strict=False)
                        print("Custom DreamShaper v8 weights loaded successfully!")
                    
                    # Configure the base pipeline
                    if self.device == "cuda":
                        base_pipeline = base_pipeline.to(self.device)
                        base_pipeline.enable_attention_slicing(1)
                        base_pipeline.scheduler = DPMSolverMultistepScheduler.from_config(base_pipeline.scheduler.config)
                        
                        try:
                            base_pipeline.enable_xformers_memory_efficient_attention()
                            print("xFormers memory efficient attention enabled")
                        except Exception as e:
                            try:
                                base_pipeline.enable_attention_slicing("max")
                            except Exception:
                                pass
                        
                        try:
                            base_pipeline.enable_model_cpu_offload()
                            print("Model CPU offload enabled for unused components")
                        except Exception as e:
                            print(f"Model CPU offload not available: {e}")
                    
                    txt2img_pipeline = base_pipeline
                    
                    print("Creating img2img pipeline with shared components...")
                    img2img_pipeline = StableDiffusionImg2ImgPipeline(
                        vae=base_pipeline.vae,
                        text_encoder=base_pipeline.text_encoder,
                        tokenizer=base_pipeline.tokenizer,
                        unet=base_pipeline.unet,
                        scheduler=base_pipeline.scheduler,
                        safety_checker=None,
                        requires_safety_checker=False,
                        feature_extractor=getattr(base_pipeline, 'feature_extractor', None)
                    )
                    
                    return txt2img_pipeline, img2img_pipeline
                
                self.txt2img_pipeline, self.img2img_pipeline = await asyncio.get_event_loop().run_in_executor(
                    self.executor, load_models
                )
                
                self.model_loaded = True
                print("Shared DreamShaper v8 models loaded successfully!")
                
            except Exception as e:
                print(f"Error loading shared DreamShaper models: {e}")
                print("Attempting to load default Stable Diffusion 1.5 models...")
                await self._load_default_models()
    
    async def _load_default_models(self):
        """Fallback method to load default SD 1.5 models."""
        try:
            def load_models():
                # Load base txt2img pipeline
                txt2img_pipeline = StableDiffusionPipeline.from_pretrained(
                    "runwayml/stable-diffusion-v1-5",
                    torch_dtype=self.torch_dtype,
                    safety_checker=None,
                    requires_safety_checker=False,
                    use_safetensors=True
                )
                
                if self.device == "cuda":
                    txt2img_pipeline = txt2img_pipeline.to(self.device)
                    txt2img_pipeline.enable_attention_slicing(1)
                    txt2img_pipeline.scheduler = DPMSolverMultistepScheduler.from_config(txt2img_pipeline.scheduler.config)
                    
                    try:
                        txt2img_pipeline.enable_xformers_memory_efficient_attention()
                        print("xFormers memory efficient attention enabled")
                    except Exception:
                        txt2img_pipeline.enable_attention_slicing("max")
                    
                    try:
                        txt2img_pipeline.enable_model_cpu_offload()
                        print("Model CPU offload enabled for unused components")
                    except Exception as e:
                        print(f"Model CPU offload not available: {e}")
                
                # Create img2img pipeline sharing the same components
                img2img_pipeline = StableDiffusionImg2ImgPipeline(
                    vae=txt2img_pipeline.vae,
                    text_encoder=txt2img_pipeline.text_encoder,
                    tokenizer=txt2img_pipeline.tokenizer,
                    unet=txt2img_pipeline.unet,
                    scheduler=txt2img_pipeline.scheduler,
                    safety_checker=None,
                    requires_safety_checker=False,
                    feature_extractor=getattr(txt2img_pipeline, 'feature_extractor', None)
                )
                
                return txt2img_pipeline, img2img_pipeline
            
            self.txt2img_pipeline, self.img2img_pipeline = await asyncio.get_event_loop().run_in_executor(
                self.executor, load_models
            )
            
            self.model_loaded = True
            print("Default Stable Diffusion 1.5 shared models loaded successfully!")
            
        except Exception as e:
            print(f"Error loading default shared models: {e}")
            self.model_loaded = False
    
    def get_txt2img_pipeline(self):
        """Get the text-to-image pipeline."""
        return self.txt2img_pipeline if self.model_loaded else None
    
    def get_img2img_pipeline(self):
        """Get the image-to-image pipeline."""
        return self.img2img_pipeline if self.model_loaded else None
    
    def is_model_loaded(self):
        """Check if models are loaded."""
        return self.model_loaded
    
    def get_model_info(self):
        """Get information about the loaded model."""
        model_name = "DreamShaper v8" if self.custom_model_exists else "Stable Diffusion 1.5"
        device_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"
        return {
            "model_name": model_name,
            "device": self.device,
            "device_name": device_name,
            "custom_model": self.custom_model_exists
        }
    
    def cleanup_models(self):
        """Clean up pipelines and free VRAM."""
        if self.txt2img_pipeline is not None:
            del self.txt2img_pipeline
            self.txt2img_pipeline = None
        
        if self.img2img_pipeline is not None:
            del self.img2img_pipeline
            self.img2img_pipeline = None
        
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        
        gc.collect()
        self.model_loaded = False
        print("Shared models cleaned up and VRAM freed")
    
    def shutdown(self):
        """Shutdown the model manager."""
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=False)
        self.cleanup_models()

# Global instance
model_manager = SharedModelManager()

class ModelManagerCog(commands.Cog):
    """Discord cog for managing AI models."""
    
    def __init__(self, bot):
        self.bot = bot
        self.model_manager = model_manager
    
    @commands.command(name='modelstatus')
    @commands.is_owner()
    async def model_status(self, ctx):
        """Check the status of loaded models."""
        if self.model_manager.is_model_loaded():
            info = self.model_manager.get_model_info()
            embed = discord.Embed(
                title="Model Status",
                description="Models are loaded and ready",
                color=discord.Color.green()
            )
            embed.add_field(name="Model", value=info["model_name"], inline=True)
            embed.add_field(name="Device", value=f"{info['device']} ({info['device_name']})", inline=True)
            embed.add_field(name="Custom Model", value="✅" if info["custom_model"] else "❌", inline=True)
        else:
            embed = discord.Embed(
                title="Model Status",
                description="Models are not loaded",
                color=discord.Color.red()
            )
        
        await ctx.send(embed=embed)
    
    @commands.command(name='loadmodels')
    @commands.is_owner()
    async def load_models(self, ctx):
        """Load the AI models."""
        if self.model_manager.is_model_loaded():
            await ctx.send("Models are already loaded!")
            return
        
        loading_msg = await ctx.send("Loading AI models... This may take a while.")
        
        try:
            await self.model_manager.initialize_models()
            if self.model_manager.is_model_loaded():
                await loading_msg.edit(content="✅ Models loaded successfully!")
            else:
                await loading_msg.edit(content="❌ Failed to load models.")
        except Exception as e:
            await loading_msg.edit(content=f"❌ Error loading models: {str(e)}")
    
    @commands.command(name='unloadmodels')
    @commands.is_owner()
    async def unload_models(self, ctx):
        """Unload the AI models to free memory."""
        if not self.model_manager.is_model_loaded():
            await ctx.send("Models are not loaded!")
            return
        
        self.model_manager.cleanup_models()
        await ctx.send("✅ Models unloaded and memory freed!")

async def setup(bot):
    """Required setup function for Discord.py extensions."""
    await bot.add_cog(ModelManagerCog(bot)) 