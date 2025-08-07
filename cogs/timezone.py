import discord
from discord.ext import commands
import pytz
from datetime import datetime
import json
import os
from discord import ButtonStyle, SelectOption, TextStyle
from discord.ui import View, Button, Select, Modal, TextInput

class TimezoneSearchModal(Modal, title="Search Timezone"):
    def __init__(self, cog, ctx, original_message=None):
        super().__init__()
        self.cog = cog
        self.ctx = ctx
        self.original_message = original_message
        self.search_input = TextInput(
            label="Enter timezone (e.g., Asia/Tokyo)",
            placeholder="Type a timezone name...",
            style=TextStyle.short
        )
        self.add_item(self.search_input)

    async def on_submit(self, interaction: discord.Interaction):
        user_id = str(self.ctx.author.id)
        search_term = self.search_input.value.strip().lower()
        
        matching_tz = next((tz for tz in self.cog.all_timezones_cached if search_term in tz.lower()), None)

        if matching_tz:
            user_timezones = self.cog.user_timezones.setdefault(user_id, [])
            if matching_tz not in user_timezones:
                user_timezones.append(matching_tz)
                self.cog.save_data()
                await interaction.response.edit_message(content=f"Added {matching_tz} successfully!", embed=None, view=None)
                await self.cog.show_user_timezones(self.ctx)
            else:
                await interaction.response.edit_message(
                    content=f"Timezone '{matching_tz}' is already added.", 
                    embed=None, 
                    view=None
                )
        else:
            await interaction.response.edit_message(
                content=f"No matching timezone found for '{search_term}'.", 
                embed=None, 
                view=None
            )

class TimezoneCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_file = os.path.join(r"C:\Users\thoma\Documents\Python Programs\JackyBot\JackyBot March 2025\JackyBot\json", "timezone_data.json")
        self.common_timezones = [
            "UTC", "America/New_York", "America/Los_Angeles", "Europe/London",
            "Europe/Paris", "Asia/Tokyo", "Australia/Sydney", "America/Chicago",
            "America/Denver", "Asia/Shanghai", "Asia/Dubai", "Asia/Kolkata", "Pacific/Auckland"
        ]
        self.all_timezones_cached = list(pytz.all_timezones)
        self.timezone_objects = {}  # Cache timezone objects
        self.load_data()

    def load_data(self):
        os.makedirs(os.path.dirname(self.data_file), exist_ok=True)
        try:
            with open(self.data_file, 'r') as f:
                self.user_timezones = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.user_timezones = {}

    def save_data(self):
        with open(self.data_file, 'w') as f:
            json.dump(self.user_timezones, f)

    def get_timezone_object(self, timezone_str):
        if timezone_str not in self.timezone_objects:
            self.timezone_objects[timezone_str] = pytz.timezone(timezone_str)
        return self.timezone_objects[timezone_str]

    def get_user_time(self, timezone_str):
        tz = self.get_timezone_object(timezone_str)
        current_time = datetime.now(tz)
        return current_time.strftime("%H:%M:%S (%I:%M:%S %p) - %d %b %Y")

    @commands.command(name="time")
    async def time_command(self, ctx):
        user_id = str(ctx.author.id)
        if user_id in self.user_timezones and self.user_timezones[user_id]:
            await self.show_user_timezones(ctx)
        else:
            await self.show_timezone_selection(ctx)

    async def show_user_timezones(self, ctx):
        user_id = str(ctx.author.id)
        embed = discord.Embed(
            title="Your Timezones",
            description="Current times in your selected timezones:",
            color=discord.Color.blue()
        )

        for tz in self.user_timezones[user_id]:
            time_str = self.get_user_time(tz)
            embed.add_field(name=tz, value=time_str, inline=False)

        view = View()
        view.add_item(Button(label="Add More Timezones", style=ButtonStyle.primary, custom_id=f"add_tz_{user_id}"))
        view.add_item(Button(label="Delete Timezones", style=ButtonStyle.danger, custom_id=f"del_tz_{user_id}"))

        message = await ctx.reply(embed=embed, view=view)
        
        async def button_callback(interaction):
            if interaction.user.id != ctx.author.id:
                return
            if interaction.data["custom_id"].startswith("add_tz"):
                await self.show_timezone_selection(ctx, message)
            elif interaction.data["custom_id"].startswith("del_tz"):
                await self.show_delete_selection(ctx, message)
            await interaction.response.defer()

        for button in view.children:
            if isinstance(button, Button):
                button.callback = button_callback

    async def show_delete_selection(self, ctx, original_message):
        user_id = str(ctx.author.id)
        options = [SelectOption(label=tz, value=tz) for tz in self.user_timezones[user_id]]
        
        embed = discord.Embed(
            title="Delete a Timezone",
            description="Select a timezone to remove from your list",
            color=discord.Color.red()
        )

        view = View(timeout=60.0)
        select = Select(placeholder="Choose a timezone to delete...", options=options)
        view.add_item(select)

        async def select_callback(interaction):
            if interaction.user.id == ctx.author.id:
                selected_tz = interaction.data['values'][0]
                self.user_timezones[user_id].remove(selected_tz)
                if not self.user_timezones[user_id]:
                    del self.user_timezones[user_id]
                self.save_data()
                await interaction.response.edit_message(content=f"Removed {selected_tz} successfully!", embed=None, view=None)
                if user_id in self.user_timezones:
                    await self.show_user_timezones(ctx)
                else:
                    await self.show_timezone_selection(ctx)

        select.callback = select_callback
        await original_message.edit(embed=embed, view=view)

    async def show_timezone_selection(self, ctx, original_message=None, page=0):
        user_id = str(ctx.author.id)
        selected_tz = self.user_timezones.get(user_id, [])

        if page == 0:
            available_timezones = [tz for tz in self.common_timezones if tz not in selected_tz]
        else:
            other_timezones = [tz for tz in self.all_timezones_cached if tz not in self.common_timezones and tz not in selected_tz]
            start_idx = (page - 1) * 22
            available_timezones = other_timezones[start_idx:start_idx + 22]

        options = [SelectOption(label=tz, value=tz) for tz in available_timezones]

        embed = discord.Embed(
            title="Select a Timezone",
            description="Choose a timezone to add to your list" + (f" (Page {page + 1})" if page > 0 else ""),
            color=discord.Color.green()
        )

        view = View(timeout=60.0)
        select = Select(placeholder="Choose a timezone...", options=options)
        view.add_item(select)
        view.add_item(Button(label="Search For More...", style=ButtonStyle.secondary, custom_id="search"))

        if page > 0:
            view.add_item(Button(label="Previous", style=ButtonStyle.grey, custom_id="prev"))
        if len(available_timezones) == 22:
            view.add_item(Button(label="Next", style=ButtonStyle.grey, custom_id="next"))

        async def select_callback(interaction):
            if interaction.user.id == ctx.author.id:
                selected_tz = interaction.data['values'][0]
                self.user_timezones.setdefault(user_id, []).append(selected_tz)
                self.save_data()
                await interaction.response.edit_message(content="Timezone added successfully!", embed=None, view=None)
                await self.show_user_timezones(ctx)

        async def button_callback(interaction):
            if interaction.user.id == ctx.author.id:
                if interaction.data["custom_id"] == "search":
                    await interaction.response.send_modal(TimezoneSearchModal(self, ctx, interaction.message))
                else:
                    new_page = page - 1 if interaction.data["custom_id"] == "prev" else page + 1
                    await self.show_timezone_selection(ctx, interaction.message, new_page)
                await interaction.response.defer()

        select.callback = select_callback
        for button in view.children:
            if isinstance(button, Button):
                button.callback = button_callback

        if original_message:
            await original_message.edit(embed=embed, view=view)
        else:
            await ctx.reply(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(TimezoneCog(bot))