import discord
from discord.ext import commands
import asyncio
import random

class SnakeGame(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.games = {}
        self.emojis = {
            "empty": "⬛",
            "food": "🍎",
            "snake_body": "🟩",
            "snake_head": {(-1, 0): "🔼", (1, 0): "🔽", (0, -1): "◀️", (0, 1): "▶️"},
            "border": "⬜",
            "border_c": "🟥"
        }

    class SnakeView(discord.ui.View):
        def __init__(self, cog):
            super().__init__(timeout=None)
            self.cog = cog

        @discord.ui.button(label="←", style=discord.ButtonStyle.primary)
        async def left(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self.cog.handle_direction(interaction, (0, -1))

        @discord.ui.button(label="↑", style=discord.ButtonStyle.primary)
        async def up(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self.cog.handle_direction(interaction, (-1, 0))

        @discord.ui.button(label="↓", style=discord.ButtonStyle.primary)
        async def down(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self.cog.handle_direction(interaction, (1, 0))

        @discord.ui.button(label="→", style=discord.ButtonStyle.primary)
        async def right(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self.cog.handle_direction(interaction, (0, 1))

        @discord.ui.button(label="Restart", style=discord.ButtonStyle.green, row=1)
        async def restart(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self.cog.handle_restart(interaction)

    async def handle_direction(self, interaction: discord.Interaction, direction):
        game_key = (interaction.channel.id, interaction.user.id)
        if game_key not in self.games:
            await interaction.response.send_message("You don't have an active game!", ephemeral=True)
            return
        game = self.games[game_key]
        if interaction.user.id != game["user_id"]:
            await interaction.response.send_message("This isn't your game!", ephemeral=True)
            return
        game["direction"] = direction
        await interaction.response.defer()

    async def handle_restart(self, interaction: discord.Interaction):
        game_key = (interaction.channel.id, interaction.user.id)
        if game_key in self.games:
            if interaction.user.id != self.games[game_key]["user_id"]:
                await interaction.response.send_message("This isn't your game!", ephemeral=True)
                return
            self.games[game_key]["task"].cancel()
        await interaction.response.defer()
        await self.start_game(interaction.message, interaction.user)

    @commands.command()
    async def snake(self, ctx):
        """Start a new Snake game"""
        game_key = (ctx.channel.id, ctx.author.id)
        if game_key in self.games:
            await ctx.send("You already have a game running in this channel! Use the Restart button to start a new game.")
            return
        
        message = await ctx.send("Starting Snake game...")
        await self.start_game(message, ctx.author)

    async def start_game(self, message, user):
        game_key = (message.channel.id, user.id)
        game = {
            "snake": [(5, 5)],
            "direction": (0, 1),
            "food": None,
            "score": 0,
            "game_over": False,
            "win_score": 20,
            "user_id": user.id,
            "message": message
        }

        self.games[game_key] = game
        self.spawn_food(game)

        embed = await self.create_embed(game, user)
        view = self.SnakeView(self)
        await message.edit(content=None, embed=embed, view=view)

        game["task"] = asyncio.create_task(self.game_loop(game_key))

    def spawn_food(self, game):
        while True:
            food = (random.randint(0, 9), random.randint(0, 9))
            if food not in game["snake"]:
                game["food"] = food
                break

    async def create_embed(self, game, user):
        snake = game["snake"]
        food = game["food"]
        direction = game["direction"]

        board = [[self.emojis["empty"] for _ in range(10)] for _ in range(10)]
        for i, j in snake[1:]:
            board[i][j] = self.emojis["snake_body"]
        i, j = snake[0]
        board[i][j] = self.emojis["snake_head"][direction]
        i, j = food
        board[i][j] = self.emojis["food"]

        border = self.emojis["border"]
        board_str = f"{self.emojis['border_c']}{border * 10}{self.emojis['border_c']}\n"
        board_str += "\n".join(f"{border}{''.join(row)}{border}" for row in board)
        board_str += f"\n{self.emojis['border_c']}{border * 10}{self.emojis['border_c']}"

        embed = discord.Embed(title=f"{user.name}'s Snake Game", description=board_str, color=0x00ff00)
        embed.add_field(name="Score", value=f"{game['score']} / {game['win_score']}")
        if game["game_over"]:
            result = "Congratulations! You won! 🎉" if game["score"] >= game["win_score"] else "Game Over! Click 'Restart' to play again."
            embed.add_field(name="Game Over", value=result)

        return embed

    async def game_loop(self, game_key):
        game = self.games[game_key]
        user = self.bot.get_user(game["user_id"])
        
        while not game["game_over"]:
            await asyncio.sleep(2)  # Update every 2 seconds

            head = game["snake"][0]
            direction = game["direction"]
            new_head = ((head[0] + direction[0]) % 10, (head[1] + direction[1]) % 10)

            if new_head in game["snake"]:
                game["game_over"] = True
            else:
                game["snake"].insert(0, new_head)
                if new_head == game["food"]:
                    game["score"] += 1
                    if game["score"] >= game["win_score"]:
                        game["game_over"] = True
                    else:
                        self.spawn_food(game)
                else:
                    game["snake"].pop()

            embed = await self.create_embed(game, user)
            await game["message"].edit(embed=embed)

        del self.games[game_key]

async def setup(bot):
    await bot.add_cog(SnakeGame(bot))