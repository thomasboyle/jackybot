import asyncio
import json
import os
from datetime import datetime
from typing import Any, Dict, Optional

import aiohttp
import discord
from discord.ext import commands, tasks


class ZenUpdatesCog(commands.Cog):
    """Posts Zen Browser release updates to a specific Discord channel.

    Data source: GitHub Releases API for zen-browser/desktop (stable releases).
    Uses ETag caching and a local JSON state to avoid duplicate posts.
    """

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.target_channel_id: int = 1403334028979077160
        self.releases_url: str = "https://api.github.com/repos/zen-browser/desktop/releases"
        self.json_dir: str = "json"
        self.state_file: str = os.path.join(self.json_dir, "zen_updates.json")

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
            "User-Agent": "JackyBot-ZenUpdates/1.0",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
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
        return {"last_release_id": None, "etag": None}

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
    async def _fetch_latest_release(self, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
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
            async with self._session.get(self.releases_url, headers=headers) as resp:
                # 304 Not Modified → keep existing cache
                if resp.status == 304:
                    self._last_check_epoch = now_epoch
                    return self._latest_cache

                if resp.status != 200:
                    return self._latest_cache

                # Update ETag if provided
                if (new_etag := resp.headers.get("ETag")):
                    self._state["etag"] = new_etag

                releases = await resp.json()
                if not isinstance(releases, list) or not releases:
                    return self._latest_cache

                # Prefer the most recent stable (non-draft, non-prerelease)
                stable = [r for r in releases if not r.get("draft") and not r.get("prerelease")]
                latest = (stable[0] if stable else releases[0])

                release_info = {
                    "id": latest.get("id"),
                    "tag": latest.get("tag_name") or "",
                    "title": latest.get("name") or latest.get("tag_name") or "Zen Browser Release",
                    "body": latest.get("body") or "",
                    "url": latest.get("html_url") or "https://github.com/zen-browser/desktop/releases",
                    "published_at": latest.get("published_at") or "",
                }

                self._latest_cache = release_info
                self._last_check_epoch = now_epoch
                return release_info
        except Exception:
            return self._latest_cache

    # ---- Posting ----
    async def _post_release(self, channel: discord.abc.MessageableChannel, release: Dict[str, Any]) -> None:
        body = release.get("body", "").strip()
        if body and len(body) > 1900:
            body = body[:1900] + "..."

        title = release.get("title") or release.get("tag") or "Zen Browser Release"
        url = release.get("url")

        embed = discord.Embed(
            title=f"🧘 Zen Browser Update: {title}",
            description=body or "A new Zen Browser release is available.",
            color=0x00A37A,
            url=url,
            timestamp=datetime.now(),
        )
        if release.get("published_at"):
            embed.set_footer(text=f"Published at {release['published_at']}")

        await channel.send(embed=embed)

    # ---- Task ----
    @tasks.loop(seconds=3600)
    async def check_for_updates(self) -> None:
        try:
            release = await self._fetch_latest_release()
            if not release:
                return

            last_id = self._state.get("last_release_id")
            current_id = release.get("id")

            if last_id == current_id:
                return

            # Resolve channel lazily
            channel = self.bot.get_channel(self.target_channel_id)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(self.target_channel_id)
                except Exception:
                    return

            await self._post_release(channel, release)

            self._state["last_release_id"] = current_id
            await self._save_state()
        finally:
            # Jitter to avoid synchronized polling across shards/instances
            await asyncio.sleep( async_jitter_seconds(300) )

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
    await bot.add_cog(ZenUpdatesCog(bot))


