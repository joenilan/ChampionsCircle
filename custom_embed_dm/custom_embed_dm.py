import discord
from redbot.core import commands, Config
from typing import Optional

class CustomEmbedDM(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        default_guild = {
            "embed_title": "Default Title",
            "embed_description": "Default Description",
            "embed_color": 0x000000,
            "embed_image_url": None
        }
        self.config.register_guild(**default_guild)

    @commands.group()
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def embedconfig(self, ctx):
        """Configure the custom embed for DMs."""
        pass

    @embedconfig.command(name="title")
    async def set_title(self, ctx, *, title: str):
        """Set the embed title."""
        await self.config.guild(ctx.guild).embed_title.set(title)
        await ctx.send(f"Embed title set to: {title}")

    @embedconfig.command(name="description")
    async def set_description(self, ctx, *, description: str):
        """Set the embed description."""
        await self.config.guild(ctx.guild).embed_description.set(description)
        await ctx.send(f"Embed description set to: {description}")

    @embedconfig.command(name="color")
    async def set_color(self, ctx, color: discord.Color):
        """Set the embed color."""
        await self.config.guild(ctx.guild).embed_color.set(color.value)
        await ctx.send(f"Embed color set to: {color}")

    @embedconfig.command(name="image")
    async def set_image(self, ctx, image_url: str):
        """Set the embed image URL."""
        await self.config.guild(ctx.guild).embed_image_url.set(image_url)
        await ctx.send(f"Embed image URL set to: {image_url}")

    @commands.command()
    @commands.guild_only()
    async def sendembed(self, ctx, user: discord.Member, *, content: str):
        """Send a customized embed to a user via DM.
        Format: Title | Description | Image URL | Message
        Use 'default' for any field to use the configured value.
        Attach an image to override the Image URL field."""
        guild_config = self.config.guild(ctx.guild)
        
        # Split the content into parts
        parts = [part.strip() for part in content.split('|', 3)]
        while len(parts) < 4:
            parts.append('default')
        
        title, description, image_url, message = parts
        
        # Use configured values for 'default' fields
        if title == 'default':
            title = await guild_config.embed_title()
        if description == 'default':
            description = await guild_config.embed_description()
        if image_url == 'default':
            image_url = await guild_config.embed_image_url()
        
        embed = discord.Embed(
            title=title,
            description=description,
            color=await guild_config.embed_color()
        )
        
        # Handle image
        if ctx.message.attachments:
            attachment = ctx.message.attachments[0]
            if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                embed.set_image(url=attachment.url)
            else:
                await ctx.send("The attached file is not a supported image format. Using the provided or configured image URL instead.")
                if image_url:
                    embed.set_image(url=image_url)
        elif image_url and image_url != 'default':
            embed.set_image(url=image_url)
        
        # Add message field if provided
        if message and message != 'default':
            embed.add_field(name="Additional Message", value=message, inline=False)

        try:
            await user.send(embed=embed)
            await ctx.send(f"Customized embed sent to {user.mention} via DM.")
        except discord.Forbidden:
            await ctx.send(f"I couldn't send a DM to {user.mention}. They might have DMs disabled.")