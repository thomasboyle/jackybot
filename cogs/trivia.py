import discord
from discord.ext import commands
import requests
from bs4 import BeautifulSoup
import random
import asyncio

class TriviaCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.trivia_active = {}
        self.handled_message_ids = set()

    @commands.command()
    async def trivia(self, ctx):
        # Ignore repeated messages
        if ctx.message.id in self.handled_message_ids:
            return
        self.handled_message_ids.add(ctx.message.id)

        # Check if the current guild is in the dictionary, if not initialize it
        if ctx.guild.id not in self.trivia_active:
            self.trivia_active[ctx.guild.id] = False

        if self.trivia_active[ctx.guild.id]:
            await ctx.send("A trivia game is already in progress.")
            return

        self.trivia_active[ctx.guild.id] = True

        # Map the category to a specific API endpoint
        category_dict = {
            "general": "9",
            "books": "10",
            "film": "11",
            "music": "12",
            "geography": "22",
            "sports": "21",
            "history": "23"
        }
        
        category_list = list(category_dict.keys())
        category_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣"]

        category_message = await ctx.send("```Please select a category:\n"
                                           "1️⃣ General\n"
                                           "2️⃣ Books\n"
                                           "3️⃣ Film\n"
                                           "4️⃣ Music\n"
                                           "5️⃣ Geography\n"
                                           "6️⃣ Sports\n"
                                           "7️⃣ History\n```")

        # Add reactions one by one, but use asyncio.gather for concurrency
        await asyncio.gather(*(category_message.add_reaction(emoji) for emoji in category_emojis))

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in category_emojis

        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=60.0, check=check)
        except asyncio.TimeoutError:
            await ctx.send("Trivia game cancelled due to inactivity.")
            self.trivia_active[ctx.guild.id] = False
            return

        category_index = category_emojis.index(str(reaction.emoji))
        category = category_list[category_index]
        category_number = category_dict[category]

        response = requests.get(f'https://opentdb.com/api.php?amount=5&category={category_number}&type=multiple')
        if response.status_code != 200:
            self.trivia_active[ctx.guild.id] = False
            await ctx.send("Failed to fetch trivia questions. Please try again later.")
            return

        data = response.json()
        questions = data['results']

        welcome_message = f"```\nWelcome to the {category} trivia game! Get ready to answer some questions. You will have 10s to select your answer before the answer is revealed.\n```"
        await ctx.send(welcome_message)

        scores = {}

        for question in questions:
            question_text = BeautifulSoup(question['question'], 'html.parser').get_text()
            options = [BeautifulSoup(option, 'html.parser').get_text() for option in question['incorrect_answers']]
            correct_answer = BeautifulSoup(question['correct_answer'], 'html.parser').get_text()

            options.append(correct_answer)
            random.shuffle(options)

            question_header = "```\nQuestion:\n```"
            await ctx.send(question_header)
            await ctx.send(f"```\n{question_text}\n```")

            options_header = "```\nOptions:\n```"
            await ctx.send(options_header)
            formatted_options = "\n".join([f"{i}. {option}" for i, option in enumerate(options, start=1)])
            options_message = await ctx.send(f"```\n{formatted_options}\n```")

            # Add reactions one by one, but use asyncio.gather for concurrency
            await asyncio.gather(*(options_message.add_reaction(emoji) for emoji in category_emojis[:len(options)]))

            def check(reaction, user):
                return user != self.bot.user and str(reaction.emoji) in category_emojis[:len(options)]

            answers = {}

            async def answer_task():
                while True:
                    try:
                        reaction, user = await self.bot.wait_for('reaction_add', timeout=10.0, check=check)
                        # If the user has not answered this question yet, save their answer
                        if user not in answers:
                            answers[user] = category_emojis.index(str(reaction.emoji)) + 1
                    except asyncio.TimeoutError:
                        break

            await answer_task()

            correct_index = options.index(correct_answer) + 1
            correct_users = [user for user, answer in answers.items() if answer == correct_index]

            for user in correct_users:
                if user in scores:
                    scores[user] += 1
                else:
                    scores[user] = 1

            if correct_users:
                await ctx.send(f"```\nCorrect answers by: {', '.join(user.name for user in correct_users)}!\n```")
            else:
                await ctx.send(f"```\nNo correct answers. The correct answer was {correct_answer}.\n```")

        # Print scores
        scores_message = "\n".join([f"{user.name}: {score}" for user, score in scores.items()])
        await ctx.send(f"```\nGame over! The final scores are:\n{scores_message}\n```")

        self.trivia_active[ctx.guild.id] = False
        print(f"Ending trivia game in guild {ctx.guild.id}")

async def setup(bot):
    await bot.add_cog(TriviaCog(bot))