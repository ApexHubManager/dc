import os
import re
import sqlite3
import secrets
import string
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
APPLICATION_ID = int(os.getenv("APPLICATION_ID", "0"))
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
GUILD_ID = int(os.getenv("GUILD_ID", "0"))

DB_FILE = os.getenv("DATABASE_FILE", "apex_cloud.db")

BRAND = "APEX CLOULD"
GREEN = 0xA7F432
RED = 0xED4245
BLUE = 0x5865F2
YELLOW = 0xFEE75C

ARROW = "<a:arrow_green_animated:1551176972015632464>"
W_ARROW = "<a:arrow_green_animated:1496588531701645472>"

BUY = "<:cart998:1551177586162278542>"
REWARD = "<a:Event:1551243218731929633>"
PARTNER = "<a:supporter:1551189615954886666>"
SUPPORT = "<:support889:1551189484077584475>"

THUMBNAIL = (
    "https://cdn.discordapp.com/attachments/"
    "1551160968682151956/1551241905202008114/"
    "1789897602018.png"
)

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    application_id=APPLICATION_ID
)

db = sqlite3.connect(DB_FILE, check_same_thread=False)
db.row_factory = sqlite3.Row


def sql(command, params=(), one=False):
    cur = db.execute(command, params)
    result = cur.fetchone() if one else cur.fetchall()
    db.commit()
    return result


def setup_database():
    tables = [
        """
        CREATE TABLE IF NOT EXISTS config (
            guild INTEGER PRIMARY KEY,
            logs INTEGER,
            welcome INTEGER,
            leave_channel INTEGER,
            member_role INTEGER,
            lockdown INTEGER DEFAULT 0
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS admins (
            guild INTEGER,
            user INTEGER,
            PRIMARY KEY(guild,user)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS managers (
            guild INTEGER,
            user INTEGER,
            PRIMARY KEY(guild,user)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS promotion_roles (
            guild INTEGER,
            role INTEGER,
            PRIMARY KEY(guild,role)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ticket_roles (
            guild INTEGER,
            role INTEGER,
            PRIMARY KEY(guild,role)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS lockdown_roles (
            guild INTEGER,
            role INTEGER,
            PRIMARY KEY(guild,role)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS link_bypass (
            guild INTEGER,
            role INTEGER,
            PRIMARY KEY(guild,role)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS badword_bypass (
            guild INTEGER,
            role INTEGER,
            PRIMARY KEY(guild,role)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS badwords (
            guild INTEGER,
            word TEXT,
            PRIMARY KEY(guild,word)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS warnings (
            guild INTEGER,
            user INTEGER,
            reason TEXT,
            created TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS plans (
            guild INTEGER,
            name TEXT,
            ram INTEGER,
            cpu INTEGER,
            disk INTEGER,
            PRIMARY KEY(guild,name)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS vps (
            id TEXT PRIMARY KEY,
            guild INTEGER,
            user INTEGER,
            plan TEXT,
            type TEXT,
            ram INTEGER,
            cpu INTEGER,
            disk INTEGER,
            ip TEXT,
            root_password TEXT,
            username TEXT,
            account_password TEXT,
            expires TEXT,
            status TEXT,
            created TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS tickets (
            channel INTEGER PRIMARY KEY,
            guild INTEGER,
            creator INTEGER,
            number INTEGER,
            category TEXT,
            claimed INTEGER DEFAULT 0,
            closed INTEGER DEFAULT 0
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS ticket_counter (
            guild INTEGER PRIMARY KEY,
            number INTEGER DEFAULT 0
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS giveaways (
            id TEXT PRIMARY KEY,
            guild INTEGER,
            channel INTEGER,
            message INTEGER,
            prize TEXT,
            ends TEXT,
            winners INTEGER,
            ended INTEGER DEFAULT 0,
            winner_ids TEXT DEFAULT ''
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS invites (
            guild INTEGER,
            user INTEGER,
            invited_user INTEGER,
            joined_at TEXT,
            left_at TEXT,
            fake INTEGER DEFAULT 0
        )
        """
    ]

    for table in tables:
        sql(table)


setup_database()


def current_time():
    return datetime.now(timezone.utc)


def is_owner(member):
    return member.id == OWNER_ID


def is_admin(member):
    if is_owner(member):
        return True

    return bool(
        sql(
            "SELECT 1 FROM admins WHERE guild=? AND user=?",
            (member.guild.id, member.id),
            True
        )
    )


def is_manager(member):
    if is_owner(member):
        return True

    return bool(
        sql(
            "SELECT 1 FROM managers WHERE guild=? AND user=?",
            (member.guild.id, member.id),
            True
        )
    )


def has_allowed_role(member, table):
    if is_owner(member):
        return True

    rows = sql(
        f"SELECT role FROM {table} WHERE guild=?",
        (member.guild.id,)
    )

    allowed = {row["role"] for row in rows}

    return any(role.id in allowed for role in member.roles)


def make_embed(title, description="", color=GREEN):
    embed = discord.Embed(
        title=f"☁️ {BRAND} — {title}",
        description=description,
        colour=color,
        timestamp=current_time()
    )
    embed.set_footer(text=f"☁️ {BRAND}")
    return embed


def box(section, content):
    return (
        "╭━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╮\n"
        f"        ☁️ {BRAND}\n"
        f"        {section}\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        f"{content}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"☁️ {BRAND}"
    )


async def respond(
    interaction,
    title,
    content,
    ephemeral=True,
    colour=GREEN
):
    await interaction.response.send_message(
        embed=make_embed(
            title,
            box(title.upper(), content),
            colour
        ),
        ephemeral=ephemeral
    )


async def log_action(guild, title, content, colour=BLUE):
    row = sql(
        "SELECT logs FROM config WHERE guild=?",
        (guild.id,),
        True
    )

    if not row or not row["logs"]:
        return

    channel = guild.get_channel(row["logs"])

    if channel:
        try:
            await channel.send(
                embed=make_embed(
                    title,
                    content,
                    colour
                )
            )
        except discord.HTTPException:
            pass


async def send_dm(member, title, content, colour=GREEN):
    try:
        await member.send(
            embed=make_embed(
                title,
                content,
                colour
            )
        )
        return True
    except (discord.Forbidden, discord.HTTPException):
        return False


def generate_id():
    chars = string.ascii_uppercase + string.digits

    while True:
        value = "APEX-" + "".join(
            secrets.choice(chars)
            for _ in range(6)
        )

        if not sql(
            "SELECT 1 FROM vps WHERE id=?",
            (value,),
            True
        ):
            return value


def parse_duration(value):
    match = re.fullmatch(
        r"(\d+)(s|m|h|d|w)",
        value.lower().strip()
    )

    if not match:
        raise ValueError(
            "Use `10m`, `1h`, `1d`, or `7d`."
        )

    amount = int(match.group(1))
    unit = match.group(2)

    multiplier = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400,
        "w": 604800
    }[unit]

    return amount * multiplier


def parse_timeout(value):
    seconds = parse_duration(value)

    if seconds > 28 * 86400:
        raise ValueError(
            "Discord timeouts cannot exceed 28 days."
        )

    return timedelta(seconds=seconds)


# ---------------- OWNER ----------------

owner_group = app_commands.Group(
    name="admin",
    description="APEX CLOULD administration"
)


