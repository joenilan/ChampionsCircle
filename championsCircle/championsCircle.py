import discord
from redbot.core import commands
import asyncio
import traceback

class ChampionsCircle(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.champions_channel = 1276624088848404490  # Replace with the actual channel ID
        self.champions_role_id = 1276625441779613863  # Replace with the actual role ID
        self.active_applications = []
        self.cancelled_applications = []
        self.approved_applications = []
        self.denied_applications = []
        self.champions_message_id = None
        self.admin_user_id = 131881984690487296  # Replace with the actual admin user ID

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
        view.add_item(CancelApplicationButton(self))
        
        embed = discord.Embed(title="Champions Circle Applications", description="Current applicants and their status.", color=0x00ff00)
        message = await ctx.send(embed=embed, view=view)
        self.champions_message_id = message.id
        await self.update_embed(ctx.guild)

        # Delete the command message
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            print("Failed to delete the setup command message.")

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
        if not self.active_applications:
            await ctx.send("There are no champions yet!")
            return

        embed = discord.Embed(title="Champions Circle", description="Our esteemed champions:", color=0x00ff00)
        for champion_id in self.active_applications:
            champion = ctx.guild.get_member(champion_id)
            if champion:
                embed.add_field(name=champion.name, value=f"ID: {champion.id}", inline=False)

        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def endtourney(self, ctx):
        """End the current tournament, clear the channel, and reset the cog's state."""
        if ctx.channel.id != self.champions_channel:
            await ctx.send("This command can only be used in the Champions Circle channel.")
            return

        # Ask for confirmation
        confirm_msg = await ctx.send("Are you sure you want to end the tournament? This will clear all messages and reset the application lists. Reply with 'yes' to confirm.")

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() == 'yes'

        try:
            await self.bot.wait_for('message', check=check, timeout=30.0)
        except asyncio.TimeoutError:
            await ctx.send("Tournament end cancelled.")
            return

        # Clear messages
        channel = ctx.channel
        await ctx.send("Ending tournament and clearing channel...")

        try:
            await channel.purge(limit=None)
        except discord.Forbidden:
            await ctx.send("I don't have permission to delete messages in this channel.")
            return
        except discord.HTTPException:
            await ctx.send("An error occurred while trying to delete messages.")
            return

        # Reset cog state
        self.active_applications = []
        self.cancelled_applications = []
        self.approved_applications = []
        self.denied_applications = []
        self.champions_message_id = None

        # Remove Champions role from all members
        guild = ctx.guild
        champions_role = guild.get_role(self.champions_role_id)
        if champions_role:
            for member in champions_role.members:
                try:
                    await member.remove_roles(champions_role)
                except discord.HTTPException:
                    print(f"Failed to remove Champions role from {member.name}")
        else:
            print(f"Champions role with ID {self.champions_role_id} not found.")

        # Send a temporary message that will be deleted after 10 seconds
        temp_msg = await channel.send("Tournament ended. Channel cleared and cog state reset. You can now use the setup_join_button command for a new tournament.", delete_after=10)

    async def update_embed(self, guild):
        embed = discord.Embed(title="Champions Circle Applications", description="Current applicants and their status.", color=0x00ff00)
        
        # Active Applications and Approved Applications side by side
        active_list = "\n".join([f"<@{user_id}>" for user_id in self.active_applications]) if self.active_applications else "No active applications"
        approved_list = "\n".join([f"<@{user_id}>" for user_id in self.approved_applications]) if self.approved_applications else "No approved applications"
        embed.add_field(name="Active Applications", value=active_list, inline=True)
        embed.add_field(name="Approved Applications", value=approved_list, inline=True)
        
        # Add a blank field to force the next row
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        
        # Denied Applications and Cancelled Applications side by side
        denied_list = "\n".join([f"<@{user_id}>" for user_id in self.denied_applications]) if self.denied_applications else "No denied applications"
        cancelled_list = "\n".join([f"<@{user_id}>" for user_id in self.cancelled_applications]) if self.cancelled_applications else "No cancelled applications"
        embed.add_field(name="Denied Applications", value=denied_list, inline=True)
        embed.add_field(name="Cancelled Applications", value=cancelled_list, inline=True)

        channel = self.bot.get_channel(self.champions_channel)
        if not channel:
            print(f"Error: Channel with ID {self.champions_channel} not found.")
            return

        try:
            if self.champions_message_id:
                message = await channel.fetch_message(self.champions_message_id)
                await message.edit(embed=embed)
            else:
                message = await channel.send(embed=embed)
                self.champions_message_id = message.id
        except discord.HTTPException as e:
            print(f"Error updating embed: {str(e)}")

    async def send_answers_to_admin(self, user, answers):
        admin_user = self.bot.get_user(self.admin_user_id)
        if not admin_user:
            print(f"Error: Admin user with ID {self.admin_user_id} not found.")
            return

        embed = discord.Embed(title=f"New Champion Application: {user.name}", color=0x00ff00)
        for question, answer in answers.items():
            embed.add_field(name=question, value=answer, inline=False)

        view = AdminResponseView(self, user.id)
        await admin_user.send(embed=embed, view=view)

    @commands.command()
    async def cancel_application(self, ctx):
        """Cancel your Champions Circle application."""
        if ctx.author.id in self.active_applications:
            self.active_applications.remove(ctx.author.id)
            self.cancelled_applications.append(ctx.author.id)
            await self.update_embed(ctx.guild)
            await ctx.send("Your Champions Circle application has been cancelled.", ephemeral=True)
        else:
            await ctx.send("You don't have an active Champions Circle application.", ephemeral=True)

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
        await self.cog.send_answers_to_admin(self.user, self.answers)
        if self.user.id not in self.cog.active_applications:
            self.cog.active_applications.append(self.user.id)
        if self.user.id in self.cog.cancelled_applications:
            self.cog.cancelled_applications.remove(self.user.id)
        await self.cog.update_embed(interaction.guild)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Your application has been cancelled.", ephemeral=True)
        if self.user.id in self.cog.active_applications:
            self.cog.active_applications.remove(self.user.id)
        if self.user.id not in self.cog.cancelled_applications:
            self.cog.cancelled_applications.append(self.user.id)
        await self.cog.update_embed(interaction.guild)
        self.stop()

class AdminResponseView(discord.ui.View):
    def __init__(self, cog, applicant_id):
        super().__init__()
        self.cog = cog
        self.applicant_id = applicant_id

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.active_applications.remove(self.applicant_id)
        self.cog.approved_applications.append(self.applicant_id)
        await self.cog.update_embed(interaction.guild)
        await interaction.response.send_message(f"Application for <@{self.applicant_id}> has been approved.")
        user = interaction.guild.get_member(self.applicant_id)
        if user:
            role = interaction.guild.get_role(self.cog.champions_role_id)
            if role:
                await user.add_roles(role)
                await user.send(f"Congratulations! Your application for the Champions Circle has been approved. You've been given the {role.name} role. Welcome to the Champions Circle!")
            else:
                print(f"Error: Champions role with ID {self.cog.champions_role_id} not found.")
                await user.send("Congratulations! Your application for the Champions Circle has been approved. However, there was an issue assigning the role. Please contact an administrator.")
        else:
            print(f"Error: User with ID {self.applicant_id} not found in the guild.")

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.red)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.active_applications.remove(self.applicant_id)
        self.cog.denied_applications.append(self.applicant_id)
        await self.cog.update_embed(interaction.guild)
        await interaction.response.send_message(f"Application for <@{self.applicant_id}> has been denied.")
        user = interaction.guild.get_member(self.applicant_id)
        if user:
            await user.send("We're sorry, but your application for the Champions Circle has been denied. If you have any questions about this decision, please contact an administrator.")
        else:
            print(f"Error: User with ID {self.applicant_id} not found in the guild.")

