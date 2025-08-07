import discord
from discord.ext import commands
from datetime import datetime
from groq import Groq

# Initialize Groq client
groq_client = Groq()

class DietCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.user_preferences = {}
        self.user_messages = {}

    @commands.command()
    async def diet(self, ctx):
        user_id = str(ctx.author.id)
        if user_id not in self.user_preferences:
            self.user_preferences[user_id] = {
                "diet_type": "balanced",
                "calories": 2000,
                "allergies": [],
                "last_refresh": datetime.now(),
                "meal_plan": None
            }

        embed = await self.create_embed(self.user_preferences[user_id])
        view = DietView(self.user_preferences[user_id], self.create_embed, self.update_message, self.generate_meal_plan, self.generate_recipe, user_id)
        message = await ctx.send(embed=embed, view=view)
        self.user_messages[user_id] = message

    async def create_embed(self, user_prefs):
        embed = discord.Embed(title="🍽️ Your AI-Powered Diet Plan", color=0x2ecc71)
        embed.set_thumbnail(url="attachment://dieticon.png")  # Replace with a relevant diet/health icon

        diet_type_emoji = {"balanced": "⚖️", "bulk": "💪", "cut": "✂️"}
        embed.add_field(
            name=f"{diet_type_emoji.get(user_prefs['diet_type'], '🍴')} Diet Type",
            value=f"**{user_prefs['diet_type'].capitalize()}**",
            inline=False
        )

        embed.add_field(
            name="🔥 Daily Calorie Goal",
            value=f"**{user_prefs['calories']} calories**",
            inline=False
        )

        allergies = ', '.join(user_prefs['allergies']) if user_prefs['allergies'] else "None"
        embed.add_field(
            name="⚠️ Allergies",
            value=f"**{allergies}**",
            inline=False
        )

        if user_prefs['meal_plan']:
            embed.add_field(
                name="📋 Your AI-Generated Meal Plan",
                value=user_prefs['meal_plan'],
                inline=False
            )
        else:
            embed.add_field(
                name="📋 Meal Plan",
                value="Use the `Generate Plan` button to create your AI-powered meal plan!",
                inline=False
            )

        embed.set_footer(text="Powered by JackyBot AI 🤖 | Eat well, feel great! 🌿")
        return embed

    async def update_message(self, user_id):
        if user_id in self.user_messages:
            message = self.user_messages[user_id]
            new_embed = await self.create_embed(self.user_preferences[user_id])
            new_view = DietView(self.user_preferences[user_id], self.create_embed, self.update_message, self.generate_meal_plan, self.generate_recipe, user_id)
            await message.edit(embed=new_embed, view=new_view)

    async def generate_meal_plan(self, user_prefs):
        prompt = f"""Generate a daily meal plan for a {user_prefs['diet_type']} diet with {user_prefs['calories']} calories.
        Allergies to avoid: {', '.join(user_prefs['allergies']) if user_prefs['allergies'] else 'None'}.
        Include breakfast, lunch, dinner, and a snack. Keep descriptions brief. Less than 900 characters including spaces. Meal titles in bold. Any measurements in grams.  Calorie total for each meal in title."""

        response = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a nutritionist AI assistant."},
                {"role": "user", "content": prompt}
            ],
            model="mixtral-8x7b-32768",
            max_tokens=300
        )

        return response.choices[0].message.content

    async def generate_recipe(self, meal_type, user_prefs):
        meal_plan = user_prefs['meal_plan']
        prompt = f"""Given the following meal plan:

        {meal_plan}

        Create a detailed recipe for the {meal_type} meal from this plan, suitable for a {user_prefs['diet_type']} diet.
        The recipe should be around {user_prefs['calories'] // 3} calories.
        Allergies to avoid: {', '.join(user_prefs['allergies']) if user_prefs['allergies'] else 'None'}.
        Include ingredients and step-by-step instructions. Ensure the recipe matches exactly what's described in the meal plan for this {meal_type}."""

        response = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a chef AI assistant with nutritional expertise."},
                {"role": "user", "content": prompt}
            ],
            model="mixtral-8x7b-32768",
            max_tokens=500
        )

        return response.choices[0].message.content