@owner_group.command(name="add", description="Add an administrator")
async def admin_add(
    interaction: discord.Interaction,
    user: discord.Member
):
    if not is_owner(interaction.user):
        return await respond(
            interaction,
            "Permission Denied",
            "Only the Owner can manage administrators.",
            True,
            RED
        )

    if user.id == OWNER_ID:
        return await respond(
            interaction,
            "Administrator",
            "The Owner already has every permission.",
            True,
            YELLOW
        )

    sql(
        "INSERT OR IGNORE INTO admins VALUES(?,?)",
        (interaction.guild.id, user.id)
    )

    await respond(
        interaction,
        "Administrator Added",
        f"{user.mention} is now an administrator."
    )

    await log_action(
        interaction.guild,
        "Admin Added",
        f"{user.mention} was added by {interaction.user.mention}."
    )


@owner_group.command(name="remove", description="Remove an administrator")
async def admin_remove(
    interaction: discord.Interaction,
    user: discord.Member
):
    if not is_owner(interaction.user):
        return await respond(
            interaction,
            "Permission Denied",
            "Only the Owner can manage administrators.",
            True,
            RED
        )

    if user.id == OWNER_ID:
        return await respond(
            interaction,
            "Protected Owner",
            "The Owner cannot be removed.",
            True,
            RED
        )

    sql(
        "DELETE FROM admins WHERE guild=? AND user=?",
        (interaction.guild.id, user.id)
    )

    await respond(
        interaction,
        "Administrator Removed",
        f"{user.mention} is no longer an administrator."
    )


bot.tree.add_command(owner_group)


# ---------------- VPS MANAGERS ----------------

vps_manager_group = app_commands.Group(
    name="vps",
    description="APEX CLOULD VPS management"
)

manager_group = app_commands.Group(
    name="manager",
    description="Manage VPS managers"
)

vps_manager_group.add_command(manager_group)


@manager_group.command(name="add", description="Add a VPS manager")
async def manager_add(
    interaction: discord.Interaction,
    user: discord.Member
):
    if not is_owner(interaction.user):
        return await respond(
            interaction,
            "Permission Denied",
            "Only the Owner can manage VPS Managers.",
            True,
            RED
        )

    sql(
        "INSERT OR IGNORE INTO managers VALUES(?,?)",
        (interaction.guild.id, user.id)
    )

    await respond(
        interaction,
        "VPS Manager Added",
        f"{user.mention} can now use VPS Manager commands."
    )


@manager_group.command(name="remove", description="Remove a VPS manager")
async def manager_remove(
    interaction: discord.Interaction,
    user: discord.Member
):
    if not is_owner(interaction.user):
        return await respond(
            interaction,
            "Permission Denied",
            "Only the Owner can manage VPS Managers.",
            True,
            RED
        )

    sql(
        "DELETE FROM managers WHERE guild=? AND user=?",
        (interaction.guild.id, user.id)
    )

    await respond(
        interaction,
        "VPS Manager Removed",
        f"{user.mention} is no longer a VPS Manager."
    )


# ---------------- VPS PLANS ----------------

plan_group = app_commands.Group(
    name="plan",
    description="Manage VPS plans"
)

vps_manager_group.add_command(plan_group)


@plan_group.command(name="add", description="Add a VPS plan")
async def plan_add(
    interaction: discord.Interaction,
    name: str,
    ram: int,
    cpu: int,
    disk: int
):
    if not is_owner(interaction.user):
        return await respond(
            interaction,
            "Permission Denied",
            "Only the Owner can manage VPS plans.",
            True,
            RED
        )

    if ram <= 0 or cpu <= 0 or disk <= 0:
        return await respond(
            interaction,
            "Invalid Plan",
            "RAM, CPU and disk must be greater than zero.",
            True,
            RED
        )

    sql(
        "INSERT OR REPLACE INTO plans VALUES(?,?,?,?,?)",
        (interaction.guild.id, name, ram, cpu, disk)
    )

    await respond(
        interaction,
        "VPS Plan Added",
        f"**Name:** {name}\n"
        f"**RAM:** {ram} MB\n"
        f"**CPU:** {cpu} Cores\n"
        f"**Disk:** {disk} GB"
    )


@plan_group.command(name="list", description="List VPS plans")
async def plan_list(interaction: discord.Interaction):
    if not is_owner(interaction.user):
        return await respond(
            interaction,
            "Permission Denied",
            "Only the Owner can view VPS plans.",
            True,
            RED
        )

    rows = sql(
        "SELECT * FROM plans WHERE guild=? ORDER BY name",
        (interaction.guild.id,)
    )

    if not rows:
        return await respond(
            interaction,
            "VPS Plans",
            "No VPS plans have been configured.",
            True,
            YELLOW
        )

    text = ""

    for row in rows:
        text += (
            f"**{row['name']}**\n"
            f"RAM: `{row['ram']} MB`\n"
            f"CPU: `{row['cpu']} Cores`\n"
            f"Disk: `{row['disk']} GB`\n\n"
        )

    await respond(
        interaction,
        "VPS Plans",
        text
    )


@plan_group.command(name="remove", description="Remove a VPS plan")
async def plan_remove(
    interaction: discord.Interaction,
    name: str
):
    if not is_owner(interaction.user):
        return await respond(
            interaction,
            "Permission Denied",
            "Only the Owner can manage VPS plans.",
            True,
            RED
        )

    sql(
        "DELETE FROM plans WHERE guild=? AND name=?",
        (interaction.guild.id, name)
    )

    await respond(
        interaction,
        "VPS Plan Removed",
        f"Plan `{name}` has been removed."
    )


# ---------------- VPS CREATE ----------------

