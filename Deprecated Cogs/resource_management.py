import asyncio
from discord.ext import commands
from weakref import WeakValueDictionary
from functools import lru_cache
from typing import Callable, Dict, Tuple, Any, Optional

class ResourceManagementCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.combined_queue = asyncio.PriorityQueue()  # Using priority queue for better scheduling
        self.queue_task = None
        self.is_running = True
        self.cog_cache = WeakValueDictionary()  # Cache for cog references to reduce lookups
        self.command_map: Dict[str, Callable] = {}  # Pre-defined command map
        self.start_queue_processing()

    def start_queue_processing(self):
        """Start the queue processing task."""
        if self.queue_task is None or self.queue_task.done():
            self.queue_task = self.bot.loop.create_task(self.process_queue())

    async def cog_unload(self):
        """Properly clean up resources when the cog is unloaded."""
        self.is_running = False
        if self.queue_task and not self.queue_task.done():
            self.queue_task.cancel()
            try:
                await self.queue_task
            except asyncio.CancelledError:
                pass
            finally:
                self.queue_task = None
        
        # Clear caches
        self.cog_cache.clear()
        self.command_map.clear()
        self.get_cog_reference.cache_clear()

    async def process_queue(self):
        """Process items from the queue with improved error handling."""
        while self.is_running:
            try:
                # Using timeout to allow periodic checking of self.is_running
                priority, (cog, ctx, prompt, command_type) = await asyncio.wait_for(
                    self.combined_queue.get(), timeout=1.0
                )
                await self.process_request(cog, ctx, prompt, command_type)
                
            except asyncio.TimeoutError:
                # Just a timeout for checking is_running, continue loop
                continue
            except asyncio.CancelledError:
                # Task was cancelled, exit loop
                break
            except Exception as e:
                print(f"Queue processing error: {e}")
            finally:
                # No need for sleep - the queue already acts as a rate limiter
                # and wait_for with timeout provides the periodic check
                pass

    async def process_request(self, cog, ctx, prompt, command_type):
        """Process a request with better error handling and performance."""
        try:
            # Use pre-built command map with direct method references
            if not self.command_map:
                self._build_command_map()
                
            handler = self.command_map.get(command_type)
            if handler:
                if command_type == '3d':
                    await handler(cog, ctx, prompt)
                elif command_type == 'create':
                    await handler(cog, prompt, ctx)
                elif command_type == 'paint':
                    await handler(cog, ctx, prompt=prompt)
            else:
                await ctx.send(f"Unknown command type: {command_type}")
                
        except Exception as e:
            await ctx.send(f"Error processing {command_type} request: {str(e)}")
        finally:
            self.combined_queue.task_done()

    def _build_command_map(self):
        """Build the command map once to avoid repeated lambda creation."""
        self.command_map = {
            '3d': lambda cog, ctx, prompt: cog.process_request(ctx, prompt),
            'create': lambda cog, prompt, ctx: cog.process_request(prompt, ctx),
            'paint': lambda cog, ctx, prompt: cog.paint_command(ctx, prompt=prompt)
        }

    @lru_cache(maxsize=8)
    def get_cog_reference(self, cog_name: str) -> Optional[commands.Cog]:
        """Get and cache cog references to reduce lookups."""
        return self.bot.get_cog(cog_name)

    async def add_to_queue(self, cog, ctx, prompt, command_type, priority=5):
        """Add a request to the queue with priority support."""
        if self.combined_queue.qsize() >= 10:
            await ctx.reply("Queue is full. Please try again later.")
            return False
            
        # Add item with priority (lower number = higher priority)
        await self.combined_queue.put((priority, (cog, ctx, prompt, command_type)))
        position = self.combined_queue.qsize()
        await ctx.reply(f"Your {command_type} request has been added to the queue. Position: {position}")
        return True

    @commands.command(name='3d')
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def three_d_command(self, ctx, *, prompt):
        """Handle 3D generation requests."""
        three_d_cog = self.get_cog_reference('ThreeDGenerationCog')
        if three_d_cog:
            await self.add_to_queue(three_d_cog, ctx, prompt, '3d')
        else:
            await ctx.reply("The 3D generation cog is not loaded.")

    @commands.command(name='create')
    @commands.cooldown(1, 30, commands.BucketType.user)
    async def create_command(self, ctx, *, prompt):
        """Handle image creation requests."""
        image_gen_cog = self.get_cog_reference('ImageGenerationCog')
        if image_gen_cog:
            await self.add_to_queue(image_gen_cog, ctx, prompt, 'create')
        else:
            await ctx.reply("The image generation cog is not loaded.")

    @commands.Cog.listener()
    async def on_command(self, ctx):
        """Intercept paint commands and add them to the queue."""
        if ctx.command and ctx.command.name == 'paint':
            paint_cog = self.get_cog_reference('PaintCog')
            if paint_cog:
                # Get the prompt from the context
                prompt = ctx.kwargs.get('prompt', '')
                # Add the paint request to the queue
                if await self.add_to_queue(paint_cog, ctx, prompt, 'paint'):
                    # Prevent the original command from running only if added to queue
                    ctx.command = None
            else:
                await ctx.reply("The paint cog is not loaded.")

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """Handle command errors with efficient error handling."""
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"Please wait {error.retry_after:.1f} seconds before using this command again.")
        elif not isinstance(error, commands.CommandNotFound):
            await ctx.send(f"An error occurred: {str(error)}")

async def setup(bot):
    """Add the cog to the bot."""
    await bot.add_cog(ResourceManagementCog(bot))