'use strict';
const fs = require('fs');
const path = require('path');
const TelegramBot = require('node-telegram-bot-api');

// ================================================================ sozlamalar
try { // .env faylni o'qish (qo'shimcha paketsiz)
  for (const line of fs.readFileSync(path.join(__dirname, '.env'), 'utf8').split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Za-z_]+)\s*=\s*(.*?)\s*$/);
    if (m && !(m[1] in process.env)) process.env[m[1]] = m[2].replace(/^["']|["']$/g, '');
  }
} catch (_) {}

const TOKEN = process.env.BOT_TOKEN;
if (!TOKEN) { console.error('BOT_TOKEN topilmadi (.env yoki hosting sozlamalarini tekshiring)'); process.exit(1); }
const MAIN_ADMIN = Number(process.env.ADMIN_ID || 8849504131);
const MAX_CHANNELS = 7;
const MAX_ALBUMS = 5;
const GENRES = ['Komediya', 'Qo‘rqinchli', 'Drama', 'Jangari', 'Fantastika', 'Melodrama', 'Triller', 'Multfilm', 'Sarguzasht', 'Serial'];
const GENRE_INFO = `🎭 Janrlar haqida:

😂 Komediya — kulgili va yengil filmlar.
😱 Qo‘rqinchli — dahshat va sirli filmlar.
🎭 Drama — hayotiy, his-tuyg‘uga boy filmlar.
💥 Jangari — jang, quvish va portlashlar.
🚀 Fantastika — kelajak, koinot va g‘aroyib olamlar.
💞 Melodrama — sevgi va munosabatlar haqida.
🔪 Triller — zo‘riqish va kutilmagan burilishlar.
🧸 Multfilm — bolalar va butun oila uchun.
🗺 Sarguzasht — safar va qiziqarli kashfiyotlar.
📺 Serial — ko‘p qismli filmlar.

Bitta film bir nechta janrda bo‘lishi mumkin (masalan: Komediya + Qo‘rqinchli).`;
const DEFAULTS = { contact: 'https://t.me/Madaniyatlikman', official: 'https://t.me/VibeMediaRasmiy', priceStars: 135, days: 30 };

// ================================================================ baza (JSON fayl)
const DB_FILE = path.join(process.env.DATA_DIR || __dirname, 'data.json');
let db = {
  users: {}, channels: [], logs: [], admins: [], movies: {}, albums: {},
  nextCode: 100, nextAlbum: 1, searches: 0, payments: [], settings: { ...DEFAULTS },
};
try {
  db = Object.assign(db, JSON.parse(fs.readFileSync(DB_FILE, 'utf8')));
  db.settings = Object.assign({}, DEFAULTS, db.settings);
} catch (_) {}

let saveTimer = null;
function save() {
  if (saveTimer) return;
  saveTimer = setTimeout(() => {
    saveTimer = null;
    try { fs.writeFileSync(DB_FILE + '.tmp', JSON.stringify(db)); fs.renameSync(DB_FILE + '.tmp', DB_FILE); }
    catch (e) { console.error('Saqlashda xato:', e.message); }
  }, 500);
}
process.on('SIGTERM', () => { try { fs.writeFileSync(DB_FILE, JSON.stringify(db)); } catch (_) {} process.exit(0); });

