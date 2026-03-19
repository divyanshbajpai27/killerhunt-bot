import discord
from discord import app_commands
import asyncio
from datetime import datetime
import pytz
import json
import os
from collections import Counter

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

GUILD_ID = 1482792426992304359
DATA_FILE = "killerhunt_data.json"

# ====================== CUSTOM EMOJIS ======================
ITEM_EMOJIS = {
    "Sniper": "<:Sniper:1484098474571206777>",
    "Revival Kit": "<:Revive:1484099033541640212>",
    "True Glass": "<:True_Glass:1484098420854755459>",
    "Team Reveal": "<:Team_Reveal:1484098361177936003>"
}

# ====================== DAILY ROLES ======================
DAY_ROLES = {
    0: ["Interrogator"], 1: ["Interrogator"], 2: ["Interrogator"],
    3: ["Voter"], 4: ["Voter", "ClueHunter"], 5: ["Voter", "ClueHunter", "Shopper"], 6: []
}
ALL_DAILY_ROLES = ["Interrogator", "Voter", "ClueHunter", "Shopper"]

# ====================== MARKETPLACE ======================
SHOP = {
    "Sniper": {"cost": 150},
    "Revival Kit": {"cost": 200},
    "True Glass": {"cost": 120},
    "Team Reveal": {"cost": 80}
}

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            raw = json.load(f)
            for uid in raw:
                if isinstance(raw[uid].get("inventory"), list):
                    raw[uid]["inventory"] = dict(Counter(raw[uid]["inventory"]))
                if "votes" not in raw[uid]:
                    raw[uid]["votes"] = {}
            return raw
    return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

data = load_data()

ghost_role_name = "Ghost"

async def make_ghost(member):
    guild = member.guild
    participant_role = discord.utils.get(guild.roles, name="Participant")
    ghost_role = discord.utils.get(guild.roles, name=ghost_role_name)
    for rname in ALL_DAILY_ROLES:
        role = discord.utils.get(guild.roles, name=rname)
        if role and role in member.roles:
            await member.remove_roles(role)
    if participant_role and participant_role in member.roles:
        await member.remove_roles(participant_role)
    if ghost_role and ghost_role not in member.roles:
        await member.add_roles(ghost_role)

class ConfirmGhostView(discord.ui.View):
    def __init__(self, action_func):
        super().__init__(timeout=30)
        self.action_func = action_func

    @discord.ui.button(label="Confirm (Become Ghost)", style=discord.ButtonStyle.red)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.action_func()
        await interaction.response.edit_message(content="✅ Action confirmed. You are now a **Ghost**.", view=None)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.gray)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ Cancelled.", view=None)
        self.stop()

# ====================== ROLE MANAGER ======================
async def manage_daily_roles():
    guild = client.get_guild(GUILD_ID)
    if not guild: return
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    weekday = now.weekday()
    hour = now.hour
    in_window = 18 <= hour < 21
    roles_today = DAY_ROLES.get(weekday, [])

    participant_role = discord.utils.get(guild.roles, name="Participant")
    ghost_role = discord.utils.get(guild.roles, name=ghost_role_name)
    if not participant_role: return

    to_add = []
    to_remove = []

    for member in guild.members:
        if participant_role not in member.roles: continue
        if ghost_role and ghost_role in member.roles: continue

        if in_window:
            for rname in roles_today:
                role = discord.utils.get(guild.roles, name=rname)
                if role and role not in member.roles:
                    to_add.append((member, role))
        else:
            for rname in ALL_DAILY_ROLES:
                role = discord.utils.get(guild.roles, name=rname)
                if role and role in member.roles:
                    to_remove.append((member, role))

    for i, (member, role) in enumerate(to_add):
        await member.add_roles(role, reason="Daily Killer Hunt role")
        await asyncio.sleep(0.35 if i % 8 != 0 else 1.2)
    for i, (member, role) in enumerate(to_remove):
        await member.remove_roles(role, reason="Daily role window ended")
        await asyncio.sleep(0.35 if i % 8 != 0 else 1.2)

# ====================== BOT START ======================
@client.event
async def on_ready():
    print(f"✅ Killer Hunt Bot Online as {client.user}")
    await tree.sync(guild=discord.Object(id=GUILD_ID))
    print("✅ Slash commands synced!")
    while True:
        await manage_daily_roles()
        await asyncio.sleep(60)

# ====================== EPHEMERAL VOTE ======================
@tree.command(name="vote", description="Vote on a team")
@app_commands.describe(team="Team role to vote for", points="Points to spend")
async def vote(interaction: discord.Interaction, team: discord.Role, points: int):
    if not discord.utils.get(interaction.user.roles, name="Voter"):
        await interaction.response.send_message("❌ You need the **Voter** role.", ephemeral=True)
        return
    if points < 5:
        await interaction.response.send_message("❌ Minimum 5 points!", ephemeral=True)
        return
    if team in interaction.user.roles:
        await interaction.response.send_message("❌ You cannot vote for your own team!", ephemeral=True)
        return

    uid = str(interaction.user.id)
    if uid not in data:
        data[uid] = {"points": 0, "inventory": {}, "votes": {}}
    if "votes" not in data[uid]:
        data[uid]["votes"] = {}

    if data[uid]["points"] < points:
        await interaction.response.send_message("❌ Not enough points!", ephemeral=True)
        return

    if data[uid]["points"] - points == 0:
        async def do_vote():
            data[uid]["points"] = 0
            data[uid]["votes"][str(team.id)] = data[uid]["votes"].get(str(team.id), 0) + points
            save_data(data)
            await make_ghost(interaction.user)

        view = ConfirmGhostView(do_vote)
        await interaction.response.send_message(
            f"⚠️ This vote will use **all** your points and turn you into a Ghost.\nConfirm?", 
            view=view, 
            ephemeral=True
        )
    else:
        data[uid]["points"] -= points
        data[uid]["votes"][str(team.id)] = data[uid]["votes"].get(str(team.id), 0) + points
        save_data(data)
        await interaction.response.send_message(f"✅ Voted **{points}** points on {team.mention}!", ephemeral=False)

