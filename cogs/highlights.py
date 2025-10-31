import discord
from discord.ext import commands
import asyncio
from datetime import datetime
import json
import os

class HighlightsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.star_emoji = "⭐"
        self.data_file = 'data/highlights_data.json'
        self.settings_file = os.environ.get('COG_SETTINGS_PATH', 'data/cog_settings.json')
        self.highlighted_messages = set()
        self._image_extensions = ('.png', '.jpg', '.jpeg', '.gif', '.webp')
        self._video_extensions = ('.mp4', '.mov', '.avi', '.webm')
        self.load_data()

    def cog_unload(self):
        self.save_data()

    def load_data(self):
        """Load previously highlighted messages to avoid duplicates."""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                    self.highlighted_messages = set(data.get('highlighted_messages', []))
            except Exception as e:
                print(f"Error loading highlights data: {e}")
                self.highlighted_messages = set()

    def save_data(self):
        """Save highlighted messages data."""
        try:
            data = {
                'highlighted_messages': list(self.highlighted_messages)
            }
            with open(self.data_file, 'w') as f:
                json.dump(data, f)
        except Exception as e:
            print(f"Error saving highlights data: {e}")

    def get_highlight_channel_name(self, guild_id):
        """Get the configured highlight channel name for a server."""
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r') as f:
                    settings = json.load(f)
                    server_settings = settings.get(str(guild_id), {})
                    highlights_settings = server_settings.get('highlights', {})
                    channel_name = highlights_settings.get('channel_name')
                    if channel_name:
                        return channel_name
        except Exception as e:
            print(f"Error reading highlights channel setting: {e}")

        # Default fallback
        return "teli-highlights"

    async def get_highlight_channel(self, guild):
        """Get or create the highlights channel."""
        channel_name = self.get_highlight_channel_name(guild.id)
        highlight_channel = discord.utils.get(guild.channels, name=channel_name)

        if not highlight_channel:
            try:
                # Create the channel if it doesn't exist
                highlight_channel = await guild.create_text_channel(
                    channel_name,
                    topic="⭐ Highlighted messages from the server"
                )
                await highlight_channel.send("✨ **Welcome to the highlights channel!** ✨\nMessages starred with ⭐ will appear here.")
            except discord.Forbidden:
                print(f"No permission to create highlights channel in {guild.name}")
                return None
            except Exception as e:
                print(f"Error creating highlights channel: {e}")
                return None

        return highlight_channel

    def format_message_content(self, message):
        """Format the message content, handling different content types."""
        parts = [message.content] if message.content else []
        
        # Handle embeds
        for embed in message.embeds:
            if embed.description:
                parts.append(f"**Embed:** {embed.description}")
            if embed.title:
                parts.append(f"**Title:** {embed.title}")
        
        content = '\n'.join(parts) if parts else "*[No text content]*"
        
        # Truncate if too long
        return content[:1800] + "..." if len(content) > 1800 else content

    async def create_highlight_embed(self, message, reactor):
        """Create an embed for the highlighted message."""
        embed = discord.Embed(
            description=self.format_message_content(message),
            color=0xFFD700,  # Gold color for star
            timestamp=message.created_at
        )
        
        # Author information
        embed.set_author(
            name=f"{message.author.display_name} ({message.author.name})",
            icon_url=message.author.display_avatar.url
        )
        
        # Channel and server info
        embed.add_field(
            name="📍 Channel",
            value=f"{message.channel.mention}",
            inline=True
        )
        
        embed.add_field(
            name="⭐ Highlighted by",
            value=f"{reactor.display_name}",
            inline=True
        )
        
        embed.add_field(
            name="🔗 Jump to Message",
            value=f"[Click here]({message.jump_url})",
            inline=True
        )
        
        # Handle image attachments
        files_to_send = []
        attachment_info = []
        first_image_set = False
        
        for attachment in message.attachments:
            filename_lower = attachment.filename.lower()
            
            if filename_lower.endswith(self._image_extensions):
                # For images, set as embed image if it's the first one
                if not first_image_set:
                    embed.set_image(url=attachment.url)
                    first_image_set = True
                attachment_info.append(f"🖼️ {attachment.filename}")
            elif filename_lower.endswith(self._video_extensions):
                attachment_info.append(f"🎥 {attachment.filename}")
            else:
                attachment_info.append(f"📎 {attachment.filename}")
        
        if attachment_info:
            embed.add_field(
                name="📁 Attachments",
                value="\n".join(attachment_info),
                inline=False
            )
        
        embed.set_footer(text=f"Message ID: {message.id}")
        
        return embed, files_to_send

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        """Handle star reactions added to messages."""
        # Ignore bot reactions
        if user.bot:
            return
        
        # Check if it's a star emoji
        if str(reaction.emoji) != self.star_emoji:
            return
        
        message = reaction.message
        
        # Don't highlight messages from the highlights channel itself
        highlight_channel_name = self.get_highlight_channel_name(message.guild.id)
        if message.channel.name == highlight_channel_name:
            return
        
        # Check if message was already highlighted
        message_id = f"{message.guild.id}-{message.id}"
        if message_id in self.highlighted_messages:
            return
        
        # Get the highlights channel
        highlight_channel = await self.get_highlight_channel(message.guild)
        if not highlight_channel:
            return
        
        try:
            # Create and send the highlight embed
            embed, files = await self.create_highlight_embed(message, user)
            await highlight_channel.send(embed=embed, files=files)
            
            # Mark message as highlighted
            self.highlighted_messages.add(message_id)
            
        except discord.Forbidden:
            print(f"No permission to send message to highlights channel in {message.guild.name}")
        except Exception as e:
            print(f"Error sending highlight message: {e}")

    @commands.Cog.listener()
    async def on_reaction_remove(self, reaction, user):
        """Handle star reactions removed from messages (optional cleanup)."""
        # This could be used to remove highlights if the star count drops to 0
        # For now, we'll keep highlights permanent once created
        pass

    @commands.command(name='highlight_stats')
    @commands.has_permissions(manage_messages=True)
    async def highlight_stats(self, ctx):
        """Show statistics about highlights in this server."""
        guild_id_str = str(ctx.guild.id)
        guild_highlights = [msg_id for msg_id in self.highlighted_messages if msg_id.startswith(guild_id_str)]
        
        highlight_channel_name = self.get_highlight_channel_name(ctx.guild.id)
        embed = discord.Embed(
            title="⭐ Highlight Statistics",
            description=f"This server has **{len(guild_highlights)}** highlighted messages",
            color=0xFFD700
        )

        highlight_channel = discord.utils.get(ctx.guild.channels, name=highlight_channel_name)
        if highlight_channel:
            embed.add_field(
                name="📍 Highlights Channel",
                value=highlight_channel.mention,
                inline=False
            )
        else:
            embed.add_field(
                name="📍 Highlights Channel",
                value=f"Not created yet (will be created automatically as #{highlight_channel_name})",
                inline=False
            )
        
        embed.add_field(
            name="ℹ️ How it works",
            value=f"React with {self.star_emoji} to any message to highlight it!",
            inline=False
        )
        
        await ctx.reply(embed=embed)

    @commands.command(name='create_highlights')
    @commands.has_permissions(administrator=True)
    async def create_highlights_channel(self, ctx):
        """Manually create the highlights channel."""
        highlight_channel = await self.get_highlight_channel(ctx.guild)
        if highlight_channel:
            await ctx.reply(f"✅ Highlights channel ready: {highlight_channel.mention}")
        else:
            await ctx.reply("❌ Failed to create highlights channel. Check bot permissions.")

async def setup(bot):
    await bot.add_cog(HighlightsCog(bot)) 