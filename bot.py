import discord
import ctypes
import ctypes.util
import asyncio
import os
import aiofiles
from discord.ext import commands
from gtts import gTTS
from groq import Groq
import json
import time
import signal
import sys
from functools import partial

# --- Configuration ---
class Config:
    CHANNEL_ID = 1132395937180950599
    AUTHORIZED_USER_ID = 103873926622363648
    EMBED_COLOR = 0x0099ff
    MAX_DELETE_MESSAGES = 5
    SAVE_COOLDOWN = 5
    CLEANUP_INTERVAL = 1800
    MAX_MESSAGES = 50
    MAX_PROCESSED_MESSAGES = 500
    MAX_CONNECTIONS = 2
    MAX_WORKERS = 2
    COOLDOWN_RATE = 1
    COOLDOWN_PER = 120

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True
bot = commands.Bot(command_prefix='!', intents=intents, chunk_guilds_at_startup=False, case_insensitive=True, max_messages=Config.MAX_MESSAGES)

# Connection pool
class ConnectionPool:
    __slots__ = ('connections', '_index', '_mask')

    def __init__(self, max_connections=Config.MAX_CONNECTIONS):
        if not (api_key := os.environ.get("GROQ_API_KEY")):
            raise ValueError("GROQ_API_KEY environment variable not set.")
        self.connections = tuple(Groq(api_key=api_key) for _ in range(max_connections))
        self._index = 0
        self._mask = max_connections - 1

    def get_connection(self):
        conn = self.connections[self._index]
        self._index = (self._index + 1) & self._mask
        return conn

    async def close(self):
        for conn in self.connections:
            close_attr = getattr(conn, 'close', None)
            if close_attr is None:
                continue
            result = close_attr()
            if asyncio.iscoroutine(result):
                await result

# Bot state
class BotState:
    __slots__ = ('jackychat_channels', 'processed_messages', 'last_save_time', 'last_cleanup_time', 'broadcast_semaphore')

    def __init__(self):
        self.jackychat_channels = {}
        self.processed_messages = set()
        self.last_save_time = 0
        self.last_cleanup_time = time.time()
        self.broadcast_semaphore = asyncio.Semaphore(5)

bot.pool = ConnectionPool()
bot.state = BotState()

# Cleanup task
async def cleanup_task():
    while True:
        await asyncio.sleep(Config.CLEANUP_INTERVAL)
        bot.state.processed_messages.clear()
        bot.state.last_cleanup_time = time.time()

# Setup hook
async def setup_hook():
    cog_files = [f[:-3] for f in os.listdir('./cogs') if f.endswith('.py')]
    # Exclude AI image generation and model management cogs, and cogs with missing assets
    disabled_cogs = ['image_gen', 'model_manager', 'music', 'quote', 'server_manager']
    cog_files = [f for f in cog_files if f not in disabled_cogs]
    results = await asyncio.gather(*(bot.load_extension(f'cogs.{f}') for f in cog_files), return_exceptions=True)
    for filename, result in zip(cog_files, results):
        if isinstance(result, Exception):
            print(f'Failed to load {filename}: {result}')
    
    asyncio.create_task(cleanup_task())

bot.setup_hook = setup_hook

# Ready handler (fires once)
_ready_once = False

@bot.event
async def on_ready():
    global _ready_once
    if _ready_once:
        return
    _ready_once = True

    await load_jackychat_channels()
    print('Bot is ready')

    channel = bot.get_channel(Config.CHANNEL_ID)
    if channel:
        try:
            await channel.send('JackyBot Online...')
        except discord.Forbidden:
            print(f"Missing permissions to send message in channel {Config.CHANNEL_ID}")
        except Exception as e:
            print(f"Failed to send startup message: {e}")

    # Ensure Opus is loaded for voice support
    try:
        if not discord.opus.is_loaded():
            opus_path = ctypes.util.find_library('opus')
            if opus_path:
                discord.opus.load_opus(opus_path)
    except Exception as e:
        print(f"Warning: Opus library not loaded ({e}). Voice may fail. Install Opus or ensure it is on PATH.")

