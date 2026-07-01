import subprocess
import sys
import os

# --- АВТОМАТИЧЕСКАЯ УСТАНОВКА ЗАВИСИМОСТЕЙ ---
def install_dependencies():
    """Автоматически устанавливает зависимости при первом запуске"""
    try:
        import aiogram
        import apscheduler
        print("✅ Все зависимости уже установлены")
        return True
    except ImportError as e:
        print(f"📦 Устанавливаю зависимости: {e}")
        try:
            subprocess.check_call([
                sys.executable, "-m", "pip", "install",
                "aiogram==3.2.0",
                "apscheduler==3.10.4",
                "--no-cache-dir"
            ])
            print("✅ Зависимости успешно установлены!")
            return True
        except Exception as install_error:
            print(f"❌ Ошибка установки зависимостей: {install_error}")
            return False

# Устанавливаем зависимости перед запуском
if not install_dependencies():
    print("❌ Не удалось установить зависимости. Бот не запустится.")
    sys.exit(1)

# Теперь импортируем все остальное
import sqlite3
import random
import logging
import asyncio
from datetime import datetime, date, timedelta
from calendar import monthrange
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from collections import defaultdict

# --- ДИАГНОСТИКА ---
print("🚀 Запуск бота...")
print(f"📁 Текущая директория: {os.getcwd()}")
print(f"📁 Python версия: {sys.version}")

# --- ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ---
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    print("❌ ОШИБКА: BOT_TOKEN не найден!")
    raise ValueError("❌ BOT_TOKEN не найден! Добавьте переменную в Railway.")

# Если ADMIN_ID не число, игнорируем его
try:
    ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
except ValueError:
    ADMIN_ID = 0
    print("⚠️ ADMIN_ID не является числом, используем 0")

print(f"✅ TOKEN загружен: {TOKEN[:10]}...")
print(f"✅ ADMIN_ID: {ADMIN_ID}")

# --- СОСТОЯНИЯ FSM ---
class BudgetStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_category = State()
    waiting_confirmation = State()

# --- БАЗА ДАННЫХ ---
print("📊 Инициализация базы данных...")
os.makedirs('data', exist_ok=True)
DB_PATH = os.path.join('data', 'budget.db')

conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''
    CREATE TABLE IF NOT EXISTS budget (
        id INTEGER PRIMARY KEY,
        balance REAL DEFAULT 0,
        last_transaction_date TIMESTAMP
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        username TEXT,
        type TEXT,
        amount REAL,
        category TEXT,
        description TEXT,
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS achievements (
        user_id INTEGER,
        achievement TEXT,
        unlocked_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (user_id, achievement)
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS user_stats (
        user_id INTEGER PRIMARY KEY,
        total_income REAL DEFAULT 0,
        total_expense REAL DEFAULT 0,
        days_tracking INTEGER DEFAULT 0,
        last_activity DATE
    )
''')

cursor.execute("INSERT OR IGNORE INTO budget (id, balance, last_transaction_date) VALUES (1, 0, NULL)")
conn.commit()
print("✅ База данных готова")

# --- КАТЕГОРИИ РАСХОДОВ ---
CATEGORIES = {
    '🏠 Вещи для дома': ['мебель', 'посуда', 'декор', 'бытовая химия'],
    '👕 Одежда': ['обувь', 'верхняя одежда', 'белье', 'аксессуары'],
    '🍎 Еда домой': ['продукты', 'бакалея', 'овощи', 'фрукты', 'мясо'],
    '🍽️ Еда не дома': ['кафе', 'ресторан', 'доставка', 'фастфуд'],
    '🚗 Транспорт': ['бензин', 'такси', 'метро', 'автобус', 'ремонт авто'],
    '🎮 Развлечение': ['кино', 'игры', 'подписки', 'хобби', 'путешествия'],
    '🐕 Собака': ['корм', 'ветеринар', 'игрушки', 'груминг', 'аксессуары'],
    '🛠️ Услуги': ['парикмахерская', 'образование', 'ремонт', 'коммуналка', 'интернет']
}

CATEGORY_NAMES = list(CATEGORIES.keys())

# --- ДОСТИЖЕНИЯ ---
ACHIEVEMENTS = {
    'first_transaction': '🌟 Первая транзакция!',
    'first_expense': '💸 Первый расход учтен!',
    'first_income': '💰 Первый доход!',
    'tracking_week': '📅 7 дней ведения бюджета!',
    'tracking_month': '📅 30 дней ведения бюджета!',
    'tracking_year': '🎉 Год с бюджетом!',
    'saved_100': '💎 Сэкономил 100 руб. за день!',
    'saved_500': '💎 Сэкономил 500 руб. за день!',
    'saved_1000': '💪 Сэкономил 1000 руб. за неделю!',
    'saved_5000': '🔥 Сэкономил 5000 руб. за месяц!',
    'saved_10000': '👑 Сэкономил 10000 руб.!',
    'expenses_10': '📊 10 расходов учтено',
    'expenses_50': '📊 50 расходов учтено',
    'expenses_100': '📊 100 расходов учтено!',
    'expenses_500': '🏆 500 расходов! Ты профи!',
    'income_10k': '💵 Доход 10 000 руб.',
    'income_50k': '💵 Доход 50 000 руб.',
    'income_100k': '💎 Доход 100 000 руб!',
    'income_500k': '👑 Доход 500 000 руб!',
    'category_master': '🎯 Использовал все категории!',
    'food_lover': '🍕 10 трат в категории "Еда"',
    'shopaholic': '🛍️ 10 трат в категории "Одежда"',
    'pet_lover': '🐕 10 трат в категории "Собака"',
    'transporter': '🚗 10 трат в категории "Транспорт"',
    'entertainer': '🎮 10 трат в категории "Развлечения"',
    'home_maker': '🏠 10 трат в категории "Вещи для дома"',
    'service_user': '🛠️ 10 трат в категории "Услуги"',
    'balance_1000': '💰 Баланс 1000 руб.',
    'balance_5000': '💰 Баланс 5000 руб.',
    'balance_10000': '💰 Баланс 10000 руб.',
    'balance_50000': '💰 Баланс 50000 руб.',
    'balance_100000': '👑 Баланс 100000 руб!',
    'budget_master': '🏆 30 дней в лимите!',
    'economist': '📉 Экономия 10 дней подряд',
    'no_expense_day': '🌙 День без трат',
    'weekend_warrior': '🎉 Траты в выходной',
    'early_bird': '🌅 Ранняя транзакция (до 8:00)',
    'night_owl': '🦉 Поздняя транзакция (после 23:00)',
    'perfect_week': '✨ Идеальная неделя (без превышений)',
    'generous': '🎁 Трата более 5000 руб.',
    'careful': '🧐 Трата менее 50 руб.',
    'diverse': '🌈 5 разных категорий за день',
    'combo_5': '🔥 5 транзакций за день!',
    'combo_10': '🔥 10 транзакций за день!',
    'combo_20': '💥 20 транзакций за день!',
    'veteran': '🎖️ 100 дней с ботом',
    'legend': '⚡ 365 дней с ботом',
    'millionaire': '💎 Накопил 1 000 000 руб!',
    'wise': '🧘 50 дней без превышения лимита',
    'disciplined': '🎯 100 дней без превышения лимита',
    'zen': '☯️ 365 дней без превышения лимита',
    'profit': '📈 Доход превысил расход за месяц',
}

# --- ФУНКЦИИ БАЗЫ ДАННЫХ ---
def get_balance():
    cursor.execute("SELECT balance FROM budget WHERE id=1")
    return cursor.fetchone()[0]

def update_balance(amount):
    new_balance = get_balance() + amount
    cursor.execute("UPDATE budget SET balance = ?, last_transaction_date = CURRENT_TIMESTAMP WHERE id=1", (new_balance,))
    conn.commit()
    return new_balance

def add_transaction(user_id, username, type_, amount, category, description=""):
    cursor.execute('''
        INSERT INTO transactions (user_id, username, type, amount, category, description)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, username, type_, amount, category, description))
    conn.commit()
    
    cursor.execute('''
        INSERT INTO user_stats (user_id, total_income, total_expense, last_activity)
        VALUES (?, 0, 0, CURRENT_DATE)
        ON CONFLICT(user_id) DO UPDATE SET
            total_income = total_income + CASE WHEN ? = 'income' THEN ? ELSE 0 END,
            total_expense = total_expense + CASE WHEN ? = 'expense' THEN ? ELSE 0 END,
            last_activity = CURRENT_DATE
    ''', (user_id, type_, amount, type_, amount))
    conn.commit()
    return cursor.lastrowid

