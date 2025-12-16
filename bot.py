import discord
import ctypes
import ctypes.util
import asyncio
import os
import aiofiles
from discord.ext import commands
from gtts import gTTS
from groq import Groq
import time
import signal
import sys

try:
    import orjson as json
    _ORJSON = True
except ImportError:
    import json
    _ORJSON = False

_CHANNEL_ID = 1132395937180950599
_AUTH_USER_ID = 103873926622363648
_EMBED_COLOR = 0x0099ff
_MAX_DEL_MSG = 5
_SAVE_CD = 5
_CLEANUP_INT = 1800
_MAX_MSG = 50
_MAX_CONN = 2
_CD_RATE = 1
_CD_PER = 120
_JACKYBOT_CHAT = "jackybot-chat"
_CONN_MASK = _MAX_CONN - 1
_NS_TO_MS = 1_000_000
_RATE_SLEEP = 0.2
_JSON_SEP = (',', ':')
_DATA_PATH = 'data/jackychat_channels.json'
_DISABLED_COGS = frozenset(('image_gen', 'model_manager', 'music', 'quote', 'server_manager'))

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True
bot = commands.Bot(command_prefix='!', intents=intents, chunk_guilds_at_startup=False, case_insensitive=True, max_messages=_MAX_MSG)

class ConnectionPool:
    __slots__ = ('connections', '_index')

    def __init__(self):
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY environment variable not set.")
        self.connections = tuple(Groq(api_key=api_key) for _ in range(_MAX_CONN))
        self._index = 0

    def get_connection(self):
        idx = self._index
        self._index = (idx + 1) & _CONN_MASK
        return self.connections[idx]

    async def close(self):
        iscoro = asyncio.iscoroutine
        for conn in self.connections:
            close_fn = getattr(conn, 'close', None)
            if close_fn is not None:
                result = close_fn()
                if iscoro(result):
                    await result

class BotState:
    __slots__ = ('jackychat_channels', 'processed_messages', 'last_save_time', 'last_cleanup_time', 'broadcast_semaphore')

    def __init__(self):
        self.jackychat_channels = {}
        self.processed_messages = set()
        self.last_save_time = 0.0
        self.last_cleanup_time = time.time()
        self.broadcast_semaphore = asyncio.Semaphore(5)

bot.pool = ConnectionPool()
bot.state = BotState()

_state = bot.state
_processed = _state.processed_messages
_channels = _state.jackychat_channels
_semaphore = _state.broadcast_semaphore
_bot_user = None

async def cleanup_task():
    sleep = asyncio.sleep
    interval = _CLEANUP_INT
    processed = _processed
    state = _state
    get_time = time.time
    while True:
        await sleep(interval)
        processed.clear()
        state.last_cleanup_time = get_time()

async def setup_hook():
    listdir = os.listdir
    disabled = _DISABLED_COGS
    load_ext = bot.load_extension
    cog_files = [f[:-3] for f in listdir('./cogs') if f[-3:] == '.py' and f[:-3] not in disabled]
    results = await asyncio.gather(*(load_ext(f'cogs.{f}') for f in cog_files), return_exceptions=True)
    for filename, result in zip(cog_files, results):
        if isinstance(result, Exception):
            print(f'Failed to load {filename}: {result}')
    asyncio.create_task(cleanup_task())

bot.setup_hook = setup_hook

_ready_once = False

@bot.event
async def on_ready():
    global _ready_once, _bot_user
    if _ready_once:
        return
    _ready_once = True
    _bot_user = bot.user

    await load_jackychat_channels()
    print('Bot is ready')

    channel = bot.get_channel(_CHANNEL_ID)
    if channel:
        try:
            await channel.send('JackyBot Online...')
        except discord.Forbidden:
            print(f"Missing permissions in channel {_CHANNEL_ID}")
        except Exception as e:
            print(f"Failed to send startup message: {e}")

    opus = discord.opus
    try:
        if not opus.is_loaded():
            opus_path = ctypes.util.find_library('opus')
            if opus_path:
                opus.load_opus(opus_path)
    except Exception as e:
        print(f"Warning: Opus library not loaded ({e}). Voice may fail.")

@bot.event
async def on_message(message):
    author = message.author
    if author.id == _bot_user.id:
        return
    guild = message.guild
    if guild is None:
        return

    msg_channel = message.channel
    channel_id = msg_channel.id
    msg_id = message.id
    key = (channel_id << 64) | msg_id
    
    processed = _processed
    if key in processed:
        return
    processed.add(key)

    channel_name = msg_channel.name
    if _JACKYBOT_CHAT in channel_name:
        guild_id = guild.id
        channels = _channels
        current = channels.get(guild_id)

        if current is not msg_channel:
            channels[guild_id] = msg_channel
            asyncio.create_task(save_jackychat_channels())

        embed = discord.Embed(
            title=f"Broadcast from {guild.name}",
            description=f"{author.mention}: {message.content}",
            color=_EMBED_COLOR
        )
        attachments = message.attachments
        if attachments:
            embed.set_image(url=attachments[0].url)

        targets = [(gid, ch) for gid, ch in channels.items() if gid != guild_id and ch is not None]
        if targets:
            asyncio.create_task(_broadcast(targets, embed))

    await bot.process_commands(message)

async def _broadcast(targets, embed):
    sem = _semaphore
    tasks = [_send_one(ch, embed, sem) for _, ch in targets]
    await asyncio.gather(*tasks, return_exceptions=True)

