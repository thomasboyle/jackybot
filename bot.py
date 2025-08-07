import discord
import asyncio
import os
import aiofiles
import random
from discord.ext import commands
from gtts import gTTS
from groq import Groq
import json
from functools import lru_cache
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
        await asyncio.gather(*(conn.close() for conn in self.connections if hasattr(conn, 'close')))

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
    results = await asyncio.gather(*(bot.load_extension(f'cogs.{f}') for f in cog_files), return_exceptions=True)
    for filename, result in zip(cog_files, results):
        if isinstance(result, Exception):
            print(f'Failed to load {filename}: {result}')
    
    asyncio.create_task(cleanup_task())
    await load_jackychat_channels()
    print('Bot is ready')
    
    if channel := bot.get_channel(Config.CHANNEL_ID):
        try:
            asyncio.create_task(channel.send('JackyBot Online...'))
        except discord.Forbidden:
            print(f"Missing permissions to send message in channel {Config.CHANNEL_ID}")

bot.setup_hook = setup_hook

# Channel cache
@lru_cache(maxsize=50)
def get_channel_cached(channel_id):
    return bot.get_channel(channel_id)

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
            await asyncio.gather(*tasks)
    
    await bot.process_commands(message)

# Shutdown handler
@bot.event
async def on_close():
    print("Bot is shutting down...")
    if bot.pool: await bot.pool.close()
    if bot.executor: bot.executor.shutdown(wait=False)
    print("Cleanup complete.")

# Ping command
@bot.command()
async def ping(ctx):
    start = time.perf_counter()
    msg = await ctx.reply("Measuring latency...")
    end = time.perf_counter()
    await msg.edit(content=f'Pong! API: {round(bot.latency * 1000)}ms | Message: {round((end - start) * 1000)}ms')

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
        vc.play(discord.FFmpegPCMAudio(temp_file), after=lambda e: (print(f"Error in voice playback: {e}") if e else None, asyncio.run_coroutine_threadsafe(delete_file(temp_file), bot.loop)))
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
                    if channel := get_channel_cached(channel_id):
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
    await bot.close()
    loop.stop()

# Main entry point
async def main():
    token = os.environ.get("Discord_Bot_Token")
    if not token:
        print("Error: Discord_Bot_Token environment variable not set.")
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
        if not bot.is_closed():
            await bot.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot shutdown requested.")