def get_last_transaction_date():
    cursor.execute("SELECT last_transaction_date FROM budget WHERE id=1")
    result = cursor.fetchone()[0]
    if result:
        return datetime.strptime(result, '%Y-%m-%d %H:%M:%S')
    return None

def get_user_achievements(user_id):
    cursor.execute("SELECT achievement FROM achievements WHERE user_id = ?", (user_id,))
    return [row[0] for row in cursor.fetchall()]

def unlock_achievement(user_id, achievement_key):
    if achievement_key not in ACHIEVEMENTS:
        return False
    cursor.execute('''
        INSERT OR IGNORE INTO achievements (user_id, achievement)
        VALUES (?, ?)
    ''', (user_id, achievement_key))
    conn.commit()
    return cursor.rowcount > 0

# --- РАСЧЕТ ДНЕВНОГО ЛИМИТА ---
def get_days_until_next_payday():
    today = date.today()
    if today.month == 12:
        next_month = 1
        next_year = today.year + 1
    else:
        next_month = today.month + 1
        next_year = today.year
    payday = date(next_year, next_month, 5)
    delta = payday - today
    return delta.days

def get_daily_limit():
    balance = get_balance()
    days = get_days_until_next_payday()
    if days <= 0:
        return balance
    return round(balance / days, 2) if days > 0 else 0

# --- ФУНКЦИИ ДЛЯ ДОСТИЖЕНИЙ ---
def check_achievements(user_id, username):
    unlocked = []
    
    cursor.execute('''
        SELECT COUNT(*), SUM(CASE WHEN type = 'expense' THEN 1 ELSE 0 END),
               SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END),
               COUNT(DISTINCT category)
        FROM transactions
        WHERE user_id = ?
    ''', (user_id,))
    total, expenses_count, total_income, categories_count = cursor.fetchone()
    
    balance = get_balance()
    
    cursor.execute('''
        SELECT COUNT(DISTINCT date(date))
        FROM transactions
        WHERE user_id = ?
    ''', (user_id,))
    active_days = cursor.fetchone()[0] or 0
    
    checks = [
        (total == 1, 'first_transaction'),
        (expenses_count == 1, 'first_expense'),
        (total_income > 0, 'first_income'),
        (expenses_count >= 10, 'expenses_10'),
        (expenses_count >= 50, 'expenses_50'),
        (expenses_count >= 100, 'expenses_100'),
        (expenses_count >= 500, 'expenses_500'),
        (total_income >= 10000, 'income_10k'),
        (total_income >= 50000, 'income_50k'),
        (total_income >= 100000, 'income_100k'),
        (total_income >= 500000, 'income_500k'),
        (balance >= 1000, 'balance_1000'),
        (balance >= 5000, 'balance_5000'),
        (balance >= 10000, 'balance_10000'),
        (balance >= 50000, 'balance_50000'),
        (balance >= 100000, 'balance_100000'),
        (active_days >= 7, 'tracking_week'),
        (active_days >= 30, 'tracking_month'),
        (active_days >= 365, 'tracking_year'),
        (categories_count >= len(CATEGORY_NAMES), 'category_master'),
    ]
    
    for condition, key in checks:
        if condition and unlock_achievement(user_id, key):
            unlocked.append(ACHIEVEMENTS[key])
    
    return unlocked

# --- ГЕНЕРАЦИЯ КЛАВИАТУР ---
def get_main_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.row(
        types.KeyboardButton(text="💰 Баланс"),
        types.KeyboardButton(text="📊 Отчеты")
    )
    builder.row(
        types.KeyboardButton(text="💸 Расход"),
        types.KeyboardButton(text="📈 Доход")
    )
    builder.row(
        types.KeyboardButton(text="🏆 Достижения"),
        types.KeyboardButton(text="📖 Цитата")
    )
    return builder.as_markup(resize_keyboard=True)

def get_category_keyboard():
    builder = InlineKeyboardBuilder()
    for category in CATEGORY_NAMES:
        builder.add(InlineKeyboardButton(text=category, callback_data=f"cat_{category}"))
    builder.adjust(2)
    return builder.as_markup()

