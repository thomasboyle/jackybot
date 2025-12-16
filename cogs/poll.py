import discord
from discord.ext import commands
import datetime
import asyncio
import re

POLL_ARGS_PATTERN = re.compile(r'"([^"]*)"')
EMOJI_NUMBERS = ("1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟")
PROGRESS_FILLED = "🔹"
PROGRESS_EMPTY = "🔸"

class PollCog(commands.Cog):
    __slots__ = ('bot', 'active_polls', 'user_votes')

    def __init__(self, bot):
        self.bot = bot
        self.active_polls = {}
        self.user_votes = {}

    def create_glass_embed(self, title, description="", color=0x2B2D31):
        return discord.Embed(title=title, description=description, color=color, timestamp=datetime.datetime.now())

    def parse_poll_args(self, content):
        return POLL_ARGS_PATTERN.findall(content)

    @commands.command(name="poll", aliases=["p"])
    async def poll(self, ctx, *, args=None):
        if args:
            parsed_args = self.parse_poll_args(args)
            if len(parsed_args) >= 3:
                question = parsed_args[0]
                options = parsed_args[1:min(11, len(parsed_args))]
                await self.create_poll(ctx, question, options)
                return
            else:
                error_embed = self.create_glass_embed(
                    "❌ Invalid Format",
                    'Use: `!poll "Question?" "Option 1" "Option 2" "Option 3"`\n'
                    'Or use `!poll` for interactive mode.',
                    0xFF6B6B
                )
                await ctx.reply(embed=error_embed, delete_after=15)
                return

        setup_embed = self.create_glass_embed(
            "🗳️ Quick Poll Setup",
            "**Step 1:** Type your question\n"
            "**Step 2:** Type options separated by `;`\n"
            "**Example:** `What's your favorite color?`\n"
            "Then: `Red; Blue; Green; Yellow`",
            0x7289DA
        )
        setup_embed.set_footer(text="💡 Tip: Use quoted format for faster creation!")

        setup_msg = await ctx.reply(embed=setup_embed)

        def message_check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            question_msg = await self.bot.wait_for('message', timeout=60.0, check=message_check)
            question = question_msg.content.strip()

            options_embed = self.create_glass_embed(
                "📝 Options Setup",
                f"**Question:** {question}\n\n"
                "Now enter your options separated by `;`\n"
                "**Example:** `Red; Blue; Green; Yellow`",
                0x7289DA
            )
            options_prompt = await ctx.send(embed=options_embed)

            options_msg = await self.bot.wait_for('message', timeout=60.0, check=message_check)
            options = [opt.strip() for opt in options_msg.content.split(';') if opt.strip()]

            if len(options) < 2:
                error_embed = self.create_glass_embed(
                    "❌ Error",
                    "You need at least 2 options for a poll!",
                    0xFF6B6B
                )
                await ctx.reply(embed=error_embed, delete_after=10)
                return

            cleanup_msgs = [setup_msg, question_msg, options_prompt, options_msg]
            await asyncio.gather(*[msg.delete() for msg in cleanup_msgs], return_exceptions=True)

            await self.create_poll(ctx, question, options[:10])

        except asyncio.TimeoutError:
            timeout_embed = self.create_glass_embed(
                "⏰ Timeout",
                "Poll creation timed out. Try again!",
                0xFF6B6B
            )
            await ctx.reply(embed=timeout_embed, delete_after=10)

    async def create_poll(self, ctx, question, options):
        now = datetime.datetime.now()
        poll_embed = discord.Embed(color=0x2B2D31, timestamp=now)
        poll_embed.title = f"🗳️ {question}"

        options_text = "".join(f"{EMOJI_NUMBERS[i]} **{option}**\n" for i, option in enumerate(options))

        poll_embed.add_field(name="📊 Options", value=options_text, inline=False)
        poll_embed.add_field(
            name="🎯 How to Vote",
            value="React with the corresponding emoji to cast your vote!\n"
                  "You can change your vote by reacting to a different option.",
            inline=False
        )
        poll_embed.set_footer(
            text=f"✨ Poll by {ctx.author.display_name} • React to vote!",
            icon_url=ctx.author.avatar.url if ctx.author.avatar else None
        )

        poll_msg = await ctx.send(embed=poll_embed)

        await asyncio.gather(*[poll_msg.add_reaction(EMOJI_NUMBERS[i]) for i in range(len(options))])

        self.active_polls[poll_msg.id] = {
            "author": ctx.author.id,
            "question": question,
            "choices": options,
            "created_at": now,
            "channel_id": ctx.channel.id
        }
        self.user_votes[poll_msg.id] = {}

        success_embed = self.create_glass_embed(
            "✅ Poll Created!",
            f"Your poll **{question}** is now live!\n"
            f"🎯 **{len(options)}** options available\n"
            f"📊 Use `!endpoll {poll_msg.id}` to end it",
            0x00FF88
        )
        success_embed.set_footer(text="💫 Powered by glass morphism design")
        await ctx.reply(embed=success_embed, delete_after=20)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if user.bot or reaction.message.id not in self.active_polls:
            return

        emoji_str = str(reaction.emoji)
        if emoji_str not in EMOJI_NUMBERS:
            return

        option_index = EMOJI_NUMBERS.index(emoji_str)
        poll_data = self.active_polls[reaction.message.id]

        if option_index >= len(poll_data["choices"]):
            return

        poll_votes = self.user_votes[reaction.message.id]

        if user.id in poll_votes:
            prev_emoji = EMOJI_NUMBERS[poll_votes[user.id]]
            await reaction.message.remove_reaction(prev_emoji, user)

        poll_votes[user.id] = option_index

        try:
            vote_embed = self.create_glass_embed(
                "🗳️ Vote Registered!",
                f"**Poll:** {poll_data['question']}\n"
                f"**Your Choice:** {poll_data['choices'][option_index]}\n\n"
                f"✨ You can change your vote anytime by reacting to a different option!",
                0x00FF88
            )
            vote_embed.set_footer(text="🔒 Your vote is private and secure")
            await user.send(embed=vote_embed)
        except:
            pass

    @commands.command(name="endpoll", aliases=["ep"])
    async def endpoll(self, ctx, message_id: int = None):
        if not message_id:
            async for message in ctx.channel.history(limit=100):
                if message.author == self.bot.user and message.id in self.active_polls:
                    message_id = message.id
                    break

            if not message_id:
                error_embed = self.create_glass_embed(
                    "❌ No Active Polls",
                    "No active polls found in this channel.\n"
                    "Use `!endpoll <message_id>` to end a specific poll.",
                    0xFF6B6B
                )
                await ctx.reply(embed=error_embed, delete_after=15)
                return

        if message_id not in self.active_polls:
            error_embed = self.create_glass_embed(
                "❌ Poll Not Found",
                "This poll doesn't exist or has already ended.",
                0xFF6B6B
            )
            await ctx.reply(embed=error_embed, delete_after=10)
            return

        poll_data = self.active_polls[message_id]
        if ctx.author.id != poll_data["author"] and not ctx.author.guild_permissions.manage_messages:
            error_embed = self.create_glass_embed(
                "🔒 Permission Denied",
                "Only the poll creator or moderators can end this poll.",
                0xFF6B6B
            )
            await ctx.reply(embed=error_embed, delete_after=10)
            return

        try:
            message = await ctx.channel.fetch_message(message_id)
        except discord.NotFound:
            error_embed = self.create_glass_embed(
                "❌ Message Not Found",
                "Could not find the poll message.",
                0xFF6B6B
            )
            await ctx.reply(embed=error_embed, delete_after=10)
            return

        now = datetime.datetime.now()
        results_embed = discord.Embed(title="📊 Poll Results", color=0x2B2D31, timestamp=now)
        results_embed.add_field(name="❓ Question", value=f"**{poll_data['question']}**", inline=False)

        vote_counts = []
        for i, choice in enumerate(poll_data["choices"]):
            reaction = discord.utils.get(message.reactions, emoji=EMOJI_NUMBERS[i])
            count = (reaction.count - 1) if reaction else 0
            vote_counts.append((i, choice, count))

        total_votes = sum(c[2] for c in vote_counts)

        results_text = ""
        for i, choice, count in vote_counts:
            if total_votes > 0:
                percentage = (count * 100) / total_votes
                bar_length = int(percentage / 10)
                progress_bar = PROGRESS_FILLED * bar_length + PROGRESS_EMPTY * (10 - bar_length)
                results_text += f"{EMOJI_NUMBERS[i]} **{choice}**\n└ {count} votes ({percentage:.1f}%) {progress_bar}\n\n"
            else:
                results_text += f"{EMOJI_NUMBERS[i]} **{choice}**\n└ 0 votes (0.0%) {PROGRESS_EMPTY * 10}\n\n"

        results_embed.add_field(name="📈 Results", value=results_text, inline=False)

        duration_seconds = (now - poll_data['created_at']).seconds
        results_embed.add_field(
            name="📊 Summary",
            value=f"**Total Votes:** {total_votes}\n"
                  f"**Options:** {len(poll_data['choices'])}\n"
                  f"**Duration:** {duration_seconds // 60} minutes",
            inline=False
        )

        author_member = ctx.guild.get_member(poll_data['author'])
        author_display = author_member.display_name if author_member else "Unknown User"
        results_embed.set_footer(
            text=f"✨ Poll by {author_display} • Ended",
            icon_url=author_member.avatar.url if author_member and author_member.avatar else None
        )

        await ctx.send(embed=results_embed)

        del self.active_polls[message_id]
        del self.user_votes[message_id]

        complete_embed = self.create_glass_embed(
            "🎉 Poll Completed!",
            f"Poll **{poll_data['question']}** has been successfully ended.\n"
            f"Total participants: **{total_votes}**",
            0x00FF88
        )
        await ctx.reply(embed=complete_embed, delete_after=15)

    @commands.command(name="polls", aliases=["listpolls"])
    async def list_polls(self, ctx):
        server_polls = [(poll_id, poll_data) for poll_id, poll_data in self.active_polls.items()
                       if poll_data.get("channel_id") == ctx.channel.id]

        if not server_polls:
            embed = self.create_glass_embed(
                "📊 No Active Polls",
                "There are no active polls in this channel.",
                0x7289DA
            )
            await ctx.reply(embed=embed, delete_after=15)
            return

        embed = self.create_glass_embed(
            "📊 Active Polls",
            f"Found **{len(server_polls)}** active poll(s) in this channel:",
            0x7289DA
        )

        for poll_id, poll_data in server_polls[:5]:
            author = ctx.guild.get_member(poll_data["author"])
            author_name = author.display_name if author else "Unknown"
            question_display = poll_data['question'][:50] + ('...' if len(poll_data['question']) > 50 else '')
            embed.add_field(
                name=f"🗳️ {question_display}",
                value=f"**ID:** `{poll_id}`\n**Author:** {author_name}\n**Options:** {len(poll_data['choices'])}",
                inline=False
            )

        embed.set_footer(text="💡 Use !endpoll <id> to end a specific poll")
        await ctx.reply(embed=embed)

async def setup(bot):
    await bot.add_cog(PollCog(bot))