class DietView(discord.ui.View):
    def __init__(self, user_prefs, create_embed_func, update_message_func, generate_meal_plan_func, generate_recipe_func, user_id):
        super().__init__()
        self.user_prefs = user_prefs
        self.create_embed = create_embed_func
        self.update_message = update_message_func
        self.generate_meal_plan = generate_meal_plan_func
        self.generate_recipe = generate_recipe_func
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("This isn't your diet plan. Please use the `!diet` command to create your own.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Generate Plan", style=discord.ButtonStyle.success, emoji="🍳")
    async def generate_plan(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(thinking=True)
        self.user_prefs['meal_plan'] = await self.generate_meal_plan(self.user_prefs)
        await self.update_message(self.user_id)
        await interaction.followup.send("Your meal plan has been generated! 🎉", ephemeral=True)

    @discord.ui.button(label="Get Recipe", style=discord.ButtonStyle.primary, emoji="📖")
    async def get_recipe(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.user_prefs['meal_plan']:
            await interaction.response.send_message("Please generate a meal plan first!", ephemeral=True)
            return

        options = [
            discord.SelectOption(label="Breakfast", value="breakfast", emoji="🍳"),
            discord.SelectOption(label="Lunch", value="lunch", emoji="🥗"),
            discord.SelectOption(label="Dinner", value="dinner", emoji="🍽️")
        ]
        
        select = discord.ui.Select(placeholder="Choose a meal for the recipe", options=options)
        
        async def select_callback(interaction: discord.Interaction):
            await interaction.response.defer(thinking=True)
            meal_type = select.values[0]
            recipe = await self.generate_recipe(meal_type, self.user_prefs)
            
            embed = discord.Embed(title=f"🍳 Recipe for {meal_type.capitalize()}", color=0x3498db)
            embed.description = recipe
            embed.set_footer(text="Powered by JackyBot AI 🤖 | Bon appétit! 👨‍🍳")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
        
        select.callback = select_callback
        view = discord.ui.View()
        view.add_item(select)
        await interaction.response.send_message("Select a meal to get its recipe:", view=view, ephemeral=True)

    @discord.ui.button(label="Change Diet Type", style=discord.ButtonStyle.secondary, emoji="🔄")
    async def change_diet_type(self, interaction: discord.Interaction, button: discord.ui.Button):
        options = [
            discord.SelectOption(label="Balanced", description="A balanced diet for general health", emoji="⚖️"),
            discord.SelectOption(label="Bulk", description="A high-calorie diet for gaining muscle", emoji="💪"),
            discord.SelectOption(label="Cut", description="A low-calorie diet for losing fat", emoji="✂️")
        ]
        
        select = discord.ui.Select(placeholder="Choose your diet type", options=options)
        
        async def select_callback(interaction: discord.Interaction):
            self.user_prefs["diet_type"] = select.values[0].lower()
            self.user_prefs["meal_plan"] = None  # Reset meal plan when diet type changes
            await self.update_message(self.user_id)
            await interaction.response.send_message(f"Diet type changed to {select.values[0]}. Generate a new plan to see meal changes!", ephemeral=True)
        
        select.callback = select_callback
        view = discord.ui.View()
        view.add_item(select)
        await interaction.response.send_message("Select your new diet type:", view=view, ephemeral=True)

    @discord.ui.button(label="Set Calories", style=discord.ButtonStyle.secondary, emoji="🔥")
    async def set_calories(self, interaction: discord.Interaction, button: discord.ui.Button):
        class CalorieModal(discord.ui.Modal, title="Set Daily Calorie Goal"):
            calories = discord.ui.TextInput(label="Daily Calories", placeholder="Enter a number between 1000 and 5000")

            def __init__(self, view):
                super().__init__()
                self.view = view

            async def on_submit(self, interaction: discord.Interaction):
                try:
                    calories = int(self.calories.value)
                    if 1000 <= calories <= 5000:
                        self.view.user_prefs["calories"] = calories
                        self.view.user_prefs["meal_plan"] = None  # Reset meal plan when calories change
                        await self.view.update_message(self.view.user_id)
                        await interaction.response.send_message(f"Calorie goal updated to {calories} calories per day. 🎉", ephemeral=True)
                    else:
                        await interaction.response.send_message("Please enter a calorie goal between 1000 and 5000. 🙏", ephemeral=True)
                except ValueError:
                    await interaction.response.send_message("Please enter a valid number. 🔢", ephemeral=True)

        await interaction.response.send_modal(CalorieModal(self))

    @discord.ui.button(label="Manage Allergies", style=discord.ButtonStyle.secondary, emoji="⚠️")
    async def manage_allergies(self, interaction: discord.Interaction, button: discord.ui.Button):
        options = [
            discord.SelectOption(label="Add Allergies", value="add", emoji="➕"),
            discord.SelectOption(label="Remove Allergy", value="remove", emoji="➖")
        ]
        
        select = discord.ui.Select(placeholder="Choose an action", options=options)
        
        async def select_callback(interaction: discord.Interaction):
            if select.values[0] == "add":
                modal = discord.ui.Modal(title="Add Allergies")
                modal.add_item(discord.ui.TextInput(label="Allergies", placeholder="Enter allergies, separated by commas"))
                
                async def modal_callback(interaction: discord.Interaction):
                    allergies = [allergy.strip().lower() for allergy in modal.children[0].value.split(',')]
                    added_allergies = []
                    already_present = []
                    
                    for allergy in allergies:
                        if allergy and allergy not in self.user_prefs["allergies"]:
                            self.user_prefs["allergies"].append(allergy)
                            added_allergies.append(allergy)
                        elif allergy:
                            already_present.append(allergy)
                    
                    if added_allergies:
                        self.user_prefs["meal_plan"] = None  # Reset meal plan when allergies change
                        await self.update_message(self.user_id)
                    
                    response = ""
                    if added_allergies:
                        response += f"Added the following allergies: {', '.join(added_allergies)}. 🆕\n"
                    if already_present:
                        response += f"The following allergies were already in your list: {', '.join(already_present)}. 📝\n"
                    if not response:
                        response = "No valid allergies were provided. 🚫"
                    
                    await interaction.response.send_message(response, ephemeral=True)
                
                modal.on_submit = modal_callback
                await interaction.response.send_modal(modal)
            else:
                if not self.user_prefs["allergies"]:
                    await interaction.response.send_message("You don't have any allergies to remove. 🎉", ephemeral=True)
                else:
                    options = [discord.SelectOption(label=allergy, value=allergy) for allergy in self.user_prefs["allergies"]]
                    remove_select = discord.ui.Select(placeholder="Choose an allergy to remove", options=options)
                    
                    async def remove_callback(interaction: discord.Interaction):
                        allergy = remove_select.values[0]
                        self.user_prefs["allergies"].remove(allergy)
                        self.user_prefs["meal_plan"] = None  # Reset meal plan when allergies change
                        await self.update_message(self.user_id)
                        await interaction.response.send_message(f"Removed {allergy} from your allergies list. ✅", ephemeral=True)
                    
                    remove_select.callback = remove_callback
                    view = discord.ui.View()
                    view.add_item(remove_select)
                    await interaction.response.send_message("Select an allergy to remove:", view=view, ephemeral=True)
        
        select.callback = select_callback
        view = discord.ui.View()
        view.add_item(select)
        await interaction.response.send_message("Choose an action for managing allergies:", view=view, ephemeral=True)

async def setup(bot):
    await bot.add_cog(DietCog(bot))