import discord
from discord.ext import commands
import asyncio
import io
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from transformers import pipeline
import scipy.io.wavfile
import numpy as np

class AIAudio(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.generation_lock = asyncio.Lock()
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.synthesiser = None
        self.model_loaded = False
        self.model_lock = asyncio.Lock()  # Lock for model loading/unloading

    def cog_unload(self):
        """Clean up resources when cog is unloaded."""
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=False)
        self._cleanup_model()

    def _load_model_sync(self):
        """Load the MusicGen model synchronously."""
        if self.model_loaded:
            return True

        try:
            print("Loading MusicGen model...")
            self.synthesiser = pipeline("text-to-audio", "facebook/musicgen-small")
            self.model_loaded = True
            print("✅ MusicGen model loaded successfully!")
            return True
        except Exception as e:
            print(f"❌ Error loading MusicGen model: {e}")
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
        """Clean up the MusicGen model and free VRAM."""
        if self.synthesiser is not None:
            print("Unloading MusicGen model...")
            del self.synthesiser
            self.synthesiser = None

        # Clear CUDA cache if available
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                print("✅ CUDA cache cleared")
        except ImportError:
            pass

        self.model_loaded = False
        print("✅ MusicGen model unloaded and VRAM freed")

    def generate_audio_sync(self, prompt: str) -> tuple:
        """Synchronous audio generation function."""
        if not self.synthesiser:
            raise Exception("Model not loaded")

        try:
            # Generate music with the given prompt
            # MusicGen generates ~5 seconds with 256 tokens, ~10 seconds with 512 tokens
            # Using 500 tokens for approximately 10 seconds of audio
            music = self.synthesiser(
                prompt,
                forward_params={"do_sample": True, "max_new_tokens": 500}
            )

            # Create temporary file
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_file:
                temp_path = temp_file.name

            # Save the generated audio
            scipy.io.wavfile.write(
                temp_path,
                rate=music["sampling_rate"],
                data=music["audio"]
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
        # Load model if not already loaded
        if not self.model_loaded:
            loading_msg = await ctx.reply("🔄 Loading MusicGen model... This may take a moment.")
            model_loaded = await self._load_model()
            if not model_loaded:
                await loading_msg.edit(content="❌ Failed to load MusicGen model. Please try again later.")
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
                title="⏳ Music Generation Queue",
                description=f"**Your prompt:** {prompt}\n\n🔄 Another music generation is currently in progress. Your request has been added to the queue.\n\n⏱️ Please wait for the current generation to complete...",
                color=0xffaa00
            )
            queue_embed.set_footer(text="You'll be notified when generation starts")
            await ctx.reply(embed=queue_embed)

        async with self.generation_lock:
            try:
                # Send initial generation message
                embed = discord.Embed(
                    title="🎵 Generating Music",
                    description=f"**Prompt:** {prompt}\n\n🎼 Creating your custom music... This may take 10-30 seconds.",
                    color=0x3498db
                )
                embed.set_footer(text="Please be patient, AI music generation takes time")
                status_msg = await ctx.reply(embed=embed)

                start_time = time.time()

                # Generate audio in thread pool to avoid blocking
                temp_path, sample_rate = await asyncio.get_event_loop().run_in_executor(
                    self.executor, self.generate_audio_sync, prompt
                )

                generation_time = time.time() - start_time

                try:
                    # Send the generated audio file
                    with open(temp_path, 'rb') as audio_file:
                        discord_file = discord.File(audio_file, filename=f"musicgen_{int(time.time())}.wav")

                        result_embed = discord.Embed(
                            title="🎵 Music Generated!",
                            description=f"**Prompt:** {prompt}\n\n✅ Generated in {generation_time:.1f} seconds\n🎚️ Sample Rate: {sample_rate}Hz\n⏱️ Duration: ~10 seconds",
                            color=0x2ecc71
                        )
                        result_embed.set_footer(text="Powered by JackyBot")

                        await ctx.reply(file=discord_file, embed=result_embed)

                    # Update status message
                    await status_msg.delete()

                finally:
                    # Clean up temporary file
                    try:
                        os.unlink(temp_path)
                    except:
                        pass

            except Exception as e:
                error_embed = discord.Embed(
                    title="❌ Generation Failed",
                    description=f"**Prompt:** {prompt}\n\n❌ Error: {str(e)}\n\nPlease try again with a different prompt.",
                    color=0xe74c3c
                )
                await ctx.reply(embed=error_embed)
                print(f"Music generation error: {e}")
                import traceback
                traceback.print_exc()

        # Clean up model after generation (whether successful or failed)
        self._cleanup_model()

async def setup(bot):
    await bot.add_cog(AIAudio(bot))
