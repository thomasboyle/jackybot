import discord
from discord.ext import commands, tasks
import asyncio
from bs4 import BeautifulSoup
import re
from datetime import datetime
import json
import os
import logging
from playwright.async_api import async_playwright
from packaging import version
import random

class SteamOSUpdatesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.update_channel_name = "steamos-updates"
        self.update_url = "https://store.steampowered.com/news/app/1675200"
        self.json_dir = "C:\\Users\\thoma\\Documents\\Python Programs\\JackyBot\\JackyBot March 2025\\JackyBot\\json\\"
        self.updates_file = os.path.join(self.json_dir, "steamos_updates.json")
        self.server_updates = self.load_updates()
        self.latest_update_cache = None
        self.last_check_time = 0
        self.cache_ttl = 1800  # 30 minutes
        
        # Playwright setup
        self.playwright = None
        self.browser = None
        self.page = None
        
        # Logging
        logging.basicConfig(filename='steamos_bot.log', level=logging.INFO,
                          format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger('SteamOSUpdates')

    async def cog_load(self):
        """Setup playwright browser and start update checking"""
        try:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=True, args=['--disable-gpu', '--disable-dev-shm-usage'])
            self.page = await (await self.browser.new_context()).new_page()
            self.check_for_updates.start()
            self.logger.info("SteamOS cog loaded successfully")
        except Exception as e:
            self.logger.error(f"Failed to setup browser: {e}")

    async def cog_unload(self):
        """Clean shutdown"""
        self.check_for_updates.cancel()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

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
        """Fetch latest SteamOS update with caching"""
        current_time = int(datetime.now().timestamp())
        
        # Return cache if valid
        if (not force_refresh and self.latest_update_cache and 
            current_time - self.last_check_time < self.cache_ttl):
            return self.latest_update_cache

        try:
            await self.page.goto(self.update_url, timeout=20000)
            await self.page.wait_for_selector('a[href*="/news/app/1675200/view/"]', timeout=8000)
            
            # Get minimal HTML
            news_section = await self.page.query_selector('.eventcapsule_List')
            html = await (news_section.inner_html() if news_section else self.page.content())
            
            soup = BeautifulSoup(html, 'html.parser')
            posts = soup.find_all('a', href=re.compile(r'/news/app/1675200/view/\d+'), limit=5)
            
            if not posts:
                return self.latest_update_cache

            # Process only SteamOS/Steam Deck posts
            updates = []
            steamos_pattern = re.compile(r'SteamOS|Steam Deck', re.IGNORECASE)
            version_pattern = re.compile(r'\d+\.\d+\.\d+')
            
            for post in posts:
                title_elem = post.find('div', string=re.compile(r'.+'))
                if not title_elem:
                    continue
                    
                title = title_elem.text.strip()
                if not steamos_pattern.search(title):
                    continue

                # Extract version
                version_match = version_pattern.search(title)
                version_str = version_match.group() if version_match else "0.0.0"

                # Get date and content efficiently
                date_elem = post.find('div', string=re.compile(r'(ago|\d{1,2}\s\w+\s\d{4})'))
                date_str = date_elem.text.strip() if date_elem else "Unknown"
                
                content_elem = post.find('div', string=re.compile(r'.{10,}'))
                content = content_elem.text.strip() if content_elem else title

                link = post.get('href', '')
                if link and not link.startswith('http'):
                    link = f"https://store.steampowered.com{link}"

                updates.append({
                    'title': title,
                    'date': date_str,
                    'content': content[:1500] + ("..." if len(content) > 1500 else ""),
                    'link': link or self.update_url,
                    'version': version.parse(version_str)
                })

            if updates:
                # Get latest version
                latest = max(updates, key=lambda x: x['version'])
                del latest['version']  # Remove sorting field
                
                self.latest_update_cache = latest
                self.last_check_time = current_time
                return latest

        except Exception as e:
            self.logger.error(f"Fetch error: {e}")
            
        return self.latest_update_cache

    @tasks.loop(seconds=3600)
    async def check_for_updates(self):
        """Check for updates every hour with jitter"""
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
        """Post update to all steamos-update channels"""
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
        """Create and send update embed"""
        embed = discord.Embed(
            title=update_info['title'],
            description=update_info['content'],
            color=0x1a9fff,
            url=update_info['link']
        )
        
        embed.set_author(
            name="SteamOS Update", 
            icon_url="https://cdn.cloudflare.steamstatic.com/steamdeck/images/steamdeck_logo.png"
        )
        embed.set_footer(text=f"Posted on {update_info['date']}")
        
        await channel.send(embed=embed)

    @commands.command(name="steamos_latest")
    @commands.has_permissions(administrator=True)
    async def steamos_latest(self, ctx):
        """Display the most recent SteamOS update"""
        await ctx.send("Fetching latest SteamOS update...")
        
        update_info = await self.fetch_latest_update(force_refresh=True)
        if update_info:
            await self.post_update(ctx.channel, update_info)
            
            # Check if already posted to dedicated channel
            channel = discord.utils.get(ctx.guild.text_channels, name=self.update_channel_name)
            if channel and channel.id != ctx.channel.id:
                guild_id = str(ctx.guild.id)
                status = ("already posted" if guild_id in self.server_updates and 
                         self.server_updates[guild_id]["last_update"] == update_info['title']
                         else "not yet posted")
                await ctx.send(f"ℹ️ Update {status} to #{self.update_channel_name}")
        else:
            await ctx.send("❌ No SteamOS updates found")

async def setup(bot):
    await bot.add_cog(SteamOSUpdatesCog(bot))