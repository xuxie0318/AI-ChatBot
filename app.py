import os
import discord
import asyncio
from discord.ext import commands
from google import genai
from sqlalchemy import create_engine, text

# 讀取設定
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
API_KEY = os.getenv('GEMINI_API_KEY')
DB_URL = os.getenv('DATABASE_URL')
CHAR_NAME = os.getenv('CHARACTER_NAME', '機器人')

# 資料庫連線池設定
engine = create_engine(
    DB_URL,
    connect_args={"sslmode": "require"},
    pool_pre_ping=True
)

# 自動建立通用資料表
def init_db():
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS chat_history (
                id SERIAL PRIMARY KEY,
                bot_name TEXT,
                user_id TEXT,
                msg TEXT,
                reply TEXT,
                ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
init_db()

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)
client = genai.Client(api_key=API_KEY)

@bot.event
async def on_message(message):
    if message.author == bot.user: return
    
    # 統一過濾器：清洗 Markdown
    def clean_text(text):
        for char in ['*', '#', '`', '_', '[', ']', '(', ')', '~', '>']:
            text = text.replace(char, '')
        return text

    with engine.begin() as conn:
        # 讀取該角色最近的 3 筆歷史
        rows = conn.execute(
            text("SELECT msg, reply FROM chat_history WHERE bot_name = :name ORDER BY ts DESC LIMIT 3"),
            {"name": CHAR_NAME}
        ).fetchall()
        context = "\n".join([f"紀錄: {r[0]}\n回覆: {r[1]}" for r in rows[::-1]])
        
        system_prompt = (f"你現在是 {CHAR_NAME}。個性：{os.getenv('CHARACTER_TRAITS')}。"
                         "規則：嚴禁透露是AI，嚴禁使用任何 Markdown 格式，回覆請保持口語與簡潔。")
        
        response = client.models.generate_content(
            model='gemini-3.1-flash-lite',
            contents=f"上下文:\n{context}\n\n訊息: {message.content}",
            config={"system_instruction": system_prompt}
        )
        
        reply = clean_text(response.text)
        
        # 儲存紀錄
        conn.execute(
            text("INSERT INTO chat_history (bot_name, user_id, msg, reply) VALUES (:name, :uid, :msg, :rep)"),
            {"name": CHAR_NAME, "uid": str(message.author.id), "msg": message.content, "rep": reply}
        )

    await message.channel.send(reply)

bot.run(TOKEN)