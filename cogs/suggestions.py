import discord
from discord.ext import commands
from discord.ui import View, Button
import asyncio
from typing import Dict, List


class SuggestionView(View):
    def __init__(self, cog, topic: str, creator_id: int):
        super().__init__(timeout=None)  # Persistent view
        self.cog = cog
        self.topic = topic
        self.creator_id = creator_id
    
    @discord.ui.button(label="Add Suggestion", style=discord.ButtonStyle.green, emoji="💡", custom_id="add_suggestion")
    async def add_suggestion_button(self, interaction: discord.Interaction, button: Button):
        """Button for users to add their suggestions"""
        # Send ephemeral message asking for suggestion
        await interaction.response.send_message(
            f"📝 **Submit your suggestion for:** {self.topic}\n\n"
            "Please reply to this message with your suggestion. Your message will be deleted after submission to keep it private.",
            ephemeral=True
        )
        
        # Wait for the user's response
        def check(m):
            return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id
        
        try:
            msg = await self.cog.bot.wait_for('message', timeout=300.0, check=check)
            
            # Store the suggestion
            suggestion_text = msg.content
            message_id = interaction.message.id
            
            if message_id not in self.cog.suggestions:
                self.cog.suggestions[message_id] = []
            
            self.cog.suggestions[message_id].append({
                'user': interaction.user.display_name,
                'user_id': interaction.user.id,
                'suggestion': suggestion_text
            })
            
            # Delete the user's message to hide it
            try:
                await msg.delete()
            except discord.Forbidden:
                pass  # Bot doesn't have delete permissions
            except discord.NotFound:
                pass  # Message already deleted
            
            # Send confirmation (ephemeral follow-up)
            try:
                await interaction.followup.send(
                    "✅ Your suggestion has been submitted successfully and your message has been deleted!",
                    ephemeral=True
                )
            except:
                # If the interaction expired, try to DM the user
                try:
                    await interaction.user.send(
                        f"✅ Your suggestion for **{self.topic}** has been submitted successfully!"
                    )
                except:
                    pass
            
        except asyncio.TimeoutError:
            try:
                await interaction.followup.send(
                    "⏰ You took too long to respond. Please try again.",
                    ephemeral=True
                )
            except:
                pass
    
    @discord.ui.button(label="Reveal Suggestions", style=discord.ButtonStyle.primary, emoji="📊", custom_id="reveal_suggestions")
    async def reveal_suggestions_button(self, interaction: discord.Interaction, button: Button):
        """Button only the creator can press to reveal all suggestions"""
        # Check if the user is the creator
        if interaction.user.id != self.creator_id:
            await interaction.response.send_message(
                "❌ Only the creator of this suggestion request can reveal the suggestions.",
                ephemeral=True
            )
            return
        
        message_id = interaction.message.id
        suggestions = self.cog.suggestions.get(message_id, [])
        
        if not suggestions:
            await interaction.response.send_message(
                "📭 No suggestions have been submitted yet.",
                ephemeral=True
            )
            return
        
        # Create embed with all suggestions
        embed = discord.Embed(
            title=f"📊 Suggestions for: {self.topic}",
            description=f"Total suggestions received: **{len(suggestions)}**",
            color=0x2B2D31,
            timestamp=discord.utils.utcnow()
        )
        
        # Group suggestions into fields (Discord has a limit of 25 fields and 1024 chars per field)
        suggestions_text = ""
        for i, suggestion in enumerate(suggestions, 1):
            suggestion_line = f"**{i}.** {suggestion['suggestion']}\n"
            suggestions_text += suggestion_line
        
        # Split into chunks if too long
        if len(suggestions_text) <= 1024:
            embed.add_field(
                name="💡 Submitted Suggestions",
                value=suggestions_text,
                inline=False
            )
        else:
            # Split into multiple fields
            chunks = []
            current_chunk = ""
            for i, suggestion in enumerate(suggestions, 1):
                suggestion_line = f"**{i}.** {suggestion['suggestion']}\n"
                if len(current_chunk) + len(suggestion_line) > 1024:
                    chunks.append(current_chunk)
                    current_chunk = suggestion_line
                else:
                    current_chunk += suggestion_line
            
            if current_chunk:
                chunks.append(current_chunk)
            
            for idx, chunk in enumerate(chunks, 1):
                embed.add_field(
                    name=f"💡 Suggestions (Part {idx}/{len(chunks)})",
                    value=chunk,
                    inline=False
                )
        
        embed.set_footer(
            text=f"Revealed by {interaction.user.display_name}",
            icon_url=interaction.user.avatar.url if interaction.user.avatar else None
        )
        
        await interaction.response.send_message(embed=embed)


class SuggestionsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.suggestions: Dict[int, List[dict]] = {}  # message_id -> list of suggestions
        print("SuggestionsCog loaded successfully!")
    
    @commands.command(name="suggestions", aliases=["suggest"])
    @commands.has_permissions(administrator=True)
    async def create_suggestion_request(self, ctx, *, topic: str = None):
        """
        Create a new suggestion request.
        
        Usage: !suggestions <topic>
        Example: !suggestions What features should we add to the server?
        """
        if not topic:
            error_embed = discord.Embed(
                title="❌ Missing Topic",
                description="Please provide a topic for the suggestions.\n\n"
                           "**Usage:** `!suggestions <topic>`\n"
                           "**Example:** `!suggestions What features should we add to the server?`",
                color=0xFF6B6B
            )
            await ctx.reply(embed=error_embed, delete_after=15)
            return
        
        # Create the main suggestion embed
        embed = discord.Embed(
            title="💡 {topic}",
            description=f"**Suggestions Request:**\n\n"
                       "Click the **Add Suggestion** button below to submit your ideas!\n"
                       "Your submissions will be kept private until revealed.",
            color=0x7289DA,
            timestamp=discord.utils.utcnow()
        )
        
        embed.add_field(
            name="📝 How to Submit",
            value="1. Click the **Add Suggestion** button\n"
                  "2. Reply with your suggestion\n"
                  "3. Your message will be automatically deleted for privacy",
            inline=False
        )
        
        embed.set_footer(
            text=f"Created by {ctx.author.display_name}",
            icon_url=ctx.author.avatar.url if ctx.author.avatar else None
        )
        
        # Create and send the view with buttons
        view = SuggestionView(self, topic, ctx.author.id)
        message = await ctx.send(embed=embed, view=view)
        
        # Initialize suggestions storage for this message
        self.suggestions[message.id] = []
        
        # Send confirmation
        confirmation = discord.Embed(
            title="✅ Suggestion Request Created!",
            description=f"Your suggestion request for **{topic}** is now live!\n\n"
                       f"🔒 You can reveal all suggestions by clicking the **Reveal Suggestions** button.\n"
                       f"📊 Use this button when you're ready to see what everyone suggested.",
            color=0x00FF88
        )
        await ctx.reply(embed=confirmation, delete_after=20)
    
    @commands.command(name="clear_suggestions")
    @commands.has_permissions(administrator=True)
    async def clear_suggestions(self, ctx, message_id: int = None):
        """
        Clear suggestions for a specific message or all suggestions.
        
        Usage: !clear_suggestions [message_id]
        """
        if message_id:
            if message_id in self.suggestions:
                del self.suggestions[message_id]
                await ctx.reply(f"✅ Cleared suggestions for message ID `{message_id}`.", delete_after=10)
            else:
                await ctx.reply(f"❌ No suggestions found for message ID `{message_id}`.", delete_after=10)
        else:
            self.suggestions.clear()
            await ctx.reply("✅ Cleared all suggestions data.", delete_after=10)
    
    @create_suggestion_request.error
    async def create_suggestion_request_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            embed = discord.Embed(
                title="🔒 Permission Denied",
                description="You need administrator privileges to create suggestion requests.",
                color=0xFF6B6B
            )
            await ctx.reply(embed=embed, delete_after=10)
        else:
            await ctx.reply(f"An error occurred: {error}", delete_after=10)
    
    @clear_suggestions.error
    async def clear_suggestions_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            embed = discord.Embed(
                title="🔒 Permission Denied",
                description="You need administrator privileges to clear suggestions.",
                color=0xFF6B6B
            )
            await ctx.reply(embed=embed, delete_after=10)


async def setup(bot):
    await bot.add_cog(SuggestionsCog(bot))

