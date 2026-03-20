import discord
import os
import json
import asyncio
from datetime import datetime
import pytz
from collections import Counter
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = discord.Bot(intents=intents)

GUILD_ID = 1482792426992304359
DATA_FILE = "killerhunt_data.json"

ITEM_EMOJIS = {
    "Sniper": "<:Sniper:1484098474571206777>",
    "Revival Kit": "<:Revive:1484099033541640212>",
    "True Glass": "<:True_Glass:1484098420854755459>",
    "Team Reveal": "<:Team_Reveal:1484098361177936003>"
}

DAY_ROLES = {
    0: ["Interrogator"], 1: ["Interrogator"], 2: ["Interrogator"],
    3: ["Voter"], 4: ["Voter", "ClueHunter"], 5: ["Voter", "ClueHunter", "Shopper"], 6: []
}
ALL_DAILY_ROLES = ["Interrogator", "Voter", "ClueHunter", "Shopper"]
SHOP = {
    "Sniper": 150, "Revival Kit": 200, "True Glass": 120, "Team Reveal": 80
}

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
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

async def make_ghost(member):
    guild = member.guild
    for r in ALL_DAILY_ROLES:
        role = discord.utils.get(guild.roles, name=r)
        if role and role in member.roles:
            await member.remove_roles(role)
    if p := discord.utils.get(guild.roles, name="Participant"):
        if p in member.roles: await member.remove_roles(p)
    if g := discord.utils.get(guild.roles, name="Ghost"):
        if g not in member.roles: await member.add_roles(g)

class ConfirmGhostView(discord.ui.View):
    def __init__(self, action_func):
        super().__init__(timeout=30)
        self.action_func = action_func

    @discord.ui.button(label="Confirm (Become Ghost)", style=discord.ButtonStyle.red)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.action_func()
        await interaction.response.edit_message(content="✅ Confirmed. You are now a **Ghost**.", view=None)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.gray)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="❌ Cancelled.", view=None)
        self.stop()

async def manage_daily_roles():
    guild = bot.get_guild(GUILD_ID)
    if not guild: return
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    weekday = now.weekday()
    hour = now.hour
    in_window = 18 <= hour < 21
    roles_today = DAY_ROLES.get(weekday, [])
    participant_role = discord.utils.get(guild.roles, name="Participant")
    ghost_role = discord.utils.get(guild.roles, name="Ghost")
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

@bot.event
async def on_ready():
    print(f"✅ Killer Hunt Bot Online as {bot.user}")
    print("📦 Using discord from:", discord.__file__)
    print("📦 Version:", getattr(discord, "__version__", "Unknown"))
    
    # This is the modern, reliable way in py-cord
    await bot.sync_commands(guild_ids=[GUILD_ID])
    print("✅ Slash commands synced to your server!")
    
    while True:
        await manage_daily_roles()
        await asyncio.sleep(60)

# ====================== COMMANDS ======================
@bot.command(description="Reaper only - Force sync all slash commands")
async def sync(ctx: discord.ApplicationContext):
    if not discord.utils.get(ctx.author.roles, name="Reaper"):
        await ctx.respond("❌ Reaper only!", ephemeral=True)
        return
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    await ctx.respond("✅ All slash commands force-synced! Try /vote now.", ephemeral=False)

@bot.command(description="Vote on a team")
@discord.option("team", discord.Role, description="Team role")
@discord.option("points", int, description="Points (min 5)")
async def vote(ctx: discord.ApplicationContext, team: discord.Role, points: int):
    if not discord.utils.get(ctx.author.roles, name="Voter"):
        await ctx.respond("❌ You need the **Voter** role.", ephemeral=True)
        return
    if points < 5:
        await ctx.respond("❌ Minimum 5 points!", ephemeral=True)
        return
    if team in ctx.author.roles:
        await ctx.respond("❌ You cannot vote for your own team!", ephemeral=True)
        return
    uid = str(ctx.author.id)
    if uid not in data:
        data[uid] = {"points": 0, "inventory": {}, "votes": {}}
    if data[uid]["points"] < points:
        await ctx.respond("❌ Not enough points!", ephemeral=True)
        return
    if data[uid]["points"] - points == 0:
        async def do_vote():
            data[uid]["points"] = 0
            data[uid]["votes"][str(team.id)] = data[uid]["votes"].get(str(team.id), 0) + points
            save_data(data)
            await make_ghost(ctx.author)
        view = ConfirmGhostView(do_vote)
        await ctx.respond(f"⚠️ This vote will use **all** your points and turn you into a Ghost.\nConfirm?", view=view, ephemeral=True)
    else:
        data[uid]["points"] -= points
        data[uid]["votes"][str(team.id)] = data[uid]["votes"].get(str(team.id), 0) + points
        save_data(data)
        await ctx.respond(f"✅ Voted **{points}** points on {team.mention}!", ephemeral=False)

@bot.command(description="Buy an item")
@discord.option("item", str, description="Item name")
async def buy(ctx: discord.ApplicationContext, item: str):
    item = item.title()
    if item not in SHOP:
        await ctx.respond("❌ Item not found!", ephemeral=True)
        return
    if not discord.utils.get(ctx.author.roles, name="Shopper"):
        await ctx.respond("❌ Marketplace only open Saturday 6–9 PM!", ephemeral=True)
        return
    uid = str(ctx.author.id)
    if uid not in data:
        data[uid] = {"points": 0, "inventory": {}, "votes": {}}
    cost = SHOP[item]
    if data[uid]["points"] < cost:
        await ctx.respond(f"❌ Not enough points! Need {cost}.", ephemeral=True)
        return
    if data[uid]["points"] - cost == 0:
        async def do_buy():
            data[uid]["points"] = 0
            data[uid]["inventory"][item] = data[uid]["inventory"].get(item, 0) + 1
            save_data(data)
            await make_ghost(ctx.author)
        view = ConfirmGhostView(do_buy)
        await ctx.respond(f"⚠️ This purchase will use **all** your points and turn you into a Ghost.\nConfirm?", view=view, ephemeral=True)
    else:
        data[uid]["points"] -= cost
        data[uid]["inventory"][item] = data[uid]["inventory"].get(item, 0) + 1
        save_data(data)
        emoji = ITEM_EMOJIS.get(item, "")
        await ctx.respond(f"✅ {emoji} Bought **{item}** for {cost} points!", ephemeral=False)

# ====================== MESSAGE COMMANDS ======================
@bot.event
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

bot.run(os.getenv("TOKEN"))
