import discord  # type: ignore
from discord import app_commands  # type: ignore
from discord.ext import commands  # type: ignore
import random
import json
import os
from dotenv import load_dotenv  # type: ignore
from flask import Flask # type: ignore

# Flaskアプリケーションのインスタンスを作成
app = Flask(__name__)

load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="/", intents=intents)

# グローバル変数: 
user_history = {} # 履歴（ユーザーごとに保持）
multi_draw_user_ids = {} # 抽選ユーザー対象記録（ユーザーごとに保持）
all_weapons = {} # 武器一覧
weapon_types = ["シューター", "ローラー", "チャージャー", "スピナー", "ブラスター", "マニューバー", "フデ", "スロッシャー", "シェルター", "ストリンガー", "ワイパー"]


# 武器読み込み関数
def load_weapons():
    with open("weapons_list.json", "r", encoding="utf-8") as f:
        return json.load(f)

# --- ビュー定義 ---
class MainMenu(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        global all_weapons
        all_weapons = load_weapons()

    @discord.ui.button(label="🎲 1つ引く", style=discord.ButtonStyle.primary)
    async def single_weapon(self, interaction: discord.Interaction, button: discord.ui.Button):
        await show_random_weapon(interaction)

    @discord.ui.button(label="🔍 武器種で絞って引く", style=discord.ButtonStyle.secondary)
    async def filter_by_type(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("武器種を選んでください：", view=WeaponTypeMenu(), ephemeral=True)

    @discord.ui.button(label="👥 複数人で引く", style=discord.ButtonStyle.success)
    async def multi_user_draw(self, interaction: discord.Interaction, button: discord.ui.Button):
        members = [m for m in interaction.guild.members if not m.bot]
        await interaction.response.send_message(
            "抽選するユーザーを選択してください：",
            view=UserSelectMenu(members),
            ephemeral=True
        )

    @discord.ui.button(label="🕘 履歴を表示する", style=discord.ButtonStyle.secondary)
    async def show_history(self, interaction: discord.Interaction, button: discord.ui.Button):
        history = user_history.get(interaction.user.id, [])[-10:][::-1]
        if not history:
            await interaction.response.send_message("📭 履歴が見つかりません。", ephemeral=True)
            return
        history_text = "\n".join([f"{str(idx+1) + '個前':>6}. {item}" for idx, item in enumerate(history)])
        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(label="メニューに戻る", style=discord.ButtonStyle.secondary, custom_id="menu"))
        await interaction.response.send_message(f"🗂 **最近の履歴（最大10件）**\n{history_text}", view=view, ephemeral=True)

class WeaponTypeMenu(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

        for wtype in weapon_types:
            self.add_item(WeaponTypeButton(wtype))

class WeaponTypeButton(discord.ui.Button):
    def __init__(self, wtype):
        super().__init__(label=wtype, style=discord.ButtonStyle.primary)
        self.wtype = wtype

    async def callback(self, interaction: discord.Interaction):
        weapons = [w for w in all_weapons if w["type"] == self.wtype]
        weapon = random.choice(weapons)
        await send_weapon_embed(interaction, weapon, weapons, filter_type=self.wtype)

class UserSelectMenu(discord.ui.View):
    def __init__(self, members: list[discord.Member]):
        super().__init__(timeout=None)
        options = [
            discord.SelectOption(label=member.display_name, value=str(member.id))
            for member in members[:25]
        ]
        self.select = discord.ui.Select(
            placeholder="ユーザーを選択（最大25人）",
            min_values=1,
            max_values=len(options),
            options=options
        )
        self.select.callback = self.select_callback  # コールバックをバインド
        self.add_item(self.select)
        self.add_item(MultiDrawConfirmButton())

    async def select_callback(self, interaction: discord.Interaction):
        # 選択時に特に何もせず確認ボタンで処理
        await interaction.response.defer()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # 初期表示でのオプション更新
        members = [m for m in interaction.guild.members if not m.bot]
        self.select.options = [discord.SelectOption(label=member.display_name, value=str(member.id)) for member in members[:25]]
        return True

class MultiDrawConfirmButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="抽選開始", style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        user_weapons = {}
        view: UserSelectMenu = self.view  # type: ignore
        user_ids = [int(uid) for uid in view.select.values]
        multi_draw_user_ids[interaction.user.id] = user_ids
        for uid in user_ids:
            user_weapons[uid] = random.choice(all_weapons)

        await send_multi_weapon_embed(interaction, user_weapons, all_weapons)


# --- 共通関数 ---
async def send_weapon_embed(interaction: discord.Interaction, weapon, weapons, filter_type=None):
    title_prefix = "🎯 武器抽選結果"
    if filter_type:
        title_prefix = f"🎯 武器抽選結果（タイプ: {filter_type}）"
    embed = discord.Embed(
        title=title_prefix,
        description=f"**{weapon['name']}**\nサブ: {weapon['subName']}\nスペシャル: {weapon['specialName']}\nスペシャルポイント: {weapon['specialPoint']}",
        color=discord.Color.blurple()
    )
    image_path = os.path.join("images", weapon["image"])
    if not os.path.isfile(image_path):
        await interaction.response.send_message(f"⚠️ 画像が見つかりません: `{image_path}`", ephemeral=True)
        return
    file = discord.File(image_path, filename="weapon.png")
    embed.set_image(url="attachment://weapon.png")
    user_history.setdefault(interaction.user.id, []).append(weapon['name'])
    view = discord.ui.View(timeout=None)
    view.add_item(discord.ui.Button(label="もう一度引く", style=discord.ButtonStyle.primary, custom_id="weapon_filter_retry" if filter_type else "retry"))
    view.add_item(discord.ui.Button(label="メニューに戻る", style=discord.ButtonStyle.secondary, custom_id="menu"))
    await interaction.response.send_message(file=file, embed=embed, view=view, ephemeral=True)

async def send_multi_weapon_embed(interaction: discord.Interaction, user_weapons: dict, weapons, filter_type=None):
    embeds = []
    files = []
    for uid, weapon in user_weapons.items():
        user = interaction.guild.get_member(uid)
        user_history.setdefault(uid, []).append(weapon['name'])
        embed = discord.Embed(
            title=f"{user.display_name} の武器抽選結果",
            description=f"**{weapon['name']}**\nサブ: {weapon['subName']}\nスペシャル: {weapon['specialName']}\nスペシャルポイント: {weapon['specialPoint']}",
            color=discord.Color.green()
        )
        image_path = os.path.join("images", weapon["image"])
        if os.path.isfile(image_path):
            file = discord.File(image_path, filename=f"weapon_{uid}.png")
            embed.set_image(url=f"attachment://weapon_{uid}.png")
            files.append(file)
        embeds.append(embed)

    temp_view = discord.ui.View(timeout=None)
    temp_view.add_item(discord.ui.Button(label="もう一度引く", style=discord.ButtonStyle.primary, custom_id="multi_retry"))
    temp_view.add_item(discord.ui.Button(label="メニューに戻る", style=discord.ButtonStyle.secondary, custom_id="menu"))

    await interaction.response.send_message(
        content="🎯 **複数人武器抽選結果（全体公開）**",
        embeds=embeds,
        files=files,
        view=temp_view,
        ephemeral=False
    )

async def show_random_weapon(interaction: discord.Interaction):
    weapon = random.choice(all_weapons)
    await send_weapon_embed(interaction, weapon, all_weapons)

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if not interaction.type == discord.InteractionType.component:
        return

    if interaction.data["custom_id"] == "retry":
        new_weapon = random.choice(all_weapons)
        await send_weapon_embed(interaction, new_weapon, all_weapons)

    elif interaction.data["custom_id"] == "weapon_filter_retry":
        history = user_history.get(interaction.user.id, [])
        if not history:
            await interaction.response.send_message("履歴がないため再抽選できません。", ephemeral=True)
            return
        last_weapon_name = history[-1]
        target_weapon = next((w for w in all_weapons if w["name"] == last_weapon_name), None)
        if not target_weapon:
            await interaction.response.send_message("前回の武器情報が見つかりません。", ephemeral=True)
            return
        same_type_weapons = [w for w in all_weapons if w["type"] == target_weapon["type"]]
        new_weapon = random.choice(same_type_weapons)
        await send_weapon_embed(interaction, new_weapon, same_type_weapons, filter_type=target_weapon["type"])

    elif interaction.data["custom_id"] == "menu":
        await interaction.response.send_message("🔰 **スプラトゥーン3 武器抽選メニュー**", view=MainMenu(), ephemeral=True)
        
    elif interaction.data["custom_id"] == "multi_retry":
        user_weapons = {}
        for uid in multi_draw_user_ids[interaction.user.id]:
            user_weapons[uid] = random.choice(all_weapons)

        await send_multi_weapon_embed(interaction, user_weapons, all_weapons)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Bot is ready. Logged in as {bot.user}")

@bot.tree.command(name="weapon", description="スプラトゥーン3の武器抽選メニューを表示します")
async def weapon(interaction: discord.Interaction):
    await interaction.response.send_message("🔰 **スプラトゥーン3 武器抽選メニュー**", view=MainMenu(), ephemeral=True)

# Flaskサーバーを指定したポートで起動
if __name__ == "__main__":
    from threading import Thread

    def run_flask():
        app.run(host='0.0.0.0', port=5000)

    # Flaskサーバーを別スレッドで起動
    flask_thread = Thread(target=run_flask)
    flask_thread.start()

bot.run(TOKEN)
