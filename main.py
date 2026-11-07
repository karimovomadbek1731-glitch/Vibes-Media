import os
import asyncio
import sqlite3
import logging
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    Message, CallbackQuery, LabeledPrice, PreCheckoutQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ================= SOZLAMALAR =================

TOKEN = os.getenv("9273297548:AAG25UUvYdmaE7nZxS5JhsMKJonzuTdOhwg")
ADMIN_ID = 8849504131

ADMIN_CONTACT = "@Madaniyatlikman"
CHANNEL = "@VibeMediaRasmiy"

PREMIUM_DAYS = 30
PREMIUM_STARS = 125

GENRES = [
    "Komediya", "Drama", "Qo‘rqinchli",
    "Fantastika", "Jangari", "Romantika",
    "Sarguzasht", "Triller", "Multfilm",
    "Detektiv", "Tarixiy", "Oilaviy"
]

logging.basicConfig(level=logging.INFO)

if not TOKEN:
    raise ValueError("BOT_TOKEN environment variable kiritilmagan!")

bot = Bot(TOKEN)
dp = Dispatcher()

# ================= BAZA =================

def connect():
    con = sqlite3.connect("vibemedia.db")
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with connect() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY,
            username TEXT,
            name TEXT,
            premium_until TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS movies(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            title TEXT,
            genre TEXT,
            description TEXT,
            file_id TEXT,
            file_type TEXT
        );

        CREATE TABLE IF NOT EXISTS history(
            user_id INTEGER,
            movie_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS favorites(
            user_id INTEGER,
            movie_id INTEGER,
            UNIQUE(user_id,movie_id)
        );

        CREATE TABLE IF NOT EXISTS likes(
            user_id INTEGER,
            movie_id INTEGER,
            UNIQUE(user_id,movie_id)
        );

        CREATE TABLE IF NOT EXISTS searches(
            movie_id INTEGER PRIMARY KEY,
            count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS admins(
            user_id INTEGER PRIMARY KEY
        );

        CREATE TABLE IF NOT EXISTS albums(
            user_id INTEGER,
            name TEXT
        );

        CREATE TABLE IF NOT EXISTS banned(
            user_id INTEGER PRIMARY KEY
        );
        """)
        con.execute(
            "INSERT OR IGNORE INTO admins(user_id) VALUES(?)",
            (ADMIN_ID,)
        )


def is_admin(user_id):
    with connect() as con:
        return con.execute(
            "SELECT 1 FROM admins WHERE user_id=?", (user_id,)
        ).fetchone() is not None


def is_premium(user_id):
    with connect() as con:
        row = con.execute(
            "SELECT premium_until FROM users WHERE id=?", (user_id,)
        ).fetchone()

    if not row or not row["premium_until"]:
        return False

    try:
        return datetime.fromisoformat(row["premium_until"]) > datetime.now()
    except ValueError:
        return False


def register_user(user):
    with connect() as con:
        con.execute("""
        INSERT INTO users(id,username,name)
        VALUES(?,?,?)
        ON CONFLICT(id) DO UPDATE SET
        username=excluded.username,
        name=excluded.name
        """, (user.id, user.username or "", user.full_name or ""))


# ================= TUGMALAR =================

def start_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✔️ Obuna bo‘lish",
                              url=f"https://t.me/{CHANNEL.replace('@','')}")],
        [InlineKeyboardButton(text="☑️ Tekshirish",
                              callback_data="check_subscription")],
        [InlineKeyboardButton(text="💎 Premium",
                              callback_data="premium")]
    ])


def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Menyu")],
            [KeyboardButton(text="📺 Rasmiy kanal"),
             KeyboardButton(text="🖍 Yordam")]
        ],
        resize_keyboard=True
    )


def menu_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔍 Film va seriallar qidirish")],
            [KeyboardButton(text="📍 Profil"),
             KeyboardButton(text="📊 Statistika")],
            [KeyboardButton(text="💎 Premium obuna")],
            [KeyboardButton(text="🖍 Yordam"),
             KeyboardButton(text="📒 Qo‘llanma")],
            [KeyboardButton(text="📺 Rasmiy kanal")]
        ],
        resize_keyboard=True
    )


def search_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔎 Nomi orqali qidirish")],
            [KeyboardButton(text="🔢 Kod orqali qidirish")],
            [KeyboardButton(text="🎭 Janrlar")],
            [KeyboardButton(text="📚 Janrlar haqida")],
            [KeyboardButton(text="⬅️ Ortga qaytish")]
        ],
        resize_keyboard=True
    )


def back_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⬅️ Ortga qaytish")]],
        resize_keyboard=True
    )


# ================= OBUNA TEKSHIRISH =================

async def subscription_ok(user_id):
    with connect() as con:
        channels = con.execute(
            "SELECT name FROM albums WHERE user_id=-1"
        ).fetchall()

    channel_list = [CHANNEL]

    for channel in channel_list:
        try:
            member = await bot.get_chat_member(channel, user_id)
            if member.status not in ("member", "administrator", "creator"):
                return False
        except Exception:
            return False

    return True


async def allowed(user_id):
    if is_admin(user_id) or is_premium(user_id):
        return True
    return await subscription_ok(user_id)


async def show_start(message):
    name = message.from_user.first_name
    await message.answer(
        f"Assalomu aleykum {name}!\n\n"
        "Xush kelibsiz Vibe Media botiga!\n"
        "Botdan foydalanish uchun avval majburiy kanalga obuna bo‘ling.\n\n"
        "📍 Premium orqali reklamasiz va majburiy obunasiz foydalanishingiz mumkin.",
        reply_markup=start_keyboard()
    )


@dp.message(CommandStart())
async def start(message: Message):
    register_user(message.from_user)
    await show_start(message)


@dp.callback_query(F.data == "check_subscription")
async def check_subscription(call: CallbackQuery):
    if await subscription_ok(call.from_user.id):
        await call.message.answer(
            "✅ Obuna tasdiqlandi!\n\n"
            "Assalomu aleykum!\n🍿 Vibe Media botiga xush kelibsiz.\n\n"
            "O‘z Vibeyingizni yarating!",
            reply_markup=main_keyboard()
        )
        await call.answer("Obuna tasdiqlandi!")
    else:
        await call.answer(
            "❌ Siz hali kanalga obuna bo‘lmagansiz!",
            show_alert=True
        )


# ================= PREMIUM =================

def premium_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"⭐️ {PREMIUM_STARS} Stars orqali",
            callback_data="buy_stars"
        )],
        [InlineKeyboardButton(
            text="Admin orqali olish",
            url=f"https://t.me/{ADMIN_CONTACT.replace('@','')}"
        )],
        [InlineKeyboardButton(
            text="⬅️ Ortga qaytish",
            callback_data="premium_back"
        )]
    ])


@dp.callback_query(F.data == "premium")
@dp.message(F.text == "💎 Premium obuna")
async def premium(event):
    if isinstance(event, CallbackQuery):
        message = event.message
        user_id = event.from_user.id
    else:
        message = event
        user_id = event.from_user.id

    if is_premium(user_id):
        with connect() as con:
            row = con.execute(
                "SELECT premium_until FROM users WHERE id=?",
                (user_id,)
            ).fetchone()

        await message.answer(
            f"💎 Siz Premium a'zosisiz!\n"
            f"Amal qilish muddati: {row['premium_until']}"
        )
    else:
        await message.answer(
            "💎 Premium nima?\n\n"
            "Premium sizga 30 kun davomida majburiy obunasiz "
            "va reklamalarsiz kino hamda seriallarni ko‘rish imkonini beradi.\n\n"
            f"💳 Narxi: 15 000 so‘m\n"
            f"⭐️ Telegram Stars: {PREMIUM_STARS}",
            reply_markup=premium_keyboard()
        )

    if isinstance(event, CallbackQuery):
        await event.answer()


@dp.callback_query(F.data == "premium_back")
async def premium_back(call: CallbackQuery):
    await call.message.answer("Asosiy menyu:", reply_markup=main_keyboard())
    await call.answer()


@dp.callback_query(F.data == "buy_stars")
async def buy_stars(call: CallbackQuery):
    await bot.send_invoice(
        chat_id=call.from_user.id,
        title="Vibe Media Premium",
        description="30 kunlik Premium obuna",
        payload=f"premium_{call.from_user.id}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="Premium 30 kun", amount=PREMIUM_STARS)]
    )
    await call.answer()


@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)


@dp.message(F.successful_payment)
async def successful_payment(message: Message):
    payment = message.successful_payment

    if payment.currency != "XTR":
        return

    if payment.total_amount != PREMIUM_STARS:
        return

    expiry = datetime.now() + timedelta(days=PREMIUM_DAYS)

    with connect() as con:
        con.execute(
            "UPDATE users SET premium_until=? WHERE id=?",
            (expiry.isoformat(), message.from_user.id)
        )

    await message.answer(
        "🎉 Tabriklaymiz!\n\n"
        "💎 Premium obunangiz faollashtirildi.\n"
        "Amal qilish muddati: 30 kun.",
        reply_markup=main_keyboard()
    )


# ================= MENYU =================

@dp.message(F.text == "📊 Menyu")
@dp.message(Command("menu"))
async def menu(message: Message):
    if not await allowed(message.from_user.id):
        await show_start(message)
        return

    await message.answer("🗂 Vibe Media menyusi:", reply_markup=menu_keyboard())


@dp.message(F.text == "⬅️ Ortga qaytish")
async def back(message: Message):
    await message.answer("Asosiy menyu:", reply_markup=menu_keyboard())


@dp.message(F.text == "📺 Rasmiy kanal")
async def official(message: Message):
    await message.answer("📺 Rasmiy kanal: https://t.me/VibeMediaRasmiy")


@dp.message(F.text == "🖍 Yordam")
async def support(message: Message):
    await message.answer(f"🖍 Savol va takliflar: {ADMIN_CONTACT}")


@dp.message(F.text == "📒 Qo‘llanma")
@dp.message(Command("help"))
async def guide(message: Message):
    await message.answer(
        "📒 VIBE MEDIA QO‘LLANMASI\n\n"
        "🔍 Film qidirish — nom, kod yoki janr orqali qidirish.\n"
        "📍 Profil — shaxsiy profilingiz.\n"
        "📊 Statistika — bot statistikasi.\n"
        "💎 Premium — 30 kunlik obuna.\n"
        "❤️ Sevimlilar — saqlangan filmlar.\n"
        "👍 Like — filmga baho berish.\n\n"
        "Film kodini yuborib ham topishingiz mumkin."
    )


@dp.message(F.text == "🔍 Film va seriallar qidirish")
async def search_menu(message: Message):
    if not await allowed(message.from_user.id):
        await show_start(message)
        return
    await message.answer("🔍 Qidirish turini tanlang:", reply_markup=search_keyboard())


@dp.message(F.text == "🔎 Nomi orqali qidirish")
async def name_search(message: Message):
    await message.answer("Film yoki serial nomini yuboring:", reply_markup=back_keyboard())


@dp.message(F.text == "🔢 Kod orqali qidirish")
async def code_search(message: Message):
    await message.answer("🔢 Film kodini yuboring:", reply_markup=back_keyboard())


@dp.message(F.text == "🎭 Janrlar")
async def genres(message: Message):
    kb = InlineKeyboardBuilder()
    for genre in GENRES:
        kb.button(text=genre, callback_data=f"genre:{genre}")
    kb.adjust(2)
    await message.answer("🎭 Janrni tanlang:", reply_markup=kb.as_markup())


@dp.message(F.text == "📚 Janrlar haqida")
async def genre_info(message: Message):
    await message.answer(
        "🎭 JANRLAR\n\n" +
        "\n".join(f"• {g}" for g in GENRES)
    )


@dp.callback_query(F.data.startswith("genre:"))
async def genre_result(call: CallbackQuery):
    genre = call.data.split(":", 1)[1]
    with connect() as con:
        rows = con.execute(
            "SELECT * FROM movies WHERE genre LIKE ? ORDER BY id DESC LIMIT 50",
            (f"%{genre}%",)
        ).fetchall()

    if not rows:
        await call.message.answer("Bu janrda hozircha film yo‘q.")
    else:
        kb = InlineKeyboardBuilder()
        for row in rows:
            kb.button(text=row["title"], callback_data=f"movie:{row['id']}")
        kb.adjust(1)
        await call.message.answer(
            f"🎭 {genre} janridagi filmlar:",
            reply_markup=kb.as_markup()
        )
    await call.answer()


# ================= FILM YUBORISH =================

async def send_movie(message, row):
    user_id = message.from_user.id
    with connect() as con:
        con.execute(
            "INSERT INTO history(user_id,movie_id) VALUES(?,?)",
            (user_id, row["id"])
        )
        con.execute(
            "INSERT INTO searches(movie_id,count) VALUES(?,1) "
            "ON CONFLICT(movie_id) DO UPDATE SET count=count+1",
            (row["id"],)
        )

    caption = (
        f"🎬 <b>{row['title']}</b>\n\n"
        f"🔢 Kod: <code>{row['code']}</code>\n"
        f"🎭 Janr: {row['genre']}\n\n"
        f"{row['description'] or ''}"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="❤️ Sevimli", callback_data=f"fav:{row['id']}"),
            InlineKeyboardButton(text="👍 Like", callback_data=f"like:{row['id']}")
        ]
    ])

    if row["file_type"] == "video":
        await message.answer_video(row["file_id"], caption=caption, reply_markup=kb)
    elif row["file_type"] == "photo":
        await message.answer_photo(row["file_id"], caption=caption, reply_markup=kb)
    elif row["file_type"] == "document":
        await message.answer_document(row["file_id"], caption=caption, reply_markup=kb)
    else:
        await message.answer(caption, reply_markup=kb)


@dp.callback_query(F.data.startswith("movie:"))
async def movie_callback(call: CallbackQuery):
    movie_id = int(call.data.split(":")[1])
    with connect() as con:
        row = con.execute("SELECT * FROM movies WHERE id=?", (movie_id,)).fetchone()
    if row:
        await send_movie(call.message, row)
    else:
        await call.answer("Film topilmadi.", show_alert=True)
    await call.answer()


@dp.message()
async def search_handler(message: Message):
    if not message.text or message.text.startswith("/"):
        return

    if message.text in [
        "📊 Menyu", "📺 Rasmiy kanal", "🖍 Yordam",
        "📒 Qo‘llanma", "🔍 Film va seriallar qidirish",
        "🔎 Nomi orqali qidirish", "🔢 Kod orqali qidirish",
        "🎭 Janrlar", "📚 Janrlar haqida", "⬅️ Ortga qaytish",
        "📍 Profil", "📊 Statistika", "💎 Premium obuna"
    ]:
        return

    if not await allowed(message.from_user.id):
        await show_start(message)
        return

    q = message.text.strip()
    with connect() as con:
        rows = con.execute(
            "SELECT * FROM movies WHERE code=? OR title LIKE ? OR genre LIKE ? LIMIT 10",
            (q, f"%{q}%", f"%{q}%")
        ).fetchall()

    if not rows:
        await message.answer("😕 Film topilmadi. Nom yoki kodni tekshiring.")
        return

    for row in rows:
        await send_movie(message, row)


# ================= PROFIL =================

@dp.message(F.text == "📍 Profil")
@dp.message(Command("profile"))
async def profile(message: Message):
    uid = message.from_user.id
    with connect() as con:
        count = con.execute(
            "SELECT COUNT(*) n FROM history WHERE user_id=?", (uid,)
        ).fetchone()["n"]
        favs = con.execute(
            "SELECT COUNT(*) n FROM favorites WHERE user_id=?", (uid,)
        ).fetchone()["n"]
        likes = con.execute(
            "SELECT COUNT(*) n FROM likes WHERE user_id=?", (uid,)
        ).fetchone()["n"]

    premium = "Faol 💎" if is_premium(uid) else "Faol emas"
    await message.answer(
        f"📍 SHAXSIY PROFIL\n\n"
        f"👤 Ism: {message.from_user.full_name}\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"🔎 Qidiruvlar: {count}\n"
        f"❤️ Sevimlilar: {favs}\n"
        f"👍 Like bosilgan: {likes}\n"
        f"💎 Premium: {premium}"
    )


# ================= STATISTIKA =================

@dp.message(F.text == "📊 Statistika")
async def statistics(message: Message):
    with connect() as con:
        users = con.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
        movies = con.execute("SELECT COUNT(*) n FROM movies").fetchone()["n"]
        premium = con.execute(
            "SELECT COUNT(*) n FROM users WHERE premium_until>?",
            (datetime.now().isoformat(),)
        ).fetchone()["n"]
        searches = con.execute("SELECT COALESCE(SUM(count),0) n FROM searches").fetchone()["n"]

    await message.answer(
        f"📊 VIBE MEDIA STATISTIKASI\n\n"
        f"👥 Foydalanuvchilar: {users}\n"
        f"🎬 Film va seriallar: {movies}\n"
        f"💎 Premium egalari: {premium}\n"
        f"🔎 Qidiruvlar: {searches}"
    )


# ================= ADMIN =================

class AddMovie(StatesGroup):
    media = State()
    details = State()


@dp.message(Command("st"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        return

    await message.answer(
        "🛠 VIBE MEDIA ADMIN PANEL\n\n"
        "/add — barcha filmlar ro‘yxati\n"
        "/new — film yoki serial qo‘shish\n"
        "/stats — statistika\n"
        "/m XABAR — hammaga xabar yuborish\n"
        "/rek XABAR — Premium bo‘lmaganlarga reklama\n"
        "/gift USER_ID — 30 kun Premium sovg‘a\n"
        "/ban USER_ID — foydalanuvchini ban qilish\n"
        "/unban USER_ID — bandan chiqarish\n"
        "/adminadd USER_ID — admin qo‘shish\n"
        "/adminremove USER_ID — adminni olib tashlash\n"
        "/top — eng ko‘p qidirilgan filmlar"
    )


@dp.message(Command("new"))
async def new_movie(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.set_state(AddMovie.media)
    await message.answer("🎬 Film videosi, rasmi yoki faylini yuboring.")


@dp.message(AddMovie.media, F.video | F.photo | F.document)
async def receive_media(message: Message, state: FSMContext):
    if message.video:
        file_id, file_type = message.video.file_id, "video"
    elif message.photo:
        file_id, file_type = message.photo[-1].file_id, "photo"
    else:
        file_id, file_type = message.document.file_id, "document"

    await state.update_data(file_id=file_id, file_type=file_type)
    await state.set_state(AddMovie.details)
    await message.answer(
        "Ma’lumotlarni shu formatda yuboring:\n\n"
        "<code>KOD | NOMI | JANR | TAVSIF</code>"
    )


@dp.message(AddMovie.details)
async def save_movie(message: Message, state: FSMContext):
    data = await state.get_data()
    parts = [x.strip() for x in (message.text or "").split("|", 3)]

    if len(parts) < 3:
        await message.answer("Format noto‘g‘ri. Qayta yuboring.")
        return

    code, title, genre = parts[:3]
    description = parts[3] if len(parts) > 3 else ""

    try:
        with connect() as con:
            con.execute(
                "INSERT INTO movies(code,title,genre,description,file_id,file_type) "
                "VALUES(?,?,?,?,?,?)",
                (code, title, genre, description, data["file_id"], data["file_type"])
            )
        await message.answer(f"✅ {title} bazaga qo‘shildi.")
        await state.clear()
    except sqlite3.IntegrityError:
        await message.answer("Bu kino kodi oldin ishlatilgan. Boshqa kod kiriting.")


@dp.message(Command("add"))
async def list_movies(message: Message):
    if not is_admin(message.from_user.id):
        return
    with connect() as con:
        rows = con.execute("SELECT code,title,genre FROM movies ORDER BY id DESC LIMIT 100").fetchall()
    if not rows:
        await message.answer("Hozircha filmlar yo‘q.")
        return
    text = "📚 FILMLAR RO‘YXATI\n\n"
    for r in rows:
        text += f"🔢 {r['code']} — {r['title']} ({r['genre']})\n"
    await message.answer(text[:4000])


@dp.message(Command("stats"))
async def admin_stats(message: Message):
    if not is_admin(message.from_user.id):
        return
    await statistics(message)


@dp.message(Command("top"))
async def top_movies(message: Message):
    if not is_admin(message.from_user.id):
        return
    with connect() as con:
        rows = con.execute("""
        SELECT m.title,s.count FROM searches s
        JOIN movies m ON m.id=s.movie_id
        ORDER BY s.count DESC LIMIT 20
        """).fetchall()
    if not rows:
        await message.answer("Qidiruv statistikasi hali bo‘sh.")
        return
    await message.answer("🏅 ENG KO‘P QIDIRILGANLAR\n\n" +
                         "\n".join(f"{i+1}. {r['title']} — {r['count']} marta"
                                   for i, r in enumerate(rows)))


async def send_to_users(text, premium_only=False):
    with connect() as con:
        rows = con.execute("SELECT id,premium_until FROM users").fetchall()

    sent = 0
    for row in rows:
        if premium_only:
            until = row["premium_until"]
            if until and datetime.fromisoformat(until) > datetime.now():
                continue
        try:
            await bot.send_message(row["id"], text)
            sent += 1
            await asyncio.sleep(0.04)
        except Exception:
            pass
    return sent


@dp.message(Command("m"))
async def broadcast(message: Message):
    if not is_admin(message.from_user.id):
        return
    text = message.text.partition(" ")[2].strip()
    if not text:
        await message.answer("Ishlatish: /m Xabar matni")
        return
    sent = await send_to_users(text)
    await message.answer(f"✅ Xabar {sent} ta foydalanuvchiga yuborildi.")


@dp.message(Command("rek"))
async def advertisement(message: Message):
    if not is_admin(message.from_user.id):
        return
    text = message.text.partition(" ")[2].strip()
    if not text:
        await message.answer("Ishlatish: /rek Reklama matni")
        return
    sent = await send_to_users(text, premium_only=True)
    await message.answer(f"✅ Reklama {sent} ta Premium bo‘lmagan foydalanuvchiga yuborildi.")


@dp.message(Command("gift"))
async def gift_premium(message: Message):
    if not is_admin(message.from_user.id):
        return
    try:
        uid = int(message.text.split()[1])
    except (IndexError, ValueError):
        await message.answer("Ishlatish: /gift USER_ID")
        return
    expiry = datetime.now() + timedelta(days=PREMIUM_DAYS)
    with connect() as con:
        con.execute(
            "UPDATE users SET premium_until=? WHERE id=?",
            (expiry.isoformat(), uid)
        )
    await message.answer("💎 Premium sovg‘a qilindi.")


@dp.message(Command("ban"))
async def ban_user(message: Message):
    if not is_admin(message.from_user.id):
        return
    try:
        uid = int(message.text.split()[1])
    except (IndexError, ValueError):
        await message.answer("Ishlatish: /ban USER_ID")
        return
    with connect() as con:
        con.execute("INSERT OR IGNORE INTO banned(user_id) VALUES(?)", (uid,))
    await message.answer("Foydalanuvchi ban qilindi.")


@dp.message(Command("unban"))
async def unban_user(message: Message):
    if not is_admin(message.from_user.id):
        return
    try:
        uid = int(message.text.split()[1])
    except (IndexError, ValueError):
        await message.answer("Ishlatish: /unban USER_ID")
        return
    with connect() as con:
        con.execute("DELETE FROM banned WHERE user_id=?", (uid,))
    await message.answer("Foydalanuvchi bandan chiqarildi.")


@dp.message(Command("adminadd"))
async def admin_add(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        uid = int(message.text.split()[1])
    except (IndexError, ValueError):
        await message.answer("Ishlatish: /adminadd USER_ID")
        return
    with connect() as con:
        con.execute("INSERT OR IGNORE INTO admins(user_id) VALUES(?)", (uid,))
    await message.answer("Admin qo‘shildi.")


@dp.message(Command("adminremove"))
async def admin_remove(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        uid = int(message.text.split()[1])
    except (IndexError, ValueError):
        await message.answer("Ishlatish: /adminremove USER_ID")
        return
    if uid == ADMIN_ID:
        await message.answer("Asosiy adminni olib tashlab bo‘lmaydi.")
        return
    with connect() as con:
        con.execute("DELETE FROM admins WHERE user_id=?", (uid,))
    await message.answer("Admin olib tashlandi.")


@dp.message()
async def banned_check(message: Message):
    with connect() as con:
        row = con.execute(
            "SELECT 1 FROM banned WHERE user_id=?", (message.from_user.id,)
        ).fetchone()
    if row:
        await message.answer("Siz botdan foydalanish huquqidan mahrum qilingansiz.")


async def main():
    init_db()
    logging.info("Vibe Media bot ishga tushdi.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
'''

requirements = "aiogram>=3.13,<4.0\n"
readme = """VIBE MEDIA — Python / aiogram 3

ENVIRONMENT VARIABLES:
BOT_TOKEN=BotFather bergan yangi token
ADMIN_ID=8849504131
REQUIRED_CHANNELS=@VibeMediaRasmiy
ADMIN_CONTACT=Madaniyatlikman

O‘rnatish:
pip install -r requirements.txt
python bot.py

Admin buyruqlari:
 /st
 /new
 /add
 /stats
 /top
 /m XABAR
 /rek REKLAMA
 /gift USER_ID
 /ban USER_ID
 /unban USER_ID
 /adminadd USER_ID
 /adminremove USER_ID

Film qo‘shish:
1. /new yuboring.
2. Video/rasm/fayl yuboring.
3. KOD | NOMI | JANR | TAVSIF formatida ma’lumot yuboring.

Muhim:
- Eski, chatda oshkor bo‘lgan tokenni BotFather orqali bekor qiling.
- Yangi tokenni kodga yozmang; hosting Environment Variables bo‘limida BOT_TOKEN nomi bilan saqlang.
- Majburiy obuna kanali botda admin huquqiga ega bo‘lishi kerak.
- SQLite bazasi bot.db o‘rniga vibemedia.db nomida yaratiladi.
- Telegram Stars to‘lovi 125 XTR qilib sozlangan.
- Bu kod barcha ko‘rsatilgan funksiyalarning to‘liq nusxasi emas: albomlarni boshqarish, alohida log kanal sozlamasi, serial epizodlari, reklama filtrlari va qidiruv tarixini alohida ko‘rish hali qo‘shilmagan.
"""

files = {
    "bot.py": bot_py,
    "requirements.txt": requirements,
    "README.txt": readme,
    ".env.example": "BOT_TOKEN=YANGI_TOKEN\nADMIN_ID=8849504131\nREQUIRED_CHANNELS=@VibeMediaRasmiy\nADMIN_CONTACT=Madaniyatlikman\n"
}
for name, content in files.items():
    with open(os.path.join(base, name), "w", encoding="utf-8") as f:
        f.write(content)

zip_path = "/mnt/data/vibe_media_python_bot.zip"
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
    for name in files:
        z.write(os.path.join(base, name), arcname=name)

print(zip_path)
