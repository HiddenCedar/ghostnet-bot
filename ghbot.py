"""
GhostNet BIN Search Bot - ULTIMATE EDITION
All Features: Admin, Monetization, User Features, Technical
"""
import csv
import logging
import os
import re
import time
import requests
import subprocess
import threading
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler

# Configuration
TELEGRAM_TOKEN = "7733679875:AAGQec-kzXTHG7o70KNF1T1vdAKSaGwb_lQ"
BOT_NAME = "GhostNet BIN Bot"
DEVELOPER = "silverfield"
CREATOR_ID = 5826390461
START_TIME = time.time()

# Payment
MONERO_ADDRESS = "82eDyheDkTZLPUBMX4nhrcbxBDJkHsNprJbebADwmjkj75uPRyCzTcdeHzNNPL6KRjXSdUiKtANNTS3e9uBzU21BHGY9W8K"
PRO_PRICE_USD = 15
FREE_SEARCH_LIMIT = 5
MIN_XMR = 0.006

# Setup
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Load BIN DB
BIN_DB = {}
# CSV - use URL for production
CSV_PATH = os.environ.get("BIN_CSV", "https://raw.githubusercontent.com/HiddenCedar/ghostnet-bot/master/bin-list-data.csv")

def load_bin_database():
    global BIN_DB
    try:
        # Check if CSV_PATH is a URL
        if CSV_PATH.startswith('http'):
            logger.info("Downloading BIN database from URL...")
            import io
            resp = requests.get(CSV_PATH, timeout=60)
            resp.raise_for_status()
            f = io.StringIO(resp.text)
            reader = csv.DictReader(f)
        else:
            with open(CSV_PATH, 'r', encoding='utf-8', errors='ignore') as f:
                reader = csv.DictReader(f)
        
        for row in reader:
            bin_num = row.get('BIN', '').strip()
            if bin_num and len(bin_num) >= 6:
                key = bin_num[:6]
                if key not in BIN_DB:
                    BIN_DB[key] = {
                        "scheme": row.get('Brand', 'N/A').upper(),
                        "type": row.get('Type', 'N/A').upper(),
                        "brand": row.get('Brand', 'N/A').upper(),
                        "category": row.get('Category', ''),
                        "country": {
                            "name": row.get('CountryName', 'N/A'),
                            "alpha2": row.get('isoCode2', 'N/A'),
                            "emoji": get_emoji(row.get('isoCode2', '')),
                        },
                        "bank": {
                            "name": row.get('Issuer', 'N/A'),
                            "phone": row.get('IssuerPhone', 'N/A'),
                            "url": row.get('IssuerUrl', 'N/A'),
                            "city": "N/A",
                        }
                    }
        logger.info(f"Loaded {len(BIN_DB)} BINs!")
    except Exception as e:
        logger.error(f"CSV error: {e}")
        BIN_DB = {}

def get_emoji(cc):
    m = {"US": "🇺🇸", "GB": "🇬🇧", "DE": "🇩🇪", "FR": "🇫🇷", "CN": "🇨🇳", "JP": "🇯🇵", "KR": "🇰🇷", "IN": "🇮🇳", "BR": "🇧🇷", "CA": "🇨🇦", "AU": "🇦🇺", "RU": "🇷🇺", "NL": "🇳🇱"}
    return m.get(cc.upper(), "")

logger.info("Loading...")
load_bin_database()

# Managers
class CreatorManager:
    def __init__(self):
        self.creator_id = CREATOR_ID
        self.blocked_users = set()
    
    def is_creator(self, uid): return uid == self.creator_id
    def block_user(self, uid): self.blocked_users.add(uid)
    def unblock_user(self, uid): self.blocked_users.discard(uid)
    def is_blocked(self, uid): return uid in self.blocked_users

CREATOR = CreatorManager()

class LocalAI:
    def __init__(self):
        self.fraud_kw = ["fake", "fraud", "hack", "scam", "test"]
    
    def analyze(self, tx):
        if len(tx) != 64: return True, "Invalid length"
        if not re.match(r'^[a-fA-F0-9]+$', tx): return True, "Invalid chars"
        for kw in self.fraud_kw:
            if kw in tx.lower(): return True, f"Keyword: {kw}"
        return False, "OK"

AI = LocalAI()

