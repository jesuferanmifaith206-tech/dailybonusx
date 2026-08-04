import os
import logging
import json
import sqlite3
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from dotenv import load_dotenv
import random

# Load environment variables
load_dotenv()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token from environment variable
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN not set!")
    exit(1)

# Constants
DAILY_BONUS_AMOUNT = 100
STREAK_BONUS = {1: 50, 2: 75, 3: 100, 4: 150, 5: 200, 6: 250, 7: 500}

# SQLite Database Setup
DB_NAME = 'bot_data.db'

def get_db():
    """Get database connection."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize database tables."""
    with get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT,
                points INTEGER DEFAULT 0,
                streak INTEGER DEFAULT 0,
                last_claim TEXT DEFAULT '',
                total_claimed INTEGER DEFAULT 0,
                referral_code TEXT,
                referrals INTEGER DEFAULT 0,
                last_spin TEXT DEFAULT '',
                referral_bonus_given INTEGER DEFAULT 0
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS referrals (
                referral_code TEXT,
                user_id TEXT,
                referred_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        conn.commit()
        logger.info("✅ Database initialized!")

def get_user(user_id):
    """Get user data from database."""
    with get_db() as conn:
        cursor = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

def create_user(user_id, username):
    """Create new user in database."""
    referral_code = generate_referral_code(user_id)
    with get_db() as conn:
        conn.execute('''
            INSERT INTO users (user_id, username, referral_code)
            VALUES (?, ?, ?)
        ''', (user_id, username, referral_code))
        conn.commit()
    return get_user(user_id)

def update_user(user_id, data):
    """Update user data in database."""
    fields = []
    values = []
    for key, value in data.items():
        fields.append(f"{key} = ?")
        values.append(value)
    values.append(user_id)
    
    with get_db() as conn:
        conn.execute(f'UPDATE users SET {", ".join(fields)} WHERE user_id = ?', values)
        conn.commit()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message when /start is issued."""
    user = update.effective_user
    user_id = str(user.id)
    
    # Check if user exists, create if not
    user_data = get_user(user_id)
    if not user_data:
        user_data = create_user(user_id, user.username or user.full_name)
        logger.info(f"New user: {user_id}")
    
    welcome_message = f"""
🎮 *Welcome to Daily Bonus Bot!* 🎮

Hi {user.full_name}! 👋

💰 *Earn daily bonuses and rewards!*
• Daily check-in rewards
• Streak multipliers (up to 500 bonus!)
• Referral rewards
• Spin to win!

🔹 *Commands:*
/daily - Claim your daily bonus
/stats - Check your stats
/refer - Get your referral link
/spin - Spin the wheel of fortune
/help - Help & support

Let's start earning! 🚀
"""
    
    keyboard = [
        [InlineKeyboardButton("🎁 Claim Daily Bonus", callback_data='claim_daily')],
        [InlineKeyboardButton("🎰 Spin Wheel", callback_data='spin_wheel')],
        [InlineKeyboardButton("📊 My Stats", callback_data='show_stats')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        welcome_message,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def daily_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle daily bonus claim."""
    user_id = str(update.effective_user.id)
    query = update.callback_query
    
    if query:
        await query.answer()
        message = query.message
    else:
        message = update.message
    
    try:
        user_data = get_user(user_id)
        if not user_data:
            await message.reply_text("❌ User not found. Please use /start first.")
            return
        
        today = datetime.now().strftime('%Y-%m-%d')
        last_claim = user_data.get('last_claim', '')
        
        # Check if already claimed today
        if last_claim == today:
            response = (
                "⏰ *You've already claimed today's bonus!*\n"
                f"Come back tomorrow for your {user_data['streak'] + 1} day streak! 🔥"
            )
            if query:
                await query.edit_message_text(response, parse_mode='Markdown')
            else:
                await message.reply_text(response, parse_mode='Markdown')
            return
        
        # Calculate bonus
        streak = user_data.get('streak', 0) + 1
        bonus = DAILY_BONUS_AMOUNT + STREAK_BONUS.get(streak, 50)
        
        # Update user data
        update_user(user_id, {
            'points': user_data['points'] + bonus,
            'streak': streak,
            'last_claim': today,
            'total_claimed': user_data['total_claimed'] + bonus
        })
        
        # Send success message
        streak_message = f"🔥 *{streak} DAY STREAK!*" if streak > 1 else "🌟 *First day!*"
        
        response = (
            f"🎉 *Daily Bonus Claimed!*\n\n"
            f"{streak_message}\n"
            f"💰 Bonus: +{bonus} points\n"
            f"📊 Total Points: {user_data['points'] + bonus}\n"
            f"📈 Streak: {streak} days\n\n"
            f"💡 Claim again tomorrow for even bigger rewards!"
        )
        
        if query:
            await query.edit_message_text(response, parse_mode='Markdown')
        else:
            await message.reply_text(response, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in daily_bonus: {e}")
        await message.reply_text("❌ Something went wrong. Please try again later.")

async def spin_wheel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Spin the wheel for random rewards."""
    user_id = str(update.effective_user.id)
    query = update.callback_query
    
    if query:
        await query.answer()
        message = query.message
    else:
        message = update.message
    
    try:
        user_data = get_user(user_id)
        if not user_data:
            await message.reply_text("❌ User not found. Please use /start first.")
            return
        
        # Check cooldown (1 hour between spins)
        last_spin = user_data.get('last_spin', '')
        if last_spin:
            last_spin_time = datetime.fromisoformat(last_spin)
            time_diff = datetime.now() - last_spin_time
            if time_diff < timedelta(hours=1):
                wait_minutes = 60 - int(time_diff.total_seconds() // 60)
                response = (
                    f"⏳ *Wait!*\n"
                    f"You need to wait {wait_minutes} minutes between spins!"
                )
                if query:
                    await query.edit_message_text(response, parse_mode='Markdown')
                else:
                    await message.reply_text(response, parse_mode='Markdown')
                return
        
        # Spin rewards
        rewards = [10, 20, 30, 50, 75, 100, 150, 200, 500]
        reward = random.choice(rewards)
        
        # Bonus multipliers
        multiplier = 1
        if random.random() < 0.15:  # 15% chance
            multiplier = 2
            reward *= 2
        
        # Update user data
        update_user(user_id, {
            'points': user_data['points'] + reward,
            'last_spin': datetime.now().isoformat()
        })
        
        emojis = ["🎰", "✨", "🎯", "💎", "🌟", "🎲"]
        result_emoji = random.choice(emojis)
        
        spin_message = f"""
{result_emoji} *WHEEL OF FORTUNE* {result_emoji}

🎡 You spun and won...

💰 *+{reward} points* {'🎉 DOUBLE!' if multiplier == 2 else ''}

📊 Total Points: {user_data['points'] + reward}

⏰ Spin again in 1 hour!
"""
        
        if query:
            await query.edit_message_text(spin_message, parse_mode='Markdown')
        else:
            await message.reply_text(spin_message, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error in spin_wheel: {e}")
        await message.reply_text("❌ Something went wrong. Please try again later.")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user statistics."""
    user_id = str(update.effective_user.id)
    query = update.callback_query
    
    if query:
        await query.answer()
        message = query.message
    else:
        message = update.message
    
    try:
        user_data = get_user(user_id)
        if not user_data:
            await message.reply_text("❌ User not found. Please use /start first.")
            return
        
        stats_message = f"""
📊 *Your Stats* 📊

💰 Points: {user_data['points']}
🔥 Streak: {user_data['streak']} days
🎁 Total Claimed: {user_data['total_claimed']} points
👥 Referrals: {user_data.get('referrals', 0)}
📅 Last Claim: {user_data.get('last_claim', 'Never')}

💡 Keep playing to earn more!
"""
        
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh Stats", callback_data='show_stats')],
            [InlineKeyboardButton("🏆 Leaderboard", callback_data='leaderboard')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if query:
            await query.edit_message_text(stats_message, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await message.reply_text(stats_message, reply_markup=reply_markup, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in stats: {e}")
        await message.reply_text("❌ Something went wrong. Please try again later.")

async def refer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate referral link."""
    user_id = str(update.effective_user.id)
    
    try:
        user_data = get_user(user_id)
        if not user_data:
            await update.message.reply_text("❌ User not found. Please use /start first.")
            return
        
        referral_code = user_data.get('referral_code')
        bot_username = (await context.bot.get_me()).username
        
        referral_message = f"""
👥 *Referral Program* 👥

Share your referral link and earn rewards!

🔗 *Your Referral Link:*
`https://t.me/{bot_username}?start={referral_code}`

🎁 *Rewards:*
• You get 50 points per referral
• Your friend gets 25 points bonus
• Special rewards at 5, 10, 25 referrals

👥 Referrals: {user_data.get('referrals', 0)}

Share with your friends! 🚀
"""
        
        await update.message.reply_text(referral_message, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error in refer: {e}")
        await update.message.reply_text("❌ Something went wrong. Please try again later.")

async def handle_referral(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle referral link clicks."""
    if not context.args:
        return
    
    referral_code = context.args[0]
    user_id = str(update.effective_user.id)
    
    try:
        user_data = get_user(user_id)
        if not user_data:
            await update.message.reply_text("❌ Please use /start first.")
            return
        
        if user_data.get('referral_bonus_given', 0) == 0:
            update_user(user_id, {
                'points': user_data['points'] + 25,
                'referral_bonus_given': 1
            })
            
            await update.message.reply_text(
                "✅ *Welcome!* 🎉\n\n"
                "You've been referred by a friend!\n"
                "🎁 You get a 25 points bonus!\n\n"
                "Use /daily to claim your daily bonus!",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "👋 Welcome back!\n"
                "Use /start to see your stats.",
                parse_mode='Markdown'
            )
            
    except Exception as e:
        logger.error(f"Error in handle_referral: {e}")
        await update.message.reply_text("❌ Something went wrong. Please try again later.")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show leaderboard."""
    query = update.callback_query
    
    if query:
        await query.answer()
        message = query.message
    else:
        message = update.message
    
    try:
        with get_db() as conn:
            cursor = conn.execute('''
                SELECT username, points, streak
                FROM users
                ORDER BY points DESC
                LIMIT 10
            ''')
            top_users = cursor.fetchall()
        
        leaderboard_text = "🏆 *Leaderboard* 🏆\n\n"
        if not top_users:
            leaderboard_text += "No users yet. Be the first!"
        else:
            for i, row in enumerate(top_users, 1):
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                leaderboard_text += f"{medal} {row['username']}: {row['points']} pts 🔥{row['streak']}d\n"
        
        if query:
            await query.edit_message_text(leaderboard_text, parse_mode='Markdown')
        else:
            await message.reply_text(leaderboard_text, parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Error in leaderboard: {e}")
        await message.reply_text("❌ Something went wrong. Please try again later.")

def generate_referral_code(user_id: str) -> str:
    """Generate a unique referral code."""
    import hashlib
    return hashlib.md5(f"{user_id}{datetime.now().timestamp()}".encode()).hexdigest()[:8]

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a help message."""
    help_text = """
❓ *Help & Commands* ❓

🎮 *Available Commands:*
/daily - Claim your daily bonus
/stats - Check your statistics
/refer - Get your referral link
/spin - Spin the wheel of fortune
/help - Show this help message

💰 *How to Earn:*
• Daily check-in bonuses (increasing rewards)
• Spin the wheel every hour
• Refer friends and earn rewards

💡 *Tips:*
• Keep your streak alive for bigger rewards
• Share your referral link with friends
• Check back daily for special events
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button presses."""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'claim_daily':
        await daily_bonus(update, context)
    elif query.data == 'spin_wheel':
        await spin_wheel(update, context)
    elif query.data == 'show_stats':
        await stats(update, context)
    elif query.data == 'leaderboard':
        await leaderboard(update, context)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors."""
    logger.error(f"Update {update} caused error {context.error}")
    if update and hasattr(update, 'effective_message'):
        await update.effective_message.reply_text(
            "❌ An error occurred. Please try again later."
        )

def main() -> None:
    """Start the bot."""
    logger.info("🚀 Starting Daily Bonus Bot...")
    
    # Initialize database
    init_db()
    
    # Create application
    application = Application.builder().token(TOKEN).build()
    
    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("daily", daily_bonus))
    application.add_handler(CommandHandler("spin", spin_wheel))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("refer", refer))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    
    # Callback handlers
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Referral handler
    application.add_handler(MessageHandler(filters.Regex('^/start '), handle_referral))
    
    # Error handler
    application.add_error_handler(error_handler)
    
    logger.info("✅ Bot is ready! Listening for updates...")
    
    # Run the bot
    application.run_polling()

if __name__ == '__main__':
    main()