def get_report_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="📊 За неделю", callback_data="report_week"),
        InlineKeyboardButton(text="📊 За месяц", callback_data="report_month"),
        InlineKeyboardButton(text="📈 По категориям", callback_data="report_categories")
    )
    builder.adjust(2)
    return builder.as_markup()

# --- ИНИЦИАЛИЗАЦИЯ БОТА ---
print("🤖 Инициализация бота...")
storage = MemoryStorage()
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=storage)
scheduler = AsyncIOScheduler()
print("✅ Бот инициализирован")

# --- ОБРАБОТЧИКИ КОМАНД ---
@dp.message(Command("start"))
async def start(message: types.Message):
    cursor.execute('''
        INSERT OR IGNORE INTO user_stats (user_id, total_income, total_expense, last_activity)
        VALUES (?, 0, 0, CURRENT_DATE)
    ''', (message.from_user.id,))
    conn.commit()
    
    welcome_text = (
        "🏠 *Семейный бюджет Красновых*\n\n"
        "Я помогу вам вести общий бюджет!\n"
        "Все пользователи видят один баланс и могут вносить траты.\n\n"
        "📌 *Как пользоваться:*\n"
        "💰 *Баланс* - проверить остаток и дневной лимит\n"
        "💸 *Расход* - добавить трату (выберите категорию)\n"
        "📈 *Доход* - добавить поступление\n"
        "📊 *Отчеты* - статистика за неделю/месяц\n"
        "🏆 *Достижения* - ваши успехи\n"
        "📖 *Цитата* - мудрая мысль о деньгах"
    )
    await message.answer(welcome_text, reply_markup=get_main_keyboard())
    print(f"✅ Новый пользователь: {message.from_user.id}")

@dp.message(lambda msg: msg.text == "💰 Баланс")
async def show_balance(message: types.Message):
    balance = get_balance()
    daily_limit = get_daily_limit()
    days = get_days_until_next_payday()
    
    text = f"💰 *Текущий баланс:* {balance:.2f} руб.\n\n"
    if days > 0:
        text += f"📅 До 5-го числа следующего месяца осталось {days} дней.\n"
        text += f"📊 *Дневной лимит:* {daily_limit:.2f} руб./день\n"
        
        last_date = get_last_transaction_date()
        if last_date:
            hours_ago = (datetime.now() - last_date).total_seconds() / 3600
            if hours_ago > 24:
                text += f"\n⚠️ *Напоминание:* Последняя операция была {int(hours_ago/24)} дней назад. Пора записать траты!"
        elif balance > 0:
            text += f"\n💡 *Совет:* У вас есть {balance:.2f} руб. Запишите первую трату, чтобы начать бюджет!"
    else:
        text += "📅 Сегодня 5-е или позже. Новый доход еще не поступил."
    
    if days > 0 and daily_limit > 0:
        cursor.execute('''
            SELECT SUM(amount) FROM transactions
            WHERE type = 'expense' AND date >= datetime('now', 'start of day')
        ''')
        today_expense = cursor.fetchone()[0] or 0
        if today_expense > daily_limit:
            text += f"\n\n🚨 *Внимание!* Вы превысили дневной лимит на {today_expense - daily_limit:.2f} руб. Сегодня лучше экономить!"
        elif today_expense > daily_limit * 0.8:
            text += f"\n\n⚠️ Осталось потратить сегодня: {daily_limit - today_expense:.2f} руб. Будьте осторожны!"
    
    await message.answer(text, reply_markup=get_main_keyboard())

@dp.message(lambda msg: msg.text == "💸 Расход")
async def expense_start(message: types.Message, state: FSMContext):
    await state.set_state(BudgetStates.waiting_for_amount)
    await state.update_data(transaction_type='expense')
    await message.answer(
        "💸 Введите сумму расхода (например: 150.5):",
        reply_markup=get_main_keyboard()
    )

@dp.message(lambda msg: msg.text == "📈 Доход")
async def income_start(message: types.Message, state: FSMContext):
    await state.set_state(BudgetStates.waiting_for_amount)
    await state.update_data(transaction_type='income')
    await message.answer(
        "📈 Введите сумму дохода (например: 50000):",
        reply_markup=get_main_keyboard()
    )