class UserManager:
    def __init__(self):
        self.users = {}
        self.used_txs = set()
        self.total_revenue = 0.0
    
    def get(self, uid):
        if uid not in self.users:
            self.users[uid] = {
                "searches": 0, "pro": False, "pro_expires": 0,
                "history": [], "favorites": [], "tx_hashes": []
            }
        return self.users[uid]
    
    def can_search(self, uid):
        if CREATOR.is_creator(uid): return True
        u = self.get(uid)
        return u["pro"] and u["pro_expires"] > time.time() or u["searches"] < FREE_SEARCH_LIMIT
    
    def inc_search(self, uid, bin_num):
        if CREATOR.is_creator(uid): return
        u = self.get(uid)
        u["searches"] += 1
        u["history"].append({"bin": bin_num, "time": time.time()})
        if len(u["history"]) > 50: u["history"] = u["history"][-50:]
    
    def add_pro(self, uid, tx, amt):
        u = self.get(uid)
        u["pro"] = True
        u["pro_expires"] = time.time() + 31536000
        u["searches"] = 0
        u["tx_hashes"].append(tx)
        if amt > 0: self.total_revenue += amt
    
    def is_pro(self, uid):
        u = self.get(uid)
        return u["pro"] and u["pro_expires"] > time.time()
    
    def add_favorite(self, uid, bin_num):
        u = self.get(uid)
        if bin_num not in u["favorites"]:
            u["favorites"].append(bin_num)
    
    def rem_favorite(self, uid, bin_num):
        u = self.get(uid)
        if bin_num in u["favorites"]:
            u["favorites"].remove(bin_num)
    
    def get_history(self, uid):
        return self.get(uid).get("history", [])[-10:][::-1]
    
    def get_favorites(self, uid):
        return self.get(uid).get("favorites", [])
    
    def is_tx_used(self, tx): return tx in self.used_txs
    def mark_tx(self, tx, uid):
        self.used_txs.add(tx)
        self.get(uid)["tx_hashes"].append(tx)
    def remove_pro(self, uid):
        if uid in self.users: self.users[uid]["pro"] = False

USERS = UserManager()

class ServerStats:
    def __init__(self):
        self.total = 0
        self.local = 0
        self.api = 0
    def rec(self, local): self.total += 1; self.local += 1 if local else 0

STATS = ServerStats()

