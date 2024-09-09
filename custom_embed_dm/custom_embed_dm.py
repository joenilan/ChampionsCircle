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
        Format: Title | Description | [Custom message] | [IMAGE]
        Use 'default' for title or description to use the configured value.
        Place IMAGE where you want the image to appear in the embed.
        Attach an image or use a URL in place of IMAGE."""
        guild_config = self.config.guild(ctx.guild)
        
        # Split the content into parts
        parts = [part.strip() for part in content.split('|')]
        
        title = parts[0] if parts else 'default'
        description = parts[1] if len(parts) > 1 else 'default'
        
        # Use configured values for 'default' fields
        if title == 'default':
            title = await guild_config.embed_title()
        if description == 'default':
            description = await guild_config.embed_description()
        
        embed = discord.Embed(
            title=title,
            description=description,
            color=await guild_config.embed_color()
        )
        
        # Prepare image URL
        image_url = None
        if ctx.message.attachments:
            attachment = ctx.message.attachments[0]
            if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                image_url = attachment.url
            else:
                await ctx.send("The attached file is not a supported image format.")
        
        # Process the remaining parts
        additional_message = ""
        for part in parts[2:]:
            if part.upper() == 'IMAGE':
                if image_url:
                    embed.set_image(url=image_url)
                elif await guild_config.embed_image_url():
                    embed.set_image(url=await guild_config.embed_image_url())
            elif part.startswith('http') and not image_url:
                embed.set_image(url=part)
            else:
                additional_message += part + "\n"
        
        # Add the additional message after processing all parts
        if additional_message:
            embed.add_field(name="Additional Message", value=additional_message.strip(), inline=False)

        try:
            await user.send(embed=embed)
            await ctx.send(f"Customized embed sent to {user.mention} via DM.")
        except discord.Forbidden:
            await ctx.send(f"I couldn't send a DM to {user.mention}. They might have DMs disabled.")