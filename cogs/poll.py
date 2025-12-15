import discord
from discord.ext import commands
import datetime
import asyncio
import re

POLL_ARGS_PATTERN = re.compile(r'"([^"]*)"')
EMOJI_NUMBERS = ("1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟")

class PollCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_polls = {}
        self.user_votes = {}
        print("PollCog loaded successfully with enhanced UX!")

    def create_glass_embed(self, title, description="", color=0x2B2D31):
        """Creates a glass morphism-inspired embed"""
        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.datetime.now()
        )
        return embed

    def parse_poll_args(self, content):
        """Parse poll arguments from quoted strings"""
        return POLL_ARGS_PATTERN.findall(content)

    @commands.command(name="poll", aliases=["p"])
    async def poll(self, ctx, *, args=None):
        """
        Creates a poll with multiple options
        
        Quick format: !poll "Question?" "Option 1" "Option 2" "Option 3"
        Interactive format: !poll (then follow prompts)
        """
        if args:
            # Quick format - parse quoted arguments
            parsed_args = self.parse_poll_args(args)
            if len(parsed_args) >= 3:  # At least question + 2 options
                question = parsed_args[0]
                options = parsed_args[1:min(11, len(parsed_args))]  # Max 10 options
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
        
        # Interactive format - much faster than before
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
            # Get question
            question_msg = await self.bot.wait_for('message', timeout=60.0, check=message_check)
            question = question_msg.content.strip()
            
            # Get options
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
            
            # Clean up setup messages
            cleanup_msgs = [setup_msg, question_msg, options_prompt, options_msg]
            await asyncio.gather(*[msg.delete() for msg in cleanup_msgs], return_exceptions=True)
            
            await self.create_poll(ctx, question, options[:10])  # Max 10 options
            
        except asyncio.TimeoutError:
            timeout_embed = self.create_glass_embed(
                "⏰ Timeout",
                "Poll creation timed out. Try again!",
                0xFF6B6B
            )
            await ctx.reply(embed=timeout_embed, delete_after=10)
            return

    async def create_poll(self, ctx, question, options):
        """Create the actual poll with glass morphism design"""
        # Create main poll embed with glass morphism styling
        poll_embed = discord.Embed(
            color=0x2B2D31,  # Dark glass-like color
            timestamp=datetime.datetime.now()
        )
        
        # Set up the poll title with glass morphism effect
        poll_embed.title = f"🗳️ {question}"
        
        # Create options display with enhanced styling
        options_text = ""
        for i, option in enumerate(options):
            emoji = EMOJI_NUMBERS[i]
            options_text += f"{emoji} **{option}**\n"
        
        poll_embed.add_field(
            name="📊 Options",
            value=options_text,
            inline=False
        )
        
        # Add visual elements for glass morphism feel
        poll_embed.add_field(
            name="🎯 How to Vote",
            value="React with the corresponding emoji to cast your vote!\n"
                  "You can change your vote by reacting to a different option.",
            inline=False
        )
        
        # Glass morphism-inspired footer
        poll_embed.set_footer(
            text=f"✨ Poll by {ctx.author.display_name} • React to vote!",
            icon_url=ctx.author.avatar.url if ctx.author.avatar else None
        )
        
        # Add a subtle accent
        poll_embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/1234567890123456789.png")  # Optional: custom poll icon
        
        poll_msg = await ctx.send(embed=poll_embed)
        
        # Add reactions
        for i in range(len(options)):
            await poll_msg.add_reaction(self.emoji_numbers[i])
        
        # Store poll data
        self.active_polls[poll_msg.id] = {
            "author": ctx.author.id,
            "question": question,
            "choices": options,
            "created_at": datetime.datetime.now(),
            "channel_id": ctx.channel.id
        }
        
        self.user_votes[poll_msg.id] = {}
        
        # Send confirmation with glass morphism styling
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
        """Handle vote reactions with enhanced feedback"""
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
        
        # Remove previous vote
        if user.id in poll_votes:
            prev_emoji = EMOJI_NUMBERS[poll_votes[user.id]]
            await reaction.message.remove_reaction(prev_emoji, user)
        
        poll_votes[user.id] = option_index
        
        # Send glass morphism confirmation DM
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
        """Ends a poll and displays results with glass morphism styling"""
        if not message_id:
            # Find the most recent poll in this channel
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
        
        # Create glass morphism results embed
        results_embed = discord.Embed(
            title=f"📊 Poll Results",
            color=0x2B2D31,
            timestamp=datetime.datetime.now()
        )
        
        results_embed.add_field(
            name="❓ Question",
            value=f"**{poll_data['question']}**",
            inline=False
        )
        
        # Calculate and display results
        total_votes = 0
        results_text = ""
        
        for i, choice in enumerate(poll_data["choices"]):
            emoji = EMOJI_NUMBERS[i]
            reaction = discord.utils.get(message.reactions, emoji=emoji)
            count = (reaction.count - 1) if reaction else 0
            total_votes += count
            
            # Create progress bar effect
            if total_votes > 0:
                percentage = (count / total_votes) * 100 if total_votes > 0 else 0
                bar_length = int(percentage / 10)
                progress_bar = "🔹" * bar_length + "🔸" * (10 - bar_length)
                results_text += f"{emoji} **{choice}**\n"
                results_text += f"└ {count} votes ({percentage:.1f}%) {progress_bar}\n\n"
            else:
                results_text += f"{emoji} **{choice}**\n└ 0 votes (0.0%) 🔸🔸🔸🔸🔸🔸🔸🔸🔸🔸\n\n"
        
        results_embed.add_field(
            name="📈 Results",
            value=results_text,
            inline=False
        )
        
        results_embed.add_field(
            name="📊 Summary",
            value=f"**Total Votes:** {total_votes}\n"
                  f"**Options:** {len(poll_data['choices'])}\n"
                  f"**Duration:** {(datetime.datetime.now() - poll_data['created_at']).seconds // 60} minutes",
            inline=False
        )
        
        # Glass morphism footer
        author_name = ctx.guild.get_member(poll_data['author'])
        author_display = author_name.display_name if author_name else "Unknown User"
        results_embed.set_footer(
            text=f"✨ Poll by {author_display} • Ended",
            icon_url=author_name.avatar.url if author_name and author_name.avatar else None
        )
        
        await ctx.send(embed=results_embed)
        
        # Clean up
        del self.active_polls[message_id]
        del self.user_votes[message_id]
        
        # Send completion message
        complete_embed = self.create_glass_embed(
            "🎉 Poll Completed!",
            f"Poll **{poll_data['question']}** has been successfully ended.\n"
            f"Total participants: **{total_votes}**",
            0x00FF88
        )
        await ctx.reply(embed=complete_embed, delete_after=15)

    @commands.command(name="polls", aliases=["listpolls"])
    async def list_polls(self, ctx):
        """List all active polls in the server"""
        server_polls = []
        for poll_id, poll_data in self.active_polls.items():
            if poll_data.get("channel_id") == ctx.channel.id:
                server_polls.append((poll_id, poll_data))
        
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
        
        for poll_id, poll_data in server_polls[:5]:  # Show max 5 polls
            author = ctx.guild.get_member(poll_data["author"])
            author_name = author.display_name if author else "Unknown"
            embed.add_field(
                name=f"🗳️ {poll_data['question'][:50]}{'...' if len(poll_data['question']) > 50 else ''}",
                value=f"**ID:** `{poll_id}`\n"
                      f"**Author:** {author_name}\n"
                      f"**Options:** {len(poll_data['choices'])}",
                inline=False
            )
        
        embed.set_footer(text="💡 Use !endpoll <id> to end a specific poll")
        await ctx.reply(embed=embed)

async def setup(bot):
    await bot.add_cog(PollCog(bot))