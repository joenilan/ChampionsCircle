import discord
from redbot.core import commands, Config
from discord.ext.commands import guild_only
import asyncio
import logging
from datetime import datetime, timedelta, timezone

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
            "application_duration": 7,  # days
            "custom_questions": [
                "Epic Account ID:",
                "Rank:",
                "Primary Platform (PC, Xbox, PlayStation, Switch):",
                "Preferred Region for Matches (NA East, NA West, EU, Other - please specify if Other):",
                "RL Tracker Link:",
                "Have you read and understood the tournament rules? (Yes/No)",
                "Do you agree to follow the tournament code of conduct? (Yes/No)",
                "Any special requests or additional notes? (e.g., match scheduling preferences, etc)"
            ],
            "tourney_title": "Champions Circle Tournament",
            "tourney_description": "Join our exciting tournament!",
            "tourney_time": None,  # We'll store this as a UTC timestamp
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
    @guild_only()
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
    @guild_only()
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
    @guild_only()
    async def list_champions(self, ctx):
        approved_applications = await self.config.guild(ctx.guild).approved_applications()
        if not approved_applications:
            await ctx.send("There are no champions yet!")
            return

        embed = discord.Embed(title="Champions Circle", description="Our esteemed champions:", color=0x00ff00)
        for application in approved_applications:
            champion_id = application['user_id']
            champion = ctx.guild.get_member(champion_id)
            if champion:
                rank = application['answers'].get('Rank:', 'Unranked')
                tracker_link = application['answers'].get('RL Tracker Link:', 'Not provided')
                value = f"Rank: [{rank}]({tracker_link})" if tracker_link != 'Not provided' else f"Rank: {rank}"
                embed.add_field(name=champion.name, value=value, inline=False)

        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(administrator=True)
    @guild_only()
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
    @guild_only()
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
        tourney_title = await self.config.guild(guild).tourney_title()
        embed = discord.Embed(title=tourney_title, color=0x00ff00)
        
        # Add tournament details
        tourney_description = await self.config.guild(guild).tourney_description()
        tourney_time = await self.config.guild(guild).tourney_time()
        
        embed.add_field(name="Description", value=tourney_description, inline=False)
        
        if tourney_time:
            embed.add_field(name="Time", value=f"<t:{tourney_time}:F>", inline=False)
        else:
            embed.add_field(name="Time", value="Not set", inline=False)
        
        async def format_user_entry(application):
            user_id = application['user_id']
            user = guild.get_member(user_id)
            if not user:
                return f"<@{user_id}> (User left server)"
            
            rank = "Unranked"
            tracker_link = ""
            if 'answers' in application:
                questions = await self.config.guild(guild).custom_questions()
                rank_question = next((q for q in questions if q.lower().startswith("rank")), None)
                tracker_question = next((q for q in questions if "tracker" in q.lower()), None)
                
                if rank_question and rank_question in application['answers']:
                    rank = application['answers'][rank_question]
                if tracker_question and tracker_question in application['answers']:
                    tracker_link = application['answers'][tracker_question]
            
            if tracker_link:
                return f"<@{user_id}> - [{rank}]({tracker_link})"
            else:
                return f"<@{user_id}> - {rank}"

        active_applications = await self.config.guild(guild).active_applications()
        active_list = "\n".join([await format_user_entry(app) for app in active_applications]) or "No active applications"
        
        approved_applications = await self.config.guild(guild).approved_applications()
        approved_list = "\n".join([await format_user_entry(app) for app in approved_applications]) or "No approved applications"
        
        denied_applications = await self.config.guild(guild).denied_applications()
        denied_list = "\n".join([await format_user_entry(app) for app in denied_applications]) or "No denied applications"
        
        cancelled_applications = await self.config.guild(guild).cancelled_applications()
        cancelled_list = "\n".join([await format_user_entry(app) for app in cancelled_applications]) or "No cancelled applications"
        
        embed.add_field(name="🟦 Active Applications", value=active_list, inline=False)
        embed.add_field(name="🟩 Approved Applications", value=approved_list, inline=False)
        embed.add_field(name="🟥 Denied Applications", value=denied_list, inline=False)
        embed.add_field(name="🟨 Cancelled Applications", value=cancelled_list, inline=False)

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
    @guild_only()
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
    @guild_only()
    async def setchampionschannel(self, ctx, channel: discord.TextChannel):
        """Set the Champions Circle channel."""
        await self.config.guild(ctx.guild).champions_channel.set(channel.id)
        await ctx.send(f"Champions Circle channel set to {channel.mention}")

    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    @guild_only()
    async def setapplicationduration(self, ctx, days: int):
        """Set the duration for which applications remain open."""
        await self.config.guild(ctx.guild).application_duration.set(days)
        await ctx.send(f"Application duration set to {days} days.")

    @commands.command()
    @commands.admin_or_permissions(administrator=True)
    @guild_only()
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
        """Display help for Champions Circle commands."""
        embed = discord.Embed(title="Champions Circle Help", color=0x00ff00)
        
        # General commands
        embed.add_field(name="General Commands", value="\u200b", inline=False)
        embed.add_field(name="cchelp", value="Display this help message", inline=False)
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

        # Tournament management commands
        embed.add_field(name="Tournament Management", value="\u200b", inline=False)
        embed.add_field(name="tourney settitle", value="Set the tournament title", inline=False)
        embed.add_field(name="tourney setdescription", value="Set the tournament description", inline=False)
        embed.add_field(name="tourney settime", value="Set the tournament time (format: YYYY-MM-DD HH:MM)", inline=False)

        # Question management commands
        embed.add_field(name="Question Management", value="\u200b", inline=False)
        embed.add_field(name="questions add", value="Add a custom question to the Champions Circle application", inline=False)
        embed.add_field(name="questions remove", value="Remove a custom question from the Champions Circle application", inline=False)
        embed.add_field(name="questions list", value="List all custom questions for the Champions Circle application", inline=False)

        await ctx.send(embed=embed)

    @commands.command()
    @commands.has_permissions(administrator=True)
    @guild_only()
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
        embed.add_field(name="Tournament Title", value=settings['tourney_title'], inline=False)
        embed.add_field(name="Tournament Description", value=settings['tourney_description'], inline=False)
        
        if settings['tourney_time']:
            embed.add_field(name="Tournament Time", value=f"<t:{settings['tourney_time']}:F>", inline=False)
        else:
            embed.add_field(name="Tournament Time", value="Not set", inline=False)
        
        embed.add_field(name="Active Applications", value=len(settings['active_applications']), inline=True)
        embed.add_field(name="Approved Applications", value=len(settings['approved_applications']), inline=True)
        embed.add_field(name="Denied Applications", value=len(settings['denied_applications']), inline=True)
        embed.add_field(name="Cancelled Applications", value=len(settings['cancelled_applications']), inline=True)
        
        cooldown = self.application_cooldowns._cooldown
        embed.add_field(name="Application Cooldown", value=f"{cooldown.per} seconds", inline=False)

        await ctx.send(embed=embed)

    @commands.group()
    @commands.admin_or_permissions(administrator=True)
    @guild_only()
    async def questions(self, ctx):
        """Manage custom questions for the Champions Circle application."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @questions.command(name="add")
    @guild_only()
    async def add_question(self, ctx, *, question: str):
        """Add a custom question to the Champions Circle application."""
        async with self.config.guild(ctx.guild).custom_questions() as questions:
            questions.append(question)
        await ctx.send(f"Question added: {question}")

    @questions.command(name="remove")
    @guild_only()
    async def remove_question(self, ctx, index: int):
        """Remove a custom question from the Champions Circle application."""
        async with self.config.guild(ctx.guild).custom_questions() as questions:
            if 1 <= index <= len(questions):
                removed_question = questions.pop(index - 1)
                await ctx.send(f"Question removed: {removed_question}")
            else:
                await ctx.send("Invalid question index.")

    @questions.command(name="list")
    @guild_only()
    async def list_questions(self, ctx):
        """List all custom questions for the Champions Circle application."""
        try:
            questions = await self.config.guild(ctx.guild).custom_questions()
            if questions:
                question_list = "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))
                await ctx.send(f"Current custom questions:\n{question_list}")
            else:
                await ctx.send("No custom questions set.")
        except AttributeError:
            await ctx.send("This command can only be used in a server.")

    @commands.group()
    @commands.admin_or_permissions(administrator=True)
    @guild_only()
    async def tourney(self, ctx):
        """Manage tournament details."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help(ctx.command)

    @tourney.command(name="settitle")
    async def set_tourney_title(self, ctx, *, title: str):
        """Set the tournament title."""
        await self.config.guild(ctx.guild).tourney_title.set(title)
        await ctx.send(f"Tournament title set to: {title}")
        await self.update_embed(ctx.guild)

    @tourney.command(name="setdescription")
    async def set_tourney_description(self, ctx, *, description: str):
        """Set the tournament description."""
        await self.config.guild(ctx.guild).tourney_description.set(description)
        await ctx.send(f"Tournament description set to: {description}")
        await self.update_embed(ctx.guild)

    @tourney.command(name="settime")
    async def set_tourney_time(self, ctx, *, time: str):
        """Set the tournament time (format: YYYY-MM-DD HH:MM)."""
        try:
            tourney_time = datetime.strptime(time, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
            timestamp = int(tourney_time.timestamp())
            await self.config.guild(ctx.guild).tourney_time.set(timestamp)
            await ctx.send(f"Tournament time set to: <t:{timestamp}:F>")
            await self.update_embed(ctx.guild)
        except ValueError:
            await ctx.send("Invalid time format. Please use YYYY-MM-DD HH:MM")

    @tourney.command(name="help")
    async def tourney_help(self, ctx):
        """Display help for tourney commands."""
        embed = discord.Embed(title="Tournament Management Commands", color=0x00ff00)
        embed.add_field(name="tourney settitle", value="Set the tournament title", inline=False)
        embed.add_field(name="tourney setdescription", value="Set the tournament description", inline=False)
        embed.add_field(name="tourney settime", value="Set the tournament time (format: YYYY-MM-DD HH:MM)", inline=False)
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
        questions = await self.cog.config.guild(self.user.guild).custom_questions()

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
                active_applications.append({
                    "user_id": self.user.id,
                    "timestamp": datetime.now().timestamp(),
                    "answers": self.answers  # Store the answers
                })
                await self.cog.config.guild(guild).active_applications.set(active_applications)
            cancelled_applications = await self.cog.config.guild(guild).cancelled_applications()
            if self.user.id in cancelled_applications:
                cancelled_applications.remove(self.user.id)
                await self.cog.config.guild(guild).cancelled_applications.set(cancelled_applications)
            await self.cog.update_embed(guild)
            
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

    async def move_application(self, guild, target_list):
        for list_name in ['active_applications', 'approved_applications', 'denied_applications', 'cancelled_applications']:
            current_list = await self.cog.config.guild(guild).get_raw(list_name)
            application = next((app for app in current_list if app['user_id'] == self.applicant_id), None)
            if application:
                current_list.remove(application)
                await self.cog.config.guild(guild).set_raw(list_name, value=current_list)
                if list_name != target_list:
                    target = await self.cog.config.guild(guild).get_raw(target_list)
                    target.append(application)
                    await self.cog.config.guild(guild).set_raw(target_list, value=target)
                return application
        return None

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.green)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer()
            
            guild = self.cog.bot.get_guild(self.guild_id)
            if not guild:
                await interaction.followup.send("Error: Unable to find the guild. Please try again or contact an administrator.")
                return

            application = await self.move_application(guild, 'approved_applications')
            if not application:
                await interaction.followup.send(f"Error: Application for <@{self.applicant_id}> not found.")
                return

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

            application = await self.move_application(guild, 'denied_applications')
            if not application:
                await interaction.followup.send(f"Error: Application for <@{self.applicant_id}> not found.")
                return

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
        # Create a dummy message object for cooldown purposes
        class DummyMessage:
            def __init__(self, author):
                self.author = author

        dummy_message = DummyMessage(interaction.user)
        bucket = self.cog.application_cooldowns.get_bucket(dummy_message)
        retry_after = bucket.update_rate_limit()
        if retry_after:
            minutes, seconds = divmod(int(retry_after), 60)
            await interaction.response.send_message(f"You can apply again in {minutes} minutes and {seconds} seconds.", ephemeral=True)
            return

        if interaction.user.id in [app['user_id'] for app in await self.cog.config.guild(interaction.guild).active_applications()]:
            await interaction.response.send_message("You already have an active application for the Champions Circle.", ephemeral=True)
            return

        view = QuestionnaireView(self.cog, interaction.user)
        await interaction.response.send_message("Great! Let's start your application process. Click the button below to begin the questionnaire:", view=view, ephemeral=True)

