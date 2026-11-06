"""All user-facing (Persian) texts. Never hard-code UI text in handlers.

Messages are sent with HTML parse mode: escape any user-provided value with
``bot.formatters.esc`` before putting it into one of these templates.
"""

from __future__ import annotations

from eventum_hq.services.permissions import MenuItem

# ---- main menu -------------------------------------------------------------

MENU_LABELS: dict[MenuItem, str] = {
    MenuItem.MY_TASKS: "📋 کارهای من",
    MenuItem.LIBRARY: "📚 کتابخانه",
    MenuItem.NEW_REEL: "➕ ریل جدید",
    MenuItem.REVIEW_QUEUE: "👀 منتظر بررسی من",
    MenuItem.APPROVAL_QUEUE: "✅ منتظر تأیید من",
    MenuItem.READY_TO_PUBLISH: "🚀 آماده انتشار",
    MenuItem.NEW_TASK: "➕ تسک جدید",
    MenuItem.ALL_TASKS: "🗂 همهٔ کارها",
    MenuItem.REPORT: "📊 گزارش",
    MenuItem.TEAM: "👥 تیم",
    MenuItem.HELP: "❓ راهنما",
}

MENU_PLACEHOLDER = "یکی از گزینه‌ها را انتخاب کنید"
MENU_SHOWN = "منوی اصلی 👇"

# ---- /start and access request --------------------------------------------

WELCOME_KNOWN = "سلام {name} 👋\nبه Eventum HQ خوش آمدید. از منوی پایین استفاده کنید."
WELCOME_KNOWN_NO_NAME = "سلام 👋\nبه Eventum HQ خوش آمدید. از منوی پایین استفاده کنید."

ACCESS_REQUEST_SENT = (
    "درخواست شما برای مدیر ارسال شد. ✉️\n"
    "بعد از تأیید، همین‌جا پیام می‌گیرید."
)
ACCESS_REQUEST_ALREADY_SENT = (
    "درخواست شما قبلاً برای مدیر ارسال شده است. ⏳\n"
    "لطفاً منتظر بمانید."
)

ACCESS_REQUEST_CARD = (
    "🔔 <b>درخواست دسترسی جدید</b>\n\n"
    "نام: {name}\n"
    "نام کاربری: {username}\n"
    "شناسهٔ تلگرام: <code>{telegram_id}</code>"
)
BTN_APPROVE_AS_MEMBER = "✅ تأیید به‌عنوان عضو"
BTN_REJECT = "❌ رد"

ACCESS_CARD_APPROVED_SUFFIX = "\n\n✅ <b>تأیید شد</b> توسط {actor}"
ACCESS_CARD_REJECTED_SUFFIX = "\n\n❌ <b>رد شد</b> توسط {actor}"
ACCESS_ALREADY_DECIDED = "این درخواست قبلاً بررسی شده است."
ACCESS_STATUS_LABELS = {
    "APPROVED": "✅ تأییدشده",
    "REJECTED": "❌ ردشده",
    "PENDING": "⏳ در انتظار",
}
ACCESS_CARD_CURRENT_STATUS = "\n\nوضعیت فعلی: {status}"

ACCESS_APPROVED_FOR_USER = (
    "✅ دسترسی شما به Eventum HQ تأیید شد.\n"
    "از منوی پایین استفاده کنید."
)
ACCESS_REJECTED_FOR_USER = "درخواست دسترسی شما به Eventum HQ تأیید نشد."

NO_USERNAME = "—"
NO_NAME = "(بدون نام)"

# ---- generic ---------------------------------------------------------------

COMING_SOON = "🚧 بخش «{label}» هنوز آماده نیست و در نسخه‌های بعدی فعال می‌شود."
PERMISSION_DENIED = "⛔️ اجازهٔ این کار را ندارید."
NOT_FOUND = "موردی پیدا نشد."
CANCELLED = "لغو شد. ✅"
NOTHING_TO_CANCEL = "کاری در جریان نیست که لغو شود."
UNKNOWN_INPUT = "متوجه نشدم. 🤔\nاز دکمه‌های منو استفاده کنید یا /help را بزنید."
GENERIC_ERROR = "⚠️ مشکلی پیش آمد. لطفاً دوباره تلاش کنید."

HELP = (
    "❓ <b>راهنمای Eventum HQ</b>\n\n"
    "این ربات محل ثبت و پیگیری همهٔ کارهای تیم Eventum Space است.\n\n"
    "<b>دستورها</b>\n"
    "/start — شروع و نمایش منو\n"
    "/menu — نمایش منوی اصلی\n"
    "/my — کارهای من\n"
    "/cancel — لغو کار نیمه‌تمام\n"
    "/help — همین راهنما\n\n"
    "دکمه‌های منو بر اساس نقش شما نمایش داده می‌شوند. "
    "بخش‌ها به‌تدریج فعال می‌شوند."
)

# ---- bot command list (Telegram "Menu" button) ------------------------------

COMMANDS: dict[str, str] = {
    "start": "شروع و نمایش منو",
    "menu": "منوی اصلی",
    "my": "کارهای من",
    "cancel": "لغو کار نیمه‌تمام",
    "help": "راهنما",
}