@vps_manager_group.command(
    name="create",
    description="Create a VPS record"
)
@app_commands.describe(
    user="VPS owner",
    plan="Configured VPS plan",
    type="VM or CT",
    days="Number of days"
)
async def vps_create(
    interaction: discord.Interaction,
    user: discord.Member,
    plan: str,
    type: str,
    days: int
):
    if not is_manager(interaction.user):
        return await respond(
            interaction,
            "Permission Denied",
            "Only VPS Managers and the Owner can create VPSs.",
            True,
            RED
        )

    row = sql(
        "SELECT * FROM plans WHERE guild=? AND name=?",
        (interaction.guild.id, plan),
        True
    )

    if not row:
        return await respond(
            interaction,
            "Plan Not Found",
            f"VPS plan `{plan}` does not exist.",
            True,
            RED
        )

    type = type.upper()

    if type not in ("VM", "CT"):
        return await respond(
            interaction,
            "Invalid Type",
            "Type must be `VM` or `CT`.",
            True,
            RED
        )

    if days < 1 or days > 3650:
        return await respond(
            interaction,
            "Invalid Days",
            "Days must be between 1 and 3650.",
            True,
            RED
        )

    vps_id = generate_id()
    root_password = secrets.token_urlsafe(16)
    username = (
        user.name.lower()
        .replace(" ", "")
        .replace("_", "")[:12]
        or "customer"
    )
    account_password = secrets.token_urlsafe(12)

    expires = current_time() + timedelta(days=days)

    sql(
        """
        INSERT INTO vps
        (id,guild,user,plan,type,ram,cpu,disk,ip,root_password,
         username,account_password,expires,status,created)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            vps_id,
            interaction.guild.id,
            user.id,
            plan,
            type,
            row["ram"],
            row["cpu"],
            row["disk"],
            "Pending",
            root_password,
            username,
            account_password,
            expires.isoformat(),
            "pending",
            current_time().isoformat()
        )
    )

    content = (
        "╭━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╮\n"
        "        ☁️ APEX CLOULD\n"
        "        🖥️ VPS CREATED\n"
        "╰━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╯\n\n"
        "🎉 Your VPS has been successfully created!\n\n"
        f"🆔 **VPS ID**\n`{vps_id}`\n\n"
        f"📦 **Plan**\n`{plan}`\n\n"
        f"💻 **Type**\n`{type}`\n\n"
        f"🧠 **RAM**\n`{row['ram']} MB`\n\n"
        f"⚙️ **CPU**\n`{row['cpu']} Cores`\n\n"
        f"💾 **Disk**\n`{row['disk']} GB`\n\n"
        "🌐 **IP Address**\n`Pending`\n\n"
        "🖥️ **VPS Login**\n`root`\n\n"
        f"🔑 **Root Password**\n`{root_password}`\n\n"
        f"👤 **Account Username**\n`{username}`\n\n"
        f"🔐 **Account Password**\n`{account_password}`\n\n"
        f"📅 **Expires**\n`{expires.strftime('%d %b %Y %H:%M UTC')}`\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔐 Keep your VPS credentials private.\n"
        "☁️ APEX CLOULD • VPS Management"
    )

    await send_dm(
        user,
        "VPS Created",
        content
    )

    await respond(
        interaction,
        "VPS Created",
        f"VPS `{vps_id}` was created for {user.mention}.\n"
        "Credentials were sent privately by DM."
    )

    await log_action(
        interaction.guild,
        "VPS Created",
        f"VPS `{vps_id}` created for {user.mention}."
    )


@vps_manager_group.command(
    name="info",
    description="View private VPS information"
)
async def vps_info(
    interaction: discord.Interaction,
    vps_id: str
):
    row = sql(
        "SELECT * FROM vps WHERE id=? AND guild=?",
        (vps_id.upper(), interaction.guild.id),
        True
    )

    if not row:
        return await respond(
            interaction,
            "VPS Not Found",
            "That VPS ID does not exist.",
            True,
            RED
        )

    if not (
        is_owner(interaction.user)
        or is_manager(interaction.user)
        or row["user"] == interaction.user.id
    ):
        return await respond(
            interaction,
            "Permission Denied",
            "You cannot view this VPS.",
            True,
            RED
        )

    text = (
        f"🆔 **VPS ID**\n`{row['id']}`\n\n"
        f"📦 **Plan**\n`{row['plan']}`\n\n"
        f"💻 **Type**\n`{row['type']}`\n\n"
        f"🧠 **RAM**\n`{row['ram']} MB`\n\n"
        f"⚙️ **CPU**\n`{row['cpu']} Cores`\n\n"
        f"💾 **Disk**\n`{row['disk']} GB`\n\n"
        f"🌐 **IP Address**\n`{row['ip']}`\n\n"
        "🖥️ **VPS Login**\n`root`\n\n"
        f"🔑 **Root Password**\n`{row['root_password']}`\n\n"
        f"👤 **Account Username**\n`{row['username']}`\n\n"
        f"🔐 **Account Password**\n`{row['account_password']}`\n\n"
        f"📅 **Expires**\n`{row['expires']}`\n\n"
        f"📡 **Status**\n`{row['status']}`"
    )

    await respond(
        interaction,
        "VPS Info",
        box("🖥️ VPS INFO", text),
        True
    )


@vps_manager_group.command(
    name="list",
    description="List VPSs"
)
async def vps_list(interaction: discord.Interaction):
    if not is_manager(interaction.user):
        return await respond(
            interaction,
            "Permission Denied",
            "Only VPS Managers and the Owner can use this command.",
            True,
            RED
        )

    rows = sql(
        "SELECT * FROM vps WHERE guild=? ORDER BY created DESC",
        (interaction.guild.id,)
    )

    if not rows:
        return await respond(
            interaction,
            "VPS List",
            "No VPSs exist.",
            True,
            YELLOW
        )

    text = ""

    for row in rows:
        member = interaction.guild.get_member(row["user"])
        owner = member.mention if member else f"`{row['user']}`"

        text += (
            f"🆔 `{row['id']}`\n"
            f"👤 {owner}\n"
            f"📦 `{row['plan']}` • `{row['type']}`\n"
            f"📡 `{row['status']}`\n\n"
        )

    await respond(
        interaction,
        "VPS List",
        text
    )


@vps_manager_group.command(
    name="suspend",
    description="Suspend a VPS"
)
async def vps_suspend(
    interaction: discord.Interaction,
    vps_id: str
):
    if not is_manager(interaction.user):
        return await respond(
            interaction,
            "Permission Denied",
            "Only VPS Managers and the Owner can use this command.",
            True,
            RED
        )

    row = sql(
        "SELECT * FROM vps WHERE id=? AND guild=?",
        (vps_id.upper(), interaction.guild.id),
        True
    )

    if not row:
        return await respond(
            interaction,
            "VPS Not Found",
            "That VPS does not exist.",
            True,
            RED
        )

    sql(
        "UPDATE vps SET status='suspended' WHERE id=?",
        (row["id"],)
    )

    await respond(
        interaction,
        "VPS Suspended",
        f"VPS `{row['id']}` is now suspended."
    )


@vps_manager_group.command(
    name="unsuspend",
    description="Unsuspend a VPS"
)
async def vps_unsuspend(
    interaction: discord.Interaction,
    vps_id: str,
    days: int
):
    if not is_manager(interaction.user):
        return await respond(
            interaction,
            "Permission Denied",
            "Only VPS Managers and the Owner can use this command.",
            True,
            RED
        )

    row = sql(
        "SELECT * FROM vps WHERE id=? AND guild=?",
        (vps_id.upper(), interaction.guild.id),
        True
    )

    if not row:
        return await respond(
            interaction,
            "VPS Not Found",
            "That VPS does not exist.",
            True,
            RED
        )

    expires = current_time() + timedelta(days=days)

    sql(
        "UPDATE vps SET status='online',expires=? WHERE id=?",
        (expires.isoformat(), row["id"])
    )

    await respond(
        interaction,
        "VPS Unsuspended",
        f"VPS `{row['id']}` is active until "
        f"`{expires.strftime('%d %b %Y %H:%M UTC')}`."
    )


@vps_manager_group.command(
    name="delete",
    description="Permanently delete a VPS"
)
async def vps_delete(
    interaction: discord.Interaction,
    vps_id: str
):
    if not is_owner(interaction.user):
        return await respond(
            interaction,
            "Permission Denied",
            "Only the Owner can permanently delete VPSs.",
            True,
            RED
        )

    row = sql(
        "SELECT * FROM vps WHERE id=? AND guild=?",
        (vps_id.upper(), interaction.guild.id),
        True
    )

    if not row:
        return await respond(
            interaction,
            "VPS Not Found",
            "That VPS does not exist.",
            True,
            RED
        )

    sql(
        "DELETE FROM vps WHERE id=?",
        (row["id"],)
    )

    await respond(
        interaction,
        "VPS Deleted",
        f"VPS `{row['id']}` has been permanently deleted.",
        True,
        RED
    )


bot.tree.add_command(vps_manager_group)


# ---------------- CONFIG ----------------

config_group = app_commands.Group(
    name="config",
    description="APEX CLOULD configuration"
)

automod_group = app_commands.Group(
    name="automod",
    description="Automod configuration"
)

config_group.add_command(automod_group)


@config_group.command(
    name="logs",
    description="Set the logging channel"
)
async def config_logs(
    interaction: discord.Interaction,
    channel: discord.TextChannel
):
    if not is_owner(interaction.user):
        return await respond(
            interaction,
            "Permission Denied",
            "Only the Owner can configure logs.",
            True,
            RED
        )

    sql(
        "INSERT OR IGNORE INTO config(guild) VALUES(?)",
        (interaction.guild.id,)
    )

    sql(
        "UPDATE config SET logs=? WHERE guild=?",
        (channel.id, interaction.guild.id)
    )

    await respond(
        interaction,
        "Logs Configured",
        f"Logs will now be sent to {channel.mention}."
    )


@config_group.command(
    name="memberrole",
    description="Set the automatic member role"
)
async def config_memberrole(
    interaction: discord.Interaction,
    role: discord.Role
):
    if not is_admin(interaction.user):
        return await respond(
            interaction,
            "Permission Denied",
            "Administrator access is required.",
            True,
            RED
        )

    sql(
        "INSERT OR IGNORE INTO config(guild) VALUES(?)",
        (interaction.guild.id,)
    )

    sql(
        "UPDATE config SET member_role=? WHERE guild=?",
        (role.id, interaction.guild.id)
    )

    await respond(
        interaction,
        "Member Role",
        f"New members will receive {role.mention}."
    )


@config_group.command(
    name="welcome",
    description="Set welcome channel"
)
async def config_welcome(
    interaction: discord.Interaction,
    channel: discord.TextChannel
):
    if not is_admin(interaction.user):
        return await respond(
            interaction,
            "Permission Denied",
            "Administrator access is required.",
            True,
            RED
        )

    sql(
        "INSERT OR IGNORE INTO config(guild) VALUES(?)",
        (interaction.guild.id,)
    )

    sql(
        "UPDATE config SET welcome=? WHERE guild=?",
        (channel.id, interaction.guild.id)
    )

    await respond(
        interaction,
        "Welcome Channel",
        f"Welcome messages will be sent to {channel.mention}."
    )


@config_group.command(
    name="leave",
    description="Set leave channel"
)
async def config_leave(
    interaction: discord.Interaction,
    channel: discord.TextChannel
):
    if not is_admin(interaction.user):
        return await respond(
            interaction,
            "Permission Denied",
            "Administrator access is required.",
            True,
            RED
        )

    sql(
        "INSERT OR IGNORE INTO config(guild) VALUES(?)",
        (interaction.guild.id,)
    )

    sql(
        "UPDATE config SET leave_channel=? WHERE guild=?",
        (channel.id, interaction.guild.id)
    )

    await respond(
        interaction,
        "Leave Channel",
        f"Leave messages will be sent to {channel.mention}."
    )


@automod_group.command(
    name="badword",
    description="Add a bad word"
)
async def badword_add(
    interaction: discord.Interaction,
    word: str
):
    if not is_admin(interaction.user):
        return await respond(
            interaction,
            "Permission Denied",
            "Administrator access is required.",
            True,
            RED
        )

    sql(
        "INSERT OR IGNORE INTO badwords VALUES(?,?)",
        (interaction.guild.id, word.lower())
    )

    await respond(
        interaction,
        "Bad Word Added",
        f"`{word}` was added to the bad-word filter."
    )


@automod_group.command(
    name="badwordremove",
    description="Remove a bad word"
)
async def badword_remove(
    interaction: discord.Interaction,
    word: str
):
    if not is_admin(interaction.user):
        return await respond(
            interaction,
            "Permission Denied",
            "Administrator access is required.",
            True,
            RED
        )

    sql(
        "DELETE FROM badwords WHERE guild=? AND word=?",
        (interaction.guild.id, word.lower())
    )

    await respond(
        interaction,
        "Bad Word Removed",
        f"`{word}` was removed."
    )


@automod_group.command(
    name="badwordlist",
    description="List bad words"
)
async def badword_list(interaction: discord.Interaction):
    if not is_admin(interaction.user):
        return await respond(
            interaction,
            "Permission Denied",
            "Administrator access is required.",
            True,
            RED
        )

    rows = sql(
        "SELECT word FROM badwords WHERE guild=? ORDER BY word",
        (interaction.guild.id,)
    )

    text = "\n".join(
        f"• `{row['word']}`"
        for row in rows
    ) or "No bad words configured."

    await respond(
        interaction,
        "Bad Word List",
        text
    )


@automod_group.command(
    name="linkbypass",
    description="Add a link bypass role"
)
async def link_bypass_add(
    interaction: discord.Interaction,
    role: discord.Role
):
    if not is_admin(interaction.user):
        return await respond(
            interaction,
            "Permission Denied",
            "Administrator access is required.",
            True,
            RED
        )

    sql(
        "INSERT OR IGNORE INTO link_bypass VALUES(?,?)",
        (interaction.guild.id, role.id)
    )

    await respond(
        interaction,
        "Link Bypass",
        f"{role.mention} can bypass link protection."
    )


@automod_group.command(
    name="badwordbypass",
    description="Add a bad-word bypass role"
)
async def badword_bypass_add(
    interaction: discord.Interaction,
    role: discord.Role
):
    if not is_admin(interaction.user):
        return await respond(
            interaction,
            "Permission Denied",
            "Administrator access is required.",
            True,
            RED
        )

    sql(
        "INSERT OR IGNORE INTO badword_bypass VALUES(?,?)",
        (interaction.guild.id, role.id)
    )

    await respond(
        interaction,
        "Bad Word Bypass",
        f"{role.mention} can bypass the bad-word filter."
    )


bot.tree.add_command(config_group)


# ---------------- MODERATION ----------------

@bot.tree.command(name="kick", description="Kick a member")
@app_commands.describe(reason="Reason for the kick")
async def kick(
    interaction: discord.Interaction,
    user: discord.Member,
    reason: str
):
    if not is_admin(interaction.user):
        return await respond(interaction, "Permission Denied",
                             "Administrator access is required.", True, RED)

    if user.id == OWNER_ID:
        return await respond(interaction, "Protected Owner",
                             "The Owner cannot be kicked.", True, RED)

    await send_dm(
        user,
        "Kicked",
        f"You have been kicked from **{BRAND}**.\n\n📝 Reason: {reason}",
        RED
    )

    await user.kick(reason=reason)

    await respond(
        interaction,
        "Member Kicked",
        f"{user.mention} was kicked.\n📝 Reason: {reason}"
    )

    await log_action(
        interaction.guild,
        "Member Kicked",
        f"{user.mention} was kicked by {interaction.user.mention}.\nReason: {reason}",
        RED
    )


@bot.tree.command(name="ban", description="Ban a member")
@app_commands.describe(reason="Reason for the ban")
async def ban(
    interaction: discord.Interaction,
    user: discord.Member,
    reason: str
):
    if not is_admin(interaction.user):
        return await respond(interaction, "Permission Denied",
                             "Administrator access is required.", True, RED)

    if user.id == OWNER_ID:
        return await respond(interaction, "Protected Owner",
                             "The Owner cannot be banned.", True, RED)

    await send_dm(
        user,
        "Banned",
        f"You have been banned from **{BRAND}**.\n\n📝 Reason: {reason}",
        RED
    )

    await user.ban(reason=reason)

    await respond(
        interaction,
        "Member Banned",
        f"{user.mention} was banned.\n📝 Reason: {reason}"
    )

    await log_action(
        interaction.guild,
        "Member Banned",
        f"{user.mention} was banned by {interaction.user.mention}.\nReason: {reason}",
        RED
    )


@bot.tree.command(name="warn", description="Warn a member")
async def warn(
    interaction: discord.Interaction,
    user: discord.Member,
    reason: str
):
    if not is_admin(interaction.user):
        return await respond(interaction, "Permission Denied",
                             "Administrator access is required.", True, RED)

    if user.id == OWNER_ID:
        return await respond(interaction, "Protected Owner",
                             "The Owner cannot be warned.", True, RED)

    sql(
        "INSERT INTO warnings VALUES(?,?,?,?)",
        (
            interaction.guild.id,
            user.id,
            reason,
            current_time().isoformat()
        )
    )

    count = sql(
        "SELECT COUNT(*) AS n FROM warnings WHERE guild=? AND user=?",
        (interaction.guild.id, user.id),
        True
    )["n"]

    if count >= 3:
        await user.timeout(
            timedelta(hours=24),
            reason="Reached 3 warnings"
        )

        sql(
            "DELETE FROM warnings WHERE guild=? AND user=?",
            (interaction.guild.id, user.id)
        )

        await send_dm(
            user,
            "Warning Limit",
            "You have reached **3/3 warnings**.\n\n"
            f"📝 Reason: {reason}\n"
            "⏱️ Action: 24-hour timeout\n\n"
            "Your warning count has been reset.",
            RED
        )

        text = (
            f"{user.mention} reached **3/3 warnings**.\n"
            "They received a 24-hour timeout and their warnings were reset."
        )
    else:
        await send_dm(
            user,
            "Warning",
            f"You have received a warning in **{BRAND}**.\n\n"
            f"⚠️ Warning: **{count}/3**\n"
            f"📝 Reason: {reason}",
            YELLOW
        )

        text = (
            f"{user.mention} received warning **{count}/3**.\n"
            f"📝 Reason: {reason}"
        )

    await respond(
        interaction,
        "Warning Issued",
        text
    )


@bot.tree.command(name="warnings", description="View warnings")
async def warnings(
    interaction: discord.Interaction,
    user: discord.Member
):
    if not is_admin(interaction.user):
        return await respond(interaction, "Permission Denied",
                             "Administrator access is required.", True, RED)

    rows = sql(
        "SELECT reason,created FROM warnings WHERE guild=? AND user=? ORDER BY created",
        (interaction.guild.id, user.id)
    )

    if not rows:
        text = f"{user.mention} has no active warnings."
    else:
        text = "\n".join(
            f"⚠️ **{i}.** {row['reason']}"
            for i, row in enumerate(rows, 1)
        )

    await respond(
        interaction,
        "Warnings",
        text
    )


@bot.tree.command(name="clearwarnings", description="Clear warnings")
async def clearwarnings(
    interaction: discord.Interaction,
    user: discord.Member
):
    if not is_admin(interaction.user):
        return await respond(interaction, "Permission Denied",
                             "Administrator access is required.", True, RED)

    sql(
        "DELETE FROM warnings WHERE guild=? AND user=?",
        (interaction.guild.id, user.id)
    )

    await respond(
        interaction,
        "Warnings Cleared",
        f"All warnings for {user.mention} were cleared."
    )


@bot.tree.command(name="timeout", description="Timeout a member")
async def timeout(
    interaction: discord.Interaction,
    user: discord.Member,
    duration: str,
    reason: str
):
    if not is_admin(interaction.user):
        return await respond(interaction, "Permission Denied",
                             "Administrator access is required.", True, RED)

    if user.id == OWNER_ID:
        return await respond(interaction, "Protected Owner",
                             "The Owner cannot be timed out.", True, RED)

    try:
        delta = parse_timeout(duration)
    except ValueError as error:
        return await respond(interaction, "Invalid Duration",
                             str(error), True, RED)

    await user.timeout(delta, reason=reason)

    await send_dm(
        user,
        "Timeout",
        f"You have been timed out in **{BRAND}**.\n\n"
        f"⏱️ Duration: {duration}\n"
        f"📝 Reason: {reason}",
        YELLOW
    )

    await respond(
        interaction,
        "Member Timed Out",
        f"{user.mention} was timed out for `{duration}`."
    )


@bot.tree.command(name="untimeout", description="Remove a timeout")
async def untimeout(
    interaction: discord.Interaction,
    user: discord.Member,
    reason: str
):
    if not is_admin(interaction.user):
        return await respond(interaction, "Permission Denied",
                             "Administrator access is required.", True, RED)

    await user.timeout(None, reason=reason)

    await send_dm(
        user,
        "Timeout Removed",
        "Your timeout has been removed.\n\n"
        "You can now participate in the server again."
    )

    await respond(
        interaction,
        "Timeout Removed",
        f"{user.mention} can participate again."
    )


@bot.tree.command(name="clear", description="Clear messages")
async def clear(
    interaction: discord.Interaction,
    amount: int
):
    if not is_admin(interaction.user):
        return await respond(interaction, "Permission Denied",
                             "Administrator access is required.", True, RED)

    if amount < 1 or amount > 100:
        return await respond(interaction, "Invalid Amount",
                             "Choose between 1 and 100 messages.", True, RED)

    await interaction.response.defer(ephemeral=True)

    deleted = await interaction.channel.purge(limit=amount)

    await interaction.followup.send(
        embed=make_embed(
            "Messages Cleared",
            f"Deleted `{len(deleted)}` messages.",
            GREEN
        ),
        ephemeral=True
    )


# ---------------- ROLES ----------------

role_group = app_commands.Group(
    name="role",
    description="Role management"
)


@role_group.command(name="add", description="Give a role")
async def role_add(
    interaction: discord.Interaction,
    user: discord.Member,
    role: discord.Role
):
    if not is_admin(interaction.user):
        return await respond(interaction, "Permission Denied",
                             "Administrator access is required.", True, RED)

    if role >= interaction.guild.me.top_role:
        return await respond(interaction, "Role Error",
                             "I cannot manage that role.", True, RED)

    await user.add_roles(role)

    await respond(
        interaction,
        "Role Added",
        f"{role.mention} was added to {user.mention}."
    )


@role_group.command(name="remove", description="Remove a role")
async def role_remove(
    interaction: discord.Interaction,
    user: discord.Member,
    role: discord.Role
):
    if not is_admin(interaction.user):
        return await respond(interaction, "Permission Denied",
                             "Administrator access is required.", True, RED)

    await user.remove_roles(role)

    await respond(
        interaction,
        "Role Removed",
        f"{role.mention} was removed from {user.mention}."
    )


@role_group.command(name="info", description="View role information")
async def role_info(
    interaction: discord.Interaction,
    role: discord.Role
):
    if not is_admin(interaction.user):
        return await respond(interaction, "Permission Denied",
                             "Administrator access is required.", True, RED)

    await respond(
        interaction,
        "Role Info",
        f"**Name:** {role.name}\n"
        f"**Members:** {len(role.members)}\n"
        f"**Mentionable:** {role.mentionable}\n"
        f"**Managed:** {role.managed}"
    )


bot.tree.add_command(role_group)


# ---------------- PROMOTION ----------------

@bot.tree.command(name="promotion", description="Promote a member")
async def promotion(
    interaction: discord.Interaction,
    user: discord.Member,
    role: discord.Role
):
    if not is_owner(interaction.user):
        return await respond(
            interaction,
            "Permission Denied",
            "Only the Owner can use promotion.",
            True,
            RED
        )

    allowed = sql(
        "SELECT 1 FROM promotion_roles WHERE guild=? AND role=?",
        (interaction.guild.id, role.id),
        True
    )

    if not allowed:
        return await respond(
            interaction,
            "Role Not Whitelisted",
            "That role is not in the Promotion Role whitelist.",
            True,
            RED
        )

    await user.add_roles(role)

    await respond(
        interaction,
        "Promotion",
        f"{user.mention} has been promoted to {role.mention}."
    )


# ---------------- SERVER INFO ----------------

@bot.tree.command(name="serverinfo", description="Show server information")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild

    bots = sum(member.bot for member in guild.members)

    embed = make_embed(
        "Server Info",
        "",
        GREEN
    )

    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    embed.add_field(
        name="👑 Owner",
        value=guild.owner.mention if guild.owner else "Unknown",
        inline=False
    )
    embed.add_field(
        name="👥 Members",
        value=str(guild.member_count),
        inline=True
    )
    embed.add_field(
        name="🤖 Bots",
        value=str(bots),
        inline=True
    )
    embed.add_field(
        name="🚀 Total Boosts",
        value=str(guild.premium_subscription_count),
        inline=True
    )
    embed.add_field(
        name="📅 Created",
        value=discord.utils.format_dt(guild.created_at, "F"),
        inline=False
    )
    embed.add_field(
        name="🔐 Verification",
        value=str(guild.verification_level).title(),
        inline=True
    )
    embed.add_field(
        name="💬 Channels",
        value=str(len(guild.channels)),
        inline=True
    )
    embed.add_field(
        name="🎭 Roles",
        value=str(len(guild.roles)),
        inline=True
    )
    embed.add_field(
        name="😀 Emojis",
        value=str(len(guild.emojis)),
        inline=True
    )
    embed.add_field(
        name="🔊 Voice Channels",
        value=str(len(guild.voice_channels)),
        inline=True
    )

    await interaction.response.send_message(
        embed=embed,
        ephemeral=False
    )


# ---------------- HELP ----------------

@bot.tree.command(name="help", description="Show available commands")
async def help_command(interaction: discord.Interaction):
    lines = [
        "**Everyone**",
        "`/help` `/serverinfo` `!i`",
    ]

    if is_admin(interaction.user):
        lines += [
            "",
            "**Admin**",
            "`/config` `/role` `/kick` `/ban` `/warn`",
            "`/warnings` `/clearwarnings` `/timeout` `/untimeout` `/clear`"
        ]

    if is_manager(interaction.user):
        lines += [
            "",
            "**VPS Manager**",
            "`/vps create` `/vps suspend` `/vps unsuspend`",
            "`/vps info` `/vps list`"
        ]

    if is_owner(interaction.user):
        lines += [
            "",
            "**Owner**",
            "`/admin` `/vps delete` `/vps plan`",
            "`/promotion` `/lockdown`"
        ]

    await respond(
        interaction,
        "Help",
        "\n".join(lines),
        True
    )


# ---------------- MESSAGE ----------------

@bot.tree.command(name="msg", description="Send an embed message")
async def msg(
    interaction: discord.Interaction,
    channel: discord.TextChannel,
    text: str,
    title: str = "APEX CLOULD"
):
    if not (
        is_admin(interaction.user)
        or is_manager(interaction.user)
    ):
        return await respond(
            interaction,
            "Permission Denied",
            "Admin or VPS Manager access is required.",
            True,
            RED
        )

    await channel.send(
        embed=make_embed(
            title,
            text,
            GREEN
        )
    )

    await respond(
        interaction,
        "Message Sent",
        f"Your message was sent to {channel.mention}."
    )


# ---------------- TICKET ----------------

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Claim Ticket",
        emoji="🙋",
        style=discord.ButtonStyle.primary,
        custom_id="apex_ticket_claim"
    )
    async def claim(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        ticket = sql(
            "SELECT * FROM tickets WHERE channel=?",
            (interaction.channel.id,),
            True
        )

        if not ticket:
            return await respond(
                interaction,
                "Ticket Error",
                "This is not a ticket.",
                True,
                RED
            )

        if not (
            is_owner(interaction.user)
            or has_allowed_role(interaction.user, "ticket_roles")
        ):
            return await respond(
                interaction,
                "Permission Denied",
                "You do not have ticket access.",
                True,
                RED
            )

        sql(
            "UPDATE tickets SET claimed=? WHERE channel=?",
            (interaction.user.id, interaction.channel.id)
        )

        await interaction.response.send_message(
            embed=make_embed(
                "Ticket Claimed",
                f"🙋 Claimed by {interaction.user.mention}."
            )
        )

        await log_action(
            interaction.guild,
            "Ticket Claimed",
            f"Ticket `APEX-{ticket['number']:04d}` claimed by {interaction.user.mention}."
        )

    @discord.ui.button(
        label="Close Ticket",
        emoji="🔒",
        style=discord.ButtonStyle.danger,
        custom_id="apex_ticket_close"
    )
    async def close(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        ticket = sql(
            "SELECT * FROM tickets WHERE channel=?",
            (interaction.channel.id,),
            True
        )

        if not ticket:
            return await respond(
                interaction,
                "Ticket Error",
                "This is not a ticket.",
                True,
                RED
            )

        if not (
            interaction.user.id == ticket["creator"]
            or is_owner(interaction.user)
            or has_allowed_role(interaction.user, "ticket_roles")
        ):
            return await respond(
                interaction,
                "Permission Denied",
                "You cannot close this ticket.",
                True,
                RED
            )

        await close_ticket(interaction, ticket)


async def close_ticket(interaction, ticket):
    channel = interaction.channel

    messages = []

    try:
        async for message in channel.history(
            limit=None,
            oldest_first=True
        ):
            messages.append(
                f"[{message.created_at.isoformat()}] "
                f"{message.author}: {message.content}"
            )
    except discord.HTTPException:
        pass

    transcript = "\n".join(messages)
    file = discord.File(
        io.BytesIO(transcript.encode("utf-8")),
        filename=f"APEX-{ticket['number']:04d}-transcript.txt"
    )

    creator = interaction.guild.get_member(ticket["creator"])

    if creator:
        await send_dm(
            creator,
            "Ticket Closed",
            f"🎟️ Ticket: `APEX-{ticket['number']:04d}`\n"
            f"📂 Category: `{ticket['category']}`\n"
            f"👤 Closed by: {interaction.user.mention}\n\n"
            "Your complete ticket transcript is attached.",
            GREEN
        )

        try:
            await creator.send(file=file)
        except discord.HTTPException:
            pass

    sql(
        "UPDATE tickets SET closed=1 WHERE channel=?",
        (channel.id,)
    )

    await channel.set_permissions(
        creator,
        view_channel=False,
        send_messages=False
    )

    await channel.edit(
        name=f"closed-{channel.name}"
    )

    await interaction.response.send_message(
        embed=make_embed(
            "Ticket Closed",
            f"🔒 Closed by {interaction.user.mention}."
        )
    )

    await log_action(
        interaction.guild,
        "Ticket Closed",
        f"Ticket `APEX-{ticket['number']:04d}` closed by {interaction.user.mention}."
    )


@bot.tree.command(name="ticket", description="Ticket commands")
async def ticket_root(interaction: discord.Interaction):
    await respond(
        interaction,
        "Tickets",
        "Use the ticket commands from `/ticket`."
    )


ticket_group = app_commands.Group(
    name="ticket",
    description="Ticket management"
)

@ticket_group.command(name="setup", description="Create the ticket panel")
async def ticket_setup(interaction: discord.Interaction):
    if not is_admin(interaction.user):
        return await respond(
            interaction,
            "Permission Denied",
            "Administrator access is required.",
            True,
            RED
        )

    description = (
        "📩 **Support Tickets**\n\n"
        f"{ARROW} **Need Help? Please Read Carefully**\n"
        f"{ARROW} Click the button that best matches the type of support you need.\n"
        f"{ARROW} Provide a clear and detailed description of your issue.\n"
        f"{ARROW} Include screenshots, error messages, or steps to reproduce.\n"
        f"{ARROW} Missing or vague information may cause delays.\n"
        f"{ARROW} Repeated spam or unnecessary pinging may lead to a timeout.\n"
        f"{ARROW} Reward Claim: No alt accounts, no rejoin counts, no fake counts.\n\n"
        f"{ARROW} Thank you for helping us help you!"
    )

    view = TicketCategoryView()

    await interaction.channel.send(
        embed=make_embed(
            "Support Tickets",
            description
        ),
        view=view
    )

    await respond(
        interaction,
        "Ticket Setup",
        "The ticket panel has been created."
    )


class TicketCategoryView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def open_ticket(
        self,
        interaction,
        category,
        emoji
    ):
        existing = sql(
            """
            SELECT channel FROM tickets
            WHERE guild=? AND creator=? AND closed=0
            """,
            (interaction.guild.id, interaction.user.id),
            True
        )

        if existing:
            channel = interaction.guild.get_channel(
                existing["channel"]
            )

            if channel:
                return await respond(
                    interaction,
                    "Ticket Already Open",
                    f"You already have {channel.mention}.",
                    True,
                    YELLOW
                )

        counter = sql(
            "SELECT number FROM ticket_counter WHERE guild=?",
            (interaction.guild.id,),
            True
        )

        number = (counter["number"] + 1) if counter else 1

        if counter:
            sql(
                "UPDATE ticket_counter SET number=? WHERE guild=?",
                (number, interaction.guild.id)
            )
        else:
            sql(
                "INSERT INTO ticket_counter VALUES(?,?)",
                (interaction.guild.id, number)
            )

        overwrites = {
            interaction.guild.default_role:
                discord.PermissionOverwrite(view_channel=False),
            interaction.user:
                discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True
                )
        }

        for row in sql(
            "SELECT role FROM ticket_roles WHERE guild=?",
            (interaction.guild.id,)
        ):
            role = interaction.guild.get_role(row["role"])

            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True
                )

        channel = await interaction.guild.create_text_channel(
            name=f"ticket-{number:04d}",
            overwrites=overwrites
        )

        sql(
            "INSERT INTO tickets VALUES(?,?,?,?,?,?,?)",
            (
                channel.id,
                interaction.guild.id,
                interaction.user.id,
                number,
                category,
                0,
                0
            )
        )

        content = (
            f"🎟️ **Ticket:** `APEX-{number:04d}`\n"
            f"👤 **Created by:** {interaction.user.mention}\n"
            f"📂 **Category:** {emoji} {category}\n"
            "👤 **Claimed by:** Nobody\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{ARROW} **Welcome to your support ticket!**\n\n"
            "Please explain your issue clearly and provide all relevant information.\n\n"
            f"{ARROW} **Please include:**\n"
            "> • A clear description of your issue\n"
            "> • Screenshots when necessary\n"
            "> • Error messages\n"
            "> • Any relevant information\n\n"
            f"{ARROW} **Support Guidelines**\n"
            "> Please be patient while waiting for staff.\n"
            "> Do not repeatedly ping staff.\n"
            "> Do not spam the ticket.\n"
            "> Missing information may delay support.\n\n"
            f"{ARROW} **A staff member will assist you shortly.**"
        )

        await channel.send(
            embed=make_embed(
                "Support Ticket",
                content
            ),
            view=TicketView()
        )

        await send_dm(
            interaction.user,
            "Ticket Opened",
            f"🎟️ Ticket: `APEX-{number:04d}`\n"
            f"📂 Category: `{category}`\n\n"
            "Your support ticket has been successfully opened."
        )

        await interaction.response.send_message(
            embed=make_embed(
                "Ticket Created",
                f"Your ticket is ready: {channel.mention}"
            ),
            ephemeral=True
        )


    @discord.ui.button(
        label="BUY",
        emoji=BUY,
        style=discord.ButtonStyle.success,
        custom_id="apex_ticket_buy"
    )
    async def buy(self, interaction, button):
        await self.open_ticket(interaction, "BUY", BUY)

    @discord.ui.button(
        label="REWARD CLAIM",
        emoji=REWARD,
        style=discord.ButtonStyle.success,
        custom_id="apex_ticket_reward"
    )
    async def reward(self, interaction, button):
        await self.open_ticket(interaction, "REWARD CLAIM", REWARD)

    @discord.ui.button(
        label="PARTNERSHIP",
        emoji=PARTNER,
        style=discord.ButtonStyle.primary,
        custom_id="apex_ticket_partner"
    )
    async def partnership(self, interaction, button):
        await self.open_ticket(interaction, "PARTNERSHIP", PARTNER)

    @discord.ui.button(
        label="GENERAL SUPPORT",
        emoji=SUPPORT,
        style=discord.ButtonStyle.secondary,
        custom_id="apex_ticket_support"
    )
    async def support(self, interaction, button):
        await self.open_ticket(interaction, "GENERAL SUPPORT", SUPPORT)


ticket_group.add_command(ticket_setup)
bot.tree.add_command(ticket_group)


# ---------------- LOCKDOWN ----------------

lockdown_group = app_commands.Group(
    name="lockdown",
    description="Server lockdown management"
)


@lockdown_group.command(name="start", description="Start lockdown")
async def lockdown_start(interaction: discord.Interaction):
    if not is_owner(interaction.user):
        return await respond(
            interaction,
            "Permission Denied",
            "Only the Owner can start lockdown.",
            True,
            RED
        )

    everyone = interaction.guild.default_role

    await interaction.channel.set_permissions(
        everyone,
        send_messages=False
    )

    sql(
        "INSERT OR IGNORE INTO config(guild) VALUES(?)",
        (interaction.guild.id,)
    )

    sql(
        "UPDATE config SET lockdown=1 WHERE guild=?",
        (interaction.guild.id,)
    )

    for row in sql(
        "SELECT role FROM lockdown_roles WHERE guild=?",
        (interaction.guild.id,)
    ):
        role = interaction.guild.get_role(row["role"])

        if role:
            await interaction.channel.set_permissions(
                role,
                send_messages=True
            )

    await respond(
        interaction,
        "Lockdown Started",
        "Server lockdown has been enabled.",
        False,
        RED
    )


@lockdown_group.command(name="unlock", description="End lockdown")
async def lockdown_unlock(interaction: discord.Interaction):
    if not is_owner(interaction.user):
        return await respond(
            interaction,
            "Permission Denied",
            "Only the Owner can end lockdown.",
            True,
            RED
        )

    everyone = interaction.guild.default_role

    await interaction.channel.set_permissions(
        everyone,
        send_messages=None
    )

    sql(
        "UPDATE config SET lockdown=0 WHERE guild=?",
        (interaction.guild.id,)
    )

    await respond(
        interaction,
        "Lockdown Removed",
        "Server lockdown has been removed.",
        False
    )


@lockdown_group.command(
    name="roleadd",
    description="Allow a role during lockdown"
)
async def lockdown_role_add(
    interaction: discord.Interaction,
    role: discord.Role
):
    if not is_owner(interaction.user):
        return await respond(
            interaction,
            "Permission Denied",
            "Only the Owner can configure lockdown roles.",
            True,
            RED
        )

    sql(
        "INSERT OR IGNORE INTO lockdown_roles VALUES(?,?)",
        (interaction.guild.id, role.id)
    )

    await respond(
        interaction,
        "Lockdown Role",
        f"{role.mention} can speak during lockdown."
    )


@lockdown_group.command(
    name="roleremove",
    description="Remove a lockdown role"
)
async def lockdown_role_remove(
    interaction: discord.Interaction,
    role: discord.Role
):
    if not is_owner(interaction.user):
        return await respond(
            interaction,
            "Permission Denied",
            "Only the Owner can configure lockdown roles.",
            True,
            RED
        )

    sql(
        "DELETE FROM lockdown_roles WHERE guild=? AND role=?",
        (interaction.guild.id, role.id)
    )

    await respond(
        interaction,
        "Lockdown Role Removed",
        f"{role.mention} was removed."
    )


bot.tree.add_command(lockdown_group)


# ---------------- WELCOME / LEAVE ----------------

@bot.event
async def on_member_join(member):
    row = sql(
        "SELECT * FROM config WHERE guild=?",
        (member.guild.id,),
        True
    )

    if not row:
        return

    if row["member_role"]:
        role = member.guild.get_role(row["member_role"])

        if role:
            try:
                await member.add_roles(role)
            except discord.HTTPException:
                pass

    if row["welcome"]:
        channel = member.guild.get_channel(row["welcome"])

        if channel:
            description = (
                f"{W_ARROW} Your journey to fast, powerful hosting starts here.\n\n"
                "🚀 **What we offer:**\n"
                f"{W_ARROW} High-performance nodes\n"
                f"{W_ARROW} Advanced DDoS protection\n"
                f"{W_ARROW} Instant deployment\n"
                f"{W_ARROW} Budget & premium plans\n\n"
                f"{SUPPORT} **Need assistance?**\n"
                f"{W_ARROW} Open a ticket in <#{TICKET_INFO}> — our team will respond fast ⚡\n\n"
                f"{PARTNER} **Earn free hosting!**\n"
                f"{W_ARROW} Invite friends and unlock credits, upgrades & rewards."
            )

            e = make_embed(
                "Welcome to APEX CLOULD™!",
                description
            )
            e.set_thumbnail(url=THUMBNAIL)

            try:
                await channel.send(
                    content=member.mention,
                    embed=e
                )
            except discord.HTTPException:
                pass

    await send_dm(
        member,
        "Welcome to APEX CLOULD™!",
        f"Hey {member.mention}! 👋\n\n"
        "🚀 **Your hosting journey starts here.**\n\n"
        f"{W_ARROW} **What we offer:**\n"
        "• 🖥️ VPS & server hosting\n"
        "• ⚡ Fast deployment\n"
        "• 🛡️ DDoS-protected infrastructure\n"
        "• 💰 Free & affordable plans\n"
        "• 🎁 Community rewards\n"
        "• 🛠️ Support from our team"
    )


@bot.event
async def on_member_remove(member):
    row = sql(
        "SELECT leave_channel FROM config WHERE guild=?",
        (member.guild.id,),
        True
    )

    if row and row["leave_channel"]:
        channel = member.guild.get_channel(row["leave_channel"])

        if channel:
            e = make_embed(
                "Goodbye from APEX CLOULD™!",
                f"{W_ARROW} We’re sorry to see you leave!\n\n"
                "🚀 **Before you go:**\n"
                f"{W_ARROW} Thank you for being part of our community\n"
                f"{W_ARROW} Your support means a lot to us\n"
                f"{W_ARROW} You’re always welcome back\n\n"
                f"{SUPPORT} Need us again?\n"
                f"{W_ARROW} You can always rejoin APEX CLOULD™."
            )
            e.set_thumbnail(url=THUMBNAIL)

            try:
                await channel.send(embed=e)
            except discord.HTTPException:
                pass

    await send_dm(
        member,
        "Goodbye from APEX CLOULD™!",
        "Hey, we're sorry to see you leave. 👋\n\n"
        f"{W_ARROW} **Before you go:**\n"
        "• Thank you for being part of the community\n"
        "• Your support means a lot to us\n"
        "• You're always welcome back\n\n"
        f"{SUPPORT} **Need us again?**\n"
        "You can always rejoin APEX CLOULD™ whenever you want."
    )


# ---------------- AUTOMOD ----------------

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if not message.guild:
        await bot.process_commands(message)
        return

    member = message.author

    if is_admin(member):
        await bot.process_commands(message)
        return

    link_roles = {
        row["role"]
        for row in sql(
            "SELECT role FROM link_bypass WHERE guild=?",
            (message.guild.id,)
        )
    }

    word_roles = {
        row["role"]
        for row in sql(
            "SELECT role FROM badword_bypass WHERE guild=?",
            (message.guild.id,)
        )
    }

    member_roles = {role.id for role in member.roles}

    link_allowed = bool(link_roles & member_roles)
    word_allowed = bool(word_roles & member_roles)

    if not link_allowed and re.search(
        r"(https?://|www\.|discord\.gg/)",
        message.content,
        re.I
    ):
        try:
            await message.delete()
        except discord.HTTPException:
            pass

        try:
            await member.timeout(
                timedelta(minutes=10),
                reason="Automod link protection"
            )
        except discord.HTTPException:
            pass

        await send_dm(
            member,
            "Automod",
            "Your message contained a link and was removed.\n\n"
            "⏱️ You received a 10-minute timeout.",
            RED
        )

        await log_action(
            message.guild,
            "Link Automod",
            f"{member.mention} posted a link.",
            RED
        )

        return

    if not word_allowed:
        words = [
            row["word"]
            for row in sql(
                "SELECT word FROM badwords WHERE guild=?",
                (message.guild.id,)
            )
        ]

        content = message.content.lower()

        if any(
            re.search(
                rf"\b{re.escape(word)}\b",
                content
            )
            for word in words
        ):
            try:
                await message.delete()
            except discord.HTTPException:
                pass

            try:
                await member.timeout(
                    timedelta(minutes=10),
                    reason="Automod bad word"
                )
            except discord.HTTPException:
                pass

            await send_dm(
                member,
                "Automod",
                "Your message contained a blocked word and was removed.\n\n"
                "⏱️ You received a 10-minute timeout.",
                RED
            )

            await log_action(
                message.guild,
                "Bad Word Automod",
                f"{member.mention} triggered the bad-word filter.",
                RED
            )

            return

    await bot.process_commands(message)


# ---------------- INVITE TRACKER ----------------

@bot.command(name="i")
async def invite_command(ctx):
    if not ctx.guild:
        return

    total = sql(
        "SELECT COUNT(*) AS n FROM invites WHERE guild=? AND user=?",
        (ctx.guild.id, ctx.author.id),
        True
    )["n"]

    left = sql(
        """
        SELECT COUNT(*) AS n FROM invites
        WHERE guild=? AND user=? AND left_at IS NOT NULL
        """,
        (ctx.guild.id, ctx.author.id),
        True
    )["n"]

    fake = sql(
        """
        SELECT COUNT(*) AS n FROM invites
        WHERE guild=? AND user=? AND fake=1
        """,
        (ctx.guild.id, ctx.author.id),
        True
    )["n"]

    real = total - fake - left

    text = (
        f"👤 {ctx.author.mention}\n\n"
        "📊 **Invite Statistics**\n\n"
        f"✅ **Real Invites**\n> {max(real, 0)}\n\n"
        f"👥 **Total Invites**\n> {total}\n\n"
        f"🚪 **Left**\n> {left}\n\n"
        f"🤖 **Fake**\n> {fake}\n"
    )

    await ctx.send(
        embed=make_embed(
            "INVITE TRACKER",
            box("INVITE TRACKER", text)
        )
    )


# ---------------- READY / SYNC ----------------

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} ({bot.user.id})")

    try:
        guild = discord.Object(id=GUILD_ID)

        synced = await bot.tree.sync(
            guild=guild
        )

        print(
            f"Synced {len(synced)} commands to guild {GUILD_ID}."
        )
    except Exception as error:
        print(f"Guild command sync failed: {error}")

        try:
            synced = await bot.tree.sync()
            print(
                f"Global sync completed: {len(synced)} commands."
            )
        except Exception as global_error:
            print(f"Global sync failed: {global_error}")


if not TOKEN or TOKEN == "YOUR_DISCORD_BOT_TOKEN":
    raise RuntimeError(
        "Set DISCORD_TOKEN in .env before starting the bot."
    )

bot.run(TOKEN)
