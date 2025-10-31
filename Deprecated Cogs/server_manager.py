import discord
from discord.ext import commands
import groq
import os
import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import threading
import time
from collections import defaultdict

class SimpleCache:
    """Thread-safe cache with TTL for metric data."""
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

    def set(self, key: str, value, ttl_seconds: int = 300):
        with self._lock:
            self._cache[key] = (value, time.time() + ttl_seconds)


class ServerManager(commands.Cog):
    """Autonomous AI agent that manages Discord server engagement through data-driven decisions."""
    
    __slots__ = ('bot', 'groq_client', 'model', 'target_server_id', 'log_server_id', 
                 'log_channel_name', 'decision_interval', 'cache', 'memory_file',
                 'autonomous_task', 'is_paused', 'authorized_user_id', 'last_decision_time')

    def __init__(self, bot):
        self.bot = bot
        
        # Configuration
        self.target_server_id = 1078653820139229194
        self.log_server_id = 515628838991167498
        self.log_channel_name = "jackybot-manager"
        self.decision_interval = 7200  # 2 hours in seconds
        self.authorized_user_id = 103873926622363648
        
        # Groq API setup
        self.groq_api_key = os.environ.get("GROQ_API_KEY")
        if not self.groq_api_key:
            print("WARNING: GROQ_API_KEY not set. Server manager will not work.")
            self.groq_client = None
        else:
            self.groq_client = groq.Client(
                api_key=self.groq_api_key,
                max_retries=2
            )
        self.model = "openai/gpt-oss-120b"
        
        # State management
        self.cache = SimpleCache()
        self.memory_file = "data/server_manager_memory.json"
        self.is_paused = False
        self.last_decision_time = None
        
        # Start autonomous loop
        self.autonomous_task = asyncio.create_task(self.autonomous_management_loop())

    def cog_unload(self):
        """Clean up background tasks when the cog is unloaded."""
        self.autonomous_task.cancel()

    # ==================== STORAGE SYSTEM ====================
    
    def load_memory(self) -> Dict:
        """Load agent's persistent memory from JSON file."""
        try:
            if os.path.exists(self.memory_file):
                with open(self.memory_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            print(f"Error loading memory: {e}")
        
        # Return default memory structure
        return {
            "decisions": [],
            "historical_metrics": [],
            "action_history": [],
            "learning_notes": [],
            "last_updated": None
        }

    def save_memory(self, memory: Dict):
        """Save updated memory state to JSON file."""
        try:
            memory["last_updated"] = datetime.now().isoformat()
            with open(self.memory_file, 'w', encoding='utf-8') as f:
                json.dump(memory, f, indent=2)
        except Exception as e:
            print(f"Error saving memory: {e}")

    def update_historical_metrics(self, memory: Dict, current_metrics: Dict):
        """Add current metrics to historical data with 7-day rolling window."""
        historical = memory.get("historical_metrics", [])
        
        # Add current metrics with timestamp
        historical.append({
            "timestamp": datetime.now().isoformat(),
            "metrics": current_metrics
        })
        
        # Keep only last 7 days
        cutoff_time = datetime.now() - timedelta(days=7)
        historical = [
            h for h in historical 
            if datetime.fromisoformat(h["timestamp"]) > cutoff_time
        ]
        
        memory["historical_metrics"] = historical

    # ==================== DATA COLLECTION SYSTEM ====================
    
    async def collect_member_metrics(self, guild: discord.Guild) -> Dict:
        """Collect member-related metrics from the guild."""
        try:
            total_members = guild.member_count
            
            # Count members by status
            online_members = sum(1 for m in guild.members if m.status != discord.Status.offline)
            bot_count = sum(1 for m in guild.members if m.bot)
            human_count = total_members - bot_count
            
            # Role distribution (top 10 roles by member count)
            role_distribution = {}
            for role in guild.roles:
                if role.name != "@everyone" and len(role.members) > 0:
                    role_distribution[role.name] = len(role.members)
            
            top_roles = dict(sorted(role_distribution.items(), key=lambda x: x[1], reverse=True)[:10])
            
            return {
                "total_members": total_members,
                "human_members": human_count,
                "bot_members": bot_count,
                "online_members": online_members,
                "role_distribution": top_roles
            }
        except Exception as e:
            print(f"Error collecting member metrics: {e}")
            return {}

    async def collect_message_metrics(self, guild: discord.Guild) -> Dict:
        """Collect message activity metrics from the guild."""
        try:
            cutoff_time = datetime.now() - timedelta(hours=24)
            
            channel_activity = {}
            total_messages = 0
            active_users = set()
            hourly_activity = defaultdict(int)
            
            # Analyze text channels
            for channel in guild.text_channels:
                try:
                    if not channel.permissions_for(guild.me).read_message_history:
                        continue
                    
                    message_count = 0
                    async for message in channel.history(limit=500, after=cutoff_time):
                        message_count += 1
                        total_messages += 1
                        if not message.author.bot:
                            active_users.add(message.author.id)
                        
                        # Track hourly activity
                        hour = message.created_at.hour
                        hourly_activity[hour] += 1
                    
                    if message_count > 0:
                        channel_activity[channel.name] = message_count
                        
                except discord.Forbidden:
                    continue
                except Exception as e:
                    print(f"Error reading channel {channel.name}: {e}")
                    continue
            
            # Find peak activity hours
            peak_hours = sorted(hourly_activity.items(), key=lambda x: x[1], reverse=True)[:3]
            peak_hours_list = [f"{hour}:00" for hour, _ in peak_hours]
            
            return {
                "total_messages_24h": total_messages,
                "active_communicators_24h": len(active_users),
                "channel_activity": dict(sorted(channel_activity.items(), key=lambda x: x[1], reverse=True)[:10]),
                "peak_activity_hours": peak_hours_list
            }
        except Exception as e:
            print(f"Error collecting message metrics: {e}")
            return {}

    async def collect_voice_metrics(self, guild: discord.Guild) -> Dict:
        """Collect voice activity metrics from the guild."""
        try:
            voice_channels = {}
            total_voice_members = 0
            
            for channel in guild.voice_channels:
                member_count = len(channel.members)
                if member_count > 0:
                    voice_channels[channel.name] = member_count
                    total_voice_members += member_count
            
            return {
                "current_voice_members": total_voice_members,
                "active_voice_channels": voice_channels,
                "total_voice_channels": len(guild.voice_channels)
            }
        except Exception as e:
            print(f"Error collecting voice metrics: {e}")
            return {}

    async def collect_all_metrics(self) -> Optional[Dict]:
        """Collect all server metrics."""
        guild = self.bot.get_guild(self.target_server_id)
        if not guild:
            print(f"Could not find target guild {self.target_server_id}")
            return None
        
        member_metrics = await self.collect_member_metrics(guild)
        message_metrics = await self.collect_message_metrics(guild)
        voice_metrics = await self.collect_voice_metrics(guild)
        
        return {
            "timestamp": datetime.now().isoformat(),
            "server_name": guild.name,
            "member_metrics": member_metrics,
            "message_metrics": message_metrics,
            "voice_metrics": voice_metrics,
            "channel_count": {
                "text": len(guild.text_channels),
                "voice": len(guild.voice_channels),
                "categories": len(guild.categories)
            },
            "role_count": len(guild.roles)
        }

    # ==================== AI DECISION ENGINE ====================
    
    def construct_system_prompt(self) -> str:
        """Create comprehensive system prompt for the AI agent."""
        return """You are an autonomous Discord server manager AI agent. Your primary goal is to maximize server engagement, measured by:
- Total messages sent
- Total voice minutes
- Number of active communicators
- Number of visitors

You are given complete context about the current server state, historical trends, and previous actions. You must make ONE data-driven decision per cycle.

AVAILABLE ACTIONS:
1. "create_announcement" - Send announcement to a specific channel
   Parameters: {"channel_name": str, "message": str}

2. "create_text_channel" - Create a new text channel
   Parameters: {"name": str, "category": str, "topic": str}

3. "create_voice_channel" - Create a new voice channel
   Parameters: {"name": str, "category": str}

4. "modify_channel" - Modify existing channel
   Parameters: {"channel_name": str, "new_name": str (optional), "new_topic": str (optional), "slowmode": int (optional)}

5. "create_role" - Create a new role
   Parameters: {"name": str, "color": str (hex), "permissions": list}

6. "modify_role" - Modify existing role
   Parameters: {"role_name": str, "new_name": str (optional), "new_color": str (optional)}

7. "create_event" - Create a scheduled event
   Parameters: {"name": str, "description": str, "start_time": str (ISO format or relative like "+24h"), "channel_name": str (optional)}

8. "no_action" - Take no action if metrics are stable
   Parameters: {"reason": str}

CONSTRAINTS:
- You CANNOT delete channels, roles, or messages
- You CANNOT assign administrator or manage_server permissions
- You are limited to 1 action per decision cycle
- All decisions must be based on data and trends
- Consider the impact of previous actions before making new ones

RESPONSE FORMAT (JSON only):
{
  "analysis": "Detailed analysis of current metrics and trends",
  "proposed_action": "action_name",
  "parameters": {...},
  "reasoning": "Why this action will improve engagement",
  "expected_impact": "Specific expected outcome with metrics"
}

Think critically. Be strategic. Prioritize actions with highest potential impact. Avoid redundant actions."""

    async def make_decision(self, current_metrics: Dict, memory: Dict) -> Optional[Dict]:
        """Use AI to analyze metrics and make a decision."""
        if not self.groq_client:
            print("Groq client not available")
            return None
        
        try:
            # Prepare context for AI
            context_parts = [
                "=== CURRENT METRICS ===",
                json.dumps(current_metrics, indent=2),
                "\n=== HISTORICAL TRENDS ===",
                self._format_historical_trends(memory),
                "\n=== PREVIOUS ACTIONS (Last 5) ===",
                self._format_action_history(memory.get("action_history", [])[-5:]),
                "\n=== LEARNING NOTES ===",
                self._format_learning_notes(memory.get("learning_notes", [])[-3:])
            ]
            
            context = "\n".join(context_parts)
            
            # Make API call
            loop = asyncio.get_event_loop()
            completion = await loop.run_in_executor(
                None,
                lambda: self.groq_client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": self.construct_system_prompt()},
                        {"role": "user", "content": context}
                    ],
                    max_tokens=1024,
                    temperature=0.7
                )
            )
            
            response_text = completion.choices[0].message.content
            
            # Parse JSON response
            decision = json.loads(response_text)
            
            # Validate decision structure
            required_keys = ["analysis", "proposed_action", "parameters", "reasoning", "expected_impact"]
            if not all(key in decision for key in required_keys):
                print(f"Invalid decision structure: {decision}")
                return None
            
            return decision
            
        except json.JSONDecodeError as e:
            print(f"Failed to parse AI response as JSON: {e}")
            return None
        except Exception as e:
            print(f"Error making decision: {e}")
            return None

    def _format_historical_trends(self, memory: Dict) -> str:
        """Format historical metrics for AI context."""
        historical = memory.get("historical_metrics", [])
        if not historical:
            return "No historical data available yet."
        
        recent = historical[-7:]  # Last 7 data points
        trends = []
        
        for h in recent:
            timestamp = h.get("timestamp", "Unknown")
            metrics = h.get("metrics", {})
            msg_metrics = metrics.get("message_metrics", {})
            trends.append(
                f"{timestamp}: Messages={msg_metrics.get('total_messages_24h', 0)}, "
                f"Communicators={msg_metrics.get('active_communicators_24h', 0)}"
            )
        
        return "\n".join(trends)

    def _format_action_history(self, actions: List[Dict]) -> str:
        """Format action history for AI context."""
        if not actions:
            return "No previous actions."
        
        history = []
        for action in actions:
            timestamp = action.get("timestamp", "Unknown")
            action_type = action.get("action", "Unknown")
            result = action.get("result", "Unknown")
            history.append(f"{timestamp}: {action_type} - {result}")
        
        return "\n".join(history)

    def _format_learning_notes(self, notes: List[Dict]) -> str:
        """Format learning notes for AI context."""
        if not notes:
            return "No learning notes yet."
        
        formatted = []
        for note in notes:
            formatted.append(f"- {note.get('note', '')}")
        
        return "\n".join(formatted)

    # ==================== ACTION EXECUTION SYSTEM ====================
    
    DANGEROUS_PERMISSIONS = [
        'administrator', 'manage_guild', 'manage_channels', 'manage_roles',
        'ban_members', 'kick_members', 'manage_webhooks', 'manage_emojis'
    ]

    async def execute_action(self, decision: Dict) -> Tuple[bool, str]:
        """Execute the decided action with safety checks."""
        action_name = decision.get("proposed_action")
        parameters = decision.get("parameters", {})
        
        guild = self.bot.get_guild(self.target_server_id)
        if not guild:
            return False, "Target guild not found"
        
        try:
            if action_name == "create_announcement":
                return await self._execute_announcement(guild, parameters)
            elif action_name == "create_text_channel":
                return await self._execute_channel_creation(guild, parameters, "text")
            elif action_name == "create_voice_channel":
                return await self._execute_channel_creation(guild, parameters, "voice")
            elif action_name == "modify_channel":
                return await self._execute_channel_modification(guild, parameters)
            elif action_name == "create_role":
                return await self._execute_role_creation(guild, parameters)
            elif action_name == "modify_role":
                return await self._execute_role_modification(guild, parameters)
            elif action_name == "create_event":
                return await self._execute_event_creation(guild, parameters)
            elif action_name == "no_action":
                return True, f"No action taken: {parameters.get('reason', 'Metrics stable')}"
            else:
                return False, f"Unknown action: {action_name}"
                
        except discord.Forbidden:
            return False, "Missing permissions to execute action"
        except Exception as e:
            return False, f"Error executing action: {str(e)}"

    async def _execute_announcement(self, guild: discord.Guild, params: Dict) -> Tuple[bool, str]:
        """Send announcement to specified channel."""
        channel_name = params.get("channel_name", "").lower()
        message = params.get("message", "")
        
        if not channel_name or not message:
            return False, "Missing channel_name or message"
        
        channel = discord.utils.get(guild.text_channels, name=channel_name)
        if not channel:
            return False, f"Channel '{channel_name}' not found"
        
        await channel.send(message)
        return True, f"Announcement sent to #{channel_name}"

    async def _execute_channel_creation(self, guild: discord.Guild, params: Dict, channel_type: str) -> Tuple[bool, str]:
        """Create a new text or voice channel."""
        name = params.get("name", "")
        category_name = params.get("category")
        topic = params.get("topic", "") if channel_type == "text" else None
        
        if not name:
            return False, "Missing channel name"
        
        category = None
        if category_name:
            category = discord.utils.get(guild.categories, name=category_name)
        
        if channel_type == "text":
            channel = await guild.create_text_channel(name, category=category, topic=topic)
            return True, f"Created text channel #{channel.name}"
        else:
            channel = await guild.create_voice_channel(name, category=category)
            return True, f"Created voice channel {channel.name}"

    async def _execute_channel_modification(self, guild: discord.Guild, params: Dict) -> Tuple[bool, str]:
        """Modify an existing channel."""
        channel_name = params.get("channel_name", "")
        new_name = params.get("new_name")
        new_topic = params.get("new_topic")
        slowmode = params.get("slowmode")
        
        if not channel_name:
            return False, "Missing channel_name"
        
        channel = discord.utils.get(guild.text_channels, name=channel_name)
        if not channel:
            return False, f"Channel '{channel_name}' not found"
        
        changes = []
        if new_name:
            await channel.edit(name=new_name)
            changes.append(f"renamed to #{new_name}")
        if new_topic is not None:
            await channel.edit(topic=new_topic)
            changes.append("topic updated")
        if slowmode is not None:
            await channel.edit(slowmode_delay=min(slowmode, 21600))
            changes.append(f"slowmode set to {slowmode}s")
        
        return True, f"Modified #{channel_name}: {', '.join(changes)}"

    async def _execute_role_creation(self, guild: discord.Guild, params: Dict) -> Tuple[bool, str]:
        """Create a new role with safe permissions."""
        name = params.get("name", "")
        color_hex = params.get("color", "000000")
        
        if not name:
            return False, "Missing role name"
        
        # Convert hex to discord.Color
        try:
            color = discord.Color(int(color_hex.replace("#", ""), 16))
        except:
            color = discord.Color.default()
        
        # Create role with basic permissions only (no dangerous perms)
        role = await guild.create_role(name=name, color=color)
        return True, f"Created role '{role.name}'"

    async def _execute_role_modification(self, guild: discord.Guild, params: Dict) -> Tuple[bool, str]:
        """Modify an existing role."""
        role_name = params.get("role_name", "")
        new_name = params.get("new_name")
        new_color = params.get("new_color")
        
        if not role_name:
            return False, "Missing role_name"
        
        role = discord.utils.get(guild.roles, name=role_name)
        if not role:
            return False, f"Role '{role_name}' not found"
        
        changes = []
        if new_name:
            await role.edit(name=new_name)
            changes.append(f"renamed to '{new_name}'")
        if new_color:
            try:
                color = discord.Color(int(new_color.replace("#", ""), 16))
                await role.edit(color=color)
                changes.append("color updated")
            except:
                pass
        
        return True, f"Modified role '{role_name}': {', '.join(changes)}"

    async def _execute_event_creation(self, guild: discord.Guild, params: Dict) -> Tuple[bool, str]:
        """Create a scheduled event."""
        name = params.get("name", "")
        description = params.get("description", "")
        start_time_str = params.get("start_time", "")
        channel_name = params.get("channel_name")
        
        if not name or not start_time_str:
            return False, "Missing name or start_time"
        
        try:
            # Handle relative time strings like "+24h", "+2d", etc.
            if start_time_str.startswith("+"):
                time_str = start_time_str[1:]
                if time_str.endswith("h"):
                    hours = int(time_str[:-1])
                    start_time = discord.utils.utcnow() + timedelta(hours=hours)
                elif time_str.endswith("d"):
                    days = int(time_str[:-1])
                    start_time = discord.utils.utcnow() + timedelta(days=days)
                else:
                    start_time = discord.utils.utcnow() + timedelta(hours=24)
            else:
                # Parse ISO format datetime
                start_time = datetime.fromisoformat(start_time_str)
                # Ensure timezone-aware datetime
                if start_time.tzinfo is None:
                    start_time = start_time.replace(tzinfo=discord.utils.utcnow().tzinfo)
                # Check if in the past
                if start_time < discord.utils.utcnow():
                    start_time = discord.utils.utcnow() + timedelta(hours=24)
        except:
            start_time = discord.utils.utcnow() + timedelta(hours=24)
        
        end_time = start_time + timedelta(hours=2)
        
        # Find channel if specified
        channel = None
        if channel_name:
            channel = discord.utils.get(guild.voice_channels, name=channel_name)
        
        # Create event based on whether we have a channel or not
        if channel:
            event = await guild.create_scheduled_event(
                name=name,
                description=description,
                start_time=start_time,
                end_time=end_time,
                channel=channel,
                entity_type=discord.EntityType.voice,
                privacy_level=discord.PrivacyLevel.guild_only
            )
        else:
            # External event (no specific channel)
            event = await guild.create_scheduled_event(
                name=name,
                description=description,
                start_time=start_time,
                end_time=end_time,
                location="Discord Server",
                entity_type=discord.EntityType.external,
                privacy_level=discord.PrivacyLevel.guild_only
            )
        
        return True, f"Created event '{event.name}' scheduled for {start_time.strftime('%Y-%m-%d %H:%M UTC')}"

    # ==================== LOGGING SYSTEM ====================
    
    async def get_log_channel(self) -> Optional[discord.TextChannel]:
        """Get the logging channel."""
        log_guild = self.bot.get_guild(self.log_server_id)
        if not log_guild:
            return None
        
        # Try to find existing channel
        channel = discord.utils.get(log_guild.text_channels, name=self.log_channel_name)
        
        # Create if doesn't exist
        if not channel:
            try:
                channel = await log_guild.create_text_channel(
                    self.log_channel_name,
                    topic="Autonomous Server Manager logs and decision tracking"
                )
            except Exception as e:
                print(f"Could not create log channel: {e}")
                return None
        
        return channel

    async def log_decision_cycle(self, current_metrics: Dict, decision: Optional[Dict], 
                                 execution_result: Optional[Tuple[bool, str]]):
        """Log comprehensive decision cycle information."""
        channel = await self.get_log_channel()
        if not channel:
            print("Could not get log channel")
            return
        
        try:
            # Thought Process Embed
            thought_embed = discord.Embed(
                title="🧠 Thought Process & Analysis",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            
            # Current metrics summary
            msg_metrics = current_metrics.get("message_metrics", {})
            member_metrics = current_metrics.get("member_metrics", {})
            voice_metrics = current_metrics.get("voice_metrics", {})
            
            thought_embed.add_field(
                name="Current Engagement Metrics",
                value=f"📨 Messages (24h): {msg_metrics.get('total_messages_24h', 0)}\n"
                      f"👥 Active Users: {msg_metrics.get('active_communicators_24h', 0)}\n"
                      f"🎤 Voice Users: {voice_metrics.get('current_voice_members', 0)}\n"
                      f"👤 Total Members: {member_metrics.get('total_members', 0)}",
                inline=False
            )
            
            if decision:
                thought_embed.add_field(
                    name="AI Analysis",
                    value=decision.get("analysis", "No analysis")[:1024],
                    inline=False
                )
            
            await channel.send(embed=thought_embed)
            
            # Decision Embed
            if decision:
                decision_embed = discord.Embed(
                    title="📋 Final Decision",
                    color=discord.Color.gold(),
                    timestamp=datetime.now()
                )
                
                decision_embed.add_field(
                    name="Proposed Action",
                    value=f"**{decision.get('proposed_action')}**",
                    inline=False
                )
                
                decision_embed.add_field(
                    name="Parameters",
                    value=f"```json\n{json.dumps(decision.get('parameters', {}), indent=2)[:1000]}```",
                    inline=False
                )
                
                decision_embed.add_field(
                    name="Reasoning",
                    value=decision.get("reasoning", "No reasoning")[:1024],
                    inline=False
                )
                
                decision_embed.add_field(
                    name="Expected Impact",
                    value=decision.get("expected_impact", "No impact specified")[:1024],
                    inline=False
                )
                
                await channel.send(embed=decision_embed)
            
            # Execution Result Embed
            if execution_result:
                success, message = execution_result
                result_embed = discord.Embed(
                    title="✅ Action Executed" if success else "❌ Action Failed",
                    description=message,
                    color=discord.Color.green() if success else discord.Color.red(),
                    timestamp=datetime.now()
                )
                
                await channel.send(embed=result_embed)
            
            # Separator
            await channel.send("─" * 50)
            
        except Exception as e:
            print(f"Error logging decision cycle: {e}")

    # ==================== AUTONOMOUS LOOP ====================
    
    async def autonomous_management_loop(self):
        """Main autonomous loop that runs every 2 hours."""
        await self.bot.wait_until_ready()
        
        # Wait a bit for all cogs to load
        await asyncio.sleep(10)
        
        while not self.bot.is_closed():
            try:
                if self.is_paused:
                    await asyncio.sleep(60)
                    continue
                
                print(f"[ServerManager] Starting decision cycle at {datetime.now()}")
                
                # Collect current metrics
                current_metrics = await self.collect_all_metrics()
                if not current_metrics:
                    print("[ServerManager] Failed to collect metrics")
                    await asyncio.sleep(self.decision_interval)
                    continue
                
                # Load memory
                memory = self.load_memory()
                
                # Update historical metrics
                self.update_historical_metrics(memory, current_metrics)
                
                # Make decision
                decision = await self.make_decision(current_metrics, memory)
                
                # Execute action if decision was made
                execution_result = None
                if decision:
                    execution_result = await self.execute_action(decision)
                    
                    # Record action in history
                    action_record = {
                        "timestamp": datetime.now().isoformat(),
                        "action": decision.get("proposed_action"),
                        "parameters": decision.get("parameters"),
                        "result": "Success" if execution_result[0] else "Failed",
                        "message": execution_result[1]
                    }
                    memory.setdefault("action_history", []).append(action_record)
                    
                    # Add learning note if action succeeded
                    if execution_result[0]:
                        learning_note = {
                            "timestamp": datetime.now().isoformat(),
                            "note": f"Executed {decision.get('proposed_action')} - {decision.get('reasoning')}"
                        }
                        memory.setdefault("learning_notes", []).append(learning_note)
                
                # Save memory
                self.save_memory(memory)
                
                # Log everything
                await self.log_decision_cycle(current_metrics, decision, execution_result)
                
                self.last_decision_time = datetime.now()
                
                print(f"[ServerManager] Decision cycle completed at {datetime.now()}")
                
            except Exception as e:
                print(f"[ServerManager] Error in autonomous loop: {e}")
                
                # Log error to channel
                try:
                    channel = await self.get_log_channel()
                    if channel:
                        error_embed = discord.Embed(
                            title="⚠️ Error in Autonomous Loop",
                            description=str(e),
                            color=discord.Color.red(),
                            timestamp=datetime.now()
                        )
                        await channel.send(embed=error_embed)
                except:
                    pass
            
            # Wait for next cycle
            await asyncio.sleep(self.decision_interval)

    # ==================== MANUAL OVERRIDE COMMANDS ====================
    
    def _is_authorized(self, ctx) -> bool:
        """Check if user is authorized to use admin commands."""
        return ctx.author.id == self.authorized_user_id

    @commands.command(name="server_manager_status")
    async def status(self, ctx):
        """Show current agent state and recent activity."""
        if not self._is_authorized(ctx):
            return await ctx.reply("You are not authorized to use this command.")
        
        embed = discord.Embed(
            title="🤖 Server Manager Status",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        status_text = "🟢 Active" if not self.is_paused else "🔴 Paused"
        embed.add_field(name="Status", value=status_text, inline=True)
        
        if self.last_decision_time:
            time_since = datetime.now() - self.last_decision_time
            embed.add_field(
                name="Last Decision",
                value=f"{int(time_since.total_seconds() / 60)} minutes ago",
                inline=True
            )
        
        next_cycle = self.decision_interval - int((datetime.now() - self.last_decision_time).total_seconds()) if self.last_decision_time else self.decision_interval
        embed.add_field(
            name="Next Cycle",
            value=f"In {int(next_cycle / 60)} minutes",
            inline=True
        )
        
        memory = self.load_memory()
        embed.add_field(
            name="Total Actions Taken",
            value=str(len(memory.get("action_history", []))),
            inline=True
        )
        
        await ctx.reply(embed=embed)

    @commands.command(name="server_manager_pause")
    async def pause(self, ctx):
        """Pause autonomous operation."""
        if not self._is_authorized(ctx):
            return await ctx.reply("You are not authorized to use this command.")
        
        self.is_paused = True
        await ctx.reply("⏸️ Server manager paused. Use `!server_manager_resume` to resume.")

    @commands.command(name="server_manager_resume")
    async def resume(self, ctx):
        """Resume autonomous operation."""
        if not self._is_authorized(ctx):
            return await ctx.reply("You are not authorized to use this command.")
        
        self.is_paused = False
        await ctx.reply("▶️ Server manager resumed.")

    @commands.command(name="server_manager_force_cycle")
    async def force_cycle(self, ctx):
        """Trigger immediate decision cycle."""
        if not self._is_authorized(ctx):
            return await ctx.reply("You are not authorized to use this command.")
        
        await ctx.reply("🔄 Forcing decision cycle...")
        
        try:
            current_metrics = await self.collect_all_metrics()
            if not current_metrics:
                return await ctx.reply("❌ Failed to collect metrics.")
            
            memory = self.load_memory()
            self.update_historical_metrics(memory, current_metrics)
            
            decision = await self.make_decision(current_metrics, memory)
            
            if not decision:
                return await ctx.reply("❌ Failed to make decision.")
            
            execution_result = await self.execute_action(decision)
            
            action_record = {
                "timestamp": datetime.now().isoformat(),
                "action": decision.get("proposed_action"),
                "parameters": decision.get("parameters"),
                "result": "Success" if execution_result[0] else "Failed",
                "message": execution_result[1]
            }
            memory.setdefault("action_history", []).append(action_record)
            
            self.save_memory(memory)
            await self.log_decision_cycle(current_metrics, decision, execution_result)
            
            self.last_decision_time = datetime.now()
            
            status = "✅ Success" if execution_result[0] else "❌ Failed"
            await ctx.reply(f"{status}: {execution_result[1]}")
            
        except Exception as e:
            await ctx.reply(f"❌ Error: {str(e)}")


async def setup(bot):
    await bot.add_cog(ServerManager(bot))

