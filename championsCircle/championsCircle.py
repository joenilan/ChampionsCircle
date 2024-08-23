import discord
from redbot.core import commands

class ChampionsCircle(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.champions_channel = 1276624088848404490  # Replace with the actual channel ID
        self.champions_role_id = 1276625441779613863  # Replace with the actual role ID
        self.champions_list = []

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"ChampionsCircle is ready!")

    @app_commands.command()
    async def setup_join_button(self, interaction: discord.Interaction):
        if interaction.channel_id != self.champions_channel:
            await interaction.response.send_message("This command can only be used in the Champions Circle channel.", ephemeral=True)
            return

        join_button = discord.ui.Button(label="Join the Champions Circle", style=discord.ButtonStyle.green, custom_id="join_champions")
        view = discord.ui.View()
        view.add_item(join_button)

        await interaction.response.send_message("Click the button to join the Champions Circle!", view=view)

    @discord.ui.button(custom_id="join_champions")
    async def join_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.champions_list:
            await interaction.response.send_message("You are already part of the Champions Circle.", ephemeral=True)
            return

        champions_role = interaction.guild.get_role(self.champions_role_id)
        if champions_role is None:
            await interaction.response.send_message("Error: Champions role not found.", ephemeral=True)
            return

        try:
            await interaction.user.add_roles(champions_role)
            self.champions_list.append(interaction.user.id)
            await self.update_embed(interaction)
            await interaction.response.send_message(f"Welcome to the Champions Circle! You've been given the {champions_role.name} role.", ephemeral=True)
        except discord.Forbidden:
            await interaction.response.send_message("Error: I don't have permission to assign roles.", ephemeral=True)
        except discord.HTTPException:
            await interaction.response.send_message("An error occurred while assigning the role. Please try again later.", ephemeral=True)

    async def update_embed(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Champions Circle", description="A list of our esteemed champions.", color=0x00ff00)
        for champion_id in self.champions_list:
            champion = await interaction.guild.fetch_member(champion_id)
            embed.add_field(name=f"{champion.name}", value=f"ID: {champion.id}", inline=False)

        channel = self.bot.get_channel(self.champions_channel)
        message = await channel.fetch_message(1234567890)  # Replace with the actual message ID
        await message.edit(embed=embed)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def test_role_assign(self, ctx, member: discord.Member):
        role = ctx.guild.get_role(self.champions_role_id)
        if role is None:
            await ctx.send("Error: Champions role not found.")
            return
        try:
            await member.add_roles(role)
            await ctx.send(f"Successfully assigned {role.name} to {member.name}")
        except discord.Forbidden:
            await ctx.send("Error: I don't have permission to assign roles.")
        except discord.HTTPException as e:
            await ctx.send(f"An error occurred: {str(e)}")

def setup(bot):
    bot.add_cog(ChampionsCircle(bot))