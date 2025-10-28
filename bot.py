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
from concurrent.futures import ThreadPoolExecutor
import time
from collections import deque
import signal
import sys

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
    def __init__(self, max_connections=Config.MAX_CONNECTIONS):
        if not (api_key := os.environ.get("GROQ_API_KEY")):
            raise ValueError("GROQ_API_KEY environment variable not set.")
        self.connections = [Groq(api_key=api_key) for _ in range(max_connections)]
        self._index = 0

    def get_connection(self):
        conn = self.connections[self._index]
        self._index = (self._index + 1) % len(self.connections)
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
    def __init__(self):
        self.jackychat_channels = {}
        self.processed_messages = deque(maxlen=Config.MAX_PROCESSED_MESSAGES)
        self.last_save_time = 0

bot.pool = ConnectionPool()
bot.executor = ThreadPoolExecutor(max_workers=Config.MAX_WORKERS)
bot.state = BotState()

# Cleanup task
async def cleanup_task():
    while True:
        await asyncio.sleep(Config.CLEANUP_INTERVAL)
        bot.state.processed_messages.clear()

# Setup hook
async def setup_hook():
    cog_files = [f[:-3] for f in os.listdir('./cogs') if f.endswith('.py')]
    # Exclude AI image generation and model management cogs
    disabled_cogs = ['image_gen', 'model_manager', 'music']
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
    bot.state.processed_messages.append(message_id)
    
    if "jackybot-chat" in message.channel.name:
        guild_id = message.guild.id
        if bot.state.jackychat_channels.get(guild_id) != message.channel:
            bot.state.jackychat_channels[guild_id] = message.channel
            asyncio.create_task(save_jackychat_channels())
        
        embed = discord.Embed(title=f"Broadcast from {message.guild.name}", description=f"{message.author.mention}: {message.content}", color=Config.EMBED_COLOR)
        if message.attachments:
            embed.set_image(url=message.attachments[0].url)
        
        tasks = [
            ch.send(embed=embed) for gid, ch in bot.state.jackychat_channels.items()
            if gid != guild_id and ch
        ]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    await bot.process_commands(message)

# Note: discord.py has no on_close event; cleanup is handled in shutdown/main

# Ping command
@bot.command()
async def ping(ctx):
    start = time.perf_counter()
    msg = await ctx.reply("Measuring latency...")
    end = time.perf_counter()
    await msg.edit(content=f'Pong! API: {round(bot.latency * 1000)}ms | Message: {round((end - start) * 1000)}ms')

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
    if not (voice_channel := ctx.author.voice and ctx.author.voice.channel):
        return await ctx.reply('You need to be in a voice channel.')
    
    vc = ctx.voice_client or await voice_channel.connect()
    if vc.channel != voice_channel:
        await vc.move_to(voice_channel)

    temp_file = f"temp_{ctx.message.id}.mp3"
    try:
        await bot.loop.run_in_executor(bot.executor, lambda: gTTS(text=message, lang='en').save(temp_file))
        def _after(play_error):
            if play_error:
                print(f"Error in voice playback: {play_error}")
            asyncio.run_coroutine_threadsafe(delete_file(temp_file), bot.loop)
        vc.play(discord.FFmpegPCMAudio(temp_file), after=_after)
    except Exception as e:
        await ctx.reply("Failed to generate TTS audio.")
        print(f"TTS Error: {e}")
        await delete_file(temp_file)

# File deletion utility
async def delete_file(filename):
    try:
        await bot.loop.run_in_executor(bot.executor, os.remove, filename)
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"Error deleting temporary file {filename}: {e}")

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
    if time.time() - bot.state.last_save_time < Config.SAVE_COOLDOWN:
        return
    bot.state.last_save_time = time.time()
    
    data = {str(gid): {'channel_id': ch.id} for gid, ch in bot.state.jackychat_channels.items()}
    try:
        async with aiofiles.open('data/jackychat_channels.json', 'w') as f:
            await f.write(json.dumps(data))
    except Exception as e:
        print(f"Error saving jackychat channels: {e}")

# Load jackychat channels
async def load_jackychat_channels():
    try:
        async with aiofiles.open('data/jackychat_channels.json', 'r') as f:
            content = await f.read()
            if not content.strip(): return
            data = json.loads(content)
            for guild_id, info in data.items():
                if channel_id := info.get('channel_id'):
                    if channel := bot.get_channel(channel_id):
                        bot.state.jackychat_channels[int(guild_id)] = channel
    except FileNotFoundError:
        pass
    except (json.JSONDecodeError, Exception) as e:
        print(f"Could not load data/jackychat_channels.json ({e}). Starting fresh.")

# Graceful shutdown
async def shutdown(signal, loop):
    print(f"Received exit signal {signal.name}...")
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    [task.cancel() for task in tasks]
    await asyncio.gather(*tasks, return_exceptions=True)
    try:
        if bot.pool:
            await bot.pool.close()
    finally:
        if bot.executor:
            bot.executor.shutdown(wait=False)
    await bot.close()
    loop.stop()

# Main entry point
async def main():
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        print("Error: DISCORD_BOT_TOKEN environment variable not set.")
        return

    loop = asyncio.get_event_loop()
    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s, loop)))

    try:
        await bot.start(token)
    except discord.LoginFailure:
        print("Error: Invalid Discord token.")
    except Exception as e:
        print(f"Error starting bot: {e}")
    finally:
        try:
            if bot.pool:
                await bot.pool.close()
        finally:
            if bot.executor:
                bot.executor.shutdown(wait=False)
        if not bot.is_closed():
            await bot.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot shutdown requested.")