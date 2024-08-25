import discord
from redbot.core import commands, Config
import asyncio
import logging
from datetime import datetime, timedelta

class ChampionsCircle(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890)
        default_guild = {
            "champions_channel": None,
            "champions_role_id": None,
            "active_applications": [],
            "cancelled_applications": [],
            "approved_applications": [],
            "denied_applications": [],
            "champions_message_id": None,
            "application_duration": 7  # days
        }
        self.config.register_guild(**default_guild)
        self.logger = logging.getLogger("red.championsCircle")
        self.admin_user_id = 131881984690487296  # Replace with the actual admin user ID
        self.application_cooldowns = commands.CooldownMapping.from_cooldown(1, 3600, commands.BucketType.user)

    def reset_cooldowns(self):
        self.application_cooldowns = commands.CooldownMapping.from_cooldown(1, 3600, commands.BucketType.user)

    @commands.Cog.listener()
    async def on_ready(self):
        self.logger.info(f"ChampionsCircle is ready!")
        self.bot.loop.create_task(self.close_expired_applications())

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def starttourney(self, ctx):
        """Start a new tournament and set up the join button for Champions Circle applications."""
        if ctx.channel.id != await self.config.guild(ctx.guild).champions_channel():
            await ctx.send("This command can only be used in the Champions Circle channel.")
            return

        view = discord.ui.View(timeout=None)
        view.add_item(JoinButton(self))
        view.add_item(CancelApplicationButton(self))
        
        embed = discord.Embed(title="Champions Circle Applications", description="Current applicants and their status.", color=0x00ff00)
        message = await ctx.send(embed=embed, view=view)
        await self.config.guild(ctx.guild).champions_message_id.set(message.id)
        await self.update_embed(ctx.guild)

        # Delete the command message
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            self.logger.error("Failed to delete the setup command message.")

        await ctx.send("New tournament started! The join button has been set up.", delete_after=10)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def test_role_assign(self, ctx, member: discord.Member):
        role = ctx.guild.get_role(await self.config.guild(ctx.guild).champions_role_id())
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
        active_applications = await self.config.guild(ctx.guild).active_applications()
        if not active_applications:
            await ctx.send("There are no champions yet!")
            return

        embed = discord.Embed(title="Champions Circle", description="Our esteemed champions:", color=0x00ff00)
        for champion_id in active_applications:
            champion = ctx.guild.get_member(champion_id)
            if champion:
                embed.add_field(name=champion.name, value=f"ID: {champion.id}", inline=False)

        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def clearall(self, ctx):
        """Clear all messages in the Champions Circle channel."""
        if ctx.channel.id != await self.config.guild(ctx.guild).champions_channel():
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

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def endtourney(self, ctx):
        """End the current tournament, clear the channel, and reset the cog's state."""
        if ctx.channel.id != await self.config.guild(ctx.guild).champions_channel():
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
        await self.config.guild(ctx.guild).active_applications.set([])
        await self.config.guild(ctx.guild).cancelled_applications.set([])
        await self.config.guild(ctx.guild).approved_applications.set([])
        await self.config.guild(ctx.guild).denied_applications.set([])
        await self.config.guild(ctx.guild).champions_message_id.set(None)

        # Reset cooldowns
        self.reset_cooldowns()

        # Remove Champions role from all members
        guild = ctx.guild
        champions_role = guild.get_role(await self.config.guild(ctx.guild).champions_role_id())
        if champions_role:
            for member in champions_role.members:
                try:
                    await member.remove_roles(champions_role)
                except discord.HTTPException:
                    self.logger.error(f"Failed to remove Champions role from {member.name}")
        else:
            self.logger.error(f"Champions role with ID {await self.config.guild(ctx.guild).champions_role_id()} not found.")

        # Send a temporary message that will be deleted after 10 seconds
        temp_msg = await channel.send("Tournament ended. Channel cleared, cog state reset, and application cooldowns reset. You can now use the starttourney command for a new tournament.", delete_after=10)

    async def update_embed(self, guild):
        embed = discord.Embed(title="Champions Circle Applications", description="Current applicants and their status.", color=0x00ff00)
        
        active_list = "\n".join([f"<@{app['user_id']}>" for app in await self.config.guild(guild).active_applications()]) or "No active applications"
        approved_list = "\n".join([f"<@{user_id}>" for user_id in await self.config.guild(guild).approved_applications()]) or "No approved applications"
        denied_list = "\n".join([f"<@{user_id}>" for user_id in await self.config.guild(guild).denied_applications()]) or "No denied applications"
        cancelled_list = "\n".join([f"<@{user_id}>" for user_id in await self.config.guild(guild).cancelled_applications()]) or "No cancelled applications"
        
        embed.add_field(name="Active Applications", value=active_list, inline=True)
        embed.add_field(name="Approved Applications", value=approved_list, inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)  # Empty field for spacing
        embed.add_field(name="Denied Applications", value=denied_list, inline=True)
        embed.add_field(name="Cancelled Applications", value=cancelled_list, inline=True)

        channel = self.bot.get_channel(await self.config.guild(guild).champions_channel())
        if not channel:
            self.logger.error(f"Error: Channel with ID {await self.config.guild(guild).champions_channel()} not found.")
            return

        try:
            if await self.config.guild(guild).champions_message_id():
                message = await channel.fetch_message(await self.config.guild(guild).champions_message_id())
                await message.edit(embed=embed)
            else:
                message = await channel.send(embed=embed)
                await self.config.guild(guild).champions_message_id.set(message.id)
        except discord.HTTPException as e:
            self.logger.error(f"Error updating embed: {str(e)}")

    async def send_answers_to_admin(self, user, answers):
        admin_user = self.bot.get_user(self.admin_user_id)
        if not admin_user:
            self.logger.error(f"Error: Admin user with ID {self.admin_user_id} not found.")
            return

        embed = discord.Embed(title=f"New Champion Application: {user.name}", color=0x00ff00)
        for question, answer in answers.items():
            embed.add_field(name=question, value=answer, inline=False)

        view = AdminResponseView(self, user.id, user.guild.id)
        await admin_user.send(embed=embed, view=view)

    @commands.command()
    async def cancel_application(self, ctx):
        """Cancel your Champions Circle application."""
        if ctx.author.id in await self.config.guild(ctx.guild).active_applications():
            active_applications = await self.config.guild(ctx.guild).active_applications()
            active_applications.remove(ctx.author.id)
            await self.config.guild(ctx.guild).active_applications.set(active_applications)
            cancelled_applications = await self.config.guild(ctx.guild).cancelled_applications()
            cancelled_applications.append(ctx.author.id)
            await self.config.guild(ctx.guild).cancelled_applications.set(cancelled_applications)
            await self.update_embed(ctx.guild)
            await ctx.send("Your Champions Circle application has been cancelled.", ephemeral=True)
        else:
            await ctx.send("You don't have an active Champions Circle application.", ephemeral=True)

    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def setchampionschannel(self, ctx, channel: discord.TextChannel):
        """Set the Champions Circle channel."""
        await self.config.guild(ctx.guild).champions_channel.set(channel.id)
        await ctx.send(f"Champions Circle channel set to {channel.mention}")

    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def setapplicationduration(self, ctx, days: int):
        """Set the duration for which applications remain open."""
        await self.config.guild(ctx.guild).application_duration.set(days)
        await ctx.send(f"Application duration set to {days} days.")

    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    async def setchampionsrole(self, ctx, role: discord.Role):
        """Set the Champions Circle role."""
        await self.config.guild(ctx.guild).champions_role_id.set(role.id)
        await ctx.send(f"Champions Circle role set to {role.name}")

    async def close_expired_applications(self):
        """Close applications that have expired."""
        while self == self.bot.get_cog("ChampionsCircle"):
            try:
                all_guilds = await self.config.all_guilds()
                for guild_id, guild_data in all_guilds.items():
                    guild = self.bot.get_guild(guild_id)
                    if not guild:
                        continue
                    
                    active_apps = guild_data["active_applications"]
                    for app in active_apps[:]:  # Create a copy of the list to iterate over
                        if "timestamp" in app and datetime.now() - datetime.fromtimestamp(app["timestamp"]) > timedelta(days=guild_data["application_duration"]):
                            active_apps.remove(app)
                            guild_data["cancelled_applications"].append(app)
                            user = guild.get_member(app["user_id"])
                            if user:
                                try:
                                    await user.send("Your Champions Circle application has expired.")
                                except discord.HTTPException:
                                    self.logger.error(f"Failed to send expiration message to user {user.id}")
                    
                    await self.config.guild(guild).active_applications.set(active_apps)
                    await self.config.guild(guild).cancelled_applications.set(guild_data["cancelled_applications"])
                    await self.update_embed(guild)
            except Exception as e:
                self.logger.error(f"Error in close_expired_applications: {str(e)}")
            
            await asyncio.sleep(3600)  # Check every hour

    @commands.command()
    async def cchelp(self, ctx):
        """Display help information for the Champions Circle cog."""
        embed = discord.Embed(title="Champions Circle Help", description="Commands and information for the Champions Circle cog", color=0x00ff00)
        
        # User commands
        embed.add_field(name="User Commands", value="\u200b", inline=False)
        embed.add_field(name="cancel_application", value="Cancel your active Champions Circle application", inline=False)
        embed.add_field(name="list_champions", value="List current champions", inline=False)
        
        # Admin commands
        embed.add_field(name="Admin Commands", value="\u200b", inline=False)
        embed.add_field(name="starttourney", value="Start a new tournament and set up the join button for Champions Circle applications", inline=False)
        embed.add_field(name="setchampionschannel", value="Set the Champions Circle channel", inline=False)
        embed.add_field(name="setapplicationduration", value="Set the duration for which applications remain open", inline=False)
        embed.add_field(name="setchampionsrole", value="Set the Champions Circle role", inline=False)
        embed.add_field(name="endtourney", value="End the current tournament and reset the cog", inline=False)
        embed.add_field(name="clearall", value="Clear all messages in the Champions Circle channel", inline=False)
        embed.add_field(name="test_role_assign", value="Test role assignment", inline=False)
        embed.add_field(name="championssettings", value="Display current settings for the Champions Circle cog", inline=False)

        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(administrator=True)
    async def championssettings(self, ctx):
        """Display current settings for the Champions Circle cog."""
        guild = ctx.guild
        settings = await self.config.guild(guild).all()

        embed = discord.Embed(title="Champions Circle Settings", color=0x00ff00)
        
        champions_channel = self.bot.get_channel(settings['champions_channel'])
        champions_role = guild.get_role(settings['champions_role_id'])
        
        embed.add_field(name="Champions Channel", value=champions_channel.mention if champions_channel else "Not set", inline=False)
        embed.add_field(name="Champions Role", value=champions_role.mention if champions_role else "Not set", inline=False)
        embed.add_field(name="Application Duration", value=f"{settings['application_duration']} days", inline=False)
        embed.add_field(name="Active Applications", value=len(settings['active_applications']), inline=True)
        embed.add_field(name="Approved Applications", value=len(settings['approved_applications']), inline=True)
        embed.add_field(name="Denied Applications", value=len(settings['denied_applications']), inline=True)
        embed.add_field(name="Cancelled Applications", value=len(settings['cancelled_applications']), inline=True)
        
        cooldown = self.application_cooldowns._cooldown
        embed.add_field(name="Application Cooldown", value=f"{cooldown.per} seconds", inline=False)

        await ctx.send(embed=embed)

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
            "Epic Account ID:",
            "Rank:",
            "Primary Platform (PC, Xbox, PlayStation, Switch):",
            "Preferred Region for Matches (NA East, NA West, EU, Other - please specify if Other):",
            "Have you read and understood the tournament rules? (Yes/No)",
            "Do you agree to follow the tournament code of conduct? (Yes/No)",
            "Any special requests or additional notes? (e.g., match scheduling preferences, etc)"
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

        submit_view = SubmitView(self.cog, self.user, self.answers, self.user.guild.id)
        await self.user.send("Thank you for answering the questions. Would you like to submit your answers?", view=submit_view)

