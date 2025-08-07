import discord
from discord.ext import commands
import ffmpeg
import os
import tempfile
from PIL import ImageFont
import textwrap
from functools import lru_cache

class VideoTextCog2(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.font_size = 24
        self.max_width_ratio = 0.9
        self.top_margin = 20
        self.char_limit = 85
        
        # Optimized font detection - check most common first, exit early
        self.font_path = next((f for f in [
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/calibri.ttf", 
            "./arial.ttf",
            "/System/Library/Fonts/Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        ] if os.path.exists(f)), None)
        
        self._font = ImageFont.truetype(self.font_path, self.font_size) if self.font_path else ImageFont.load_default()

    @lru_cache(maxsize=8)
    def get_video_dimensions(self, template_file):
        probe = ffmpeg.probe(template_file, select_streams='v:0')
        video_info = probe['streams'][0]
        return int(video_info['width']), int(video_info['height'])

    def check_text_fit(self, text, template_file):
        width, height = self.get_video_dimensions(template_file)
        
        # Optimized text wrapping with direct calculation
        wrap_width = int(width * 0.0625)  # Simplified from complex calculation
        wrapped_text = textwrap.fill(text, width=wrap_width)
        
        # Direct line count calculation
        line_count = wrapped_text.count('\n') + 1
        estimated_height = line_count * 29 + 40  # Precalculated: (font_size + 5) + top_margin * 2
        
        return wrapped_text, estimated_height < height

    def add_text_to_video(self, text, template_file):
        if not os.path.exists(template_file):
            raise FileNotFoundError(f"{template_file} not found")

        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as temp_output:
            output_path = temp_output.name

        try:
            input_video = ffmpeg.input(template_file)
            
            # Streamlined drawtext parameters
            drawtext_params = {
                'text': text,
                'fontsize': self.font_size,
                'fontcolor': 'white',
                'box': 1,
                'boxcolor': 'black@0.5',
                'boxborderw': 5,
                'x': '(w-tw)/2',
                'y': self.top_margin
            }
            
            if self.font_path:
                drawtext_params['fontfile'] = self.font_path
            
            video_with_text = input_video.video.filter('drawtext', **drawtext_params)
            
            out = ffmpeg.output(
                video_with_text,
                input_video.audio,
                output_path,
                vcodec='libx264',
                acodec='aac',
                preset='faster',
                crf=23,
                audio_bitrate='128k',
                movflags='+faststart'
            )
            
            ffmpeg.run(out, quiet=True, overwrite_output=True)
            
        except ffmpeg.Error as e:
            try:
                os.remove(output_path)
            except OSError:
                pass
            error_details = e.stderr.decode() if e.stderr else 'Unknown ffmpeg error'
            raise Exception(f"FFmpeg processing failed: {error_details}")
        
        return output_path

    async def process_video_command(self, ctx, text: str, template_file: str):
        if len(text) > self.char_limit:
            await ctx.send(f"Error: Your text exceeds the {self.char_limit} character limit. Please shorten your message.")
            return

        async with ctx.typing():
            try:
                wrapped_text, fits = self.check_text_fit(text, template_file)
                if not fits:
                    await ctx.send("Error: The text is too long to fit in the video. Please use a shorter message.")
                    return

                output_path = self.add_text_to_video(wrapped_text, template_file)
                await ctx.reply("Here's your video with text and audio:", file=discord.File(output_path))
                
                try:
                    os.remove(output_path)
                except OSError:
                    pass
                    
            except FileNotFoundError as e:
                await ctx.send(f"Error: Template file not found - {str(e)}")
            except Exception as e:
                error_msg = str(e)
                await ctx.send(f"Video processing error: {error_msg}" if "FFmpeg processing failed" in error_msg else f"An unexpected error occurred: {error_msg}")

    @commands.command()
    async def homelander(self, ctx, *, text: str):
        """Add wrapped text (max 85 chars) to the top of a different video template while preserving audio."""
        await self.process_video_command(ctx, text, "homelander.mp4")

async def setup(bot):
    await bot.add_cog(VideoTextCog2(bot))