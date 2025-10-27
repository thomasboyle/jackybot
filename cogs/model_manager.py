import torch
from diffusers import StableDiffusionXLPipeline, UNet2DConditionModel, EulerDiscreteScheduler
from huggingface_hub import hf_hub_download
from safetensors.torch import load_file
import asyncio
import os
import gc
from concurrent.futures import ThreadPoolExecutor
import discord
from discord.ext import commands

class SharedModelManager:
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
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model_loaded = False
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.initialization_lock = asyncio.Lock()
        
        self.base_model = "stabilityai/stable-diffusion-xl-base-1.0"
        self.lightning_repo = "ByteDance/SDXL-Lightning"
        self.lightning_checkpoint = "sdxl_lightning_4step_unet.safetensors"
        self.inference_steps = 4
        
        self.cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "cache")

        self.torch_dtype = torch.float16 if self.device == "cuda" else torch.float32
        
        self._initialized = True
    
    async def initialize_models(self):
        if self.model_loaded:
            return
            
        async with self.initialization_lock:
            if self.model_loaded:
                return
                
            try:
                await self._load_sdxl_lightning_models()

            except Exception as e:
                print(f"Error loading model: {e}")
                self.model_loaded = False
    
    async def _load_sdxl_lightning_models(self):
        try:
            def load_models():
                unet = UNet2DConditionModel.from_config(
                    self.base_model, 
                    subfolder="unet"
                )
                
                # Download and load the Lightning checkpoint
                checkpoint_path = hf_hub_download(
                    self.lightning_repo, 
                    self.lightning_checkpoint,
                    cache_dir=self.cache_dir
                )
                state_dict = load_file(checkpoint_path)
                unet.load_state_dict(state_dict)
                unet = unet.to(dtype=self.torch_dtype)

                txt2img_pipeline = StableDiffusionXLPipeline.from_pretrained(
                    self.base_model,
                    unet=unet,
                    variant="fp16",
                    cache_dir=self.cache_dir
                )

                # Ensure consistent dtype across all components
                txt2img_pipeline = txt2img_pipeline.to(dtype=self.torch_dtype)

                txt2img_pipeline.scheduler = EulerDiscreteScheduler.from_config(
                    txt2img_pipeline.scheduler.config,
                    timestep_spacing="trailing"
                )

                if self.device == "cuda":
                    # Optimized for GTX 1070ti (8GB VRAM)
                    txt2img_pipeline.enable_attention_slicing(slice_size="max")
                    txt2img_pipeline.enable_vae_slicing()
                    txt2img_pipeline.enable_vae_tiling()

                    # Move to GPU explicitly
                    txt2img_pipeline = txt2img_pipeline.to(self.device)
                    
                else:
                    txt2img_pipeline = txt2img_pipeline.to("cpu")

                return txt2img_pipeline
            
            self.txt2img_pipeline = await asyncio.get_event_loop().run_in_executor(
                self.executor, load_models
            )
            
            self.model_loaded = True
            print(f"Model loaded successfully using {self.inference_steps}-step inference")
            
        except Exception as e:
            print(f"Error loading model: {e}")
            import traceback
            traceback.print_exc()
            self.model_loaded = False
    
    def get_txt2img_pipeline(self):
        return self.txt2img_pipeline if self.model_loaded else None
    
    def is_model_loaded(self):
        return self.model_loaded
    
    def get_model_info(self):
        model_name = f"SDXL-Lightning ({self.inference_steps}-step)"
        device_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"
        return {
            "model_name": model_name,
            "device": self.device,
            "device_name": device_name,
            "inference_steps": self.inference_steps,
            "optimized_8gb": True
        }
    
    def cleanup_models(self):
        if self.txt2img_pipeline is not None:
            del self.txt2img_pipeline
            self.txt2img_pipeline = None
        
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.empty_cache()
        
        gc.collect()
        self.model_loaded = False
        print("Model cleaned up and memory freed")
    
    def shutdown(self):
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=False)
        self.cleanup_models()

model_manager = SharedModelManager()

class ModelManagerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.model_manager = model_manager
    
    @commands.command(name='modelstatus')
    @commands.is_owner()
    async def model_status(self, ctx):
        if self.model_manager.is_model_loaded():
            info = self.model_manager.get_model_info()
            embed = discord.Embed(
                title="Model Status",
                description="Models are loaded and ready",
                color=discord.Color.green()
            )
            embed.add_field(name="Model", value=info["model_name"], inline=True)
            embed.add_field(name="Device", value=f"{info['device']} ({info['device_name']})", inline=True)
            embed.add_field(name="8GB Optimized", value="✅" if info.get("optimized_8gb") else "❌", inline=True)
            embed.add_field(name="Inference Steps", value=str(info.get("inference_steps", "N/A")), inline=True)
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
        if not self.model_manager.is_model_loaded():
            await ctx.send("Models are not loaded!")
            return
        
        self.model_manager.cleanup_models()
        await ctx.send("✅ Models unloaded and memory freed!")

async def setup(bot):
    await bot.add_cog(ModelManagerCog(bot)) 