class SubmitView(discord.ui.View):
    def __init__(self, cog, user, answers, guild_id):
        super().__init__()
        self.cog = cog
        self.user = user
        self.answers = answers
        self.guild_id = guild_id

    @discord.ui.button(label="Submit", style=discord.ButtonStyle.green)
    async def submit(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
            
            guild = self.cog.bot.get_guild(self.guild_id)
            if not guild:
                await interaction.followup.send("Error: Unable to find the guild. Please try again or contact an administrator.", ephemeral=True)
                return

            await self.cog.send_answers_to_admin(self.user, self.answers)
            active_applications = await self.cog.config.guild(guild).active_applications()
            if self.user.id not in [app["user_id"] for app in active_applications]:
                active_applications.append({"user_id": self.user.id, "timestamp": datetime.now().timestamp()})
                await self.cog.config.guild(guild).active_applications.set(active_applications)
            cancelled_applications = await self.cog.config.guild(guild).cancelled_applications()
            if self.user.id in cancelled_applications:
                cancelled_applications.remove(self.user.id)
                await self.cog.config.guild(guild).cancelled_applications.set(cancelled_applications)
            await self.cog.update_embed(guild)
            
            # Delete previous messages in DM
            async for message in self.user.dm_channel.history(limit=None):
                if message.author == self.cog.bot.user and message != interaction.message:
                    await message.delete()

            await interaction.followup.send("Your answers have been submitted. Thank you!", ephemeral=True)
        except Exception as e:
            self.cog.logger.error(f"Error in submit button: {str(e)}")
            await interaction.followup.send("An error occurred while submitting your application. Please try again or contact an administrator.", ephemeral=True)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Your application has been cancelled.", ephemeral=True)
        guild = self.cog.bot.get_guild(self.guild_id)
        if guild:
            active_applications = await self.cog.config.guild(guild).active_applications()
            active_applications = [app for app in active_applications if app["user_id"] != self.user.id]
            await self.cog.config.guild(guild).active_applications.set(active_applications)
            cancelled_applications = await self.cog.config.guild(guild).cancelled_applications()
            if self.user.id not in cancelled_applications:
                cancelled_applications.append(self.user.id)
                await self.cog.config.guild(guild).cancelled_applications.set(cancelled_applications)
            await self.cog.update_embed(guild)
        self.stop()

class AdminResponseView(discord.ui.View):
    def __init__(self, cog, applicant_id, guild_id):
        super().__init__()
        self.cog = cog
        self.applicant_id = applicant_id
        self.guild_id = guild_id

    async def remove_from_all_lists(self, guild):
        active_applications = await self.cog.config.guild(guild).active_applications()
        active_applications = [app for app in active_applications if app['user_id'] != self.applicant_id]
        await self.cog.config.guild(guild).active_applications.set(active_applications)

        for list_name in ['approved_applications', 'denied_applications', 'cancelled_applications']:
            current_list = await self.cog.config.guild(guild).get_raw(list_name)
            current_list = [user_id for user_id in current_list if user_id != self.applicant_id]
            await self.cog.config.guild(guild).set_raw(list_name, value=current_list)

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer()
            
            guild = self.cog.bot.get_guild(self.guild_id)
            if not guild:
                await interaction.followup.send("Error: Unable to find the guild. Please try again or contact an administrator.")
                return

            await self.remove_from_all_lists(guild)
            
            approved_applications = await self.cog.config.guild(guild).approved_applications()
            if self.applicant_id not in approved_applications:
                approved_applications.append(self.applicant_id)
                await self.cog.config.guild(guild).approved_applications.set(approved_applications)
            
            await self.cog.update_embed(guild)
            
            await interaction.followup.send(f"Application for <@{self.applicant_id}> has been approved.")
            
            user = guild.get_member(self.applicant_id)
            if user:
                role = guild.get_role(await self.cog.config.guild(guild).champions_role_id())
                if role:
                    await user.add_roles(role)
                    await user.send(f"Congratulations! Your application for the Champions Circle has been approved. You've been given the {role.name} role. Welcome to the Champions Circle!")
                else:
                    self.cog.logger.error(f"Error: Champions role with ID {await self.cog.config.guild(guild).champions_role_id()} not found.")
                    await user.send("Congratulations! Your application for the Champions Circle has been approved. However, there was an issue assigning the role. Please contact an administrator.")
            else:
                self.cog.logger.error(f"Error: User with ID {self.applicant_id} not found in the guild.")
        except Exception as e:
            self.cog.logger.error(f"Error in approve button: {str(e)}")
            await interaction.followup.send("An error occurred while processing the approval. Please try again or contact the bot administrator.")

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.red)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer()
            
            guild = self.cog.bot.get_guild(self.guild_id)
            if not guild:
                await interaction.followup.send("Error: Unable to find the guild. Please try again or contact an administrator.")
                return

            await self.remove_from_all_lists(guild)
            
            denied_applications = await self.cog.config.guild(guild).denied_applications()
            if self.applicant_id not in denied_applications:
                denied_applications.append(self.applicant_id)
                await self.cog.config.guild(guild).denied_applications.set(denied_applications)
            
            await self.cog.update_embed(guild)
            
            await interaction.followup.send(f"Application for <@{self.applicant_id}> has been denied.")
            
            user = guild.get_member(self.applicant_id)
            if user:
                await user.send("We're sorry, but your application for the Champions Circle has been denied. If you have any questions about this decision, please contact an administrator.")
            else:
                self.cog.logger.error(f"Error: User with ID {self.applicant_id} not found in the guild.")
        except Exception as e:
            self.cog.logger.error(f"Error in deny button: {str(e)}")
            await interaction.followup.send("An error occurred while processing the denial. Please try again or contact the bot administrator.")

