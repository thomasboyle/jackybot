import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from typing import List, Optional
import json
import os

class RoleManagementView(discord.ui.View):
    def __init__(self, cog, guild: discord.Guild):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        
    @discord.ui.button(label="Manage Auto-Roles", style=discord.ButtonStyle.primary, emoji="🔧")
    async def manage_auto_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = AutoRoleView(self.cog, self.guild)
        embed = discord.Embed(
            title="Auto-Role Management",
            description="Select roles that will automatically be given to new members when they join the server.",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="Bulk Role Operations", style=discord.ButtonStyle.secondary, emoji="👥")
    async def bulk_role_operations(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = BulkRoleView(self.cog, self.guild)
        embed = discord.Embed(
            title="Bulk Role Operations",
            description="Add or remove a role from all members in the server.",
            color=discord.Color.orange()
        )
        await interaction.response.edit_message(embed=embed, view=view)

class RoleSelect(discord.ui.Select):
    def __init__(self, guild: discord.Guild, current_auto_roles: List[int], cog):
        self.guild = guild
        self.current_auto_roles = set(current_auto_roles)
        self.cog = cog
        
        # Cache bot member and role position
        bot_member = guild.me
        bot_position = bot_member.top_role.position if bot_member else 0
        
        options = []
        # Pre-filter and sort roles in single pass
        manageable_roles = [r for r in guild.roles 
                          if r.name != "@everyone" and not r.managed and 
                          r.position < bot_position]
        manageable_roles.sort(key=lambda r: r.position, reverse=True)
        
        for role in manageable_roles[:25]:  # Limit to 25 upfront
            emoji = "✅" if role.id in self.current_auto_roles else "⭕"
            member_count = sum(1 for m in role.members if not m.bot)
            
            options.append(discord.SelectOption(
                label=role.name[:100],
                value=str(role.id),
                description=f"Members: {member_count} | Position: {role.position}",
                emoji=emoji
            ))
        
        if not options:
            options.append(discord.SelectOption(
                label="No manageable roles found",
                value="none",
                description="Bot needs higher role position"
            ))
        
        super().__init__(
            placeholder="Select roles to toggle as auto-roles...",
            options=options,
            max_values=len(options) if options[0].value != "none" else 1
        )
    
    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message(
                "No manageable roles available. Make sure the bot's role is positioned higher than the roles you want to manage.",
                ephemeral=True
            )
            return
            
        # Toggle roles using set operations for O(1) lookups
        current_auto_roles = self.current_auto_roles.copy()
        for role_id in (int(rid) for rid in self.values):
            if role_id in current_auto_roles:
                current_auto_roles.discard(role_id)
            else:
                current_auto_roles.add(role_id)
        
        await self.cog.save_auto_roles(self.guild.id, list(current_auto_roles))
        
        view = AutoRoleView(self.cog, self.guild)
        
        # Batch role lookups
        role_names = [role.name for role in self.guild.roles if role.id in current_auto_roles]
        
        embed = discord.Embed(
            title="Auto-Role Management",
            description="Select roles that will automatically be given to new members when they join the server.",
            color=discord.Color.green()
        )
        
        embed.add_field(
            name="Current Auto-Roles",
            value=", ".join(role_names) if role_names else "None",
            inline=False
        )
        
        await interaction.response.edit_message(embed=embed, view=view)

class AutoRoleView(discord.ui.View):
    def __init__(self, cog, guild: discord.Guild):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.add_item(RoleSelect(guild, cog.get_auto_roles(guild.id), cog))
    
    @discord.ui.button(label="Back", style=discord.ButtonStyle.gray, emoji="⬅️")
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = RoleManagementView(self.cog, self.guild)
        embed = discord.Embed(
            title="Role Management System",
            description="Choose an option below to manage server roles.",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=view)

class BulkRoleSelect(discord.ui.Select):
    def __init__(self, guild: discord.Guild):
        self.guild = guild
        
        # Cache bot member and role position
        bot_member = guild.me
        bot_position = bot_member.top_role.position if bot_member else 0
        
        # Pre-filter and sort roles in single pass
        manageable_roles = [r for r in guild.roles 
                          if r.name != "@everyone" and not r.managed and 
                          r.position < bot_position]
        manageable_roles.sort(key=lambda r: r.position, reverse=True)
        
        options = []
        for role in manageable_roles[:25]:  # Limit to 25 upfront
            member_count = sum(1 for m in role.members if not m.bot)
            options.append(discord.SelectOption(
                label=role.name[:100],
                value=str(role.id),
                description=f"Members: {member_count} | Position: {role.position}"
            ))
        
        if not options:
            options.append(discord.SelectOption(
                label="No manageable roles found",
                value="none",
                description="Bot needs higher role position"
            ))
        
        super().__init__(
            placeholder="Select a role for bulk operations...",
            options=options,
            max_values=1
        )
    
    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message(
                "No manageable roles available. Make sure the bot's role is positioned higher than the roles you want to manage.",
                ephemeral=True
            )
            return
            
        role = self.guild.get_role(int(self.values[0]))
        
        if not role:
            await interaction.response.send_message("Role not found!", ephemeral=True)
            return
        
        view = BulkRoleActionView(self.guild, role)
        member_count = sum(1 for m in role.members if not m.bot)
        
        embed = discord.Embed(
            title=f"Bulk Operations for: {role.name}",
            description=f"Choose whether to add or remove this role from all server members.\n\n**Current members with this role:** {member_count}\n**Role Position:** {role.position}",
            color=role.color
        )
        
        await interaction.response.edit_message(embed=embed, view=view)

class BulkRoleActionView(discord.ui.View):
    def __init__(self, guild: discord.Guild, role: discord.Role):
        super().__init__(timeout=300)
        self.guild = guild
        self.role = role
    
    @discord.ui.button(label="Add to All Members", style=discord.ButtonStyle.green, emoji="➕")
    async def add_to_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        if not self.guild.chunked:
            await self.guild.chunk(cache=True)
        
        # Pre-compute role membership using set for O(1) lookups
        role_members = set(self.role.members)
        members_without_role = [m for m in self.guild.members if m not in role_members and not m.bot]
        
        if not members_without_role:
            embed = discord.Embed(
                title="No Action Needed",
                description=f"All members already have the **{self.role.name}** role.",
                color=discord.Color.yellow()
            )
            await interaction.followup.edit_message(interaction.message.id, embed=embed, view=None)
            return
        
        embed = discord.Embed(
            title="Confirm Bulk Role Addition",
            description=f"Are you sure you want to add **{self.role.name}** to **{len(members_without_role)}** members?",
            color=discord.Color.red()
        )
        
        view = ConfirmationView(self.guild, self.role, "add", members_without_role)
        await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
    
    @discord.ui.button(label="Remove from All Members", style=discord.ButtonStyle.red, emoji="➖")
    async def remove_from_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        if not self.guild.chunked:
            await self.guild.chunk(cache=True)
        
        members_with_role = [m for m in self.role.members]
        
        if not members_with_role:
            embed = discord.Embed(
                title="No Action Needed",
                description=f"No members currently have the **{self.role.name}** role.",
                color=discord.Color.yellow()
            )
            await interaction.followup.edit_message(interaction.message.id, embed=embed, view=None)
            return
        
        embed = discord.Embed(
            title="Confirm Bulk Role Removal",
            description=f"Are you sure you want to remove **{self.role.name}** from **{len(members_with_role)}** members?",
            color=discord.Color.red()
        )
        
        view = ConfirmationView(self.guild, self.role, "remove", members_with_role)
        await interaction.followup.edit_message(interaction.message.id, embed=embed, view=view)
    
    @discord.ui.button(label="Back", style=discord.ButtonStyle.gray, emoji="⬅️")
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = BulkRoleView(None, self.guild)
        embed = discord.Embed(
            title="Bulk Role Operations",
            description="Add or remove a role from all members in the server.",
            color=discord.Color.orange()
        )
        await interaction.response.edit_message(embed=embed, view=view)

class ConfirmationView(discord.ui.View):
    def __init__(self, guild: discord.Guild, role: discord.Role, action: str, members: List[discord.Member]):
        super().__init__(timeout=60)
        self.guild = guild
        self.role = role
        self.action = action
        self.members = members
    
    async def process_members_in_batches(self, members: List[discord.Member], batch_size: int = 10):
        """Process members in concurrent batches with optimized rate limiting"""
        success_count = error_count = 0
        
        for i in range(0, len(members), batch_size):
            batch = members[i:i + batch_size]
            
            # Create tasks for this batch
            if self.action == "add":
                tasks = [m.add_roles(self.role, reason="Bulk role operation") for m in batch]
            else:
                tasks = [m.remove_roles(self.role, reason="Bulk role operation") for m in batch]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Count results
            for result in results:
                if isinstance(result, Exception):
                    error_count += 1
                else:
                    success_count += 1
            
            await asyncio.sleep(0.5)
            yield success_count, error_count, i + len(batch)
    
    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.red, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        progress_embed = discord.Embed(
            title=f"{'Adding' if self.action == 'add' else 'Removing'} Role...",
            description=f"Processing {len(self.members)} members. Please wait...",
            color=discord.Color.yellow()
        )
        
        await interaction.followup.edit_message(interaction.message.id, embed=progress_embed, view=None)
        
        success_count = error_count = processed = 0
        
        async for current_success, current_errors, current_processed in self.process_members_in_batches(self.members):
            success_count = current_success
            error_count = current_errors
            processed = current_processed
            
            progress_percentage = (processed * 100) // len(self.members)
            progress_embed.description = (
                f"Processing {processed}/{len(self.members)} members "
                f"({progress_percentage}%)\n"
                f"✅ Success: {success_count} | ❌ Errors: {error_count}"
            )
            
            try:
                await interaction.edit_original_response(embed=progress_embed)
            except discord.NotFound:
                pass
        
        result_embed = discord.Embed(
            title="Bulk Operation Complete",
            description=(
                f"**Role:** {self.role.name}\n"
                f"**Action:** {'Added' if self.action == 'add' else 'Removed'}\n"
                f"**Success:** {success_count}\n"
                f"**Errors:** {error_count}\n"
                f"**Total Processed:** {processed}"
            ),
            color=discord.Color.green() if error_count == 0 else discord.Color.yellow()
        )
        
        if error_count > 0:
            result_embed.add_field(
                name="Note",
                value="Some operations failed. This is usually due to permission issues or members leaving during the process.",
                inline=False
            )
        
        try:
            await interaction.edit_original_response(embed=result_embed)
        except discord.NotFound:
            pass
    
    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.gray, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="Operation Cancelled",
            description="No changes were made.",
            color=discord.Color.gray()
        )
        await interaction.response.edit_message(embed=embed, view=None)