@dp.message(BudgetStates.waiting_for_amount)
async def process_amount(message: types.Message, state: FSMContext):
    # Проверяем, хочет ли пользователь подтвердить трату
    if message.text.lower() in ['да', 'yes', 'конечно', 'подтверждаю', '+', 'lf']:
        data = await state.get_data()
        if 'pending_amount' in data:
            amount = data.get('pending_amount')
            await process_expense(message, state, amount)
            return
        else:
            await message.answer("❌ Нет суммы для подтверждения. Начните заново.")
            await state.clear()
            return
    
    try:
        amount = float(message.text.replace(',', '.').strip())
        if amount <= 0:
            await message.answer("❌ Сумма должна быть положительной! Попробуйте снова.")
            return
    except ValueError:
        await message.answer("❌ Некорректный ввод. Введите число (например: 150 или 150.5).")
        return
    
    data = await state.get_data()
    trans_type = data.get('transaction_type')
    
    if trans_type == 'expense':
        daily_limit = get_daily_limit()
        cursor.execute('''
            SELECT SUM(amount) FROM transactions
            WHERE type = 'expense' AND date >= datetime('now', 'start of day')
        ''')
        today_expense = cursor.fetchone()[0] or 0
        
        # Проверяем превышение лимита (только если лимит > 0)
        if daily_limit > 0 and today_expense + amount > daily_limit * 1.5:
            # Сохраняем сумму для подтверждения
            await state.update_data(pending_amount=amount)
            await message.answer(
                f"🚨 *Внимание!*\n"
                f"Эта трата ({amount:.2f} руб.) превышает ваш дневной лимит ({daily_limit:.2f} руб.)!\n"
                f"Сегодня уже потрачено: {today_expense:.2f} руб.\n\n"
                f"Вы уверены, что хотите потратить {amount:.2f} руб.?\n"
                f"Напишите *да* для подтверждения или введите другую сумму."
            )
            return
        
        # Если лимит не превышен, сразу добавляем
        await process_expense(message, state, amount)
    
    else:  # income
        new_balance = update_balance(amount)
        add_transaction(
            message.from_user.id,
            message.from_user.username or message.from_user.first_name,
            'income',
            amount,
            'Доход'
        )
        
        unlocked = check_achievements(message.from_user.id, message.from_user.username)
        
        response = f"✅ Доход {amount:.2f} руб. зачислен!\n"
        response += f"💰 Новый баланс: {new_balance:.2f} руб."
        
        if unlocked:
            response += "\n\n🏆 *Новые достижения:*\n" + "\n".join(f"✨ {ach}" for ach in unlocked)
        
        await state.clear()
        await message.answer(response, reply_markup=get_main_keyboard())

async def process_expense(message: types.Message, state: FSMContext, amount: float):
    """Обработка расхода с категорией"""
    # Очищаем pending_amount если был
    await state.update_data(amount=amount, pending_amount=None)
    await state.set_state(BudgetStates.waiting_for_category)
    await message.answer(
        f"💸 Сумма: {amount:.2f} руб.\n"
        f"Выберите категорию расхода:",
        reply_markup=get_category_keyboard()
    )

@dp.callback_query(BudgetStates.waiting_for_category)
async def process_category(callback: types.CallbackQuery, state: FSMContext):
    if not callback.data.startswith("cat_"):
        return
    
    category = callback.data[4:]
    data = await state.get_data()
    amount = data.get('amount')
    
    new_balance = update_balance(-amount)
    add_transaction(
        callback.from_user.id,
        callback.from_user.username or callback.from_user.first_name,
        'expense',
        amount,
        category
    )
    
    unlocked = check_achievements(callback.from_user.id, callback.from_user.username)
    
    response = f"✅ Расход {amount:.2f} руб. учтен!\n"
    response += f"📂 Категория: {category}\n"
    response += f"💰 Новый баланс: {new_balance:.2f} руб."
    
    daily_limit = get_daily_limit()
    if daily_limit > 0:
        cursor.execute('''
            SELECT SUM(amount) FROM transactions
            WHERE type = 'expense' AND date >= datetime('now', 'start of day')
        ''')
        today_expense = cursor.fetchone()[0] or 0
        
        if today_expense > daily_limit:
            response += f"\n\n⚠️ *Внимание!* Вы превысили дневной лимит на {today_expense - daily_limit:.2f} руб."
        elif today_expense > daily_limit * 0.8:
            response += f"\n\n📊 Осталось потратить сегодня: {daily_limit - today_expense:.2f} руб."
    
    if unlocked:
        response += "\n\n🏆 *Новые достижения:*\n" + "\n".join(f"✨ {ach}" for ach in unlocked)
    
    await callback.message.edit_text(response)
    await callback.answer()
    await state.clear()