async def _send_one(channel, embed, semaphore):
    async with semaphore:
        try:
            await channel.send(embed=embed)
            await asyncio.sleep(_RATE_SLEEP)
        except discord.Forbidden:
            pass
        except discord.HTTPException as e:
            if e.status == 429:
                await asyncio.sleep(getattr(e, 'retry_after', 5))
                try:
                    await channel.send(embed=embed)
                except Exception:
                    pass

@bot.command()
async def ping(ctx):
    perf_ns = time.perf_counter_ns
    start = perf_ns()
    msg = await ctx.reply("Measuring latency...")
    end = perf_ns()
    latency_ms = int(bot.latency * 1000 + 0.5)
    message_ms = (end - start) // _NS_TO_MS
    await msg.edit(content=f'Pong! API: {latency_ms}ms | Message: {message_ms}ms')

@bot.command()
async def voice_diag(ctx):
    nacl_ok = False
    try:
        import nacl
        nacl_ok = True
    except Exception:
        pass

    opus = discord.opus
    opus_loaded = opus.is_loaded()
    if not opus_loaded:
        try:
            opus_path = ctypes.util.find_library('opus')
            if opus_path:
                opus.load_opus(opus_path)
                opus_loaded = opus.is_loaded()
        except Exception:
            pass

    nacl_str = 'OK' if nacl_ok else 'MISSING'
    opus_str = 'LOADED' if opus_loaded else 'NOT LOADED'
    await ctx.reply(f"PyNaCl: {nacl_str} | Opus: {opus_str}")

@bot.command()
async def tts(ctx, *, message):
    voice_state = ctx.author.voice
    if voice_state is None or voice_state.channel is None:
        return await ctx.reply('You need to be in a voice channel.')

    voice_channel = voice_state.channel
    vc = ctx.voice_client
    if vc is None:
        vc = await voice_channel.connect()
    elif vc.channel != voice_channel:
        await vc.move_to(voice_channel)

    temp_file = f"temp_{ctx.message.id}.mp3"
    to_thread = asyncio.to_thread
    FFmpegPCMAudio = discord.FFmpegPCMAudio
    try:
        tts_obj = gTTS(text=message, lang='en')
        await to_thread(tts_obj.save, temp_file)
        def _after(err):
            if err:
                print(f"Error in voice playback: {err}")
            try:
                asyncio.create_task(delete_file(temp_file))
            except RuntimeError:
                pass
        vc.play(FFmpegPCMAudio(temp_file), after=_after)
    except Exception as e:
        await ctx.reply("Failed to generate TTS audio.")
        print(f"TTS Error: {e}")
        await delete_file(temp_file)

async def delete_file(filename):
    try:
        await asyncio.to_thread(os.remove, filename)
    except OSError:
        pass

@bot.command()
async def leave(ctx):
    vc = ctx.voice_client
    if vc:
        await vc.disconnect()
        await ctx.reply("Disconnected from voice channel.")

@bot.command()
@commands.cooldown(_CD_RATE, _CD_PER, commands.BucketType.user)
async def delete(ctx, number_of_messages: int):
    if ctx.author.id != _AUTH_USER_ID:
        return await ctx.reply("You are not authorized to use this command.")
    if number_of_messages < 1 or number_of_messages > _MAX_DEL_MSG:
        return await ctx.reply(f"Please provide a number between 1 and {_MAX_DEL_MSG}.")
    
    try:
        deleted = await ctx.channel.purge(limit=number_of_messages + 1)
        await ctx.send(f"Deleted {len(deleted)-1} messages.", delete_after=5)
    except discord.Forbidden:
        await ctx.send("I don't have permission to delete messages here.")
    except discord.HTTPException as e:
        await ctx.send(f"Failed to delete messages: {e}")

async def save_jackychat_channels():
    get_time = time.time
    current_time = get_time()
    state = _state
    if current_time - state.last_save_time < _SAVE_CD:
        return
    state.last_save_time = current_time

    channels = _channels
    if _ORJSON:
        data_bytes = json.dumps({str(gid): {'channel_id': ch.id} for gid, ch in channels.items()})
        data_str = data_bytes.decode('utf-8')
    else:
        data_str = json.dumps({str(gid): {'channel_id': ch.id} for gid, ch in channels.items()}, separators=_JSON_SEP)
    
    try:
        async with aiofiles.open(_DATA_PATH, 'w') as f:
            await f.write(data_str)
    except Exception as e:
        print(f"Error saving jackychat channels: {e}")

async def load_jackychat_channels():
    get_channel = bot.get_channel
    channels = _channels
    try:
        async with aiofiles.open(_DATA_PATH, 'r') as f:
            content = await f.read()
            if not content or content.isspace():
                return
            if _ORJSON:
                data = json.loads(content)
            else:
                data = json.loads(content)
            for guild_id_str, info in data.items():
                channel_id = info.get('channel_id')
                if channel_id:
                    channel = get_channel(channel_id)
                    if channel:
                        channels[int(guild_id_str)] = channel
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"Could not load {_DATA_PATH} ({e}). Starting fresh.")

async def shutdown(sig, loop):
    print(f"Received exit signal {sig.name}...")
    current = asyncio.current_task()
    tasks = [t for t in asyncio.all_tasks(loop) if t is not current]
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    pool = getattr(bot, 'pool', None)
    if pool:
        await pool.close()
    await bot.close()
    loop.stop()

async def main():
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if not token:
        print("Error: DISCORD_BOT_TOKEN environment variable not set.")
        return

    loop = asyncio.get_running_loop()
    if sys.platform != "win32":
        from functools import partial
        for sig in (signal.SIGINT, signal.SIGTERM):
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