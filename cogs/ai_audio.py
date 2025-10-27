import discord
from discord.ext import commands
import asyncio
import os
import tempfile
import time
import gc
from concurrent.futures import ThreadPoolExecutor
from transformers import pipeline
import scipy.io.wavfile
import torch
import warnings

class AIAudio(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.generation_lock = asyncio.Lock()
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.synthesiser = None
        self.model_loaded = False
        self.model_lock = asyncio.Lock()
        self.use_bettertransformer = False
        self._configure_cpu_optimization()

    def _configure_cpu_optimization(self):
        """Configure PyTorch for aggressive CPU inference optimization."""
        torch.set_grad_enabled(False)
        
        cpu_count = os.cpu_count() or 2
        torch.set_num_threads(cpu_count)
        torch.set_num_interop_threads(1)
        
        if hasattr(torch, 'set_float32_matmul_precision'):
            torch.set_float32_matmul_precision('high')
        
        os.environ['OMP_NUM_THREADS'] = str(cpu_count)
        os.environ['MKL_NUM_THREADS'] = str(cpu_count)
        os.environ['OPENBLAS_NUM_THREADS'] = str(cpu_count)
        os.environ['VECLIB_MAXIMUM_THREADS'] = str(cpu_count)
        os.environ['NUMEXPR_NUM_THREADS'] = str(cpu_count)
        
        try:
            import intel_extension_for_pytorch as ipex
            print(f"CPU optimization: {cpu_count} threads + Intel IPEX acceleration")
        except ImportError:
            print(f"CPU optimization: {cpu_count} threads (Install intel-extension-for-pytorch for 2-3x speedup)")

    def cog_unload(self):
        """Clean up resources when cog is unloaded."""
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=False)
        self._cleanup_model()

    def _apply_dynamic_quantization(self, model):
        """Apply dynamic quantization for faster CPU inference."""
        try:
            quantized_model = torch.quantization.quantize_dynamic(
                model,
                {torch.nn.Linear, torch.nn.Conv1d},
                dtype=torch.qint8
            )
            print("Applied dynamic int8 quantization (2-4x speedup)")
            return quantized_model
        except Exception as e:
            print(f"Quantization failed, using fp32: {e}")
            return model

    def _apply_bettertransformer(self, model):
        """Apply BetterTransformer optimization if available."""
        try:
            from optimum.bettertransformer import BetterTransformer
            optimized_model = BetterTransformer.transform(model)
            self.use_bettertransformer = True
            print("Applied BetterTransformer optimization")
            return optimized_model
        except Exception as e:
            print(f"BetterTransformer not available: {e}")
            return model

    def _load_model_sync(self):
        """Load the MusicGen model with aggressive CPU optimizations."""
        if self.model_loaded:
            return True

        try:
            print("Loading MusicGen model with CPU accelerations...")
            
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                self.synthesiser = pipeline(
                    "text-to-audio",
                    "facebook/musicgen-small",
                    device="cpu",
                    torch_dtype=torch.float32
                )
            
            if hasattr(self.synthesiser.model, 'eval'):
                self.synthesiser.model.eval()
            
            for param in self.synthesiser.model.parameters():
                param.requires_grad = False
            
            try:
                import intel_extension_for_pytorch as ipex
                self.synthesiser.model = ipex.optimize(self.synthesiser.model, dtype=torch.float32)
                print("Applied Intel IPEX optimizations")
            except ImportError:
                pass
            
            self.synthesiser.model = self._apply_bettertransformer(self.synthesiser.model)
            self.synthesiser.model = self._apply_dynamic_quantization(self.synthesiser.model)
            
            try:
                torch.jit.optimize_for_inference(torch.jit.script(self.synthesiser.model))
                print("Applied JIT optimization")
            except:
                pass
            
            self.model_loaded = True
            print("MusicGen model loaded with all CPU accelerations")
            return True
        except Exception as e:
            print(f"Error loading MusicGen model: {e}")
            self.model_loaded = False
            return False

    async def _load_model(self):
        """Load the MusicGen model asynchronously."""
        async with self.model_lock:
            if self.model_loaded:
                return True

            return await asyncio.get_event_loop().run_in_executor(
                self.executor, self._load_model_sync
            )

    def _cleanup_model(self):
        """Clean up the MusicGen model and free memory."""
        if self.synthesiser is not None:
            print("Unloading MusicGen model...")
            
            if hasattr(self.synthesiser, 'model'):
                del self.synthesiser.model
            del self.synthesiser
            self.synthesiser = None
            
            gc.collect()
            
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        self.model_loaded = False
        print("MusicGen model unloaded and memory freed")

    def generate_audio_sync(self, prompt: str) -> tuple:
        """Synchronous audio generation function with aggressive CPU optimizations."""
        if not self.synthesiser:
            raise Exception("Model not loaded")

        try:
            with torch.inference_mode(), torch.cpu.amp.autocast():
                music = self.synthesiser(
                    prompt,
                    forward_params={
                        "do_sample": True,
                        "max_new_tokens": 256,
                        "num_beams": 1,
                        "temperature": 1.0,
                        "top_k": 250,
                        "top_p": 0.0
                    }
                )

            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                temp_path = temp_file.name

            audio_data = music["audio"]
            if len(audio_data.shape) > 1:
                audio_data = audio_data[0]
            
            audio_data = audio_data.squeeze()
            
            scipy.io.wavfile.write(
                temp_path,
                rate=music["sampling_rate"],
                data=audio_data
            )

            return temp_path, music["sampling_rate"]

        except Exception as e:
            print(f"Error generating audio: {e}")
            raise

    @commands.command(name='music')
    async def generate_music(self, ctx, *, prompt: str):
        """Generate AI music using MusicGen based on your text prompt.

        Usage: !music [your prompt here]
        Example: !music lo-fi hip hop beats with rain sounds
        """
        if not self.model_loaded:
            loading_msg = await ctx.reply("Loading MusicGen model for CPU inference... This may take a moment.")
            model_loaded = await self._load_model()
            if not model_loaded:
                await loading_msg.edit(content="Failed to load MusicGen model. Please try again later.")
                return
            await loading_msg.delete()

        prompt = prompt.strip()
        if not prompt:
            await ctx.reply("❌ Please provide a prompt for music generation.\nExample: `!music soothing piano melody`")
            return

        if len(prompt) > 200:
            await ctx.reply("❌ Prompt is too long. Please keep it under 200 characters.")
            return

        if self.generation_lock.locked():
            queue_embed = discord.Embed(
                title="Music Generation Queue",
                description=f"**Your prompt:** {prompt}\n\nAnother music generation is currently in progress. Your request has been added to the queue.\n\nPlease wait for the current generation to complete...",
                color=0xffaa00
            )
            queue_embed.set_footer(text="You'll be notified when generation starts")
            await ctx.reply(embed=queue_embed)

        async with self.generation_lock:
            try:
                embed = discord.Embed(
                    title="Generating Music",
                    description=f"**Prompt:** {prompt}\n\nCreating your custom music with CPU acceleration... This may take 15-45 seconds.",
                    color=0x3498db
                )
                embed.set_footer(text="Optimized for 2-core CPU with quantization + threading")
                status_msg = await ctx.reply(embed=embed)

                start_time = time.time()

                # Generate audio in thread pool to avoid blocking
                temp_path, sample_rate = await asyncio.get_event_loop().run_in_executor(
                    self.executor, self.generate_audio_sync, prompt
                )

                generation_time = time.time() - start_time

                try:
                    with open(temp_path, 'rb') as audio_file:
                        discord_file = discord.File(audio_file, filename=f"musicgen_{int(time.time())}.wav")

                        result_embed = discord.Embed(
                            title="Music Generated!",
                            description=f"**Prompt:** {prompt}\n\nGenerated in {generation_time:.1f} seconds\nSample Rate: {sample_rate}Hz\nDuration: ~5 seconds",
                            color=0x2ecc71
                        )
                        result_embed.set_footer(text="Powered by JackyBot | Accelerated CPU Inference")

                        await ctx.reply(file=discord_file, embed=result_embed)

                    await status_msg.delete()

                finally:
                    try:
                        os.unlink(temp_path)
                    except:
                        pass

            except Exception as e:
                error_embed = discord.Embed(
                    title="Generation Failed",
                    description=f"**Prompt:** {prompt}\n\nError: {str(e)}\n\nPlease try again with a different prompt.",
                    color=0xe74c3c
                )
                await ctx.reply(embed=error_embed)
                print(f"Music generation error: {e}")
                import traceback
                traceback.print_exc()

        self._cleanup_model()

async def setup(bot):
    await bot.add_cog(AIAudio(bot))