@dp.message(lambda msg: msg.text == "📊 Отчеты")
async def show_reports(message: types.Message):
    await message.answer(
        "📊 Выберите тип отчета:",
        reply_markup=get_report_keyboard()
    )

@dp.callback_query(lambda c: c.data.startswith("report_"))
async def process_report(callback: types.CallbackQuery):
    report_type = callback.data[7:]
    
    if report_type == "week":
        report = "📊 Отчет за неделю\n\nПока нет данных"
    elif report_type == "month":
        report = "📊 Отчет за месяц\n\nПока нет данных"
    elif report_type == "categories":
        report = "📈 Расходы по категориям\n\nПока нет данных"
    else:
        report = "❌ Неизвестный тип отчета"
    
    await callback.message.edit_text(report)
    await callback.answer()

@dp.message(lambda msg: msg.text == "🏆 Достижения")
async def show_achievements(message: types.Message):
    user_achievements = get_user_achievements(message.from_user.id)
    
    if not user_achievements:
        text = "🏆 *Ваши достижения*\n\n"
        text += "Пока нет достижений. Начните активно пользоваться ботом!\n"
        text += "💡 Совет: записывайте все траты и доходы, и достижения не заставят себя ждать!"
    else:
        text = "🏆 *Ваши достижения:*\n\n"
        for ach in user_achievements:
            if ach in ACHIEVEMENTS:
                text += f"✨ {ACHIEVEMENTS[ach]}\n"
    
    text += f"\n📊 Всего: {len(user_achievements)} из {len(ACHIEVEMENTS)}"
    
    await message.answer(text, reply_markup=get_main_keyboard())

@dp.message(lambda msg: msg.text == "📖 Цитата")
async def show_quote(message: types.Message):
    quotes = [
        "Деньги — хороший слуга, но плохой хозяин.",
        "Богатство — это не количество денег, а количество вещей, от которых ты свободен.",
        "Экономный человек платит дважды.",
        "Не в деньгах счастье, но в их разумном использовании.",
        "Копейка рубль бережет.",
        "Лучше иметь деньги и не нуждаться, чем нуждаться и не иметь.",
    ]
    
    quote = random.choice(quotes)
    await message.answer(f"📖 *Цитата дня:*\n\n_{quote}_", reply_markup=get_main_keyboard())

# --- АВТОМАТИЧЕСКИЕ УВЕДОМЛЕНИЯ ---
async def daily_reminder():
    print("🌅 Отправка ежедневного уведомления...")
    balance = get_balance()
    daily_limit = get_daily_limit()
    days = get_days_until_next_payday()
    
    cursor.execute("SELECT DISTINCT user_id FROM user_stats")
    users = cursor.fetchall()
    
    for user in users:
        user_id = user[0]
        try:
            text = f"🌅 *Доброе утро! Бюджет Красновых*\n\n"
            text += f"💰 Баланс: {balance:.2f} руб.\n"
            
            if days > 0:
                text += f"📊 Дневной лимит: {daily_limit:.2f} руб.\n"
                text += f"📅 До зарплаты: {days} дней"
            
            await bot.send_message(user_id, text)
        except Exception as e:
            print(f"❌ Не удалось отправить уведомление пользователю {user_id}: {e}")

# --- ЗАПУСК БОТА ---
async def main():
    print("🚀 Запуск планировщика...")
    scheduler.add_job(daily_reminder, CronTrigger(hour=9, minute=0))
    scheduler.start()
    
    print("🤖 Бот 'Бюджет Красновых' запущен!")
    print(f"📊 База данных: {DB_PATH}")
    print("✅ Бот готов к работе!")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
