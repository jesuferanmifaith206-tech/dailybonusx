import os
import logging
import json
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from dotenv import load_dotenv
import redis
import random

# Load environment variables
load_dotenv()

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Redis connection for data storage
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')
redis_client = redis.Redis.from_url(REDIS_URL)

# Bot token from environment variable
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# Constants
DAILY_BONUS_AMOUNT = 100
STREAK_BONUS = {1: 50, 2: 75, 3: 100, 4: 150, 5: 200, 6: 250, 7: 500}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message when /start is issued."""
    user = update.effective_user
    user_id = str(user.id)
    
    # Initialize user data if not exists
    if not redis_client.exists(f"user:{user_id}"):
        user_data = {
            'username': user.username or user.full_name,
            'points': 0,
            'streak': 0,
            'last_claim': '',
            'total_claimed': 0,
            'referral_code': generate_referral_code(user_id),
            'referrals': 0,
            'last_spin': ''
        }
        redis_client.set(f"user:{user_id}", json.dumps(user_data))
    
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
        user_data = json.loads(redis_client.get(f"user:{user_id}"))
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
        user_data['points'] += bonus
        user_data['streak'] = streak
        user_data['last_claim'] = today
        user_data['total_claimed'] += bonus
        
        redis_client.set(f"user:{user_id}", json.dumps(user_data))
        
        # Send success message
        streak_message = f"🔥 *{streak} DAY STREAK!*" if streak > 1 else "🌟 *First day!*"
        
        response = (
            f"🎉 *Daily Bonus Claimed!*\n\n"
            f"{streak_message}\n"
            f"💰 Bonus: +{bonus} points\n"
            f"📊 Total Points: {user_data['points']}\n"
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
        user_data = json.loads(redis_client.get(f"user:{user_id}"))
        
        # Check cooldown (1 hour between spins)
        last_spin = user_data.get('last_spin', '')
        if last_spin:
            last_spin_time = datetime.fromisoformat(last_spin)
            if datetime.now() - last_spin_time < timedelta(hours=1):
                wait_time = 60 - (datetime.now() - last_spin_time).seconds // 60
                response = (
                    f"⏳ *Wait!*\n"
                    f"You need to wait {wait_time} minutes between spins!"
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
        
        user_data['points'] += reward
        user_data['last_spin'] = datetime.now().isoformat()
        redis_client.set(f"user:{user_id}", json.dumps(user_data))
        
        emojis = ["🎰", "✨", "🎯", "💎", "🌟", "🎲"]
        result_emoji = random.choice(emojis)
        
        spin_message = f"""
{result_emoji} *WHEEL OF FORTUNE* {result_emoji}

🎡 You spun and won...

💰 *+{reward} points* {'🎉 DOUBLE!' if multiplier == 2 else ''}

📊 Total Points: {user_data['points']}

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
        user_data = json.loads(redis_client.get(f"user:{user_id}"))
        
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
        user_data = json.loads(redis_client.get(f"user:{user_id}"))
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
        # Add bonus for new user
        user_data = json.loads(redis_client.get(f"user:{user_id}"))
        
        if 'referral_bonus_given' not in user_data:
            user_data['points'] += 25
            user_data['referral_bonus_given'] = True
            redis_client.set(f"user:{user_id}", json.dumps(user_data))
            
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
        # Get top users
        top_users = []
        keys = redis_client.keys('user:*')
        for key in keys[:20]:
            user_data = json.loads(redis_client.get(key))
            username = user_data.get('username', 'Anonymous')
            points = user_data.get('points', 0)
            top_users.append((username, points))
        
        top_users.sort(key=lambda x: x[1], reverse=True)
        
        leaderboard_text = "🏆 *Leaderboard* 🏆\n\n"
        for i, (username, points) in enumerate(top_users[:10], 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            leaderboard_text += f"{medal} {username}: {points} pts\n"
        
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

Need more help? Contact @support_username
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

def main() -> None:
    """Start the bot."""
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set!")
        return
    
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
    
    # Run the bot
    application.run_polling()

if __name__ == '__main__':
    main()