# Monero Checker
class MoneroChecker:
    def check(self, tx):
        if not tx or len(tx) != 64: return {"valid": False, "reason": "Invalid hash"}
        if not re.match(r'^[a-fA-F0-9]{64}$', tx): return {"valid": False, "reason": "Bad format"}
        if USERS.is_tx_used(tx): return {"valid": False, "reason": "FRAUD: Used!"}
        
        try:
            r = requests.get(f"https://xmr.to/api/v2/search/{tx}", headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            if r.status_code == 200:
                d = r.json()
                if d.get("status") == "success":
                    td = d.get("data", {})
                    if td.get("dest_address", "").lower() != MONERO_ADDRESS.lower():
                        return {"valid": False, "reason": "Wrong address!"}
                    amt = float(td.get("amount", 0)) / 1e12
                    conf = td.get("confirmations", 0)
                    if amt < MIN_XMR: return {"valid": False, "reason": f"Low: {amt} XMR"}
                    if conf < 1: return {"valid": False, "reason": "Not confirmed"}
                    return {"valid": True, "amount": amt, "confirmations": conf}
        except: pass
        return {"valid": False, "reason": "Verify failed"}

MONERO = MoneroChecker()

# BIN Lookup
APIS = ["https://lookup.binlist.net/{}"]

def lookup(url, bin_num, to=3):
    try:
        r = requests.get(url.format(bin_num), headers={"User-Agent": "Mozilla/5.0"}, timeout=to)
        if r.status_code == 200: return r.json()
    except: pass
    return None

def bin_lookup(bin_num):
    cb = re.sub(r'\D', '', bin_num)[:8]
    if len(cb) < 6: return None
    
    key = cb[:6]
    if key in BIN_DB:
        STATS.rec(True)
        return BIN_DB[key]
    
    for l in [8, 7]:
        if len(cb) >= l:
            k = cb[:l]
            if k in BIN_DB:
                STATS.rec(True)
                return BIN_DB[k]
    
    for api in APIS:
        d = lookup(api, cb)
        if d:
            STATS.rec(False)
            return d
    
    return None

def format_bin(d, bin_num):
    scheme = d.get("scheme", "N/A")
    typ = d.get("type", "N/A")
    brand = d.get("brand", "N/A")
    cat = d.get("category", "")
    
    c = d.get("country", {})
    cname = c.get("name", "N/A")
    ccode = c.get("alpha2", "N/A")
    emoji = c.get("emoji", "")
    
    b = d.get("bank", {})
    bname = b.get("name", "N/A")
    bphone = b.get("phone", "N/A")
    burl = b.get("url", "N/A")
    
    cs = f"\n🏷️ **Category:** {cat}" if cat else ""
    
    return f"""🔍 **BIN: {bin_num}**

💳 **Type:** {typ}
💰 **Scheme:** {scheme}
🏷️ **Brand:** {brand}{cs}

🌍 **Country:** {emoji} {cname} ({ccode})

🏦 **Bank:**
• {bname}
• 📞 {bphone}
• 🌐 {burl}"""

# Themes
def creator_theme():
    return f"""
🌟═══════════════════════════════════════🌟
       👑 GHOSTNET CREATOR PANEL 👑
🌟═══════════════════════════════════════🌟

🔥 **WELCOME CREATOR!**

📊 **Quick Stats:**
• BINs: {len(BIN_DB):,}
• Users: {len(USERS.users)}
• Total Queries: {STATS.total}
• Local Hits: {STATS.local}
• Revenue: {USERS.total_revenue:.4f} XMR

🛠️ **Admin Commands:**
/creator - This panel
/stats - Full stats
/block [id] - Block user
/unblock [id] - Unblock  
/addpro [id] - Give PRO
/removepro [id] - Remove PRO
/ban [id] - Ban user
/broadcast [msg] - Broadcast
/search [bin] - Search BIN
/users - User list

👤 **User Tools:**
/history - Search history
/favorites - Saved BINs
/searchall [bins] - Bulk search

💎 **Your Status:** 👑 CREATOR
══════════════════════════════════════════
"""

def user_theme(is_pro):
    s = "🟢 PRO" if is_pro else f"🔵 Free ({FREE_SEARCH_LIMIT - USERS.get(USERS.get(0, {}).get('searches', 0))} left)"
    return f"""👋 **{BOT_NAME}!**

Status: {s}

Commands:
/start /help /cmds
/dev /about /server
/pro /verify
/history - Your searches
/favorites - Saved BINs

BIN: `!bin [BIN]`
Bulk: `!searchall 457173 541234`

Dev: @{DEVELOPER}"""

def pro_msg():
    return f"""🔒 **PRO UPGRADE**

Free: {FREE_SEARCH_LIMIT} searches
Pro: Unlimited + History + Favorites

Price: ${PRO_PRICE_USD} USD
Amount: {MIN_XMR} XMR

━━━━━━━━━━━━━━━━━━━━━━━━━"""

def stats_msg():
    up = int(time.time() - START_TIME)
    h, m = up // 3600, (up % 3600) // 60
    
    return f"""📊 **Statistics**

**Database:** {len(BIN_DB):,} BINs

**Queries:**
• Total: {STATS.total}
• Local: {STATS.local}
• API: {STATS.api}

**Users:**
• Total: {len(USERS.users)}
• PRO: {sum(1 for u in USERS.users.values() if u.get('pro'))}
• Blocked: {len(CREATOR.blocked_users)}

**Revenue:** {USERS.total_revenue:.4f} XMR

Uptime: {h}h {m}m

━━━━━━━━━━━━━━━━━━━━━━━━━"""

# Handlers
async def start(update, ctx):
    uid = update.effective_user.id
    if CREATOR.is_blocked(uid):
        await update.message.reply_text("🚫 Blocked!")
        return
    
    if CREATOR.is_creator(uid):
        await update.message.reply_text(creator_theme())
        return
    
    kb = [[InlineKeyboardButton("🔓 Upgrade PRO", callback_data="pay")]]
    await update.message.reply_text(user_theme(USERS.is_pro(uid)), reply_markup=InlineKeyboardMarkup(kb))

async def help_cmd(update, ctx):
    uid = update.effective_user.id
    if CREATOR.is_creator(uid):
        await update.message.reply_text(creator_theme())
        return
    await update.message.reply_text("🔍 `!bin [BIN]`\n\nFree: 5/day\nPro: Unlimited", parse_mode="Markdown")

async def cmds_cmd(update, ctx):
    uid = update.effective_user.id
    if CREATOR.is_creator(uid):
        await update.message.reply_text(creator_theme())
        return
    await update.message.reply_text("📋 Commands:\n/start /help /cmds\n/dev /about /server\n/pro /verify\n/history /favorites\n!bin [BIN]", parse_mode="Markdown")

async def dev_cmd(update, ctx):
    await update.message.reply_text(f"👨‍💻 @{DEVELOPER}", parse_mode="Markdown")

async def about_cmd(update, ctx):
    await update.message.reply_text(f"❓ **{BOT_NAME}**\n\nCreator: {CREATOR_ID}\nDev: @{DEVELOPER}", parse_mode="Markdown")

async def server_cmd(update, ctx):
    await update.message.reply_text(stats_msg(), parse_mode="Markdown")

async def creator_cmd(update, ctx):
    uid = update.effective_user.id
    if not CREATOR.is_creator(uid):
        await update.message.reply_text("❌ Creator only!")
        return
    await update.message.reply_text(creator_theme())

async def stats_cmd(update, ctx):
    uid = update.effective_user.id
    if not CREATOR.is_creator(uid):
        await update.message.reply_text("❌ Creator only!")
        return
    await update.message.reply_text(stats_msg(), parse_mode="Markdown")

async def users_cmd(update, ctx):
    uid = update.effective_user.id
    if not CREATOR.is_creator(uid): return
    
    pro_users = [f"• {k}: PRO" if v.get("pro") else f"• {k}: {v.get('searches')}/5" for k,v in list(USERS.users.items())[:20]]
    await update.message.reply_text(f"📋 **Users ({len(USERS.users)}):**\n\n" + "\n".join(pro_users) + "\n\n...and more", parse_mode="Markdown")

async def block_cmd(update, ctx):
    uid = update.effective_user.id
    if not CREATOR.is_creator(uid): return
    
    try:
        parts = update.message.text.split()
        if len(parts) < 2: await update.message.reply_text("Usage: /block [id]"); return
        CREATOR.block_user(int(parts[1]))
        await update.message.reply_text(f"✅ Blocked {parts[1]}")
    except: await update.message.reply_text("Error")

async def unblock_cmd(update, ctx):
    uid = update.effective_user.id
    if not CREATOR.is_creator(uid): return
    
    try:
        parts = update.message.text.split()
        if len(parts) < 2: await update.message.reply_text("Usage: /unblock [id]"); return
        CREATOR.unblock_user(int(parts[1]))
        await update.message.reply_text(f"✅ Unblocked {parts[1]}")
    except: await update.message.reply_text("Error")

async def addpro_cmd(update, ctx):
    uid = update.effective_user.id
    if not CREATOR.is_creator(uid): return
    
    try:
        parts = update.message.text.split()
        if len(parts) < 2: await update.message.reply_text("Usage: /addpro [id]"); return
        USERS.add_pro(int(parts[1]), "gift", 0)
        await update.message.reply_text(f"✅ PRO given to {parts[1]}")
    except: await update.message.reply_text("Error")

async def removepro_cmd(update, ctx):
    uid = update.effective_user.id
    if not CREATOR.is_creator(uid): return
    
    try:
        parts = update.message.text.split()
        if len(parts) < 2: await update.message.reply_text("Usage: /removepro [id]"); return
        USERS.remove_pro(int(parts[1]))
        await update.message.reply_text(f"✅ PRO removed from {parts[1]}")
    except: await update.message.reply_text("Error")

async def ban_cmd(update, ctx):
    uid = update.effective_user.id
    if not CREATOR.is_creator(uid): return
    
    try:
        parts = update.message.text.split()
        if len(parts) < 2: await update.message.reply_text("Usage: /ban [id]"); return
        tid = int(parts[1])
        CREATOR.block_user(tid)
        USERS.remove_pro(tid)
        await update.message.reply_text(f"✅ Banned {tid}")
    except: await update.message.reply_text("Error")

async def search_cmd(update, ctx):
    uid = update.effective_user.id
    if not CREATOR.is_creator(uid): return
    
    try:
        parts = update.message.text.split()
        if len(parts) < 2: await update.message.reply_text("Usage: /search [BIN]"); return
        d = bin_lookup(parts[1])
        if d: await update.message.reply_text(format_bin(d, parts[1]), parse_mode="Markdown")
        else: await update.message.reply_text("❌ Not found")
    except: await update.message.reply_text("Error")

async def broadcast_cmd(update, ctx):
    uid = update.effective_user.id
    if not CREATOR.is_creator(uid): return
    
    msg = update.message.text.replace("/broadcast ", "")
    if not msg: await update.message.reply_text("Usage: /broadcast [message]"); return
    
    sent = 0
    for user_id in USERS.users:
        try:
            await ctx.bot.send_message(user_id, f"📢 **BROADCAST**\n\n{msg}", parse_mode="Markdown")
            sent += 1
        except: pass
    
    await update.message.reply_text(f"✅ Sent to {sent} users")

async def history_cmd(update, ctx):
    uid = update.effective_user.id
    if CREATOR.is_creator(uid):
        await update.message.reply_text(creator_theme())
        return
    
    hist = USERS.get_history(uid)
    if not hist: await update.message.reply_text("No history yet"); return
    
    txt = "📜 **Your History:**\n\n"
    for h in hist[:10]:
        t = time.strftime("%H:%M", time.localtime(h["time"]))
        txt += f"• !bin {h['bin']} - {t}\n"
    
    await update.message.reply_text(txt, parse_mode="Markdown")

async def favorites_cmd(update, ctx):
    uid = update.effective_user.id
    if CREATOR.is_creator(uid):
        await update.message.reply_text(creator_theme())
        return
    
    favs = USERS.get_favorites(uid)
    if not favs: await update.message.reply_text("No favorites yet\n\nAdd with: !fav 457173"); return
    
    txt = "⭐ **Favorites:**\n\n"
    for f in favs: txt += f"• !bin {f}\n"
    
    await update.message.reply_text(txt, parse_mode="Markdown")

async def bulk_search_cmd(update, ctx):
    uid = update.effective_user.id
    if CREATOR.is_blocked(uid): await update.message.reply_text("🚫"); return
    
    parts = update.message.text.replace("!searchall ", "").split()
    if not parts: await update.message.reply_text("Usage: !searchall 457173 541234"); return
    
    results = []
    for bin_num in parts[:10]:
        d = bin_lookup(bin_num)
        if d:
            results.append(f"✅ {bin_num}: {d.get('brand')} - {d.get('bank', {}).get('name')}")
        else:
            results.append(f"❌ {bin_num}: Not found")
    
    await update.message.reply_text("\n".join(results), parse_mode="Markdown")

async def pro_cmd(update, ctx):
    uid = update.effective_user.id
    
    if CREATOR.is_creator(uid):
        await update.message.reply_text("👑 You are the CREATOR!")
        return
    
    if USERS.is_pro(uid):
        exp = time.strftime("%Y-%m-%d", time.localtime(USERS.get(uid)["pro_expires"]))
        await update.message.reply_text(f"✅ PRO!\n\nExpires: {exp}", parse_mode="Markdown")
    else:
        kb = [[InlineKeyboardButton("💳 Pay", callback_data="pay")]]
        await update.message.reply_text(pro_msg(), reply_markup=InlineKeyboardMarkup(kb))

async def verify_cmd(update, ctx):
    uid = update.effective_user.id
    if CREATOR.is_blocked(uid): await update.message.reply_text("🚫"); return
    
    parts = update.message.text.split()
    if len(parts) < 2: await update.message.reply_text("Usage: /verify [tx]"); return
    
    tx = parts[1].strip()
    await update.message.reply_text("🔐 Verifying...", parse_mode="Markdown")
    
    fraud, reason = AI.analyze(tx)
    if fraud:
        CREATOR.block_user(uid)
        await update.message.reply_text(f"🚨 FRAUD!\n\n{reason}\n\nBlocked!")
        return
    
    r = MONERO.check(tx)
    if not r["valid"]:
        err = r.get("reason", "Failed")
        if "used" in err.lower():
            CREATOR.block_user(uid)
            await update.message.reply_text(f"🚨 FRAUD!\n\n{err}\n\nBlocked!")
            return
        await update.message.reply_text(f"❌ {err}", parse_mode="Markdown")
        return
    
    USERS.mark_tx(tx, uid)
    USERS.add_pro(uid, tx, r["amount"])
    
    await update.message.reply_text(f"✅ VERIFIED!\n\nAmount: {r['amount']:.4f} XMR\nConf: {r['confirmations']}\n\n🎉 PRO for 1 year!", parse_mode="Markdown")

async def pay_cb(update, ctx):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        f"💳 **Payment**\n\nAmount: {MIN_XMR} XMR\n\nAddress:\n```\n{MONERO_ADDRESS}\n```\n\n[QR](https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={MONERO_ADDRESS})\n\nAfter pay: `/verify [tx]`\n\n⚠️ AI fraud check!",
        parse_mode="Markdown"
    )

