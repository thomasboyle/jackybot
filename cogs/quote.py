import random
import textwrap
import io
from PIL import Image, ImageDraw, ImageFont
import discord
from discord.ext import commands

class QuoteImageCog(commands.Cog):
    __slots__ = ('bot', 'last_used_image', 'FONT', 'AUTHOR_FONT', 'cached_images',
                 'text_area_left', 'text_area_right', 'text_area_width')

    def __init__(self, bot):
        self.bot = bot
        self.last_used_image = None

        base_path = "C://Users//thoma//Documents//Python Programs//JackyBot//JackyBot March 2025//JackyBot//MemeTemplates//"
        template_images = [f"{base_path}memetemplate{i}.png" for i in range(1, 8)]

        self.FONT = ImageFont.truetype(f"{base_path}American Captain.ttf", 50)
        self.AUTHOR_FONT = ImageFont.truetype(f"{base_path}American Captain.ttf", 40)

        self.cached_images = {img_path: Image.open(img_path).copy() for img_path in template_images}

        self.text_area_left = 450
        self.text_area_right = 1150
        self.text_area_width = self.text_area_right - self.text_area_left

    def create_quote_image(self, text, author):
        available_images = [img for img in self.cached_images if img != self.last_used_image]
        base_image_path = random.choice(available_images)
        self.last_used_image = base_image_path

        base_image = self.cached_images[base_image_path].copy()
        draw = ImageDraw.Draw(base_image)

        text_position_y = 200
        author_position_y = 400

        avg_char_width = draw.textlength("x", font=self.FONT)
        max_chars = int(self.text_area_width / avg_char_width * 0.9)
        wrapped_text = textwrap.fill(text, width=max_chars)

        current_h = text_position_y
        pad = 10
        for line in wrapped_text.split('\n'):
            bbox = draw.textbbox((0, 0), line, font=self.FONT)
            width = bbox[2] - bbox[0]
            height = bbox[3] - bbox[1]
            x_position = self.text_area_left + (self.text_area_width - width) // 2
            draw.text((x_position, current_h), line, font=self.FONT, fill="white")
            current_h += height + pad

        author_text = f"- {author}"
        author_bbox = draw.textbbox((0, 0), author_text, font=self.AUTHOR_FONT)
        author_width = author_bbox[2] - author_bbox[0]
        author_x = self.text_area_left + (self.text_area_width - author_width) // 2
        draw.text((author_x, author_position_y), author_text, font=self.AUTHOR_FONT, fill="white")

        output = io.BytesIO()
        base_image.save(output, format='PNG', optimize=True)
        output.seek(0)
        return output

    @commands.command()
    async def quote(self, ctx):
        if not ctx.message.reference:
            await ctx.send("Please reply to a message with the quote.")
            return

        try:
            replied_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            quote_text = replied_message.content
            author = replied_message.author.display_name

            image_buffer = self.create_quote_image(quote_text, author)
            await ctx.reply(file=discord.File(image_buffer, filename="quote.png"))

        except discord.NotFound:
            await ctx.send("Could not find the message to quote.")
        except Exception as e:
            print(f"Error in quote command: {e}")
            await ctx.send("An error occurred while processing your request.")

async def setup(bot):
    await bot.add_cog(QuoteImageCog(bot))