class CancelApplicationButton(discord.ui.Button):
    def __init__(self, cog):
        super().__init__(style=discord.ButtonStyle.red, label="Cancel Application", custom_id="cancel_application")
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        guild = interaction.guild
        application = None

        for list_name in ['active_applications', 'approved_applications', 'denied_applications']:
            current_list = await self.cog.config.guild(guild).get_raw(list_name)
            application = next((app for app in current_list if app['user_id'] == user_id), None)
            if application:
                current_list.remove(application)
                await self.cog.config.guild(guild).set_raw(list_name, value=current_list)
                break

        if application:
            cancelled_applications = await self.cog.config.guild(guild).cancelled_applications()
            cancelled_applications.append(application)
            await self.cog.config.guild(guild).cancelled_applications.set(cancelled_applications)

            if list_name == 'approved_applications':
                role = guild.get_role(await self.cog.config.guild(guild).champions_role_id())
                if role and role in interaction.user.roles:
                    await interaction.user.remove_roles(role)
                await interaction.response.send_message("Your approved Champions Circle application has been cancelled. The Champions role has been removed if it was assigned.", ephemeral=True)
            else:
                await interaction.response.send_message("Your Champions Circle application has been cancelled.", ephemeral=True)
        else:
            await interaction.response.send_message("You don't have an active Champions Circle application to cancel.", ephemeral=True)
        
        await self.cog.update_embed(guild)

async def setup(bot):
    cog = ChampionsCircle(bot)
    await bot.add_cog(cog)
    bot.loop.create_task(cog.close_expired_applications())