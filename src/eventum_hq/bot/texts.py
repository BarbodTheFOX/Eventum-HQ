"""All user-facing (Persian) texts. Never hard-code UI text in handlers.

Messages are sent with HTML parse mode: escape any user-provided value with
``bot.formatters.esc`` before putting it into one of these templates.
"""

from __future__ import annotations

from eventum_hq.models import Role
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
    MenuItem.ADMIN_VIEW_ON: "🛠 حالت ادمین",
    MenuItem.ADMIN_VIEW_OFF: "↩️ حالت عادی",
}

MENU_PLACEHOLDER = "یکی از گزینه‌ها را انتخاب کنید"
MENU_SHOWN = "منوی اصلی 👇"
ADMIN_VIEW_ENABLED = "🛠 حالت ادمین روشن شد. همهٔ بخش‌های ربات در منو نمایش داده می‌شوند."
ADMIN_VIEW_DISABLED = "↩️ حالت عادی: منو فقط بخش‌های کار خودتان را نشان می‌دهد."

# ---- roles -------------------------------------------------------------------

ROLE_LABELS: dict[Role, str] = {
    Role.OWNER: "مالک (توسعه‌دهنده)",
    Role.DIRECTOR: "مدیر",
    Role.PROJECT_MANAGER: "مدیر پروژه",
    Role.CONTENT_SPECIALIST: "کانتنت اسپشیالیست",
    Role.DESIGNER: "دیزاینر",
    Role.EDITOR: "ادیتور",
}

# ---- /start and access request --------------------------------------------

WELCOME_KNOWN = "سلام {name} 👋\nبه Eventum HQ خوش آمدید. از منوی پایین استفاده کنید."
WELCOME_KNOWN_NO_NAME = "سلام 👋\nبه Eventum HQ خوش آمدید. از منوی پایین استفاده کنید."

CHOOSE_ROLE = (
    "سلام 👋\n"
    "برای استفاده از Eventum HQ باید مدیر ورود شما را تأیید کند.\n\n"
    "نقش خود را در تیم انتخاب کنید:"
)
ACCESS_REQUEST_SENT = (
    "درخواست شما با نقش «{role}» برای مدیر ارسال شد. ✉️\n"
    "بعد از تأیید، همین‌جا پیام می‌گیرید."
)
ACCESS_REQUEST_ALREADY_SENT = (
    "درخواست شما قبلاً برای مدیر ارسال شده است. ⏳\n"
    "لطفاً منتظر بمانید."
)
ALREADY_MEMBER = "شما قبلاً عضو شده‌اید. ✅"
INVALID_ROLE = "این نقش معتبر نیست."

ACCESS_REQUEST_CARD = (
    "🔔 <b>درخواست دسترسی جدید</b>\n\n"
    "نام: {name}\n"
    "نام کاربری: {username}\n"
    "شناسهٔ تلگرام: <code>{telegram_id}</code>\n"
    "نقش درخواستی: <b>{role}</b>"
)
BTN_APPROVE_AS = "✅ تأیید به‌عنوان {role}"
BTN_APPROVE_OTHER_ROLE = "🔄 تأیید با نقش دیگر"
BTN_BACK = "↩️ بازگشت"
BTN_REJECT = "❌ رد"
ACCESS_PICK_ROLE_HINT = "\n\n👇 نقشی را که با آن تأیید می‌کنید انتخاب کنید:"

ACCESS_CARD_APPROVED_SUFFIX = "\n\n✅ <b>تأیید شد</b> با نقش «{role}» توسط {actor}"
ACCESS_CARD_REJECTED_SUFFIX = "\n\n❌ <b>رد شد</b> توسط {actor}"
ACCESS_ALREADY_DECIDED = "این درخواست قبلاً بررسی شده است."
ACCESS_STATUS_LABELS = {
    "APPROVED": "✅ تأییدشده",
    "REJECTED": "❌ ردشده",
    "PENDING": "⏳ در انتظار",
}
ACCESS_CARD_CURRENT_STATUS = "\n\nوضعیت فعلی: {status}"

ACCESS_APPROVED_FOR_USER = (
    "✅ دسترسی شما به Eventum HQ با نقش «{role}» تأیید شد.\n"
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