class JoinButton(discord.ui.Button):
    def __init__(self, cog):
        super().__init__(style=discord.ButtonStyle.green, label="Apply for Champions Circle", custom_id="join_champions")
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id in self.cog.active_applications:
            await interaction.response.send_message("You already have an active application for the Champions Circle.", ephemeral=True)
            return

        await interaction.response.send_message("Great! Let's start your application process.", ephemeral=True)
        view = QuestionnaireView(self.cog, interaction.user)
        await interaction.followup.send("Click the button below to start the questionnaire:", view=view, ephemeral=True)

class CancelApplicationButton(discord.ui.Button):
    def __init__(self, cog):
        super().__init__(style=discord.ButtonStyle.red, label="Cancel Application", custom_id="cancel_application")
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        if user_id in self.cog.active_applications:
            self.cog.active_applications.remove(user_id)
            self.cog.cancelled_applications.append(user_id)
            await interaction.response.send_message("Your active Champions Circle application has been cancelled.", ephemeral=True)
        elif user_id in self.cog.approved_applications:
            self.cog.approved_applications.remove(user_id)
            self.cog.cancelled_applications.append(user_id)
            # Remove the Champions role if it was assigned
            role = interaction.guild.get_role(self.cog.champions_role_id)
            if role and role in interaction.user.roles:
                await interaction.user.remove_roles(role)
            await interaction.response.send_message("Your approved Champions Circle application has been cancelled. The Champions role has been removed if it was assigned.", ephemeral=True)
        elif user_id in self.cog.denied_applications:
            self.cog.denied_applications.remove(user_id)
            self.cog.cancelled_applications.append(user_id)
            await interaction.response.send_message("Your denied Champions Circle application has been removed from the records.", ephemeral=True)
        elif user_id in self.cog.cancelled_applications:
            await interaction.response.send_message("You have already cancelled your Champions Circle application.", ephemeral=True)
        else:
            await interaction.response.send_message("You don't have an active Champions Circle application to cancel.", ephemeral=True)
        
        await self.cog.update_embed(interaction.guild)

async def setup(bot):
    await bot.add_cog(ChampionsCircle(bot))