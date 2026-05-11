# notifier.py
from telegram import Bot
from telegram.error import TelegramError
import asyncio
from datetime import datetime
import nest_asyncio
nest_asyncio.apply()

class TelegramNotifier:
    def __init__(self, token, chat_id):
        self.bot = Bot(token=token)
        self.chat_id = chat_id

    async def send_message(self, text):
        try:
            await self.bot.send_message(chat_id=self.chat_id, text=text, parse_mode='HTML')
            print("📨 Message sent to Telegram")
        except TelegramError as e:
            print(f"⚠️ Telegram error: {e}")

    def send_sync(self, text):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.send_message(text))

    def format_report(self, results, top_n=10):
        sorted_res = sorted(results, key=lambda x: x['final_score'], reverse=True)
        top = sorted_res[:top_n]
        report = "<b>🔥 KUCOIN SCANNER REPORT 🔥</b>\n"
        report += f"🕒 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        report += f"📊 Total coins: {len(results)}\n"
        strong_buy = sum(1 for r in results if r['final_signal'] == 'STRONG_BUY')
        strong_sell = sum(1 for r in results if r['final_signal'] == 'STRONG_SELL')
        report += f"🟢 Strong Buy: {strong_buy}   🔴 Strong Sell: {strong_sell}\n\n"
        report += "<b>🏆 TOP 10 OPPORTUNITIES:</b>\n"
        for i, r in enumerate(top, 1):
            report += f"{i}. {r['final_signal']} <b>{r['symbol']}</b> (Score: {r['final_score']})\n"
            for tf, data in r['timeframes'].items():
                report += f"   └ {tf}: RSI={data['RSI']} | {data['Trend']}\n"
            report += "\n"
        return report