# ====================== EPHEMERAL BUY ======================
@tree.command(name="buy", description="Buy an item")
@app_commands.describe(item="Item name")
async def buy(interaction: discord.Interaction, item: str):
    item = item.title()
    if item not in SHOP:
        await interaction.response.send_message("❌ Item not found!", ephemeral=True)
        return
    if not discord.utils.get(interaction.user.roles, name="Shopper"):
        await interaction.response.send_message("❌ Marketplace only open Saturday 6–9 PM!", ephemeral=True)
        return

    uid = str(interaction.user.id)
    if uid not in data:
        data[uid] = {"points": 0, "inventory": {}, "votes": {}}
    cost = SHOP[item]["cost"]
    if data[uid]["points"] < cost:
        await interaction.response.send_message(f"❌ Not enough points! Need {cost}.", ephemeral=True)
        return

    if data[uid]["points"] - cost == 0:
        async def do_buy():
            data[uid]["points"] = 0
            data[uid]["inventory"][item] = data[uid]["inventory"].get(item, 0) + 1
            save_data(data)
            await make_ghost(interaction.user)

        view = ConfirmGhostView(do_buy)
        await interaction.response.send_message(
            f"⚠️ This purchase will use **all** your points and turn you into a Ghost.\nConfirm?", 
            view=view, 
            ephemeral=True
        )
    else:
        data[uid]["points"] -= cost
        data[uid]["inventory"][item] = data[uid]["inventory"].get(item, 0) + 1
        save_data(data)
        emoji = ITEM_EMOJIS.get(item, "")
        await interaction.response.send_message(f"✅ {emoji} Bought **{item}** for {cost} points!", ephemeral=False)

# ====================== PREFIX COMMANDS (kept for convenience) ======================
@client.event
async def on_message(message):
    if message.author.bot: return
    content = message.content.lower()

    if content == "!points":
        uid = str(message.author.id)
        pts = data.get(uid, {}).get("points", 0)
        await message.channel.send(f"**{message.author.name}**, you have **{pts}** points.")

    if content == "!inventory":
        uid = str(message.author.id)
        inv = data.get(uid, {}).get("inventory", {})
        if not inv:
            await message.channel.send(f"{message.author.mention} items: **empty**")
        else:
            lines = [f"{ITEM_EMOJIS.get(item, '•')} {item} **x{count}**" for item, count in inv.items()]
            await message.channel.send(f"{message.author.mention} items:\n" + "\n".join(lines))

    if content == "!myvotes":
        uid = str(message.author.id)
        votes = data.get(uid, {}).get("votes", {})
        if not votes:
            await message.channel.send(f"{message.author.mention} has not voted yet.")
        else:
            guild = message.guild
            lines = []
            for role_id, pts in votes.items():
                role = guild.get_role(int(role_id))
                name = role.mention if role else f"Unknown"
                lines.append(f"{name} — **{pts}** points")
            await message.channel.send(f"{message.author.mention}'s votes:\n" + "\n".join(lines))

    if content == "!votetally" and discord.utils.get(message.author.roles, name="Reaper"):
        tally = {}
        for uid, player_data in data.items():
            for role_id, pts in player_data.get("votes", {}).items():
                tally[role_id] = tally.get(role_id, 0) + pts
        if not tally:
            await message.channel.send("No votes yet.")
        else:
            guild = message.guild
            sorted_tally = sorted(tally.items(), key=lambda x: x[1], reverse=True)
            lines = []
            for role_id, pts in sorted_tally:
                role = guild.get_role(int(role_id))
                name = role.mention if role else f"Unknown"
                lines.append(f"{name} — **{pts}** total points")
            await message.channel.send("**Current Vote Tally:**\n" + "\n".join(lines))

    if content.startswith("!givepoints ") and discord.utils.get(message.author.roles, name="Reaper"):
        try:
            parts = content.split()
            user = message.mentions[0]
            amount = int(parts[-1])
            uid = str(user.id)
            if uid not in data: data[uid] = {"points": 0, "inventory": {}, "votes": {}}
            data[uid]["points"] += amount
            save_data(data)
            await message.channel.send(f"✅ Gave {amount} points to {user.mention}")
        except:
            await message.channel.send("Usage: `!givepoints @player 500`")

    if content.startswith("!codexstrike ") and discord.utils.get(message.author.roles, name="Reaper"):
        try:
            user = message.mentions[0]
            reason = " ".join(content.split()[2:]) or "No reason"
            await make_ghost(user)
            await message.channel.send(f"**SHADOW CODEX ACTIVATED**\n**Target:** {user.mention}\n**Reason:** {reason}")
        except:
            await message.channel.send("Usage: `!codexstrike @player [reason]`")

client.run(os.getenv("TOKEN"))