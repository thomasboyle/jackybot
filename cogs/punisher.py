import discord
from discord.ext import commands
import ffmpeg
import os
import tempfile
from PIL import ImageFont
import textwrap
from functools import lru_cache
import asyncio
import contextlib

class VideoTextCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.char_limit = 85
        
        # Optimized font path selection - exit early on first match
        self.font_path = next((path for path in [
            "./arial.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/calibri.ttf"
        ] if os.path.exists(path)), None)
        
        # Pre-calculate video dimensions and wrap width
        self.video_width, self.video_height = self.get_video_dimensions()
        self.wrap_width = int(self.video_width * 0.0625)

    @commands.command()
    async def punisher(self, ctx, *, text: str):
        if len(text) > self.char_limit:
            await ctx.send(f"Error: Text exceeds {self.char_limit} character limit.")
            return

        if not os.path.exists("assets/videos/template.mp4"):
            await ctx.send("Error: template.mp4 file not found.")
            return

        try:
            async with ctx.typing():
                with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_output:
                    output_path = temp_output.name
                    try:
                        await self.process_video(text, output_path)
                        await ctx.reply(file=discord.File(output_path))
                    finally:
                        with contextlib.suppress(OSError):
                            os.remove(output_path)
        except Exception as e:
            await ctx.send(f"Error: {str(e)}")

    async def process_video(self, text, output_path):
        # Direct text wrapping without escaping (ffmpeg handles most cases)
        wrapped_text = textwrap.fill(text, width=self.wrap_width)
        
        input_video = ffmpeg.input("assets/videos/template.mp4")
        
        # Streamlined drawtext parameters
        drawtext_params = {
            'text': wrapped_text,
            'fontsize': 24,
            'fontcolor': 'white',
            'box': 1,
            'boxcolor': 'black@0.5',
            'boxborderw': 5,
            'x': '(w-tw)/2',
            'y': '20',
            'line_spacing': 5
        }
        
        if self.font_path:
            drawtext_params['fontfile'] = self.font_path.replace("\\", "/")
        
        try:
            video = input_video.video.filter('drawtext', **drawtext_params)
            output = ffmpeg.output(
                video, input_video.audio, output_path,
                vcodec='libx264', acodec='aac', preset='ultrafast',
                crf=28, bufsize='2M', threads=0
            )
            
            await asyncio.to_thread(ffmpeg.run, output, quiet=True, overwrite_output=True)
            
        except ffmpeg.Error:
            # Fallback without font
            if 'fontfile' in drawtext_params:
                del drawtext_params['fontfile']
                video = input_video.video.filter('drawtext', **drawtext_params)
                output = ffmpeg.output(
                    video, input_video.audio, output_path,
                    vcodec='libx264', acodec='aac', preset='ultrafast',
                    crf=28, bufsize='2M', threads=0
                )
                await asyncio.to_thread(ffmpeg.run, output, quiet=True, overwrite_output=True)
            else:
                raise

    @lru_cache(maxsize=1)
    def get_video_dimensions(self):
        try:
            probe = ffmpeg.probe("assets/videos/template.mp4", select_streams='v:0')
            return int(probe['streams'][0]['width']), int(probe['streams'][0]['height'])
        except Exception:
            return 1920, 1080

async def setup(bot):
    await bot.add_cog(VideoTextCog(bot))