class JoinButton(discord.ui.Button):
    def __init__(self, cog):
        super().__init__(style=discord.ButtonStyle.green, label="Apply for Champions Circle", custom_id="join_champions")
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        bucket = self.cog.application_cooldowns.get_bucket(interaction.message)
        retry_after = bucket.update_rate_limit()
        if retry_after:
            minutes, seconds = divmod(int(retry_after), 60)
            await interaction.response.send_message(f"You can apply again in {minutes} minutes and {seconds} seconds.", ephemeral=True)
            return

        if interaction.user.id in [app['user_id'] for app in await self.cog.config.guild(interaction.guild).active_applications()]:
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
        active_applications = await self.cog.config.guild(interaction.guild).active_applications()
        if user_id in active_applications:
            active_applications = [app for app in active_applications if app["user_id"] != user_id]
            cancelled_applications = await self.cog.config.guild(interaction.guild).cancelled_applications()
            cancelled_applications.append(user_id)
            await self.cog.config.guild(interaction.guild).active_applications.set(active_applications)
            await self.cog.config.guild(interaction.guild).cancelled_applications.set(cancelled_applications)
            await interaction.response.send_message("Your active Champions Circle application has been cancelled.", ephemeral=True)
        elif user_id in await self.cog.config.guild(interaction.guild).approved_applications():
            approved_applications = await self.cog.config.guild(interaction.guild).approved_applications()
            approved_applications.remove(user_id)
            cancelled_applications = await self.cog.config.guild(interaction.guild).cancelled_applications()
            cancelled_applications.append(user_id)
            await self.cog.config.guild(interaction.guild).approved_applications.set(approved_applications)
            await self.cog.config.guild(interaction.guild).cancelled_applications.set(cancelled_applications)
            # Remove the Champions role if it was assigned
            role = interaction.guild.get_role(await self.cog.config.guild(interaction.guild).champions_role_id())
            if role and role in interaction.user.roles:
                await interaction.user.remove_roles(role)
            await interaction.response.send_message("Your approved Champions Circle application has been cancelled. The Champions role has been removed if it was assigned.", ephemeral=True)
        elif user_id in await self.cog.config.guild(interaction.guild).denied_applications():
            denied_applications = await self.cog.config.guild(interaction.guild).denied_applications()
            denied_applications.remove(user_id)
            cancelled_applications = await self.cog.config.guild(interaction.guild).cancelled_applications()
            cancelled_applications.append(user_id)
            await self.cog.config.guild(interaction.guild).denied_applications.set(denied_applications)
            await self.cog.config.guild(interaction.guild).cancelled_applications.set(cancelled_applications)
            await interaction.response.send_message("Your denied Champions Circle application has been removed from the records.", ephemeral=True)
        elif user_id in await self.cog.config.guild(interaction.guild).cancelled_applications():
            await interaction.response.send_message("You have already cancelled your Champions Circle application.", ephemeral=True)
        else:
            await interaction.response.send_message("You don't have an active Champions Circle application to cancel.", ephemeral=True)
        
        await self.cog.update_embed(interaction.guild)

async def setup(bot):
    cog = ChampionsCircle(bot)
    await bot.add_cog(cog)
    bot.loop.create_task(cog.close_expired_applications())