class BulkRoleView(discord.ui.View):
    def __init__(self, cog, guild: discord.Guild):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.add_item(BulkRoleSelect(guild))
    
    @discord.ui.button(label="Back", style=discord.ButtonStyle.gray, emoji="⬅️")
    async def back_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = RoleManagementView(self.cog, self.guild)
        embed = discord.Embed(
            title="Role Management System",
            description="Choose an option below to manage server roles.",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=view)

class RoleManagement(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.auto_roles_file = "json/auto_roles.json"
        self.auto_roles = self.load_auto_roles()
    
    def load_auto_roles(self) -> dict:
        """Load auto-roles from JSON file"""
        if os.path.exists(self.auto_roles_file):
            try:
                with open(self.auto_roles_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                pass
        return {}
    
    async def save_auto_roles(self, guild_id: int, role_ids: List[int]):
        """Save auto-roles to JSON file"""
        self.auto_roles[str(guild_id)] = role_ids
        os.makedirs(os.path.dirname(self.auto_roles_file), exist_ok=True)
        with open(self.auto_roles_file, 'w') as f:
            json.dump(self.auto_roles, f, indent=2)
    
    def get_auto_roles(self, guild_id: int) -> List[int]:
        """Get auto-roles for a specific guild"""
        return self.auto_roles.get(str(guild_id), [])
    
    @commands.command(name="roles")
    @commands.has_permissions(administrator=True)
    async def role_management(self, ctx):
        """Main role management command"""
        if not ctx.guild.me.guild_permissions.manage_roles:
            await ctx.reply("I need the 'Manage Roles' permission to use this command.")
            return
        
        if not ctx.guild.chunked:
            await ctx.guild.chunk(cache=True)
        
        embed = discord.Embed(
            title="Role Management System",
            description="Choose an option below to manage server roles.",
            color=discord.Color.blue()
        )
        
        view = RoleManagementView(self, ctx.guild)
        await ctx.reply(embed=embed, view=view)
    
    @commands.Cog.listener()
    async def on_member_join(self, member):
        """Automatically assign roles to new members"""
        auto_role_ids = self.get_auto_roles(member.guild.id)
        if not auto_role_ids:
            return
        
        # Cache bot top role position
        bot_top_position = member.guild.me.top_role.position
        
        roles_to_add = []
        for role_id in auto_role_ids:
            role = member.guild.get_role(role_id)
            if role and role.position < bot_top_position:
                roles_to_add.append(role)
        
        if roles_to_add:
            try:
                await member.add_roles(*roles_to_add, reason="Auto-role assignment")
            except discord.HTTPException:
                pass
    
    @role_management.error
    async def role_management_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.reply("You need administrator privileges to use this command.")
        else:
            await ctx.reply("An error occurred while processing the command.")

async def setup(bot):
    await bot.add_cog(RoleManagement(bot))