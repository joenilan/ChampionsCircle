import discord
from redbot.core import commands
import asyncio
import traceback

class ChampionsCircle(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.champions_channel = 1276624088848404490  # Replace with the actual channel ID
        self.champions_role_id = 1276625441779613863  # Replace with the actual role ID
        self.champions_list = []
        self.champions_message_id = None  # This will store the ID of the champions list message
        self.admin_user_id = 131881984690487296  # Replace with the actual ID of the admin user

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"ChampionsCircle is ready!")

    @commands.command()
    async def setup_join_button(self, ctx):
        if ctx.channel.id != self.champions_channel:
            await ctx.send("This command can only be used in the Champions Circle channel.")
            return

        view = discord.ui.View(timeout=None)
        view.add_item(JoinButton(self))
        
        embed = discord.Embed(title="Champions Circle Application", description="Click the button below to apply for the Champions Circle!", color=0x00ff00)
        message = await ctx.send(embed=embed, view=view)
        self.champions_message_id = message.id

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

    @commands.command()
    async def list_champions(self, ctx):
        if not self.champions_list:
            await ctx.send("There are no champions yet!")
            return

        embed = discord.Embed(title="Champions Circle", description="Our esteemed champions:", color=0x00ff00)
        for champion_id in self.champions_list:
            champion = ctx.guild.get_member(champion_id)
            if champion:
                embed.add_field(name=champion.name, value=f"ID: {champion.id}", inline=False)

        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def clearall(self, ctx):
        """Clear all messages in the Champions Circle channel."""
        if ctx.channel.id != self.champions_channel:
            await ctx.send("This command can only be used in the Champions Circle channel.")
            return

        # Ask for confirmation
        confirm_msg = await ctx.send("Are you sure you want to clear all messages in this channel? This action cannot be undone. Reply with 'yes' to confirm.")

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() == 'yes'

        try:
            await self.bot.wait_for('message', check=check, timeout=30.0)
        except asyncio.TimeoutError:
            await ctx.send("Clearall command cancelled.")
            return

        # Clear messages
        channel = ctx.channel
        await ctx.send("Clearing all messages...")

        try:
            async for message in channel.history(limit=None):
                await message.delete()
        except discord.Forbidden:
            await ctx.send("I don't have permission to delete messages in this channel.")
        except discord.HTTPException:
            await ctx.send("An error occurred while trying to delete messages.")
        else:
            await ctx.send("All messages have been cleared from the Champions Circle channel.", delete_after=10)

    async def update_embed(self, guild):
        embed = discord.Embed(title="Champions Circle", description="A list of our esteemed champions.", color=0x00ff00)
        for champion_id in self.champions_list:
            champion = guild.get_member(champion_id)
            if champion:
                embed.add_field(name=f"{champion.name}", value=f"ID: {champion.id}", inline=False)

        channel = self.bot.get_channel(self.champions_channel)
        if not channel:
            print(f"Error: Channel with ID {self.champions_channel} not found.")
            return

        try:
            # Try to fetch the existing message
            message = await channel.fetch_message(self.champions_message_id)
            await message.edit(embed=embed)
        except discord.NotFound:
            # If the message doesn't exist, send a new one and store its ID
            message = await channel.send(embed=embed)
            self.champions_message_id = message.id
            # You might want to save this ID to a config or database so it persists across bot restarts
        except discord.HTTPException as e:
            print(f"Error updating embed: {str(e)}")

    @commands.command()
    async def cancel_application(self, ctx):
        """Cancel your Champions Circle application."""
        if ctx.author.id in self.champions_list:
            self.champions_list.remove(ctx.author.id)
            await self.update_embed(ctx.guild)
            await ctx.send("Your Champions Circle application has been cancelled.")
        else:
            await ctx.send("You don't have an active Champions Circle application.")

class JoinButton(discord.ui.Button):
    def __init__(self, cog):
        super().__init__(style=discord.ButtonStyle.green, label="Apply for Champions Circle", custom_id="join_champions")
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id in self.cog.champions_list:
            await interaction.response.send_message("You are already part of the Champions Circle.", ephemeral=True)
            return

        await interaction.response.send_message("Great! Let's start your application process.", ephemeral=True)
        view = QuestionnaireView(self.cog, interaction.user)
        await interaction.followup.send("Click the button below to start the questionnaire:", view=view, ephemeral=True)

class QuestionnaireView(discord.ui.View):
    def __init__(self, cog, user):
        super().__init__(timeout=600)  # 10 minutes timeout
        self.cog = cog
        self.user = user
        self.answers = {}

    @discord.ui.button(label="Start Questionnaire", style=discord.ButtonStyle.primary)
    async def start_questionnaire(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Great! I'll send you the questions in DMs. Please check your Direct Messages.", ephemeral=True)
        await self.ask_questions()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel_questionnaire(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Your application has been cancelled.", ephemeral=True)
        self.stop()

    async def ask_questions(self):
        questions = [
            "What's your favorite game?",
            "How long have you been playing games?",
            "What's your preferred gaming platform?",
            "Do you have any experience in tournaments?"
        ]

        for i, question in enumerate(questions, 1):
            await self.user.send(f"Question {i}: {question}")
            
            def check(m):
                return m.author == self.user and isinstance(m.channel, discord.DMChannel)

            try:
                answer = await self.cog.bot.wait_for('message', check=check, timeout=300)  # 5 minutes timeout per question
                self.answers[question] = answer.content
            except asyncio.TimeoutError:
                await self.user.send("You took too long to answer. The questionnaire has been cancelled.")
                return

        submit_view = SubmitView(self.cog, self.user, self.answers)
        await self.user.send("Thank you for answering the questions. Would you like to submit your answers?", view=submit_view)

class SubmitView(discord.ui.View):
    def __init__(self, cog, user, answers):
        super().__init__()
        self.cog = cog
        self.user = user
        self.answers = answers

    @discord.ui.button(label="Submit", style=discord.ButtonStyle.green)
    async def submit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Your answers have been submitted. Thank you!", ephemeral=True)
        await self.send_answers_to_admin()
        self.cog.champions_list.append(self.user.id)
        await self.cog.update_embed(interaction.guild)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Your application has been cancelled.", ephemeral=True)
        self.stop()

    async def send_answers_to_admin(self):
        admin_user = self.cog.bot.get_user(self.cog.admin_user_id)
        if not admin_user:
            print(f"Error: Admin user with ID {self.cog.admin_user_id} not found.")
            return

        embed = discord.Embed(title=f"New Champion Application: {self.user.name}", color=0x00ff00)
        for question, answer in self.answers.items():
            embed.add_field(name=question, value=answer, inline=False)

        await admin_user.send(embed=embed)

async def setup(bot):
    await bot.add_cog(ChampionsCircle(bot))