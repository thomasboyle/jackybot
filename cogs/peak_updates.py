import discord
from discord.ext import commands, tasks
import asyncio
import aiohttp
from bs4 import BeautifulSoup
import re
from datetime import datetime
import json
import os
import logging
import random

class PeakUpdatesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.update_channel_name = "peak-updates"
        self.peak_news_url = "https://steamcommunity.com/app/3527290/allnews/"
        self.json_dir = "json"
        self.updates_file = os.path.join(self.json_dir, "peak_updates.json")
        self.server_updates = self.load_updates()
        self.latest_update_cache = None
        self.last_check_time = 0
        self.cache_ttl = 1800  # 30 minutes
        
        # Logging
        logging.basicConfig(filename='peak_bot.log', level=logging.INFO,
                          format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger('PeakUpdates')

    async def cog_load(self):
        """Setup and start update checking"""
        try:
            self.check_for_updates.start()
            self.logger.info("PEAK updates cog loaded successfully")
        except Exception as e:
            self.logger.error(f"Failed to setup cog: {e}")

    async def cog_unload(self):
        """Clean shutdown"""
        self.check_for_updates.cancel()

    def load_updates(self):
        """Load updates history from JSON"""
        os.makedirs(self.json_dir, exist_ok=True)
        try:
            with open(self.updates_file, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    async def save_updates(self):
        """Save updates asynchronously"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._save_sync)

    def _save_sync(self):
        """Synchronous save operation"""
        try:
            with open(self.updates_file, 'w') as f:
                json.dump(self.server_updates, f, indent=2)
        except Exception as e:
            self.logger.error(f"Save failed: {e}")

    async def fetch_latest_update(self, force_refresh=False):
        """Fetch latest PEAK update with caching"""
        current_time = int(datetime.now().timestamp())
        
        # Return cache if valid
        if (not force_refresh and self.latest_update_cache and 
            current_time - self.last_check_time < self.cache_ttl):
            return self.latest_update_cache

        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self.peak_news_url) as response:
                    if response.status != 200:
                        self.logger.error(f"HTTP {response.status} when fetching PEAK news")
                        return self.latest_update_cache
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Find the news items on the Steam community page
                    news_items = soup.find_all('div', class_='modalContentLink', limit=5)
                    
                    if not news_items:
                        # Try alternative selectors
                        news_items = soup.find_all('a', href=re.compile(r'/news/app/3527290/view/'), limit=5)
                    
                    if not news_items:
                        self.logger.warning("No news items found on PEAK page")
                        return self.latest_update_cache

                    # Process the first (most recent) news item
                    latest_item = news_items[0]
                    
                    # Extract title
                    title_elem = latest_item.find('div', class_='event_title') or latest_item.find('h3') or latest_item.find(text=re.compile(r'.+'))
                    if isinstance(title_elem, str):
                        title = title_elem.strip()
                    else:
                        title = title_elem.get_text().strip() if title_elem else "PEAK Update"
                    
                    # Extract date
                    date_elem = latest_item.find('div', class_='event_timestamp') or latest_item.find('span', string=re.compile(r'\w+ \d+'))
                    date_str = date_elem.get_text().strip() if date_elem else "Recent"
                    
                    # Extract content/description
                    content_elem = latest_item.find('div', class_='event_description') or latest_item.find('p')
                    content = content_elem.get_text().strip()[:2000] if content_elem else title
                    
                    # Extract link
                    link = latest_item.get('href', '')
                    if link and not link.startswith('http'):
                        link = f"https://steamcommunity.com{link}"
                    else:
                        link = self.peak_news_url

                    update_info = {
                        'title': title,
                        'date': date_str,
                        'content': content,
                        'link': link,
                        'timestamp': current_time
                    }
                    
                    self.latest_update_cache = update_info
                    self.last_check_time = current_time
                    return update_info

        except Exception as e:
            self.logger.error(f"Fetch error: {e}")
            
        return self.latest_update_cache

    async def summarize_update(self, update_info):
        """Summarize the update using Groq AI"""
        try:
            # Get a connection from the bot's pool
            client = self.bot.pool.get_connection()
            
            prompt = f"""
            Summarize this PEAK game patch note in a concise, Discord-friendly format. Only write about content that is contained within the patch notes post.  (max 800 characters):
            
            Title: {update_info['title']}
            Content: {update_info['content']}
            
            Focus on:
            - Key changes and fixes
            - New features or content
            - Important bug fixes
            
            Use Discord formatting (bold, bullets) and keep it engaging for gamers.
            """
            
            response = client.chat.completions.create(
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                messages=[
                    {"role": "system", "content": "You are a gaming news summarizer. Create concise, exciting, accurate summaries of game updates for Discord."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=300,
                temperature=0.7
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            self.logger.error(f"Summarization error: {e}")
            # Fallback to truncated original content
            return update_info['content'][:500] + "..." if len(update_info['content']) > 500 else update_info['content']

    @tasks.loop(seconds=7200)  # Check every 2 hours
    async def check_for_updates(self):
        """Check for updates with jitter"""
        try:
            update_info = await self.fetch_latest_update()
            if update_info:
                await self.post_to_channels(update_info)
        except Exception as e:
            self.logger.error(f"Update check failed: {e}")
        
        # Add jitter to prevent synchronized requests
        await asyncio.sleep(random.randint(-300, 300))

    @check_for_updates.before_loop
    async def before_check_for_updates(self):
        await self.bot.wait_until_ready()

    async def post_to_channels(self, update_info):
        """Post update to all peak-updates channels"""
        channels = [discord.utils.get(guild.text_channels, name=self.update_channel_name) 
                   for guild in self.bot.guilds]
        channels = [ch for ch in channels if ch]  # Filter None values
        
        for channel in channels:
            try:
                guild_id = str(channel.guild.id)
                
                # Initialize guild record if needed
                if guild_id not in self.server_updates:
                    self.server_updates[guild_id] = {"last_update": None}

                # Skip if already posted
                if self.server_updates[guild_id]["last_update"] == update_info['title']:
                    continue

                await self.post_update(channel, update_info)
                self.server_updates[guild_id]["last_update"] = update_info['title']
                
            except discord.Forbidden:
                self.logger.warning(f"No permission: {channel.guild.name}")
            except Exception as e:
                self.logger.error(f"Post failed {channel.guild.name}: {e}")
        
        # Save once after all updates
        if channels:
            await self.save_updates()

    async def post_update(self, channel, update_info):
        """Create and send update embed with AI summary"""
        try:
            # Get AI summary
            summary = await self.summarize_update(update_info)
            
            embed = discord.Embed(
                title="🏔️ PEAK Update Available!",
                description=f"**{update_info['title']}**",
                color=0x4A90E2,
                timestamp=datetime.now()
            )
            
            embed.add_field(
                name="📝 Summary",
                value=summary,
                inline=False
            )
            
            embed.add_field(
                name="📅 Date",
                value=update_info['date'],
                inline=True
            )
            
            embed.add_field(
                name="🔗 Read Full Update",
                value=f"[Steam Community]({update_info['link']})",
                inline=True
            )
            
            embed.set_footer(text="PEAK Updates • Stay informed, Scout!")
            embed.set_thumbnail(url="https://steamcdn-a.akamaihd.net/steam/apps/3527290/header.jpg")
            
            await channel.send(embed=embed)
            self.logger.info(f"Posted update '{update_info['title']}' to {channel.guild.name}")
            
        except Exception as e:
            self.logger.error(f"Failed to post update: {e}")

    @commands.command(name="peak_latest")
    @commands.has_permissions(administrator=True)
    async def peak_latest(self, ctx):
        """Manual command to check for latest PEAK update"""
        async with ctx.typing():
            try:
                update_info = await self.fetch_latest_update(force_refresh=True)
                
                if not update_info:
                    await ctx.reply("❌ Could not fetch the latest PEAK update. Check logs for details.")
                    return
                
                # Create and send embed
                await self.post_update(ctx.channel, update_info)
                
                # Mark as posted for this guild
                guild_id = str(ctx.guild.id)
                if guild_id not in self.server_updates:
                    self.server_updates[guild_id] = {}
                self.server_updates[guild_id]["last_update"] = update_info['title']
                await self.save_updates()
                
            except Exception as e:
                self.logger.error(f"Manual check failed: {e}")
                await ctx.reply(f"❌ Error fetching update: {str(e)}")

    @commands.command(name="peak_status")
    @commands.has_permissions(administrator=True)
    async def peak_status(self, ctx):
        """Check the status of PEAK update monitoring"""
        embed = discord.Embed(
            title="🏔️ PEAK Updates Status",
            color=0x4A90E2
        )
        
        embed.add_field(
            name="Task Status",
            value="✅ Running" if self.check_for_updates.is_running() else "❌ Stopped",
            inline=True
        )
        
        embed.add_field(
            name="Check Interval",
            value="Every 2 hours",
            inline=True
        )
        
        embed.add_field(
            name="Last Check",
            value=f"<t:{self.last_check_time}:R>" if self.last_check_time else "Never",
            inline=True
        )
        
        embed.add_field(
            name="Target Channel",
            value=f"#{self.update_channel_name}",
            inline=True
        )
        
        embed.add_field(
            name="Source",
            value=f"[Steam Community]({self.peak_news_url})",
            inline=True
        )
        
        guild_id = str(ctx.guild.id)
        last_update = self.server_updates.get(guild_id, {}).get("last_update", "None")
        embed.add_field(
            name="Last Posted Update",
            value=last_update,
            inline=False
        )
        
        await ctx.reply(embed=embed)

async def setup(bot):
    await bot.add_cog(PeakUpdatesCog(bot)) 