// ================================================================ yordamchilar
const S = () => db.settings;
const now = () => Math.floor(Date.now() / 1000);
const day = (ts) => new Date(ts * 1000).toISOString().slice(0, 10);
const chunk = (a, n) => { const r = []; for (let i = 0; i < a.length; i += n) r.push(a.slice(i, i + n)); return r; };
const short = (t, n = 40) => { t = String(t == null ? '' : t); return t.length > n ? t.slice(0, n - 1) + '…' : t; };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const norm = (s) => String(s).toLowerCase().replace(/[‘’`ʻʼ']/g, '');
const isAdmin = (id) => id === MAIN_ADMIN || db.admins.includes(id);
const isPremium = (u) => !!u && u.premiumUntil > now();

function ensureUser(id) {
  if (!db.users[id]) {
    db.users[id] = { id, name: '', username: '', joined: now(), last: now(), premiumUntil: 0, banned: false, searches: 0, history: [], favs: [], votes: {} };
  }
  return db.users[id];
}
function getUser(from) {
  const isNew = !db.users[from.id];
  const u = ensureUser(from.id);
  u.name = [from.first_name, from.last_name].filter(Boolean).join(' ') || 'Foydalanuvchi';
  u.username = from.username || '';
  u.last = now();
  if (isNew) logEvent(`🆕 Yangi foydalanuvchi: ${u.name} (${u.id})`);
  save();
  return u;
}
function grantPremium(id, days) {
  const u = ensureUser(id);
  u.premiumUntil = Math.max(now(), u.premiumUntil || 0) + days * 86400;
  save();
  return u;
}
function findUser(ref) {
  ref = String(ref || '').trim().replace(/^@/, '').toLowerCase();
  if (!ref) return null;
  if (/^\d+$/.test(ref)) return ensureUser(Number(ref));
  return Object.values(db.users).find((x) => (x.username || '').toLowerCase() === ref) || null;
}

// Tugmalar. style: primary (ko'k), success (yashil), danger (qizil). Bir qatorda bir xil rang.
const B = (text, data, style) => ({ text, callback_data: data, ...(style ? { style } : {}) });
const U = (text, url, style) => ({ text, url, ...(style ? { style } : {}) });
const KB = (rows) => ({ reply_markup: { inline_keyboard: rows }, disable_web_page_preview: true });
const back = (data) => [B('⬅️ Ortga qaytish', data || 'back', 'danger')];

const bot = new TelegramBot(TOKEN, { polling: true });
let BOT_ID = 0;
bot.getMe().then((me) => { BOT_ID = me.id; console.log('Bot ishga tushdi: @' + me.username); });
bot.on('polling_error', (e) => console.error('polling xato:', e.message));

async function show(chatId, msgId, text, rows) {
  if (msgId) {
    try {
      await bot.editMessageText(text, { chat_id: chatId, message_id: msgId, reply_markup: { inline_keyboard: rows || [] }, disable_web_page_preview: true });
      return;
    } catch (e) { if (String(e.message).includes('not modified')) return; }
  }
  await bot.sendMessage(chatId, text, KB(rows || []));
}

async function logEvent(text) {
  for (const ch of db.logs) {
    try { await bot.sendMessage(ch.chat, text); } catch (e) { console.error('Log kanalga yozib bo‘lmadi:', e.message); }
  }
}

// ================================================================ majburiy obuna
const subCache = new Map();
async function checkSubs(uid) {
  for (const ch of db.channels) {
    try {
      const m = await bot.getChatMember(ch.chat, uid);
      const ok = ['member', 'administrator', 'creator'].includes(m.status) || (m.status === 'restricted' && m.is_member);
      if (!ok) return false;
    } catch (e) { console.error('Obunani tekshirib bo‘lmadi', ch.chat, e.message); return false; }
  }
  return true;
}
async function allowed(uid, force) {
  if (isAdmin(uid) || isPremium(db.users[uid]) || !db.channels.length) return true;
  if (!force && (subCache.get(uid) || 0) > Date.now()) return true;
  const ok = await checkSubs(uid);
  if (ok) subCache.set(uid, Date.now() + 5 * 60 * 1000); else subCache.delete(uid);
  return ok;
}

// ================================================================ matnlar va ekranlar
const startText = (name) => `Assalomu aleykum ${name}!\nXush kelibsiz, botdan foydalanish uchun avval majburiy kanallarga obuna bo‘lib ☑️Tekshirish tugmasini bosing.\n\n📍Agar majburiy obunasiz va reklamalarsiz kino va seriallarni ko‘rmoqchi bo‘lsangiz Premiumga obuna bo‘ling.`;
function startRows() {
  const rows = db.channels.map((c) => [U('✔️ Obuna bo‘lish', c.link, 'primary')]);
  rows.push([B('☑️ Tekshirish', 'check', 'success')]);
  rows.push([B('💎 Premium', 'prem', 'danger')]);
  return rows;
}
const welcomeText = (name) => `Assalomu aleykum ${name}!\n🍿Vibe Media botiga xush kelibsiz.\n\nSiz bu bot orqali film va serialni juda sifatli holda janr, kod va nomi orqali topishingiz mumkin. To‘liq ma‘lumot olish uchun /help buyrug‘ini yuboring, menyu kerak bo‘lsa /menu buyrug‘i orqali yoki pastdagi menyu tugmasi orqali ko‘rib chiqishingiz mumkin. O‘z Vibeyingizni yarating.`;
const welcomeRows = () => [
  [B('📊 Menyu', 'menu', 'primary')],
  [U('📺 Rasmiy kanal', S().official, 'primary')],
  [U('🖍 Yordam', S().contact, 'primary')],
];
const menuRows = () => [
  [B('🔍 Film va seriallar qidirish', 'search', 'primary')],
  [B('📍 Profil', 'profile', 'success'), B('📊 Statistika', 'stats', 'success')],
  [B('💎 Premium Obuna', 'prem', 'danger')],
  [U('🖍 Yordam', S().contact, 'primary'), B('📒 Qo‘llanma', 'guide', 'primary')],
  [U('📺 Rasmiy kanal', S().official, 'primary')],
];
const searchRows = () => [
  [B('🔎 Nomi orqali qidirish', 's:name', 'primary'), B('🔢 Kod orqali qidirish', 's:code', 'primary')],
  ...chunk(GENRES.map((g, i) => B(g, 'g:' + i, 'success')), 2),
  [B('ℹ️ Janrlar haqida', 's:about', 'primary')],
  [B('⬅️ Ortga qaytish', 'menu', 'danger')],
];

const HELP = () => `🖍 Yordam — bot funksiyalari:

🔍 Film va seriallar qidirish — nomi, kodi yoki janri bo‘yicha film topish.
📍 Profil (/profile) — ID, qidiruv tarixi, sevimlilar, like bosgan filmlar va albomlar.
📊 Statistika — obunachilar, qidiruvlar, premium egalari, eng ko‘p qidirilgan filmlar.
💎 Premium Obuna — majburiy obunasiz va reklamasiz foydalanish.
📒 Qo‘llanma — botdan foydalanish tartibi.
❤️ 💔 🩵 💿 — har bir film ostida: like, dislike, sevimlilarga va albomga qo‘shish.

Buyruqlar: /start, /menu, /help, /profile
Savol va takliflar: ${S().contact}`;

const GUIDE = `📒 Qo‘llanma:

1️⃣ /start bosing, majburiy kanallarga obuna bo‘lib «☑️ Tekshirish» ni bosing (yoki Premium oling).
2️⃣ /menu orqali menyuni oching.
3️⃣ «🔍 Film va seriallar qidirish»:
   • 🔎 Nomi orqali — film nomini yozing.
   • 🔢 Kod orqali — film kodini yozing.
   • Janr tugmasi — shu janrdagi 50 tagacha film ro‘yxati chiqadi, nomi yonidagi /f kodini bossangiz film yuboriladi.
4️⃣ Serial bir necha qismdan iborat bo‘lsa, kerakli qism raqamini tanlang.
5️⃣ Film ostidagi ❤️ like, 💔 dislike, 🩵 sevimlilar va 💿 albom tugmalaridan foydalaning.
6️⃣ 📍 Profil — shaxsiy ma‘lumotlar, tarix, sevimlilar, like bosgan filmlar, albomlar (5 tagacha).
7️⃣ 📊 Statistika — bot statistikasi va eng ko‘p qidirilgan 20 ta film.
8️⃣ 💎 Premium — majburiy obunasiz va reklamasiz foydalanish.

Har bir bo‘limda «⬅️ Ortga qaytish» tugmasi bor.`;

function premiumText(u) {
  if (isPremium(u)) return `💎 Sizda Premium faol!\n\nAmal qilish muddati: ${day(u.premiumUntil)} gacha.\nMajburiy obuna va reklamalarsiz foydalanishingiz mumkin.`;
  return `💎Premium bu nima?\nBot oylik ta‘rifi, ya‘ni VIP 💎Premium sizga bir oy davomida majburiy obuna va reklamalarsiz kino va seriallarni ko‘rish imkoniyatini beradi.\n💎Premium ${S().days} kun amal qiladi va narxi - ⭐️${S().priceStars} Telegram stars.`;
}
function premiumRows(u) {
  if (isPremium(u)) return [back()];
  return [
    [B('⭐️ Premiumni stars orqali', 'stars', 'success')],
    [U('Admin orqali olish', S().contact, 'primary')],
    [B('⬅️ Ortga qaytish', 'back', 'danger')],
  ];
}

// ================================================================ filmlar
const moviesList = () => Object.values(db.movies);
const genresOf = (m) => (m.genres || []).join(', ') || '—';
function listText(title, movies) {
  if (!movies.length) return `${title}\n\nHozircha bo‘sh.`;
  return `${title}\n\n` + movies.map((m, i) => `${i + 1}. ${short(m.title)} — /f${m.code}`).join('\n') + '\n\nFilmni ochish uchun nomi yonidagi /f kodni bosing.';
}
function recordSearch(u, q) {
  u.searches = (u.searches || 0) + 1;
  db.searches = (db.searches || 0) + 1;
  u.history = (u.history || []).concat({ q, ts: now() }).slice(-30);
  save();
}
function movieRows(m, uid) {
  const u = db.users[uid] || {};
  const v = (u.votes || {})[m.code];
  const fav = (u.favs || []).includes(m.code);
  return [
    [B(`${v === 1 ? '✅' : '❤️'} ${m.likes || 0}`, `lk:${m.code}`, 'primary'), B(`${v === -1 ? '✅' : '💔'} ${m.dislikes || 0}`, `dl:${m.code}`, 'primary')],
    [B(fav ? '🩵 Sevimlilardan olib tashlash' : '🩵 Sevimlilarimga qo‘shish', `fv:${m.code}`, 'success')],
    [B('💿 Albomga qo‘shish', `aa:${m.code}`, 'success')],
  ];
}
async function sendMovie(chatId, uid, m, part) {
  const files = m.files || [];
  if (!files.length) return bot.sendMessage(chatId, '❌ Bu film hali yuklanmagan.');
  if (files.length > 1 && part == null) {
    const btns = files.map((_, i) => B(String(i + 1), `p:${m.code}:${i}`, 'primary'));
    return bot.sendMessage(chatId, `📺 ${m.title}\n🎭 ${genresOf(m)}\n🔢 Kod: ${m.code}\n\nQismni tanlang:`, KB(chunk(btns, 5)));
  }
  const idx = part || 0;
  const f = files[idx];
  if (!f) return bot.sendMessage(chatId, '❌ Qism topilmadi.');
  const caption = `🎬 ${m.title}${files.length > 1 ? ` — ${idx + 1}-qism` : ''}\n🎭 ${genresOf(m)} | 🔢 Kod: ${m.code}`;
  m.views = (m.views || 0) + 1;
  save();
  const opts = { caption, reply_markup: { inline_keyboard: movieRows(m, uid) } };
  return f.kind === 'document' ? bot.sendDocument(chatId, f.id, opts) : bot.sendVideo(chatId, f.id, opts);
}
function vote(u, m, val) {
  u.votes = u.votes || {};
  const cur = u.votes[m.code] || 0;
  if (cur === 1) m.likes = Math.max(0, (m.likes || 0) - 1);
  if (cur === -1) m.dislikes = Math.max(0, (m.dislikes || 0) - 1);
  if (cur === val) { delete u.votes[m.code]; return; }
  u.votes[m.code] = val;
  if (val === 1) m.likes = (m.likes || 0) + 1; else m.dislikes = (m.dislikes || 0) + 1;
}
const byCodes = (codes) => codes.map((c) => db.movies[c]).filter(Boolean);
const myAlbums = (uid) => Object.values(db.albums).filter((a) => a.user === uid);

// ================================================================ holatlar
const awaiting = new Map();    // uid -> 'name' | 'code' | 'albname'
const adminStates = new Map(); // adminId -> { step, draft?, skip? }

// ================================================================ admin yordamchilari
const ADMIN_HELP = `📖 Admin buyruqlari va ishlashi:

🎬 /add — filmlar ro‘yxati va yangi film qo‘shish tugmasi. Qo‘shish tartibi: nom → janr(lar) → video(lar) → /done. Bot film kodini beradi.
📋 /filmlar — barcha filmlar ro‘yxati (kod bilan)
🗑 /del KOD — filmni o‘chirish
📢 /kanal @username yoki ID — majburiy kanal/guruh qo‘shish (7 tagacha, bot u yerda admin bo‘lishi shart)
   /kanallar — ro‘yxat, /kanal_ochir RAQAM — o‘chirish
🗂 /log @username yoki ID — log kanal qo‘shish (bot admin bo‘lishi shart)
💎 /premium ID yoki @username [kun] — Premium sovg‘a qilish; /premium_ol ID — olib tashlash
🕘 Qidiruv tarixi, 💿 albomlar ro‘yxati, 👥 foydalanuvchilar — pastdagi tugmalarda
🚫 /ban ID yoki @username — bloklash; ✅ /unban — blokdan chiqarish
👮 /admin_qosh ID — admin qo‘shish; /admin_ol ID — adminni olish (faqat bosh admin)
✉️ /m — hammaga xabar yuborish
📢 /rek — faqat Premiumsizlarga reklama yuborish
💰 /narx STARS [KUN] — Premium narxi va muddati
🔗 /havola admin|kanal URL — havolalarni o‘zgartirish
❎ /cancel — joriy amalni bekor qilish`;

function adminPanelText() {
  const users = Object.values(db.users);
  const d = now() - 86400;
  return `📊 Bot statistikasi\n\n👥 Foydalanuvchilar: ${users.length}\n🆕 24 soatda yangi: ${users.filter((x) => x.joined > d).length}\n🟢 24 soatda faol: ${users.filter((x) => x.last > d).length}\n💎 Premium: ${users.filter(isPremium).length}\n🚫 Bloklanganlar: ${users.filter((x) => x.banned).length}\n🎬 Filmlar: ${moviesList().length}\n🔎 Qidiruvlar: ${db.searches || 0}\n💿 Albomlar: ${Object.keys(db.albums).length}\n📢 Majburiy kanallar: ${db.channels.length}/${MAX_CHANNELS}\n🗂 Log kanallar: ${db.logs.length}\n👮 Adminlar: ${1 + db.admins.length}\n\n${ADMIN_HELP}`;
}
const adminPanelRows = () => [
  [B('🎬 Film qo‘shish', 'ad:add', 'success'), B('📋 Filmlar', 'ad:list', 'success')],
  [B('📢 Majburiy kanal', 'ad:req', 'primary'), B('🗂 Log kanal', 'ad:log', 'primary')],
  [B('💎 Premium sovg‘a', 'ad:gift', 'danger'), B('🕘 Qidiruv tarixi', 'ad:hist', 'danger')],
  [B('💿 Albomlar', 'ad:albums', 'success'), B('👥 Foydalanuvchilar', 'ad:users', 'success')],
  [B('👮 Admin qo‘shish', 'ad:addadm', 'primary'), B('👮 Adminni olish', 'ad:deladm', 'primary')],
  [B('🚫 Ban', 'ad:ban', 'danger'), B('✅ Unban', 'ad:unban', 'danger')],
  [B('✉️ Hammaga xabar', 'ad:m', 'success'), B('📢 Reklama', 'ad:rek', 'success')],
];
const PROMPTS = {
  addreq: '📢 Majburiy kanal/guruh @username yoki ID sini yuboring (bot unda admin bo‘lishi shart). Bekor qilish: /cancel',
  addlog: '🗂 Log kanal @username yoki ID sini yuboring (bot unda admin bo‘lishi shart). Bekor qilish: /cancel',
  gift: '💎 Foydalanuvchi ID yoki @username va kunni yuboring.\nMasalan: 123456789 30 (kun yozilmasa standart muddat beriladi). Bekor qilish: /cancel',
  ban: '🚫 Bloklanadigan foydalanuvchi ID yoki @username ni yuboring:',
  unban: '✅ Blokdan chiqariladigan ID yoki @username ni yuboring:',
  addadm: '👮 Yangi admin ID sini yuboring:',
  deladm: '👮 Olinadigan admin ID sini yuboring:',
  bc: '✉️ Hammaga yuboriladigan xabarni yuboring (matn, rasm yoki video). Bekor qilish: /cancel',
  rek: '📢 Reklama xabarini yuboring (Premium egalariga yuborilmaydi). Bekor qilish: /cancel',
};

const genreRows = (sel) => [
  ...chunk(GENRES.map((g, i) => B((sel.includes(g) ? '✅ ' : '') + g, 'ag:' + i, 'success')), 2),
  [B('✅ Tayyor', 'agd', 'primary')],
];

async function addChannel(kind, raw) {
  const t = String(raw || '').trim();
  if (!t) return '❌ Kanal yuboring.';
  if (kind === 'req' && db.channels.length >= MAX_CHANNELS) return `Eng ko‘pi bilan ${MAX_CHANNELS} ta majburiy kanal bo‘ladi.`;
  const ref = /^-?\d+$/.test(t) ? Number(t) : (t.startsWith('@') ? t : '@' + t);
  let chat;
  try {
    chat = await bot.getChat(ref);
    const me = await bot.getChatMember(chat.id, BOT_ID);
    if (!['administrator', 'creator'].includes(me.status)) return '⚠️ Bot bu kanal/guruhda admin emas. Avval admin qiling.';
  } catch (_) { return '❌ Topilmadi yoki bot unda yo‘q.'; }
  let link = chat.username ? `https://t.me/${chat.username}` : chat.invite_link;
  if (!link) { try { link = await bot.exportChatInviteLink(chat.id); } catch (_) {} }
  if (!link && kind === 'req') return '❌ Havola olib bo‘lmadi. Botga havola yaratish huquqini bering.';
  const list = kind === 'req' ? db.channels : db.logs;
  const i = list.findIndex((c) => String(c.chat) === String(chat.id));
  if (i >= 0) list.splice(i, 1);
  list.push({ chat: chat.id, title: chat.title || t, link });
  subCache.clear();
  save();
  return `✅ Qo‘shildi: ${chat.title}`;
}
function gift(ref, days) {
  const u = findUser(ref);
  if (!u) return null;
  grantPremium(u.id, days);
  bot.sendMessage(u.id, `💎 Sizga ${days} kunlik Premium sovg‘a qilindi!\n${day(u.premiumUntil)} gacha majburiy obunasiz va reklamasiz foydalanishingiz mumkin.`).catch(() => {});
  return u;
}
function setBan(ref, on) {
  const u = findUser(ref);
  if (!u) return '❌ Foydalanuvchi topilmadi.';
  if (isAdmin(u.id)) return '⚠️ Adminni bloklab bo‘lmaydi.';
  u.banned = on;
  save();
  return on ? `🚫 ${u.id} bloklandi.` : `✅ ${u.id} blokdan chiqarildi.`;
}
function setAdmin(ref, on) {
  const id = Number(String(ref).trim());
  if (!id) return '❌ To‘g‘ri ID yuboring.';
  if (id === MAIN_ADMIN) return 'Bu bosh admin.';
  db.admins = db.admins.filter((x) => x !== id);
  if (on) db.admins.push(id);
  save();
  return on ? `✅ ${id} admin qilindi.` : `✅ ${id} adminlikdan olindi.`;
}
async function broadcast(msg, skipPremium) {
  let ok = 0, fail = 0;
  const targets = Object.values(db.users).filter((u) => !u.banned && !(skipPremium && isPremium(u)));
  for (const u of targets) {
    try { await bot.copyMessage(u.id, msg.chat.id, msg.message_id); ok++; } catch (_) { fail++; }
    await sleep(50);
  }
  return bot.sendMessage(msg.chat.id, `📨 Yuborildi: ${ok}\n❌ Yetmadi: ${fail}`);
}
function filmListText() {
  const list = moviesList().sort((a, b) => b.added - a.added).slice(0, 40);
  if (!list.length) return '🎬 Filmlar hali yo‘q. /add bilan qo‘shing.';
  return `🎬 Filmlar (jami ${moviesList().length}, oxirgi ${list.length} ta):\n\n` +
    list.map((m) => `${m.code} — ${short(m.title, 30)} [${genresOf(m)}] 👁${m.views || 0}`).join('\n') + '\n\nO‘chirish: /del KOD';
}

async function adminInput(msg, st) {
  const uid = msg.from.id;
  const text = (msg.text || '').trim();
  const say = (t) => bot.sendMessage(uid, t, { disable_web_page_preview: true });
  const end = () => adminStates.delete(uid);
  switch (st.step) {
    case 'title':
      if (!text) return say('Film nomini matn bilan yuboring.');
      st.draft.title = text;
      st.step = 'genres';
      return bot.sendMessage(uid, '🎭 Janr(lar)ni tanlang (bir nechta bo‘lishi mumkin) va «✅ Tayyor» ni bosing:', KB(genreRows(st.draft.genres)));
    case 'genres':
      return say('Janrni yuqoridagi tugmalar orqali tanlang.');
    case 'files': {
      const f = msg.video ? { id: msg.video.file_id, kind: 'video' } : msg.document ? { id: msg.document.file_id, kind: 'document' } : null;
      if (!f) return say('Video yoki fayl yuboring (/done — tugatish).');
      st.draft.files.push(f);
      return say(`✅ ${st.draft.files.length}-fayl qabul qilindi. Yana yuboring yoki /done bosing.`);
    }
    case 'addreq': end(); return say(await addChannel('req', text));
    case 'addlog': end(); return say(await addChannel('log', text));
    case 'gift': {
      end();
      const [ref, d] = text.split(/\s+/);
      const days = Number(d) || S().days;
      const u = gift(ref, days);
      return say(u ? `✅ ${u.id} ga ${days} kunlik Premium berildi.` : '❌ Foydalanuvchi topilmadi.');
    }
    case 'ban': end(); return say(setBan(text, true));
    case 'unban': end(); return say(setBan(text, false));
    case 'addadm': end(); return say(uid === MAIN_ADMIN ? setAdmin(text, true) : 'Faqat bosh admin.');
    case 'deladm': end(); return say(uid === MAIN_ADMIN ? setAdmin(text, false) : 'Faqat bosh admin.');
    case 'bc': end(); return broadcast(msg, st.skip);
  }
}

// ================================================================ buyruqlar
const priv = (msg) => msg.chat.type === 'private';
const userCmd = (fn) => async (msg, m) => {
  try {
    if (!priv(msg)) return;
    const u = getUser(msg.from);
    if (u.banned && !isAdmin(msg.from.id)) return bot.sendMessage(msg.chat.id, '🚫 Siz bloklangansiz.');
    await fn(msg, m, u);
  } catch (e) { console.error('buyruq xato:', e.message); }
};
const adminCmd = (fn) => async (msg, m) => {
  try {
    if (!priv(msg) || !isAdmin(msg.from.id)) return;
    await fn(msg, m);
  } catch (e) { console.error('admin xato:', e.message); bot.sendMessage(msg.chat.id, '⚠️ Xato: ' + e.message).catch(() => {}); }
};
const reply = (msg, text) => bot.sendMessage(msg.chat.id, text, { disable_web_page_preview: true });

bot.onText(/^\/start(?:@\w+)?(?:\s.*)?$/, userCmd(async (msg, m, u) => {
  if (await allowed(msg.from.id)) return show(msg.chat.id, null, welcomeText(u.name), welcomeRows());
  return show(msg.chat.id, null, startText(u.name), startRows());
}));
bot.onText(/^\/menu(?:@\w+)?$/, userCmd(async (msg, m, u) => {
  if (!(await allowed(msg.from.id))) return show(msg.chat.id, null, startText(u.name), startRows());
  return show(msg.chat.id, null, '🗂Menyu', menuRows());
}));
bot.onText(/^\/help(?:@\w+)?$/, userCmd(async (msg) => show(msg.chat.id, null, HELP(), [[U('🖍 Yordam', S().contact, 'primary')]])));
bot.onText(/^\/profil(?:e)?(?:@\w+)?$/, userCmd(async (msg, m, u) => {
  if (!(await allowed(msg.from.id))) return show(msg.chat.id, null, startText(u.name), startRows());
  return show(msg.chat.id, null, profileText(u), profileRows());
}));
bot.onText(/^\/f(\d+)(?:@\w+)?$/, userCmd(async (msg, m, u) => {
  if (!(await allowed(msg.from.id))) return show(msg.chat.id, null, startText(u.name), startRows());
  const movie = db.movies[m[1]];
  if (!movie) return bot.sendMessage(msg.chat.id, '❌ Bunday kodli film topilmadi.');
  recordSearch(u, `/f${m[1]} ${movie.title}`);
  return sendMovie(msg.chat.id, msg.from.id, movie);
}));

function profileText(u) {
  return `📍 Profil\n\n🆔 ID: ${u.id}\n👤 Ism: ${u.name}\n📅 Qo‘shilgan: ${day(u.joined)}\n💎 Premium: ${isPremium(u) ? day(u.premiumUntil) + ' gacha' : 'yo‘q'}\n🔎 Qidiruvlar soni: ${u.searches || 0}\n🩵 Sevimlilar: ${(u.favs || []).length}\n❤️ Like bosganlar: ${Object.values(u.votes || {}).filter((v) => v === 1).length}\n💿 Albomlar: ${myAlbums(u.id).length}/${MAX_ALBUMS}`;
}
const profileRows = () => [
  [B('🕘 Qidiruv tarixi', 'pf:h', 'success'), B('🩵 Sevimlilarim', 'pf:f', 'success')],
  [B('❤️ Like bosganlarim', 'pf:l', 'primary'), B('💿 Albomlarim', 'alb', 'primary')],
  [B('⬅️ Ortga qaytish', 'menu', 'danger')],
];

// --- admin buyruqlari
const sendAdminPanel = (chatId, mid) => show(chatId, mid, adminPanelText(), adminPanelRows());
bot.onText(/^\/(?:st|admin)(?:@\w+)?$/i, adminCmd(async (msg) => { adminStates.delete(msg.from.id); return sendAdminPanel(msg.chat.id); }));
bot.onText(/^\/cancel(?:@\w+)?$/, adminCmd(async (msg) => { adminStates.delete(msg.from.id); return reply(msg, '❎ Bekor qilindi.'); }));
bot.onText(/^\/add(?:@\w+)?$/, adminCmd(async (msg) => bot.sendMessage(msg.chat.id, filmListText(), KB([[B('➕ Yangi film/serial qo‘shish', 'ad:add', 'success')]]))));
bot.onText(/^\/filmlar(?:@\w+)?$/, adminCmd(async (msg) => reply(msg, filmListText())));
bot.onText(/^\/done(?:@\w+)?$/, adminCmd(async (msg) => {
  const st = adminStates.get(msg.from.id);
  if (!st || st.step !== 'files') return reply(msg, 'Avval /add orqali film qo‘shishni boshlang.');
  const d = st.draft;
  if (!d.files.length) return reply(msg, 'Hali fayl yuborilmadi.');
  const code = String(db.nextCode++);
  db.movies[code] = { code, title: d.title, genres: d.genres, files: d.files, views: 0, likes: 0, dislikes: 0, added: now() };
  save();
  adminStates.delete(msg.from.id);
  logEvent(`🎬 Yangi film qo‘shildi: ${d.title} (kod ${code})`);
  return reply(msg, `✅ Saqlandi!\n🎬 ${d.title}\n🎭 ${d.genres.join(', ')}\n📦 Fayllar: ${d.files.length}\n🔢 Kod: ${code}`);
}));
bot.onText(/^\/del\s+(\d+)/, adminCmd(async (msg, m) => {
  const mv = db.movies[m[1]];
  if (!mv) return reply(msg, 'Bunday kod topilmadi.');
  delete db.movies[m[1]];
  save();
  return reply(msg, `🗑 O‘chirildi: ${mv.title}`);
}));
bot.onText(/^\/kanal\s+(\S+)/, adminCmd(async (msg, m) => reply(msg, await addChannel('req', m[1]))));
bot.onText(/^\/log\s+(\S+)/, adminCmd(async (msg, m) => reply(msg, await addChannel('log', m[1]))));
bot.onText(/^\/kanallar(?:@\w+)?$/, adminCmd(async (msg) =>
  reply(msg, db.channels.length ? db.channels.map((c, i) => `${i + 1}. ${c.title} — ${c.link}`).join('\n') : 'Majburiy kanallar yo‘q.')));
bot.onText(/^\/kanal_ochir\s+(\d+)/, adminCmd(async (msg, m) => {
  const i = Number(m[1]) - 1;
  if (!db.channels[i]) return reply(msg, 'Bunday raqam yo‘q. /kanallar ni ko‘ring.');
  const [x] = db.channels.splice(i, 1);
  subCache.clear();
  save();
  return reply(msg, `✅ O‘chirildi: ${x.title}`);
}));
bot.onText(/^\/premium\s+(\S+)(?:\s+(\d+))?/, adminCmd(async (msg, m) => {
  const days = Number(m[2] || S().days);
  const u = gift(m[1], days);
  return reply(msg, u ? `✅ ${u.id} ${u.name ? '(' + u.name + ') ' : ''}ga ${days} kunlik Premium berildi.` : '❌ Foydalanuvchi topilmadi (@username faqat botga kirganlar uchun, ID ishlatib ko‘ring).');
}));
bot.onText(/^\/premium_ol\s+(\S+)/, adminCmd(async (msg, m) => {
  const u = findUser(m[1]);
  if (!u) return reply(msg, '❌ Foydalanuvchi topilmadi.');
  u.premiumUntil = 0;
  save();
  return reply(msg, `✅ ${u.id} dan Premium olib tashlandi.`);
}));
bot.onText(/^\/ban\s+(\S+)/, adminCmd(async (msg, m) => reply(msg, setBan(m[1], true))));
bot.onText(/^\/unban\s+(\S+)/, adminCmd(async (msg, m) => reply(msg, setBan(m[1], false))));
bot.onText(/^\/admin_qosh\s+(\S+)/, adminCmd(async (msg, m) => reply(msg, msg.from.id === MAIN_ADMIN ? setAdmin(m[1], true) : 'Faqat bosh admin.')));
bot.onText(/^\/admin_ol\s+(\S+)/, adminCmd(async (msg, m) => reply(msg, msg.from.id === MAIN_ADMIN ? setAdmin(m[1], false) : 'Faqat bosh admin.')));
bot.onText(/^\/m(?:@\w+)?$/, adminCmd(async (msg) => { adminStates.set(msg.from.id, { step: 'bc', skip: false }); return reply(msg, PROMPTS.bc); }));
bot.onText(/^\/(?:rek|reklama)(?:@\w+)?$/, adminCmd(async (msg) => { adminStates.set(msg.from.id, { step: 'bc', skip: true }); return reply(msg, PROMPTS.rek); }));
bot.onText(/^\/narx\s+(\d+)(?:\s+(\d+))?/, adminCmd(async (msg, m) => {
  S().priceStars = Number(m[1]);
  if (m[2]) S().days = Number(m[2]);
  save();
  return reply(msg, `✅ Narx: ⭐️${S().priceStars} / ${S().days} kun`);
}));
bot.onText(/^\/havola\s+(admin|kanal)\s+(\S+)/, adminCmd(async (msg, m) => {
  let url = m[2];
  if (url.startsWith('@')) url = 'https://t.me/' + url.slice(1);
  S()[m[1] === 'admin' ? 'contact' : 'official'] = url;
  save();
  return reply(msg, `✅ ${m[1]} havolasi: ${url}`);
}));

// ================================================================ Stars to'lovi
bot.on('pre_checkout_query', (q) => {
  const ok = q.invoice_payload === 'premium' && q.currency === 'XTR' && q.total_amount === S().priceStars;
  bot.answerPreCheckoutQuery(q.id, ok, ok ? {} : { error_message: 'Narx o‘zgargan. Qaytadan urinib ko‘ring.' }).catch((e) => console.error(e.message));
});

// ================================================================ tugmalar (callback)
const GATED = /^(menu|search|profile|stats|top|g:|s:|p:|pf:|alb|al:|ald:|alnew|aa:|ap:|lk:|dl:|fv:)/;
const ADMIN_CB = /^(ad:|ag:|agd|dc:|dg:)/;

bot.on('callback_query', async (q) => {
  const uid = q.from.id;
  const chatId = q.message.chat.id;
  const mid = q.message.message_id;
  const data = q.data || '';
  const u = getUser(q.from);
  const done = (text, alert) => bot.answerCallbackQuery(q.id, text ? { text, show_alert: !!alert } : {}).catch(() => {});

  try {
    if (u.banned && !isAdmin(uid)) return done('🚫 Siz bloklangansiz.', true);

    // ---------- admin tugmalari
    if (ADMIN_CB.test(data)) {
      if (!isAdmin(uid)) return done();
      await done();
      if (data === 'ad:panel') return sendAdminPanel(chatId, mid);
      if (data === 'ad:add') {
        adminStates.set(uid, { step: 'title', draft: { genres: [], files: [] } });
        return bot.sendMessage(chatId, '🎬 Film/serial nomini yuboring (bekor qilish: /cancel):');
      }
      if (data.startsWith('ag:')) {
        const st = adminStates.get(uid);
        if (!st || st.step !== 'genres') return;
        const g = GENRES[Number(data.slice(3))];
        const sel = st.draft.genres;
        const i = sel.indexOf(g);
        if (i >= 0) sel.splice(i, 1); else sel.push(g);
        return bot.editMessageReplyMarkup({ inline_keyboard: genreRows(sel) }, { chat_id: chatId, message_id: mid }).catch(() => {});
      }
      if (data === 'agd') {
        const st = adminStates.get(uid);
        if (!st || st.step !== 'genres') return;
        if (!st.draft.genres.length) return bot.sendMessage(chatId, 'Kamida bitta janrni tanlang.');
        st.step = 'files';
        return bot.sendMessage(chatId, `🎭 Janr: ${st.draft.genres.join(', ')}\n\nEndi video (yoki fayl) yuboring. Serial bo‘lsa, qismlarni ketma-ket yuboring. Tugagach /done bosing.`);
      }
      if (data === 'ad:list') return bot.sendMessage(chatId, filmListText());
      if (data === 'ad:req') {
        const rows = db.channels.map((c, i) => [B(`❌ ${short(c.title, 28)}`, `dc:${i}`, 'danger')]);
        rows.push([B('➕ Qo‘shish', 'ad:addreq', 'success')], back('ad:panel'));
        return show(chatId, mid, `📢 Majburiy kanallar (${db.channels.length}/${MAX_CHANNELS}). O‘chirish uchun nomini bosing:`, rows);
      }
      if (data === 'ad:log') {
        const rows = db.logs.map((c, i) => [B(`❌ ${short(c.title, 28)}`, `dg:${i}`, 'danger')]);
        rows.push([B('➕ Qo‘shish', 'ad:addlog', 'success')], back('ad:panel'));
        return show(chatId, mid, `🗂 Log kanallar (${db.logs.length}). O‘chirish uchun nomini bosing:`, rows);
      }
      if (data.startsWith('dc:')) { db.channels.splice(Number(data.slice(3)), 1); subCache.clear(); save(); return show(chatId, mid, '✅ O‘chirildi.', [back('ad:req')]); }
      if (data.startsWith('dg:')) { db.logs.splice(Number(data.slice(3)), 1); save(); return show(chatId, mid, '✅ O‘chirildi.', [back('ad:log')]); }
      if (data === 'ad:hist') {
        const items = [];
        for (const x of Object.values(db.users)) for (const h of x.history || []) items.push({ ...h, x });
        items.sort((a, b) => b.ts - a.ts);
        const lines = items.slice(0, 30).map((h) => `${new Date(h.ts * 1000).toISOString().slice(5, 16).replace('T', ' ')} | ${short(h.x.name, 14)} (${h.x.id}): ${short(h.q, 32)}`);
        return show(chatId, mid, '🕘 So‘nggi 30 ta qidiruv (UTC):\n\n' + (lines.join('\n') || 'Hali bo‘sh.'), [back('ad:panel')]);
      }
      if (data === 'ad:albums') {
        const all = Object.values(db.albums);
        const lines = all.slice(-40).map((a) => `👤 ${short((db.users[a.user] || {}).name, 14)} (${a.user}) — 💿 ${short(a.name, 20)} (${a.items.length} ta)`);
        return show(chatId, mid, `💿 Foydalanuvchilar albomlari (jami ${all.length}):\n\n` + (lines.join('\n') || 'Hali bo‘sh.'), [back('ad:panel')]);
      }
      if (data === 'ad:users') {
        const list = Object.values(db.users).sort((a, b) => b.joined - a.joined).slice(0, 30);
        const lines = list.map((x) => `${x.id} — ${short(x.name, 18)}${x.username ? ' @' + x.username : ''}${isPremium(x) ? ' 💎' : ''}${x.banned ? ' 🚫' : ''}`);
        return show(chatId, mid, `👥 Oxirgi qo‘shilgan 30 ta foydalanuvchi (jami ${db.users ? Object.keys(db.users).length : 0}):\n\n` + (lines.join('\n') || 'Hali bo‘sh.'), [back('ad:panel')]);
      }
      if (data === 'ad:m' || data === 'ad:rek') {
        adminStates.set(uid, { step: 'bc', skip: data === 'ad:rek' });
        return bot.sendMessage(chatId, data === 'ad:rek' ? PROMPTS.rek : PROMPTS.bc);
      }
      if (data === 'ad:addadm' || data === 'ad:deladm') {
        if (uid !== MAIN_ADMIN) return bot.sendMessage(chatId, 'Faqat bosh admin.');
        adminStates.set(uid, { step: data.slice(3) });
        return bot.sendMessage(chatId, PROMPTS[data.slice(3)]);
      }
      const step = data.slice(3); // addreq, addlog, gift, ban, unban
      if (PROMPTS[step]) {
        adminStates.set(uid, { step });
        return bot.sendMessage(chatId, PROMPTS[step]);
      }
      return;
    }

    // ---------- umumiy
    if (data === 'check') {
      if (!(await allowed(uid, true))) return done('Obuna bo‘lmadingiz!', true);
      await done();
      return show(chatId, mid, welcomeText(u.name), welcomeRows());
    }
    if (data === 'back') {
      await done();
      if (await allowed(uid)) return show(chatId, mid, '🗂Menyu', menuRows());
      return show(chatId, mid, startText(u.name), startRows());
    }
    if (data === 'prem') { await done(); return show(chatId, mid, premiumText(u), premiumRows(u)); }
    if (data === 'stars') {
      await done();
      await bot.sendMessage(chatId, `Botga ⭐️${S().priceStars} stars to‘lash tugmasini bosing. Pastda tugma bo‘ladi, bosilsa Telegram orqali stars to‘lanadi va bot avtomatik ishga tushadi. Obunalarsiz ham, reklamalarsiz ham foydalanasiz.`);
      return bot.sendInvoice(chatId, '💎 Premium', `${S().days} kunlik Premium obuna`, 'premium', '', 'XTR',
        [{ label: `Premium ${S().days} kun`, amount: S().priceStars }]);
    }

    if (GATED.test(data) && !(await allowed(uid))) return done('Avval obuna bo‘ling! /start', true);

    // ---------- film ostidagi tugmalar
    if (/^(lk|dl|fv):/.test(data)) {
      const [act, code] = data.split(':');
      const m = db.movies[code];
      if (!m) return done('Film topilmadi', true);
      if (act === 'fv') {
        u.favs = u.favs || [];
        const i = u.favs.indexOf(code);
        if (i >= 0) { u.favs.splice(i, 1); await done('Sevimlilardan olib tashlandi'); }
        else { u.favs.push(code); await done('🩵 Sevimlilarga qo‘shildi'); }
      } else {
        vote(u, m, act === 'lk' ? 1 : -1);
        await done();
      }
      save();
      return bot.editMessageReplyMarkup({ inline_keyboard: movieRows(m, uid) }, { chat_id: chatId, message_id: mid }).catch(() => {});
    }

    await done();

    // ---------- albomlar
    if (data === 'alb') {
      const mine = myAlbums(uid);
      const rows = mine.map((a) => [B(`💿 ${short(a.name, 28)} (${a.items.length})`, `al:${a.id}`, 'primary')]);
      if (mine.length < MAX_ALBUMS) rows.push([B('➕ Yangi albom', 'alnew', 'success')]);
      rows.push(back('profile'));
      return show(chatId, mid, `💿 Albomlaringiz (${mine.length}/${MAX_ALBUMS}):`, rows);
    }
    if (data === 'alnew') {
      if (myAlbums(uid).length >= MAX_ALBUMS) return done(`Eng ko‘pi bilan ${MAX_ALBUMS} ta albom ochish mumkin`, true);
      awaiting.set(uid, 'albname');
      return show(chatId, mid, '💿 Albom nomini yuboring:', [back('alb')]);
    }
    if (data.startsWith('al:')) {
      const a = db.albums[data.slice(3)];
      if (!a || a.user !== uid) return;
      return show(chatId, mid, listText(`💿 ${a.name}`, byCodes(a.items)), [[B('🗑 Albomni o‘chirish', `ald:${a.id}`, 'danger')], back('alb')]);
    }
    if (data.startsWith('ald:')) {
      const a = db.albums[data.slice(4)];
      if (a && a.user === uid) { delete db.albums[a.id]; save(); }
      return show(chatId, mid, '✅ Albom o‘chirildi.', [back('alb')]);
    }
    if (data.startsWith('aa:')) {
      const code = data.slice(3);
      const mine = myAlbums(uid);
      if (!mine.length) return bot.sendMessage(chatId, '💿 Avval albom oching: /profile → Albomlarim → ➕ Yangi albom.');
      return bot.sendMessage(chatId, 'Qaysi albomga qo‘shamiz?', KB(mine.map((a) => [B(`💿 ${short(a.name, 28)}`, `ap:${a.id}:${code}`, 'primary')])));
    }
    if (data.startsWith('ap:')) {
      const [, aid, code] = data.split(':');
      const a = db.albums[aid];
      if (!a || a.user !== uid) return;
      if (!a.items.includes(code)) a.items.push(code);
      save();
      return show(chatId, mid, `✅ «${a.name}» albomiga qo‘shildi.`, []);
    }

    // ---------- menyu va qidiruv
    if (data === 'menu') { awaiting.delete(uid); return show(chatId, mid, '🗂Menyu', menuRows()); }
    if (data === 'guide') return show(chatId, mid, GUIDE, [back('menu')]);
    if (data === 'search') { awaiting.delete(uid); return show(chatId, mid, '🔍 Film va seriallar qidirish', searchRows()); }
    if (data === 's:name') { awaiting.set(uid, 'name'); return show(chatId, mid, '🔎 Film nomini yuboring:', [back('search')]); }
    if (data === 's:code') { awaiting.set(uid, 'code'); return show(chatId, mid, '🔢 Film kodini yuboring:', [back('search')]); }
    if (data === 's:about') return show(chatId, mid, GENRE_INFO, [back('search')]);
    if (data.startsWith('g:')) {
      const genre = GENRES[Number(data.slice(2))];
      const list = moviesList().filter((m) => (m.genres || []).includes(genre)).sort((a, b) => b.added - a.added).slice(0, 50);
      return show(chatId, mid, listText(`🎭 ${genre} (${list.length} ta)`, list), [back('search')]);
    }
    if (data.startsWith('p:')) {
      const [, code, idx] = data.split(':');
      const m = db.movies[code];
      return m ? sendMovie(chatId, uid, m, Number(idx)) : undefined;
    }

    // ---------- profil
    if (data === 'profile') return show(chatId, mid, profileText(u), profileRows());
    if (data === 'pf:h') {
      const hist = (u.history || []).slice(-15).reverse();
      return show(chatId, mid, '🕘 Qidiruv tarixingiz:\n\n' + (hist.length ? hist.map((h) => `• ${short(h.q, 45)}`).join('\n') : 'Hali bo‘sh.'), [back('profile')]);
    }
    if (data === 'pf:f') return show(chatId, mid, listText('🩵 Sevimli filmlaringiz', byCodes(u.favs || [])), [back('profile')]);
    if (data === 'pf:l') {
      const codes = Object.keys(u.votes || {}).filter((c) => u.votes[c] === 1);
      return show(chatId, mid, listText('❤️ Like bosgan filmlaringiz', byCodes(codes)), [back('profile')]);
    }

    // ---------- statistika
    if (data === 'stats') {
      const users = Object.values(db.users);
      return show(chatId, mid, `📊 Statistika\n\n👥 Obunachilar: ${users.length}\n🔎 Qidirilgan filmlar: ${db.searches || 0}\n💎 Premium egalari: ${users.filter(isPremium).length}\n🎬 Bazadagi filmlar: ${moviesList().length}`, [
        [B('🏅 Eng ko‘p qidirilgan filmlar', 'top', 'success')],
        [B('🔍 Film va seriallar qidirish', 'search', 'primary')],
        [B('⬅️ Ortga qaytish', 'menu', 'danger')],
      ]);
    }
    if (data === 'top') {
      const list = moviesList().filter((m) => m.views > 0).sort((a, b) => b.views - a.views).slice(0, 20);
      return show(chatId, mid, listText('🏅 Eng ko‘p qidirilgan 20 ta film va serial', list), [
        [B('🔍 Film va seriallar qidirish', 'search', 'primary')],
        [B('⬅️ Ortga qaytish', 'stats', 'danger')],
      ]);
    }
  } catch (e) { console.error('callback xato:', e.message); }
});

// ================================================================ oddiy xabarlar
bot.on('message', async (msg) => {
  try {
    if (!msg.from || !priv(msg)) return;
    const uid = msg.from.id;
    const u = getUser(msg.from);

    // Stars to'lovi muvaffaqiyatli bo'lsa
    if (msg.successful_payment) {
      const p = msg.successful_payment;
      if (p.invoice_payload !== 'premium' || p.currency !== 'XTR') return;
      if (db.payments.includes(p.telegram_payment_charge_id)) return; // bir to'lov ikki marta hisoblanmasin
      db.payments.push(p.telegram_payment_charge_id);
      grantPremium(uid, S().days);
      logEvent(`⭐️ Premium sotib olindi: ${u.name} (${uid}) — ${p.total_amount} stars`);
      return bot.sendMessage(uid, `✅ To‘lov qabul qilindi!\n💎 Premium ${day(db.users[uid].premiumUntil)} gacha faol. Endi majburiy obunasiz va reklamasiz foydalanishingiz mumkin. /start ni bosing.`);
    }

    // Admin holatlari (film qo'shish, xabar yuborish va h.k.)
    const st = isAdmin(uid) ? adminStates.get(uid) : null;
    if (st) {
      if ((msg.text || '').startsWith('/')) return; // buyruqlar onText'da
      return adminInput(msg, st);
    }

    const text = (msg.text || '').trim();
    if (!text || text.startsWith('/')) return;
    if (u.banned && !isAdmin(uid)) return bot.sendMessage(uid, '🚫 Siz bloklangansiz.');
    if (!(await allowed(uid))) return show(uid, null, startText(u.name), startRows());

    // Albom nomi
    if (awaiting.get(uid) === 'albname') {
      awaiting.delete(uid);
      if (myAlbums(uid).length >= MAX_ALBUMS) return bot.sendMessage(uid, 'Albomlar limiti to‘ldi.');
      const id = String(db.nextAlbum++);
      db.albums[id] = { id, user: uid, name: short(text, 30), items: [] };
      save();
      return bot.sendMessage(uid, '✅ Albom yaratildi. Film ostidagi «💿 Albomga qo‘shish» tugmasi orqali unga film qo‘shing.', KB([[B('💿 Albomlarim', 'alb', 'primary')]]));
    }

    // Qidiruv: tanlangan rejim bo'yicha, bo'lmasa raqam = kod, aks holda nom
    const mode = awaiting.get(uid) || (/^\d+$/.test(text) ? 'code' : 'name');
    if (mode === 'code') {
      recordSearch(u, 'kod: ' + text);
      const movie = db.movies[text];
      if (!movie) return bot.sendMessage(uid, '❌ Bunday kodli film topilmadi.');
      return sendMovie(uid, uid, movie);
    }
    recordSearch(u, text);
    const q = norm(text);
    const found = moviesList().filter((m) => norm(m.title).includes(q)).sort((a, b) => (b.views || 0) - (a.views || 0)).slice(0, 20);
    if (!found.length) return bot.sendMessage(uid, '😕 Hech narsa topilmadi. Boshqa nom yozib ko‘ring.');
    if (found.length === 1) return sendMovie(uid, uid, found[0]);
    return bot.sendMessage(uid, listText(`🔎 «${short(text, 30)}» bo‘yicha natijalar`, found));
  } catch (e) { console.error('message xato:', e.message); }
});
