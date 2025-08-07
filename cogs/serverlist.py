import discord
from discord.ext import commands
from discord import app_commands
import asyncio


class ServerManager(commands.Cog):
    """A cog for managing server information and invite links."""
    
    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(name="servers", help="List all servers the bot is in with invite links")
    async def list_servers(self, ctx, show_invites: bool = True):
        """List all servers the bot is in and create invite links if possible."""
        
        # Check if user is bot owner or has administrator permissions
        if not await self.bot.is_owner(ctx.author):
            if not ctx.author.guild_permissions.administrator:
                await ctx.send(
                    "❌ You need administrator permissions or be the bot owner to use this command."
                )
                return
        
        # Send initial "working" message
        working_msg = await ctx.send("🔄 Gathering server information...")
        
        guilds = self.bot.guilds
        total_servers = len(guilds)
        
        if total_servers == 0:
            await working_msg.edit(content="The bot is not in any servers.")
            return
        
        embed = discord.Embed(
            title=f"Server List ({total_servers} servers)",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        
        server_info = []
        invites_created = 0
        
        for guild in guilds:
            # Basic server info
            member_count = guild.member_count
            owner = guild.owner.display_name if guild.owner else "Unknown"
            
            server_text = f"**{guild.name}**\n"
            server_text += f"ID: `{guild.id}`\n"
            server_text += f"Members: {member_count:,}\n"
            server_text += f"Owner: {owner}\n"
            
            # Try to create invite if requested and bot has permissions
            invite_link = None
            if show_invites:
                invite_link = await self._create_invite(guild)
                if invite_link:
                    server_text += f"[Join Server]({invite_link})\n"
                    invites_created += 1
                else:
                    server_text += "❌ Cannot create invite\n"
            
            server_info.append(server_text)
        
        # Split servers into multiple embeds if needed (Discord embed limit)
        servers_per_embed = 10
        total_embeds = (len(server_info) + servers_per_embed - 1) // servers_per_embed
        
        for i in range(0, len(server_info), servers_per_embed):
            if total_embeds > 1:
                current_embed = discord.Embed(
                    title=f"Server List - Page {(i // servers_per_embed) + 1}/{total_embeds}",
                    color=discord.Color.blue(),
                    timestamp=discord.utils.utcnow()
                )
            else:
                current_embed = embed
            
            chunk = server_info[i:i + servers_per_embed]
            
            for j, server in enumerate(chunk):
                current_embed.add_field(
                    name=f"Server {i + j + 1}",
                    value=server,
                    inline=False
                )
            
            if show_invites:
                current_embed.set_footer(
                    text=f"Invite links created: {invites_created}/{total_servers}"
                )
            
            if i == 0:
                await working_msg.edit(content="", embed=current_embed)
            else:
                await ctx.send(embed=current_embed)
                await asyncio.sleep(1)  # Prevent rate limiting
    
    async def _create_invite(self, guild):
        """Attempt to create an invite link for a guild."""
        try:
            # Check if bot has create instant invite permission
            bot_member = guild.get_member(self.bot.user.id)
            if not bot_member:
                return None
            
            # Look for a suitable channel to create invite from
            suitable_channel = None
            
            # First, try to find a general/welcome channel
            for channel in guild.text_channels:
                if bot_member.permissions_in(channel).create_instant_invite:
                    if any(name in channel.name.lower() for name in ['general', 'welcome', 'main', 'chat']):
                        suitable_channel = channel
                        break
            
            # If no general channel found, use the first available text channel
            if not suitable_channel:
                for channel in guild.text_channels:
                    if bot_member.permissions_in(channel).create_instant_invite:
                        suitable_channel = channel
                        break
            
            # Try system channel if no other options
            if not suitable_channel and guild.system_channel:
                if bot_member.permissions_in(guild.system_channel).create_instant_invite:
                    suitable_channel = guild.system_channel
            
            if suitable_channel:
                invite = await suitable_channel.create_invite(
                    max_age=0,  # Never expires
                    max_uses=0,  # Unlimited uses
                    temporary=False,
                    unique=False,
                    reason="Server list command"
                )
                return invite.url
            
        except discord.Forbidden:
            # Bot doesn't have permission
            pass
        except discord.HTTPException:
            # Some other error occurred
            pass
        except Exception:
            # Catch any other unexpected errors
            pass
        
        return None
    
    @commands.command(name="serverinfo", help="Get detailed information about a specific server")
    async def server_info(self, ctx, server_id: str = None):
        """Get detailed information about a specific server."""
        
        # Check permissions
        if not await self.bot.is_owner(ctx.author):
            if not ctx.author.guild_permissions.administrator:
                await ctx.send(
                    "❌ You need administrator permissions or be the bot owner to use this command."
                )
                return
        
        if server_id:
            try:
                guild_id = int(server_id)
                guild = self.bot.get_guild(guild_id)
                if not guild:
                    await ctx.send(f"❌ Bot is not in a server with ID `{server_id}`")
                    return
            except ValueError:
                await ctx.send("❌ Invalid server ID. Please provide a valid number.")
                return
        else:
            guild = ctx.guild
            if not guild:
                await ctx.send("❌ This command must be used in a server or with a server ID.")
                return
        
        # Send initial "working" message  
        working_msg = await ctx.send("🔄 Gathering server information...")
        
        # Create detailed embed
        embed = discord.Embed(
            title=f"📊 {guild.name}",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        
        # Basic info
        embed.add_field(name="Server ID", value=f"`{guild.id}`", inline=True)
        embed.add_field(name="Owner", value=guild.owner.mention if guild.owner else "Unknown", inline=True)
        embed.add_field(name="Created", value=f"<t:{int(guild.created_at.timestamp())}:R>", inline=True)
        
        # Member info
        total_members = guild.member_count
        bots = sum(1 for member in guild.members if member.bot)
        humans = total_members - bots
        
        embed.add_field(name="Total Members", value=f"{total_members:,}", inline=True)
        embed.add_field(name="Humans", value=f"{humans:,}", inline=True)
        embed.add_field(name="Bots", value=f"{bots:,}", inline=True)
        
        # Channel info
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        categories = len(guild.categories)
        
        embed.add_field(name="Text Channels", value=str(text_channels), inline=True)
        embed.add_field(name="Voice Channels", value=str(voice_channels), inline=True)
        embed.add_field(name="Categories", value=str(categories), inline=True)
        
        # Other info
        embed.add_field(name="Roles", value=str(len(guild.roles)), inline=True)
        embed.add_field(name="Boost Level", value=str(guild.premium_tier), inline=True)
        embed.add_field(name="Boosts", value=str(guild.premium_subscription_count), inline=True)
        
        # Try to create invite
        invite_link = await self._create_invite(guild)
        if invite_link:
            embed.add_field(name="Invite Link", value=f"[Join Server]({invite_link})", inline=False)
        else:
            embed.add_field(name="Invite Link", value="❌ Cannot create invite", inline=False)
        
        await working_msg.edit(content="", embed=embed)


async def setup(bot):
    """Setup function to add the cog to the bot."""
    await bot.add_cog(ServerManager(bot))
    print("ServerManager cog loaded successfully!")