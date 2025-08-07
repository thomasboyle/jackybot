import os
import random
import textwrap
from PIL import Image, ImageDraw, ImageFont
import discord
from discord.ext import commands

class QuoteImageCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_used_image = None
        self.BASE_PATH = "C://Users//thoma//Documents//Python Programs//JackyBot//JackyBot March 2025//JackyBot//MemeTemplates//"
        self.OUTPUT_PATH = f"{self.BASE_PATH}quote_output.png"
        self.TEMPLATE_IMAGES = [f"{self.BASE_PATH}memetemplate{i}.png" for i in range(1, 8)]
        
        # Initialize fonts once during initialization
        self.FONT = ImageFont.truetype(f"{self.BASE_PATH}American Captain.ttf", 50)
        self.AUTHOR_FONT = ImageFont.truetype(f"{self.BASE_PATH}American Captain.ttf", 40)
        
        # Preload and cache all template images
        self.cached_images = {}
        for img_path in self.TEMPLATE_IMAGES:
            self.cached_images[img_path] = Image.open(img_path).copy()

    def create_quote_image(self, text, author):
        try:
            # Select a random template image, excluding the last used one
            available_images = [img for img in self.TEMPLATE_IMAGES if img != self.last_used_image]
            base_image_path = random.choice(available_images)
            self.last_used_image = base_image_path

            # Use cached image and create a copy to avoid modifying the original
            base_image = self.cached_images[base_image_path].copy()
            draw = ImageDraw.Draw(base_image)

            # Define text area boundaries
            text_area_left, text_area_right = 450, 1150
            text_area_width = text_area_right - text_area_left
            text_position_y, author_position_y = 200, 400
            text_color = "white"

            # Calculate optimal text width for wrapping based on font metrics
            avg_char_width = draw.textlength("x", font=self.FONT)
            max_chars = int(text_area_width / avg_char_width * 0.9)  # 90% to account for wider chars
            
            # Wrap text more efficiently
            wrapped_text = textwrap.fill(text, width=max_chars)

            # Measure and draw wrapped text
            current_h, pad = text_position_y, 10
            for line in wrapped_text.split('\n'):
                bbox = draw.textbbox((0, 0), line, font=self.FONT)
                width, height = bbox[2] - bbox[0], bbox[3] - bbox[1]
                x_position = text_area_left + (text_area_width - width) // 2
                draw.text((x_position, current_h), line, font=self.FONT, fill=text_color)
                current_h += height + pad

            # Draw the author text
            author_text = f"- {author}"
            author_bbox = draw.textbbox((0, 0), author_text, font=self.AUTHOR_FONT)
            author_width, author_height = author_bbox[2] - author_bbox[0], author_bbox[3] - author_bbox[1]
            author_x_position = text_area_left + (text_area_width - author_width) // 2
            draw.text((author_x_position, author_position_y), author_text, font=self.AUTHOR_FONT, fill=text_color)

            # Save the modified image with optimization
            base_image.save(self.OUTPUT_PATH, optimize=True, quality=90)

            if os.path.exists(self.OUTPUT_PATH):
                return self.OUTPUT_PATH
            else:
                print("Error: Image not saved.")
                return None
        except Exception as e:
            print(f"Error in create_quote_image: {e}")
            return None

    @commands.command()
    async def quote(self, ctx):
        try:
            if ctx.message.reference:
                replied_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
                quote_text = replied_message.content
                author = replied_message.author.display_name
            else:
                await ctx.send("Please reply to a message with the quote.")
                return

            image_path = self.create_quote_image(quote_text, author)
            
            if image_path:
                with open(image_path, 'rb') as f:
                    await ctx.reply(file=discord.File(f, filename="quote.png"))
            else:
                await ctx.send("Failed to create the image.")
        except discord.NotFound:
            await ctx.send("Could not find the message to quote.")
        except IOError:
            await ctx.send("Failed to process the image file.")
        except Exception as e:
            print(f"Error in quote command: {e}")
            await ctx.send("An error occurred while processing your request.")

async def setup(bot):
    await bot.add_cog(QuoteImageCog(bot))