from .daypass import DayPass

async def setup(bot):
    await bot.add_cog(DayPass(bot))