import discord
from discord.ext import commands
from discord import Embed

class CustomEmbedDM(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def dm(self, ctx, user: discord.User, *, content: str):
        """
        Send a custom embed to a user via DM.
        Usage: !dm @user Title | Content
        To add an image, attach it to your message.
        """
        # Split content into title and body
        parts = content.split('|', 1)
        title = parts[0].strip()
        body = parts[1].strip() if len(parts) > 1 else ""

        # Create the embed
        embed = Embed(title=title, description=body, color=discord.Color.blue())

        # Check for attached image
        if ctx.message.attachments:
            image = ctx.message.attachments[0]
            embed.set_image(url=image.url)

        try:
            await user.send(embed=embed)
            await ctx.send(f"Embed sent to {user.name} via DM.")
        except discord.Forbidden:
            await ctx.send(f"Unable to send DM to {user.name}. They may have DMs disabled.")

async def setup(bot):
    await bot.add_cog(CustomEmbedDM(bot))