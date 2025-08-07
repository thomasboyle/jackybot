import discord
from discord.ext import commands
import random
import asyncio

class RandomNumberGenerator(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def prompt_user_input(self, ctx: commands.Context, prompt: str) -> int:
        """Helper function to prompt the user and wait for a valid integer input."""
        await ctx.send(prompt)

        def check(m: discord.Message) -> bool:
            return m.author == ctx.author and m.channel == ctx.channel and m.content.isdigit()

        try:
            msg = await self.bot.wait_for('message', check=check, timeout=30.0)
            return int(msg.content)
        except asyncio.TimeoutError:
            await ctx.send("You took too long to respond. Please try again.")
            raise

    @commands.command(name="rand", help="Generate a random number between a range")
    async def random_number(self, ctx: commands.Context) -> None:
        try:
            min_val = await self.prompt_user_input(ctx, "Please enter the minimum value for the range.")
            max_val = await self.prompt_user_input(ctx, "Please enter the maximum value for the range.")
        except asyncio.TimeoutError:
            return

        if min_val >= max_val:
            return await ctx.send("Invalid range! The minimum value must be less than the maximum value.")

        # Create the Go button
        view = RandomNumberButton(min_val, max_val)
        await ctx.send(f"Range selected: {min_val} to {max_val}. Press 'Go' to generate a number.", view=view)


class RandomNumberButton(discord.ui.View):
    def __init__(self, min_val: int, max_val: int) -> None:
        super().__init__()
        self.min_val = min_val
        self.max_val = max_val

    @discord.ui.button(label="Go!", style=discord.ButtonStyle.primary)
    async def generate_number(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        # Defer the interaction to give us more time
        await interaction.response.defer()

        # Simulate animated selection with a reduced delay for a more responsive feel
        for _ in range(3):  # Reduced the loop for faster response
            await asyncio.sleep(0.5)  # Shortened delay for a more snappy interaction
            temp_num = random.randint(self.min_val, self.max_val)
            await interaction.edit_original_response(content=f"Thinking... Random number could be {temp_num}...")

        # Final random number
        random_num = random.randint(self.min_val, self.max_val)
        await interaction.edit_original_response(content=f"🎉 The random number is: **{random_num}**!")


# Add the cog to the bot
async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RandomNumberGenerator(bot))
