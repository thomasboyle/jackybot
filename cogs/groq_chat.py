import discord
from discord.ext import commands
import groq
import os
from typing import Optional, Dict, List, Tuple
import re
import asyncio
from datetime import datetime, timedelta
import json
import time
from collections import deque
from functools import lru_cache
import threading
import aiofiles

class SimpleCache:
    """Simple thread-safe cache with TTL."""
    def __init__(self):
        self._cache = {}
        self._lock = threading.Lock()

    def get(self, key: str, default=None):
        with self._lock:
            if key in self._cache:
                value, expiry = self._cache[key]
                if time.time() < expiry:
                    return value
                else:
                    del self._cache[key]
            return default

    def set(self, key: str, value, ttl_seconds: int = 300):  # Default 5 minutes TTL
        with self._lock:
            self._cache[key] = (value, time.time() + ttl_seconds)

class GroqChat(commands.Cog):
    __slots__ = ('bot', 'groq_client', 'groq_api_key', 'model', 'cleanup_task', 'rate_limit_cleanup_task', 
                 'queue_processors', '_bot_id', '_bot_mentions', '_think_pattern', 'system_prompt',
                 'user_rate_limits', 'guild_rate_limits', 'request_queue', 'global_request_times', 'last_request_time',
                 'consecutive_rate_limits', 'adaptive_delay', 'last_successful_request', 'context_manager', '_cache',
                 'active_requests', 'max_concurrent_requests', 'min_request_interval')

    def __init__(self, bot):
        self.bot = bot
        self.groq_api_key = os.environ.get("GROQ_API_KEY")
        if not self.groq_api_key:
            print("WARNING: GROQ_API_KEY not set. Groq integration will not work.")
            self.groq_client = None
        else:
            self.groq_client = groq.Client(
                api_key=self.groq_api_key,
                max_retries=0
            )
        self.model = "openai/gpt-oss-120b"

        self.system_prompt = None

        self._bot_id = "1128674354696310824"
        self._bot_mentions = (f"<@{self._bot_id}>", f"<@!{self._bot_id}>")
        self._think_pattern = re.compile(r'<think>.*?</think>', re.DOTALL)

        self.user_rate_limits: Dict[int, Tuple[deque, float]] = {}
        self.guild_rate_limits: Dict[int, Tuple[deque, float]] = {}

        self.global_request_times: deque = deque(maxlen=100)
        self.last_request_time = 0
        self.last_successful_request = 0

        self.consecutive_rate_limits = 0
        self.adaptive_delay = 5.0

        self.request_queue: asyncio.Queue = asyncio.Queue()
        self.active_requests = 0
        self.max_concurrent_requests = 3
        self.min_request_interval = 0.5

        self.context_manager = None
        self._cache = SimpleCache()

        self.cleanup_task = asyncio.create_task(self._start_queue_processors())
        self.rate_limit_cleanup_task = asyncio.create_task(self._cleanup_rate_limits())
        self.queue_processors = []

    async def _load_system_prompt(self) -> str:
        """Load system prompt from file with fallback."""
        try:
            async with aiofiles.open("jackybot_system_prompt.md", "r", encoding="utf-8") as f:
                content = await f.read()
                return content.strip()
        except FileNotFoundError:
            print("WARNING: jackybot_system_prompt.md not found. Using default system prompt.")
        except Exception as e:
            print(f"WARNING: Error reading system prompt file: {e}. Using default system prompt.")

        return "You are JackyBot, a Discord bot assistant created by FakeJason. You help users with various queries ranging from server management to gaming news and creative support. Keep your total response under 2000 characters."

    def cog_unload(self):
        """Clean up the background tasks when the cog is unloaded."""
        self.cleanup_task.cancel()
        self.rate_limit_cleanup_task.cancel()
        for processor in self.queue_processors:
            processor.cancel()

    async def cog_load(self):
        """Initialize async resources after cog is loaded."""
        self.system_prompt = await self._load_system_prompt()
        await asyncio.sleep(0.1)
        self.context_manager = self.bot.get_cog("ContextManager")
    
    def _check_rate_limit(self, rate_limits_dict: Dict[int, Tuple[deque, float]], entity_id: int, max_requests: int = 3, window_seconds: int = 60) -> Tuple[bool, int]:
        """
        Generic rate limit checker for users or guilds with automatic cleanup.
        Returns (is_allowed, seconds_until_reset)
        """
        now = time.time()

        if entity_id not in rate_limits_dict:
            rate_limits_dict[entity_id] = (deque(), now)

        requests, _ = rate_limits_dict[entity_id]
        rate_limits_dict[entity_id] = (requests, now)

        while requests and requests[0] < now - window_seconds:
            requests.popleft()

        if len(requests) < max_requests:
            requests.append(now)
            return True, 0

        seconds_until_reset = int(window_seconds - (now - requests[0])) + 1
        return False, seconds_until_reset

    def check_user_rate_limit(self, user_id: int, max_requests: int = 3, window_seconds: int = 60) -> Tuple[bool, int]:
        """Check if a user has exceeded their rate limit."""
        return self._check_rate_limit(self.user_rate_limits, user_id, max_requests, window_seconds)

    def check_guild_rate_limit(self, guild_id: int, max_requests: int = 10, window_seconds: int = 60) -> Tuple[bool, int]:
        """Check if a guild has exceeded its rate limit."""
        return self._check_rate_limit(self.guild_rate_limits, guild_id, max_requests, window_seconds)
    
    async def _cleanup_rate_limits(self):
        """Periodically clean up old rate limit entries to prevent memory leaks."""
        while True:
            try:
                await asyncio.sleep(300)
                now = time.time()
                cleanup_threshold = 3600

                expired_users = [
                    user_id for user_id, (requests, last_access) in self.user_rate_limits.items()
                    if now - last_access > cleanup_threshold
                ]
                for user_id in expired_users:
                    del self.user_rate_limits[user_id]

                expired_guilds = [
                    guild_id for guild_id, (requests, last_access) in self.guild_rate_limits.items()
                    if now - last_access > cleanup_threshold
                ]
                for guild_id in expired_guilds:
                    del self.guild_rate_limits[guild_id]

                if expired_users or expired_guilds:
                    print(f"Rate limit cleanup: Removed {len(expired_users)} users, {len(expired_guilds)} guilds")

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in rate limit cleanup: {e}")
    
    async def _start_queue_processors(self):
        """Start multiple concurrent queue processors."""
        self.queue_processors = [
            asyncio.create_task(self.process_request_queue(worker_id=i))
            for i in range(self.max_concurrent_requests)
        ]
        await asyncio.gather(*self.queue_processors, return_exceptions=True)
    
    async def process_request_queue(self, worker_id: int = 0):
        """Background task to process queued API requests with adaptive rate limiting."""
        while True:
            try:
                message, messages, future = await self.request_queue.get()

                now = time.time()
                time_since_last = now - self.last_request_time

                delay = self.min_request_interval if self.consecutive_rate_limits == 0 else 2.0

                if time_since_last < delay:
                    await asyncio.sleep(delay - time_since_last)

                try:
                    self.active_requests += 1
                    response = await self._groq_request_with_retry(messages)
                    self.last_request_time = time.time()
                    self.consecutive_rate_limits = 0
                    future.set_result(response)
                except Exception as e:
                    if "429" in str(e) or "Rate limit" in str(e):
                        self.consecutive_rate_limits += 1
                    future.set_exception(e)
                finally:
                    self.active_requests -= 1

                self.request_queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in queue processor {worker_id}: {e}")
                await asyncio.sleep(1)
    
    async def _groq_request_with_retry(self, messages: List[Dict], max_retries: int = 3) -> str:
        """Make a Groq API request with exponential backoff retry logic."""
        loop = asyncio.get_event_loop()

        for attempt in range(max_retries):
            try:
                # Run the synchronous groq API call in a thread executor
                completion = await loop.run_in_executor(
                    None,
                    lambda: self.groq_client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        max_tokens=512
                    )
                )
                return completion.choices[0].message.content
            except Exception as e:
                error_str = str(e)

                # Handle rate limit errors
                if "429" in error_str or "Too Many Requests" in error_str:
                    if attempt < max_retries - 1:
                        wait_time = 60  # Wait 60 seconds for rate limit reset
                        print(f"Rate limited by Groq API. Waiting {wait_time}s (attempt {attempt + 1}/{max_retries})")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        raise Exception("⚠️ API rate limit exceeded. Please wait a minute before trying again.")

                # Handle other errors with exponential backoff
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"API error: {error_str}. Retrying in {wait_time}s")
                    await asyncio.sleep(wait_time)
                else:
                    raise

        raise Exception("Max retries exceeded")
    
    async def get_conversation_messages(self, guild_id: int, current_prompt: str, message: discord.Message = None) -> List[Dict]:
        """Get conversation messages with context information."""
        if not self.context_manager:
            self.context_manager = self.bot.get_cog("ContextManager")

        # Get base conversation from context manager
        messages = await self.context_manager.get_conversation_messages(guild_id, current_prompt, message)

        # Add relevant context information to the system prompt if this is the first message
        if messages and messages[0]["role"] == "system":
            context_info = await self.get_all_available_information(message)
            if context_info:
                messages[0]["content"] += f"\n\nContext:\n{context_info}"

        return messages

    def _is_mentioned(self, content: str) -> bool:
        """Check if bot is mentioned in the message."""
        return any(mention in content for mention in self._bot_mentions)

    def _strip_mentions(self, content: str) -> str:
        """Remove bot mentions from message content."""
        for mention in self._bot_mentions:
            content = content.replace(mention, "", 1)
        return content.strip()

    def _is_image_request(self, prompt: str) -> Tuple[bool, str]:
        """Check if message is an image generation request and extract prompt."""
        prompt_lower = prompt.lower()
        image_keywords = ['create image', 'generate image', 'imagine', 'make image', 'draw', 'generate a', 'create a']

        for keyword in image_keywords:
            if keyword in prompt_lower:
                image_prompt = re.sub(r'(?i)' + re.escape(keyword), '', prompt).strip()
                image_prompt = re.sub(r'^[\s,:;]+|[\s,:;]+$', '', image_prompt)
                return True, image_prompt
        return False, prompt

    def _detect_command_intent(self, prompt: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Detect if the user wants to execute a bot command.
        Returns (command_name, arguments) or (None, None)
        """
        prompt_lower = prompt.lower()
        
        # Help/command list requests
        if any(phrase in prompt_lower for phrase in ['show help', 'list commands', 'what commands', 'available commands', 'show commands', 'help menu']):
            return ('help', '')
        
        # Ping request
        if any(phrase in prompt_lower for phrase in ['check ping', 'bot ping', 'latency', 'response time', 'test connection']):
            return ('ping', '')
        
        # Stats request
        if any(phrase in prompt_lower for phrase in ['show stats', 'bot stats', 'statistics', 'usage stats']):
            return ('stats', '')
        
        # Bot info request
        if any(phrase in prompt_lower for phrase in ['bot info', 'botinfo', 'about bot', 'bot details']):
            return ('botinfo', '')
        
        # Free games request
        if any(phrase in prompt_lower for phrase in ['free games', 'epic games', 'show free games', 'what games are free', 'any free games']):
            return ('freegames', '')
        
        # Gaming news requests
        if 'steam deck' in prompt_lower and any(word in prompt_lower for word in ['news', 'update', 'latest']):
            return ('steamdeck', '')
        
        if 'steamos' in prompt_lower and any(word in prompt_lower for word in ['news', 'update', 'latest']):
            return ('steamos', '')
        
        if 'peak' in prompt_lower and any(word in prompt_lower for word in ['news', 'update', 'latest']):
            return ('peak', '')
        
        # Server info
        if any(phrase in prompt_lower for phrase in ['server info', 'server details', 'about server', 'guild info']):
            return ('serverinfo', '')
        
        # User info
        if any(phrase in prompt_lower for phrase in ['my info', 'user info', 'about me', 'my profile', 'my avatar']):
            return ('userinfo', '')
        
        # Avatar request
        if any(phrase in prompt_lower for phrase in ['show avatar', 'my avatar', 'get avatar', 'display avatar']):
            return ('avatar', '')
        
        # Roles management
        if any(phrase in prompt_lower for phrase in ['show roles', 'list roles', 'manage roles', 'server roles']):
            return ('roles', '')
        
        # Playlist commands
        if 'playlist' in prompt_lower or 'playlists' in prompt_lower:
            if any(word in prompt_lower for word in ['list', 'show', 'view all', 'my playlists']):
                return ('playlist', 'list')
            elif 'help' in prompt_lower:
                return ('playlist', '')
        
        # Music queue
        if any(phrase in prompt_lower for phrase in ['music queue', 'show queue', 'what\'s playing', 'song queue']):
            return ('queue', '')
        
        # Movie recommendations
        if any(phrase in prompt_lower for phrase in ['recommend movie', 'suggest movie', 'movie recommendation', 'good movies']):
            return ('movies', '')
        
        return (None, None)

    def _check_rate_limits(self, message: discord.Message) -> Tuple[bool, str]:
        """Check user and guild rate limits. Returns (allowed, error_message)."""
        # Check user rate limit (6 requests per minute)
        user_allowed, user_wait = self.check_user_rate_limit(message.author.id, max_requests=6, window_seconds=60)
        if not user_allowed:
            return False, f"⏱️ You're sending requests too quickly! Please wait {user_wait} seconds."

        # Check guild rate limit (5 requests per minute)
        guild_allowed, guild_wait = self.check_guild_rate_limit(message.guild.id, max_requests=5, window_seconds=60)
        if not guild_allowed:
            return False, f"⏱️ This server is sending requests too quickly! Please wait {guild_wait} seconds."

        return True, ""

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text (~4 chars per token)."""
        return int(len(text) / 4) + 10 if text else 0
        
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Handle incoming messages and process Groq AI requests."""
        # Ignore bot messages and DMs
        if message.author.bot or not message.guild:
            return

        # Ensure context manager is available
        if not self.context_manager:
            self.context_manager = self.bot.get_cog("ContextManager")

        content = message.content
        guild_id = message.guild.id

        # Check if bot is mentioned
        if not self._is_mentioned(content):
            # Add non-mention messages to context (if short enough)
            if len(content) <= 500:
                self.context_manager.add_message_to_context(guild_id, "user", f"{message.author.display_name}: {content}")
            return

        # Process the message and extract prompt
        prompt = await self._process_message_content(message, content)
        if not prompt:
            return  # Error message already sent

        # Check for image generation request
        is_image, image_prompt = self._is_image_request(prompt)
        if is_image:
            await self._handle_image_request(message, image_prompt)
            return

        # Check for direct command intent
        command_name, command_args = self._detect_command_intent(prompt)
        if command_name:
            await self._handle_command_request(message, command_name, command_args)
            return

        # Validate Groq client and rate limits
        if not self.groq_client:
            await message.reply("Sorry, the Groq API key is not configured.")
            return

        allowed, error_msg = self._check_rate_limits(message)
        if not allowed:
            await message.reply(error_msg)
            return

        # Process the AI request
        await self._process_ai_request(message, guild_id, prompt)

    async def _process_message_content(self, message: discord.Message, content: str) -> str:
        """Process message content and extract the prompt."""
        # Handle replies to other messages
        if message.reference and message.reference.message_id:
            try:
                original = await message.channel.fetch_message(message.reference.message_id)
                user_request = self._strip_mentions(content)
                if not user_request:
                    await message.reply("Please provide instructions along with the mention.")
                    return ""
                return f"Original message from {original.author.display_name}: \"{original.content}\"\n\nUser request: {user_request}"
            except (discord.NotFound, discord.HTTPException) as e:
                await message.reply(f"Sorry, I couldn't fetch the original message: {str(e)}")
                return ""

        # Handle regular mentions
        prompt = self._strip_mentions(content)
        if not prompt:
            await message.reply("Please provide a message along with the mention.")
            return ""

        return prompt

    async def _handle_image_request(self, message: discord.Message, image_prompt: str):
        """Handle image generation requests."""
        if not image_prompt:
            await message.reply("Try something like: `@JackyBot create image a beautiful sunset`")
            return

        try:
            create_command = self.bot.get_command('create')
            if create_command:
                ctx = await self.bot.get_context(message)
                await ctx.invoke(create_command, prompt=image_prompt)
                return
        except Exception as e:
            print(f"Failed to invoke create command: {e}")

        # Fall back to normal response if image generation fails
        await message.reply("Image generation failed. Please try again or use a different prompt.")

    async def _handle_command_request(self, message: discord.Message, command_name: str, args: str = ''):
        """Execute a bot command on behalf of the user."""
        try:
            command = self.bot.get_command(command_name)
            if not command:
                await message.reply(f"Command `{command_name}` not found.")
                return False

            ctx = await self.bot.get_context(message)
            
            # Invoke the command with arguments if provided
            if args:
                await ctx.invoke(command, *args.split())
            else:
                await ctx.invoke(command)
            
            return True
        except Exception as e:
            print(f"Failed to invoke {command_name} command: {e}")
            await message.reply(f"Sorry, I couldn't execute that command: {str(e)}")
            return False

    async def _process_ai_request(self, message: discord.Message, guild_id: int, prompt: str):
        """Process AI request through the queue system."""
        async with message.channel.typing():
            try:
                conversation_messages = await self.get_conversation_messages(guild_id, prompt, message)

                future = asyncio.Future()
                await self.request_queue.put((message, conversation_messages, future))

                queue_size = self.request_queue.qsize()
                if queue_size > 5:
                    await message.channel.send(f"⏳ Queue is busy ({queue_size} requests, ~{queue_size * 2}s wait).")

                response = await asyncio.wait_for(future, timeout=120.0)
                formatted_response = self.format_response(response)

                self.context_manager.add_message_to_context(guild_id, "user", prompt)
                self.context_manager.add_message_to_context(guild_id, "assistant", formatted_response)

                await message.reply(formatted_response)

            except asyncio.TimeoutError:
                await message.reply("⏱️ Request timed out. Please try again.")
            except Exception as e:
                error_msg = str(e)
                if "Rate limit" in error_msg or "429" in error_msg:
                    await message.reply("🚫 The AI service is rate limited. Please try again later.")
                else:
                    await message.reply(f"Sorry, I encountered an error: {error_msg}")
    
    def format_response(self, response: str) -> str:
        """Format the response with special handling for <think> tags and enforce length limit."""
        # Remove <think> sections using pre-compiled regex
        formatted = self._think_pattern.sub('', response).strip()

        # Ensure the response is under 2000 characters using slice assignment
        return formatted[:1997] + "..." if len(formatted) > 2000 else formatted

    # Consolidated information access methods

    def _get_server_info(self, guild: discord.Guild) -> str:
        """Get compact server information for context."""
        if not guild:
            return ""
        return f"SERVER: {guild.name}, {guild.member_count} members"

    async def _get_bot_stats(self) -> str:
        """Get compact bot statistics for context."""
        try:
            command_stats = await self.load_json_file("data/command_stats.json")
            total_servers = len(self.bot.guilds)
            total_users = sum(guild.member_count for guild in self.bot.guilds)
            return f"STATS: {total_servers} servers, {total_users} users, {sum(command_stats.values())} commands used"
        except:
            return ""

    async def _get_free_games(self) -> str:
        """Get current free games for context."""
        try:
            freegames_cog = self.bot.get_cog("EpicGamesCog")
            if not freegames_cog:
                return ""

            games_info = []
            for guild in self.bot.guilds[:3]:  # Limit to first 3 guilds to avoid overhead
                active_games = freegames_cog.active_games.get(str(guild.id), {})
                for game in list(active_games.values())[:2]:  # Max 2 games per guild
                    games_info.append(game['title'])

            if games_info:
                return f"FREE_GAMES: {', '.join(games_info[:3])}"  # Max 3 games total
        except:
            pass
        return ""

    def _get_timezone_info(self, user_id: str) -> str:
        """Get user's timezone information for context."""
        try:
            timezone_cog = self.bot.get_cog("TimezoneCog")
            if timezone_cog:
                user_timezones = timezone_cog.user_timezones.get(user_id, [])
                if user_timezones:
                    return f"TIME: {', '.join(user_timezones[:2])}"  # Max 2 timezones
        except:
            pass
        return ""

    def _get_gaming_news(self) -> str:
        """Get latest gaming news titles for context."""
        news_titles = []
        try:
            peak_cog = self.bot.get_cog("PeakUpdatesCog")
            if peak_cog and peak_cog.latest_update_cache:
                news_titles.append(f"PEAK: {peak_cog.latest_update_cache.get('title', '')[:30]}")
        except:
            pass

        try:
            steamos_cog = self.bot.get_cog("SteamOSUpdatesCog")
            if steamos_cog and steamos_cog.latest_update_cache:
                news_titles.append(f"SteamOS: {steamos_cog.latest_update_cache.get('title', '')[:30]}")
        except:
            pass

        return f"NEWS: {', '.join(news_titles)}" if news_titles else ""

    def _get_emotional_support(self) -> str:
        """Get emotional support resources for context."""
        return "SUPPORT: Text 'HOME' to 741741 or call 988"

    async def load_json_file(self, filename: str) -> Dict:
        """Helper method to load JSON files safely with caching."""
        cache_key = f"json_{filename}"
        cached_data = self._cache.get(cache_key)
        if cached_data is not None:
            return cached_data

        try:
            if os.path.exists(filename):
                async with aiofiles.open(filename, 'r') as f:
                    content = await f.read()
                    data = json.loads(content)
                    self._cache.set(cache_key, data, ttl_seconds=300)
                    return data
        except Exception as e:
            print(f"Error loading JSON file {filename}: {e}")
        return {}

    def get_all_bot_commands(self) -> Dict:
        """Get information about all available bot commands."""
        commands_info = {}

        try:
            for cog_name, cog in self.bot.cogs.items():
                cog_commands = {}

                # Get commands from this cog
                for command in cog.get_commands():
                    cmd_info = {
                        "name": command.name,
                        "qualified_name": command.qualified_name,
                        "description": command.help or command.description or "No description available",
                        "aliases": list(command.aliases) if command.aliases else [],
                        "usage": f"!{command.qualified_name}" + (f" {command.signature}" if command.signature else ""),
                        "cog": cog_name
                    }

                    # Add parameter information if available
                    if hasattr(command, 'params') and command.params:
                        params = []
                        for param_name, param in command.params.items():
                            if param_name not in ['self', 'ctx']:
                                param_info = {
                                    "name": param_name,
                                    "required": param.required,
                                    "default": str(param.default) if param.default != param.empty else None,
                                    "kind": str(param.kind) if hasattr(param, 'kind') else None
                                }
                                params.append(param_info)
                        cmd_info["parameters"] = params

                    cog_commands[command.name] = cmd_info

                if cog_commands:
                    commands_info[cog_name] = {
                        "description": cog.__doc__.strip() if cog.__doc__ else f"{cog_name} commands",
                        "commands": cog_commands
                    }

            return commands_info

        except Exception as e:
            return {"error": f"Could not load command information: {str(e)}"}

    async def get_all_available_information(self, message: discord.Message) -> str:
        """Compile relevant context information efficiently."""
        user_message = message.content.lower()
        info_parts = []

        if any(word in user_message for word in ["server", "guild", "member"]):
            if message.guild:
                info_parts.append(self._get_server_info(message.guild))

        if any(word in user_message for word in ["stats", "statistic", "uptime", "usage"]):
            stats_info = await self._get_bot_stats()
            if stats_info:
                info_parts.append(stats_info)

        if any(word in user_message for word in ["free", "game", "epic"]):
            games_info = await self._get_free_games()
            if games_info:
                info_parts.append(games_info)

        if any(word in user_message for word in ["time", "timezone", "clock", "when"]):
            tz_info = self._get_timezone_info(str(message.author.id))
            if tz_info:
                info_parts.append(tz_info)

        if any(word in user_message for word in ["news", "update", "patch", "steam", "peak"]):
            news_info = self._get_gaming_news()
            if news_info:
                info_parts.append(news_info)

        if any(word in user_message for word in ["sad", "depress", "suicide", "crisis", "mental", "anxiety"]):
            info_parts.append(self._get_emotional_support())

        return "\n".join(filter(None, info_parts)) or "You are JackyBot. Use !help for commands."

async def setup(bot):
    await bot.add_cog(GroqChat(bot)) 