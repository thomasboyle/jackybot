import discord
from discord.ext import commands
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)

class ButtonCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="button", description="Send a test button")
    async def button(self, ctx):
        try:
            # Create the button
            button = discord.ui.Button(label="Click me!", style=discord.ButtonStyle.primary)

            # Define what happens when the button is clicked
            async def button_callback(interaction: discord.Interaction):
                try:
                    await interaction.response.send_message("Hello!", ephemeral=True)
                except discord.errors.NotFound:
                    logging.error(f"Interaction not found: {interaction.id}")
                except discord.errors.HTTPException as e:
                    logging.error(f"HTTP Exception on interaction {interaction.id}: {e}")
                except Exception as e:
                    logging.error(f"Unexpected error on interaction {interaction.id}: {e}")

            button.callback = button_callback

            # Create a view and add the button to it
            view = discord.ui.View()
            view.add_item(button)

            # Create and send the embed with the button
            embed = discord.Embed(title="Test Button", description="Click the button below!", color=discord.Color.blue())
            await ctx.send(embed=embed, view=view)

        except discord.errors.Forbidden:
            await ctx.send("I don't have permission to send embeds or use interactions here.")
        except discord.errors.HTTPException as e:
            await ctx.send(f"An HTTP error occurred: {e}")
        except Exception as e:
            await ctx.send(f"An unexpected error occurred: {e}")
            logging.error(f"Unexpected error in button command: {e}")

async def setup(bot):
    await bot.add_cog(ButtonCog(bot))