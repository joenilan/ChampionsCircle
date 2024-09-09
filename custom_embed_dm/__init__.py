from .custom_embed_dm import CustomEmbedDM

async def setup(bot):
    await bot.add_cog(CustomEmbedDM(bot))