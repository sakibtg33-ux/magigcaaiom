import os
import asyncio
import tempfile
import httpx
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ================= লগিং সেটআপ =================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ================= কনফিগারেশন =================
TG_BOT_TOKEN = "8426545218:AAFKYlHjZwUlLrgXVPyDhRr0cMreRtPWwqw"   # @BotFather থেকে নিন
BASE_URL = "https://api.magica.com/api"
# =============================================

user_api_keys = {}
active_generations = {}

async def generate_video(prompt: str, api_key: str, progress_message, update: Update) -> str:
    async with httpx.AsyncClient(timeout=60.0) as client:
        headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {api_key}'}
        payload = {
            "nodeType": "gemini_omni_flash",
            "input": {"prompt": prompt, "duration": 10, "aspect_ratio": "9:16"},
            "subModelId": "gemini-omni-flash-text-to-video"
        }
        start_res = await client.post(f"{BASE_URL}/v1/nodes/gemini_omni_flash/run", json=payload, headers=headers)
        start_res.raise_for_status()
        run_id = start_res.json()['runId']
        await progress_message.edit_text("🔄 ভিডিও রেন্ডার হচ্ছে... 20%")
        step = 0
        while True:
            poll_res = await client.get(f"{BASE_URL}/v1/nodes/runs/{run_id}", headers=headers)
            poll_res.raise_for_status()
            data = poll_res.json()
            status = data['status']
            if status == 'COMPLETED':
                await progress_message.edit_text("✅ ভিডিও প্রস্তুত! ডাউনলোড হচ্ছে... 100%")
                return data['output']['result'][0]
            elif status == 'FAILED':
                raise Exception(data.get('error', 'Unknown error'))
            step += 1
            progress = min(20 + step * 20, 90)
            await progress_message.edit_text(f"🔄 ভিডিও রেন্ডার হচ্ছে... {progress}%")
            await asyncio.sleep(5)

async def handle_generation(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str):
    user_id = update.effective_user.id
    api_key = user_api_keys.get(user_id)
    if not api_key:
        await update.message.reply_text("❌ API key পাওয়া যায়নি। /setapi YOUR_API_KEY দিয়ে সেট করুন।", parse_mode='HTML')
        return
    try:
        progress_msg = await update.message.reply_text("⏳ ভিডিও তৈরি হচ্ছে... 0%")
        video_url = await generate_video(prompt, api_key, progress_msg, update)
        await progress_msg.edit_text("📥 ভিডিও ডাউনলোড হচ্ছে... 95%")
        async with httpx.AsyncClient(timeout=120.0) as client:
            video_response = await client.get(video_url)
            video_response.raise_for_status()
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as tmp_file:
                tmp_file.write(video_response.content)
                tmp_path = tmp_file.name
        keyboard = [[InlineKeyboardButton("📥 সরাসরি ডাউনলোড লিংক", url=video_url)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        with open(tmp_path, 'rb') as video_file:
            await update.message.reply_document(
                document=video_file,
                filename="video_10s_9x16.mp4",
                caption="✅ আপনার ভিডিও প্রস্তুত! (১০ সেকেন্ড, ৯:১৬, ৭২০পি)\nনিচের বাটনে ক্লিক করে সরাসরি ডাউনলোড করতে পারেন।",
                reply_markup=reply_markup
            )
        await progress_msg.edit_text("✅ সম্পূর্ণ! ভিডিও উপরে দেখুন।")
        os.unlink(tmp_path)
    except Exception as e:
        await progress_msg.edit_text(f"❌ দুঃখিত, ভিডিও জেনারেট করতে সমস্যা হয়েছে:\n<code>{str(e)}</code>", parse_mode='HTML')
    finally:
        if user_id in active_generations:
            del active_generations[user_id]

# ================= কমান্ড হ্যান্ডলার =================
async def set_api(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("⚠️ ব্যবহার: /setapi আপনার_এপিআই_কী", parse_mode='HTML')
        return
    user_api_keys[update.effective_user.id] = args[0].strip()
    await update.message.reply_text("✅ API key সেট হয়েছে। এখন ভিডিও জেনারেট করতে পারেন।")

# 🔥 ফিক্সড: এইচটিএমএল ট্যাগ "api_key" সরিয়ে &lt;API_KEY&gt; ব্যবহার করা হয়েছে
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("✅ Start command called by user: %s", update.effective_user.id)
    await update.message.reply_text(
        "👋 ভিডিও জেনারেশন বট!\n\n"
        "যেকোনো টেক্সট লিখে পাঠান, আমি ১০ সেকেন্ডের ৯:১৬ ভিডিও বানিয়ে ডকুমেন্ট আকারে দেব।\n\n"
        "<b>কমান্ড:</b>\n"
        "/start – শুরু\n"
        "/help – সাহায্য\n"
        "/status – চলমান কাজ\n"
        "/setapi &lt;API_KEY&gt; – API সেট করুন (প্রথমে এটি করুন)",
        parse_mode='HTML'
    )

# 🔥 ফিক্সড: এইচটিএমএল ট্যাগ সরানো হয়েছে
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 <b>গাইড:</b>\n"
        "1. /setapi YOUR_API_KEY দিন।\n"
        "2. যেকোনো প্রম্পট লিখুন (বাংলা/ইংরেজি)।\n"
        "3. আমি ভিডিও তৈরি করে ডকুমেন্ট হিসেবে পাঠাব এবং ডাউনলোড বাটন থাকবে।",
        parse_mode='HTML'
    )

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in active_generations:
        await update.message.reply_text("⏳ বর্তমানে একটি ভিডিও জেনারেট হচ্ছে। দয়া করে অপেক্ষা করুন।")
    else:
        await update.message.reply_text("✅ কোনো কাজ চলছে না।")

async def handle_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    prompt = update.message.text
    if user_id in active_generations:
        await update.message.reply_text("⚠️ আপনি আগে থেকেই একটি ভিডিও জেনারেট করছেন! দয়া করে আগেরটি শেষ হোক।")
        return
    if not user_api_keys.get(user_id):
        await update.message.reply_text("⚠️ আগে /setapi YOUR_API_KEY দিন।", parse_mode='HTML')
        return
    active_generations[user_id] = {'prompt': prompt}
    await handle_generation(update, context, prompt)

def main():
    app = Application.builder().token(TG_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("setapi", set_api))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_prompt))
    
    logger.info("🤖 বট চালু হয়েছে! এখন টেলিগ্রামে গিয়ে প্রম্পট দিন।")
    print("🤖 বট চালু হয়েছে! এখন টেলিগ্রামে গিয়ে প্রম্পট দিন।")
    app.run_polling()

if __name__ == "__main__":
    main()
