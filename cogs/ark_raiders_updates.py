import asyncio
import json
import os
from datetime import datetime
from typing import Any, Dict, Optional

import aiohttp
import discord
from discord.ext import commands, tasks


class ArkRaidersUpdatesCog(commands.Cog):
    """Posts ARC Raiders patch notes to ark-raiders-updates channels.

    Data source: Steam News API for ARC Raiders (App ID: 1808500).
    Uses ETag caching and a local JSON state to avoid duplicate posts.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.app_id: int = 1808500  # ARC Raiders Steam App ID
        self.update_channel_name: str = "ark-raiders-updates"
        self.news_url: str = f"https://api.steampowered.com/ISteamNews/GetNewsForApp/v0002/?appid={self.app_id}&count=3&maxlength=300&format=json"
        self.json_dir: str = "json"
        self.state_file: str = os.path.join(self.json_dir, "ark_raiders_updates.json")

        # In-memory state
        self._state: Dict[str, Any] = self._load_state()
        self._latest_cache: Optional[Dict[str, Any]] = None
        self._last_check_epoch: int = 0
        self._cache_ttl_seconds: int = 1800  # 30 minutes

        # HTTP session
        self._session: Optional[aiohttp.ClientSession] = None

    async def cog_load(self) -> None:
        timeout = aiohttp.ClientTimeout(total=20)
        headers = {
            "User-Agent": "JackyBot-ArkRaidersUpdates/1.0",
        }
        self._session = aiohttp.ClientSession(timeout=timeout, headers=headers)
        self.check_for_updates.start()

    async def cog_unload(self) -> None:
        self.check_for_updates.cancel()
        if self._session and not self._session.closed:
            await self._session.close()

    # ---- Persistence ----
    def _load_state(self) -> Dict[str, Any]:
        os.makedirs(self.json_dir, exist_ok=True)
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except FileNotFoundError:
            pass
        except json.JSONDecodeError:
            pass
        return {"last_news_gid": None, "etag": None}

    async def _save_state(self) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._save_state_sync)

    def _save_state_sync(self) -> None:
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self._state, f, indent=2)
        except Exception:
            # Avoid raising inside background task
            pass

    # ---- Fetching ----
    async def _fetch_latest_news(self, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        now_epoch = int(datetime.now().timestamp())

        # Serve from cache if recent
        if (
            not force_refresh
            and self._latest_cache is not None
            and (now_epoch - self._last_check_epoch) < self._cache_ttl_seconds
        ):
            return self._latest_cache

        if not self._session:
            return self._latest_cache

        headers: Dict[str, str] = {}
        if (etag := self._state.get("etag")) and not force_refresh:
            headers["If-None-Match"] = etag

        try:
            async with self._session.get(self.news_url, headers=headers) as resp:
                # 304 Not Modified → keep existing cache
                if resp.status == 304:
                    self._last_check_epoch = now_epoch
                    return self._latest_cache

                if resp.status != 200:
                    return self._latest_cache

                # Update ETag if provided
                if (new_etag := resp.headers.get("ETag")):
                    self._state["etag"] = new_etag

                data = await resp.json()
                if not isinstance(data, dict) or "appnews" not in data:
                    return self._latest_cache

                appnews = data["appnews"]
                if not isinstance(appnews, dict) or "newsitems" not in appnews:
                    return self._latest_cache

                newsitems = appnews["newsitems"]
                if not isinstance(newsitems, list) or not newsitems:
                    return self._latest_cache

                # Get the most recent news item
                latest = newsitems[0]

                news_info = {
                    "gid": latest.get("gid"),
                    "title": latest.get("title") or "ARC Raiders Update",
                    "contents": latest.get("contents") or "",
                    "url": latest.get("url") or f"https://store.steampowered.com/news/app/{self.app_id}",
                    "date": latest.get("date") or 0,
                }

                self._latest_cache = news_info
                self._last_check_epoch = now_epoch
                return news_info
        except Exception:
            return self._latest_cache

    # ---- Posting ----
    async def _post_news(self, channel: discord.abc.Messageable, news: Dict[str, Any]) -> None:
        contents = news.get("contents", "").strip()
        if contents and len(contents) > 1900:
            contents = contents[:1900] + "..."

        title = news.get("title") or "ARC Raiders Update"

        embed = discord.Embed(
            title=f"🏹 ARC Raiders Update: {title}",
            description=contents or "A new ARC Raiders update is available.",
            color=0xFF6B35,  # Orange/red color for ARC Raiders
            url=news.get("url"),
            timestamp=datetime.now(),
        )

        # Convert Unix timestamp to readable date
        if news.get("date"):
            date_obj = datetime.fromtimestamp(news["date"])
            embed.set_footer(text=f"Published on {date_obj.strftime('%B %d, %Y')}")

        await channel.send(embed=embed)

    # ---- Task ----
    @tasks.loop(seconds=3600)
    async def check_for_updates(self) -> None:
        try:
            news = await self._fetch_latest_news()
            if not news:
                return

            last_gid = self._state.get("last_news_gid")
            current_gid = news.get("gid")

            if last_gid == current_gid:
                return

            # Find all ark-raiders-updates channels across guilds
            channels = []
            for guild in self.bot.guilds:
                channel = discord.utils.get(guild.text_channels, name=self.update_channel_name)
                if channel:
                    channels.append(channel)

            if not channels:
                return

            for channel in channels:
                try:
                    await self._post_news(channel, news)
                except Exception:
                    continue

            self._state["last_news_gid"] = current_gid
            await self._save_state()
        finally:
            # Jitter to avoid synchronized polling across shards/instances
            await asyncio.sleep(async_jitter_seconds(300))

    @check_for_updates.before_loop
    async def before_check_for_updates(self) -> None:
        await self.bot.wait_until_ready()


def async_jitter_seconds(max_abs_seconds: int) -> int:
    """Return a small positive jitter up to max_abs_seconds.

    Using a simple deterministic variant based on current epoch to avoid importing random.
    """
    epoch = int(datetime.now().timestamp())
    if max_abs_seconds <= 0:
        return 0
    return (epoch % max_abs_seconds)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ArkRaidersUpdatesCog(bot))
