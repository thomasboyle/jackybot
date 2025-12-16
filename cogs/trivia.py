import discord
from discord.ext import commands
import aiohttp
import html
import random
import asyncio

CATEGORY_EMOJIS = ("1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣")
CATEGORY_DICT = {
    "general": "9", "books": "10", "film": "11", "music": "12",
    "geography": "22", "sports": "21", "history": "23"
}
CATEGORY_LIST = tuple(CATEGORY_DICT.keys())

class TriviaCog(commands.Cog):
    __slots__ = ('bot', 'trivia_active', 'handled_message_ids', 'session')

    def __init__(self, bot):
        self.bot = bot
        self.trivia_active = {}
        self.handled_message_ids = set()
        self.session = None

    async def cog_load(self):
        self.session = aiohttp.ClientSession()

    async def cog_unload(self):
        if self.session:
            await self.session.close()

    @commands.command()
    async def trivia(self, ctx):
        if ctx.message.id in self.handled_message_ids:
            return
        self.handled_message_ids.add(ctx.message.id)

        if ctx.guild.id not in self.trivia_active:
            self.trivia_active[ctx.guild.id] = False

        if self.trivia_active[ctx.guild.id]:
            await ctx.send("A trivia game is already in progress.")
            return

        self.trivia_active[ctx.guild.id] = True

        category_message = await ctx.send("```Please select a category:\n"
                                          "1️⃣ General\n2️⃣ Books\n3️⃣ Film\n4️⃣ Music\n"
                                          "5️⃣ Geography\n6️⃣ Sports\n7️⃣ History\n```")

        await asyncio.gather(*(category_message.add_reaction(emoji) for emoji in CATEGORY_EMOJIS))

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in CATEGORY_EMOJIS

        try:
            reaction, _ = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
        except asyncio.TimeoutError:
            await ctx.send("Trivia game cancelled due to inactivity.")
            self.trivia_active[ctx.guild.id] = False
            return

        category_index = CATEGORY_EMOJIS.index(str(reaction.emoji))
        category = CATEGORY_LIST[category_index]
        category_number = CATEGORY_DICT[category]

        url = f'https://opentdb.com/api.php?amount=5&category={category_number}&type=multiple'
        try:
            async with self.session.get(url) as response:
                if response.status != 200:
                    self.trivia_active[ctx.guild.id] = False
                    await ctx.send("Failed to fetch trivia questions. Please try again later.")
                    return
                data = await response.json()
        except Exception:
            self.trivia_active[ctx.guild.id] = False
            await ctx.send("Failed to fetch trivia questions. Please try again later.")
            return

        questions = data['results']

        await ctx.send(f"```\nWelcome to the {category} trivia game! Get ready to answer some questions. "
                      f"You will have 10s to select your answer before the answer is revealed.\n```")

        scores = {}

        for question in questions:
            question_text = html.unescape(question['question'])
            options = [html.unescape(opt) for opt in question['incorrect_answers']]
            correct_answer = html.unescape(question['correct_answer'])

            options.append(correct_answer)
            random.shuffle(options)

            await ctx.send("```\nQuestion:\n```")
            await ctx.send(f"```\n{question_text}\n```")
            await ctx.send("```\nOptions:\n```")

            formatted_options = "\n".join(f"{i}. {option}" for i, option in enumerate(options, start=1))
            options_message = await ctx.send(f"```\n{formatted_options}\n```")

            num_options = len(options)
            await asyncio.gather(*(options_message.add_reaction(emoji) for emoji in CATEGORY_EMOJIS[:num_options]))

            def answer_check(reaction, user):
                return user != self.bot.user and str(reaction.emoji) in CATEGORY_EMOJIS[:num_options]

            answers = {}

            async def answer_task():
                while True:
                    try:
                        reaction, user = await self.bot.wait_for('reaction_add', timeout=10.0, check=answer_check)
                        if user not in answers:
                            answers[user] = CATEGORY_EMOJIS.index(str(reaction.emoji)) + 1
                    except asyncio.TimeoutError:
                        break

            await answer_task()

            correct_index = options.index(correct_answer) + 1
            correct_users = [user for user, answer in answers.items() if answer == correct_index]

            for user in correct_users:
                scores[user] = scores.get(user, 0) + 1

            if correct_users:
                await ctx.send(f"```\nCorrect answers by: {', '.join(user.name for user in correct_users)}!\n```")
            else:
                await ctx.send(f"```\nNo correct answers. The correct answer was {correct_answer}.\n```")

        scores_message = "\n".join(f"{user.name}: {score}" for user, score in scores.items())
        await ctx.send(f"```\nGame over! The final scores are:\n{scores_message}\n```")

        self.trivia_active[ctx.guild.id] = False

async def setup(bot):
    await bot.add_cog(TriviaCog(bot))