# Message handler
@bot.event
async def on_message(message):
    if message.author == bot.user or not message.guild:
        return

    message_id = f"{message.channel.id}-{message.id}"
    if message_id in bot.state.processed_messages:
        return
    bot.state.processed_messages.add(message_id)

    channel_name = message.channel.name
    if "jackybot-chat" in channel_name:
        guild_id = message.guild.id
        state_channels = bot.state.jackychat_channels
        current_channel = state_channels.get(guild_id)

        if current_channel is not message.channel:
            state_channels[guild_id] = message.channel
            asyncio.create_task(save_jackychat_channels())

        embed = discord.Embed(title=f"Broadcast from {message.guild.name}", description=f"{message.author.mention}: {message.content}", color=Config.EMBED_COLOR)
        if message.attachments:
            embed.set_image(url=message.attachments[0].url)

        semaphore = bot.state.broadcast_semaphore
        tasks = [
            send_with_rate_limit(ch, embed, semaphore)
            for gid, ch in state_channels.items()
            if gid != guild_id and ch
        ]
        if tasks:
            asyncio.create_task(asyncio.gather(*tasks, return_exceptions=True))

    await bot.process_commands(message)

# Note: discord.py has no on_close event; cleanup is handled in shutdown/main

# Rate-limited broadcast function
async def send_with_rate_limit(channel, embed, semaphore):
    """Send message with rate limiting and error handling."""
    async with semaphore:
        try:
            await channel.send(embed=embed)
            await asyncio.sleep(0.2)
        except discord.Forbidden:
            print(f"Missing permissions in channel {channel.id}")
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = getattr(e, 'retry_after', 5)
                print(f"Rate limited, waiting {retry_after}s")
                await asyncio.sleep(retry_after)
                try:
                    await channel.send(embed=embed)
                except Exception:
                    pass
            else:
                print(f"Failed to send to {channel.id}: {e}")
        except Exception as e:
            print(f"Unexpected error sending to {channel.id}: {e}")

# Ping command
@bot.command()
async def ping(ctx):
    start = time.perf_counter_ns()
    msg = await ctx.reply("Measuring latency...")
    end = time.perf_counter_ns()
    latency_ms = round(bot.latency * 1000)
    message_ms = round((end - start) / 1_000_000)
    await msg.edit(content=f'Pong! API: {latency_ms}ms | Message: {message_ms}ms')

@bot.command()
async def voice_diag(ctx):
    """Diagnose voice dependencies (Opus, PyNaCl)."""
    nacl_ok = False
    try:
        import nacl
        nacl_ok = True
    except Exception:
        pass

    opus_loaded = discord.opus.is_loaded()
    if not opus_loaded:
        try:
            opus_path = ctypes.util.find_library('opus')
            if opus_path:
                discord.opus.load_opus(opus_path)
                opus_loaded = discord.opus.is_loaded()
        except Exception:
            pass

    await ctx.reply(f"PyNaCl: {'OK' if nacl_ok else 'MISSING'} | Opus: {'LOADED' if opus_loaded else 'NOT LOADED'}")

# TTS command
@bot.command()
async def tts(ctx, *, message):
    voice_state = ctx.author.voice
    if not voice_state or not voice_state.channel:
        return await ctx.reply('You need to be in a voice channel.')

    voice_channel = voice_state.channel
    vc = ctx.voice_client
    if vc is None:
        vc = await voice_channel.connect()
    elif vc.channel != voice_channel:
        await vc.move_to(voice_channel)

    temp_file = f"temp_{ctx.message.id}.mp3"
    try:
        await asyncio.to_thread(gTTS(text=message, lang='en').save, temp_file)
        def _after(play_error):
            if play_error:
                print(f"Error in voice playback: {play_error}")
            try:
                asyncio.create_task(delete_file(temp_file))
            except RuntimeError:
                pass
        vc.play(discord.FFmpegPCMAudio(temp_file), after=_after)
    except Exception as e:
        await ctx.reply("Failed to generate TTS audio.")
        print(f"TTS Error: {e}")
        await delete_file(temp_file)

