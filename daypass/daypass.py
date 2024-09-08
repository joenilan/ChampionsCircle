import discord
from redbot.core import commands, Config
from discord.ext.commands import guild_only
import asyncio
from datetime import datetime, timedelta
import re

class DayPass(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_guild = {
            "daypass_role_id": None,
            "daypass_channel_id": None,
            "active_passes": {}
        }
        self.config.register_guild(**default_guild)

    @commands.group()
    @commands.admin_or_permissions(administrator=True)
    @guild_only()
    async def daypass(self, ctx):
        """Manage the DayPass system."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @daypass.command(name="setrole")
    async def set_daypass_role(self, ctx, role_id: int):
        """Set the role to be used for DayPass using its ID."""
        role = ctx.guild.get_role(role_id)
        if not role:
            await ctx.send(f"No role found with ID {role_id}. Please check the ID and try again.")
            return
        await self.config.guild(ctx.guild).daypass_role_id.set(role_id)
        await ctx.send(f"DayPass role set to {role.name} (ID: {role_id})")

    @daypass.command(name="setchannel")
    async def set_daypass_channel(self, ctx, channel_id: int):
        """Set the channel to be used for DayPass using its ID."""
        channel = ctx.guild.get_channel(channel_id)
        if not channel:
            await ctx.send(f"No channel found with ID {channel_id}. Please check the ID and try again.")
            return
        await self.config.guild(ctx.guild).daypass_channel_id.set(channel_id)
        await ctx.send(f"DayPass channel set to {channel.name} (ID: {channel_id})")

    @daypass.command(name="grant")
    async def grant_daypass(self, ctx, member: discord.Member, *, duration: str):
        """
        Grant a DayPass to a user for a specified duration.
        Use format: 1d2h3m4s for 1 day, 2 hours, 3 minutes, and 4 seconds.
        """
        duration_seconds = self.parse_duration(duration)
        if duration_seconds == 0:
            await ctx.send("Invalid duration format. Use combinations like 1d, 2h, 30m, 45s.")
            return

        role_id = await self.config.guild(ctx.guild).daypass_role_id()
        channel_id = await self.config.guild(ctx.guild).daypass_channel_id()

        if not role_id or not channel_id:
            await ctx.send("DayPass role or channel has not been set. Please set them first.")
            return

        role = ctx.guild.get_role(role_id)
        channel = ctx.guild.get_channel(channel_id)

        if not role or not channel:
            await ctx.send("DayPass role or channel not found. Please check the settings.")
            return

        await member.add_roles(role)
        expiry_time = datetime.utcnow() + timedelta(seconds=duration_seconds)

        async with self.config.guild(ctx.guild).active_passes() as active_passes:
            active_passes[str(member.id)] = expiry_time.timestamp()

        duration_str = self.format_duration(duration_seconds)
        await ctx.send(f"DayPass granted to {member.mention} for {duration_str}.")
        self.bot.loop.create_task(self.remove_daypass(ctx.guild, member, role, channel, duration_seconds))

    def parse_duration(self, duration_str):
        """Parse a duration string into seconds."""
        units = {
            's': 1,
            'm': 60,
            'h': 3600,
            'd': 86400
        }
        pattern = re.compile(r'(\d+)([smhd])')
        matches = pattern.findall(duration_str.lower())
        total_seconds = 0
        for value, unit in matches:
            total_seconds += int(value) * units[unit]
        return total_seconds

    def format_duration(self, seconds):
        """Format a duration in seconds to a human-readable string."""
        days, remainder = divmod(seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if seconds > 0 or not parts:
            parts.append(f"{seconds}s")
        return " ".join(parts)

    async def remove_daypass(self, guild, member, role, channel, duration_seconds):
        await asyncio.sleep(duration_seconds)
        if role in member.roles:
            await member.remove_roles(role)
            await channel.send(f"{member.mention}'s DayPass has expired.")

        async with self.config.guild(guild).active_passes() as active_passes:
            active_passes.pop(str(member.id), None)

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if before.guild != after.guild:
            return

        role_id = await self.config.guild(after.guild).daypass_role_id()
        channel_id = await self.config.guild(after.guild).daypass_channel_id()

        if not role_id or not channel_id:
            return

        role = after.guild.get_role(role_id)
        channel = after.guild.get_channel(channel_id)

        if not role or not channel:
            return

        if role in before.roles and role not in after.roles:
            async with self.config.guild(after.guild).active_passes() as active_passes:
                active_passes.pop(str(after.id), None)
            await channel.send(f"{after.mention}'s DayPass has been manually removed.")

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        async with self.config.guild(member.guild).active_passes() as active_passes:
            if str(member.id) in active_passes:
                del active_passes[str(member.id)]

    @daypass.command(name="list")
    async def list_active_passes(self, ctx):
        """List all active DayPasses."""
        active_passes = await self.config.guild(ctx.guild).active_passes()
        if not active_passes:
            await ctx.send("There are no active DayPasses.")
            return

        embed = discord.Embed(title="Active DayPasses", color=discord.Color.blue())
        for user_id, expiry_timestamp in active_passes.items():
            user = ctx.guild.get_member(int(user_id))
            if user:
                expiry_time = datetime.fromtimestamp(expiry_timestamp)
                embed.add_field(name=user.name, value=f"Expires: {expiry_time.strftime('%Y-%m-%d %H:%M:%S UTC')}", inline=False)

        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.loop.create_task(self.check_expired_passes())

    async def check_expired_passes(self):
        while self == self.bot.get_cog("DayPass"):
            for guild in self.bot.guilds:
                role_id = await self.config.guild(guild).daypass_role_id()
                channel_id = await self.config.guild(guild).daypass_channel_id()
                role = guild.get_role(role_id)
                channel = guild.get_channel(channel_id)

                if not role or not channel:
                    continue

                async with self.config.guild(guild).active_passes() as active_passes:
                    current_time = datetime.utcnow().timestamp()
                    expired_passes = [user_id for user_id, expiry_time in active_passes.items() if expiry_time <= current_time]

                    for user_id in expired_passes:
                        member = guild.get_member(int(user_id))
                        if member and role in member.roles:
                            await member.remove_roles(role)
                            await channel.send(f"{member.mention}'s DayPass has expired.")
                        del active_passes[user_id]

            await asyncio.sleep(60)  # Check every minute

async def setup(bot):
    await bot.add_cog(DayPass(bot))