async def fav_cmd(update, ctx):
    uid = update.effective_user.id
    if CREATOR.is_blocked(uid): return
    
    parts = update.message.text.split()
    if len(parts) < 2: await update.message.reply_text("Usage: !fav [BIN]"); return
    
    bin_num = parts[1].strip()
    USERS.add_favorite(uid, bin_num)
    await update.message.reply_text(f"⭐ Added {bin_num} to favorites!")

async def unfav_cmd(update, ctx):
    uid = update.effective_user.id
    if CREATOR.is_blocked(uid): return
    
    parts = update.message.text.split()
    if len(parts) < 2: await update.message.reply_text("Usage: !unfav [BIN]"); return
    
    bin_num = parts[1].strip()
    USERS.rem_favorite(uid, bin_num)
    await update.message.reply_text(f"⭐ Removed {bin_num} from favorites!")

async def handle_msg(update, ctx):
    txt = update.message.text.strip()
    uid = update.effective_user.id
    
    if CREATOR.is_blocked(uid):
        await update.message.reply_text("🚫 Blocked!")
        return
    
    # Commands
    if txt.lower().startswith("!bin"):
        if not USERS.can_search(uid):
            kb = [[InlineKeyboardButton("💳 Pay", callback_data="pay")]]
            await update.message.reply_text(pro_msg(), reply_markup=InlineKeyboardMarkup(kb))
            return
        
        bn = re.sub(r'\D', '', txt[4:].strip())
        if not bn or len(bn) < 6:
            await update.message.reply_text("❌ Usage: !bin [BIN]"); return
        
        if not re.fullmatch(r'\d{6,8}', bn):
            await update.message.reply_text("❌ 6-8 digits"); return
        
        d = bin_lookup(bn)
        
        if not CREATOR.is_creator(uid):
            USERS.inc_search(uid, bn)
        
        if not d:
            await update.message.reply_text("❌ Not found"); return
        
        await update.message.reply_text(format_bin(d, bn), parse_mode="Markdown")
        return
    
    elif txt.lower().startswith("!searchall"):
        await bulk_search_cmd(update, ctx)
        return
    
    elif txt.lower().startswith("!fav"):
        await fav_cmd(update, ctx)
        return
    
    elif txt.lower().startswith("!unfav"):
        await unfav_cmd(update, ctx)
        return
    
    # Default
    if CREATOR.is_creator(uid):
        await update.message.reply_text(creator_theme())
    else:
        kb = [[InlineKeyboardButton("🔓 Upgrade PRO", callback_data="pay")]]
        await update.message.reply_text(user_theme(USERS.is_pro(uid)), reply_markup=InlineKeyboardMarkup(kb))

def main():
    logger.info(f"{BOT_NAME} Ultimate started!")
    logger.info(f"Creator: {CREATOR_ID}")
    
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("cmds", cmds_cmd))
    app.add_handler(CommandHandler("dev", dev_cmd))
    app.add_handler(CommandHandler("about", about_cmd))
    app.add_handler(CommandHandler("server", server_cmd))
    app.add_handler(CommandHandler("creator", creator_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(CommandHandler("block", block_cmd))
    app.add_handler(CommandHandler("unblock", unblock_cmd))
    app.add_handler(CommandHandler("addpro", addpro_cmd))
    app.add_handler(CommandHandler("removepro", removepro_cmd))
    app.add_handler(CommandHandler("ban", ban_cmd))
    app.add_handler(CommandHandler("search", search_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("history", history_cmd))
    app.add_handler(CommandHandler("favorites", favorites_cmd))
    app.add_handler(CommandHandler("pro", pro_cmd))
    app.add_handler(CommandHandler("verify", verify_cmd))
    app.add_handler(CallbackQueryHandler(pay_cb, pattern="pay"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
    
    logger.info("Running!")
    app.run_polling()

if __name__ == "__main__":
    main()