# File deletion utility
async def delete_file(filename):
    try:
        await asyncio.to_thread(os.remove, filename)
    except OSError:
        pass

# Leave command
@bot.command()
async def leave(ctx):
    if vc := ctx.voice_client:
        await vc.disconnect()
        await ctx.reply("Disconnected from voice channel.")

# Delete command
@bot.command()
@commands.cooldown(Config.COOLDOWN_RATE, Config.COOLDOWN_PER, commands.BucketType.user)
async def delete(ctx, number_of_messages: int):
    if ctx.author.id != Config.AUTHORIZED_USER_ID:
        return await ctx.reply("You are not authorized to use this command.")
    if not 1 <= number_of_messages <= Config.MAX_DELETE_MESSAGES:
        return await ctx.reply(f"Please provide a number between 1 and {Config.MAX_DELETE_MESSAGES}.")
    
    try:
        deleted = await ctx.channel.purge(limit=number_of_messages + 1)
        await ctx.send(f"Deleted {len(deleted)-1} messages.", delete_after=5)
    except discord.Forbidden:
        await ctx.send("I don't have permission to delete messages here.")
    except discord.HTTPException as e:
        await ctx.send(f"Failed to delete messages: {e}")

# Save jackychat channels
async def save_jackychat_channels():
    current_time = time.time()
    if current_time - bot.state.last_save_time < Config.SAVE_COOLDOWN:
        return
    bot.state.last_save_time = current_time

    data = {str(gid): {'channel_id': ch.id} for gid, ch in bot.state.jackychat_channels.items()}
    try:
        async with aiofiles.open('data/jackychat_channels.json', 'w') as f:
            await f.write(json.dumps(data, separators=(',', ':')))
    except Exception as e:
        print(f"Error saving jackychat channels: {e}")

# Load jackychat channels
async def load_jackychat_channels():
    try:
        async with aiofiles.open('data/jackychat_channels.json', 'r') as f:
            content = await f.read()
            if not content.strip():
                return
            data = json.loads(content)
            channels = bot.state.jackychat_channels
            for guild_id_str, info in data.items():
                if channel_id := info.get('channel_id'):
                    if channel := bot.get_channel(channel_id):
                        channels[int(guild_id_str)] = channel
    except FileNotFoundError:
        pass
    except (json.JSONDecodeError, ValueError, Exception) as e:
        print(f"Could not load data/jackychat_channels.json ({e}). Starting fresh.")

# Graceful shutdown
async def shutdown(signal, loop):
    print(f"Received exit signal {signal.name}...")
    current_task = asyncio.current_task()
    tasks = [t for t in asyncio.all_tasks(loop) if t is not current_task]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    pool = getattr(bot, 'pool', None)
    if pool:
        await pool.close()
    await bot.close()
    loop.stop()

# Main entry point
async def main():
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        print("Error: DISCORD_BOT_TOKEN environment variable not set.")
        return

    loop = asyncio.get_running_loop()
    if sys.platform != "win32":
        signals = (signal.SIGINT, signal.SIGTERM)
        for sig in signals:
            loop.add_signal_handler(sig, partial(asyncio.create_task, shutdown(sig, loop)))

    try:
        await bot.start(token)
    except discord.LoginFailure:
        print("Error: Invalid Discord token.")
    except Exception as e:
        print(f"Error starting bot: {e}")
    finally:
        pool = getattr(bot, 'pool', None)
        if pool:
            await pool.close()
        if not bot.is_closed():
            await bot.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot shutdown requested.")