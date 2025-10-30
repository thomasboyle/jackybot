import discord
from discord.ext import commands
import socketio
import asyncio
import os
import json
from typing import Dict, Set

class WebInterfaceListener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.sio = socketio.AsyncClient()
        self.server_url = os.environ.get('WEB_INTERFACE_URL', 'http://localhost:5000')
        self.guild_cog_states: Dict[int, Dict[str, bool]] = {}
        self.connection_task = None
        
        self.setup_socket_handlers()
        self.connection_task = asyncio.create_task(self.connect_to_server())
    
    def cog_unload(self):
        if self.connection_task:
            self.connection_task.cancel()
        asyncio.create_task(self.sio.disconnect())
        self.bot.remove_check(self.global_check)
    
    def setup_socket_handlers(self):
        @self.sio.on('connect')
        async def on_connect():
            print('WebInterfaceListener: Connected to web interface')
        
        @self.sio.on('disconnect')
        async def on_disconnect():
            print('WebInterfaceListener: Disconnected from web interface')
        
        @self.sio.on('cog_update')
        async def on_cog_update(data):
            server_id = int(data.get('server_id'))
            cog_name = data.get('cog_name')
            enabled = data.get('enabled')
            
            if server_id not in self.guild_cog_states:
                self.guild_cog_states[server_id] = {}
            
            self.guild_cog_states[server_id][cog_name] = enabled
            
            print(f'WebInterfaceListener: Cog {cog_name} {"enabled" if enabled else "disabled"} for server {server_id}')
    
    async def connect_to_server(self):
        await self.bot.wait_until_ready()
        
        while not self.bot.is_closed():
            try:
                if not self.sio.connected:
                    await self.sio.connect(self.server_url)
                    await self.load_all_settings()
                await asyncio.sleep(5)
            except Exception as e:
                print(f'WebInterfaceListener: Connection error: {e}')
                await asyncio.sleep(10)
    
    async def load_all_settings(self):
        settings_path = os.environ.get('COG_SETTINGS_PATH', 'data/cog_settings.json')
        try:
            if os.path.exists(settings_path):
                with open(settings_path, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                
                for server_id_str, cog_settings in settings.items():
                    server_id = int(server_id_str)
                    self.guild_cog_states[server_id] = {}
                    for cog_name, cog_config in cog_settings.items():
                        self.guild_cog_states[server_id][cog_name] = cog_config.get('enabled', True)
                
                print(f'WebInterfaceListener: Loaded settings for {len(self.guild_cog_states)} servers')
        except Exception as e:
            print(f'WebInterfaceListener: Error loading settings: {e}')
    
    def is_cog_enabled(self, guild_id: int, cog_name: str) -> bool:
        if guild_id not in self.guild_cog_states:
            return True
        
        return self.guild_cog_states[guild_id].get(cog_name, True)
    
    def get_cog_name_from_module(self, cog) -> str:
        if not cog:
            return None
        
        module_name = cog.__class__.__module__
        if module_name.startswith('cogs.'):
            return module_name.split('.')[1]
        return None
    
    async def global_check(self, ctx: commands.Context) -> bool:
        if not ctx.guild:
            return True
        
        cog = ctx.cog
        if not cog:
            return True
        
        cog_name = self.get_cog_name_from_module(cog)
        if not cog_name:
            return True
        
        if cog_name == 'web_interface_listener' or cog_name == 'help':
            return True
        
        if not self.is_cog_enabled(ctx.guild.id, cog_name):
            await ctx.reply(f'The `{cog_name}` module is currently disabled on this server.', ephemeral=True)
            return False
        
        return True

async def setup(bot):
    listener = WebInterfaceListener(bot)
    await bot.add_cog(listener)
    bot.add_check(listener.global_check)

