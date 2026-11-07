"""All user-facing (Persian) texts. Never hard-code UI text in handlers.

Messages are sent with HTML parse mode: escape any user-provided value with
``bot.formatters.esc`` before putting it into one of these templates.
"""

from __future__ import annotations

from eventum_hq.models import ApprovalChain, Role, TaskStatus
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
    "برای دیدن یک تسک، کد آن را بفرستید؛ مثلاً <code>T-0012</code>.\n\n"
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

# ---- tasks: labels -------------------------------------------------------------

STATUS_LABELS: dict[TaskStatus, str] = {
    TaskStatus.TODO: "⏳ در انتظار",
    TaskStatus.BLOCKED: "🔒 مسدود",
    TaskStatus.IN_PROGRESS: "🛠 در حال انجام",
    TaskStatus.IN_REVIEW: "👀 در بررسی",
    TaskStatus.CHANGES_REQUESTED: "✏️ نیاز به اصلاح",
    TaskStatus.APPROVED: "✅ تأییدشده — منتظر «انجام شد»",
    TaskStatus.DONE: "🏁 انجام‌شده",
    TaskStatus.CANCELLED: "❌ لغوشده",
}
STATUS_EMOJI: dict[TaskStatus, str] = {s: label.split(" ", 1)[0] for s, label in STATUS_LABELS.items()}
OVERDUE_EMOJI = "🔴"
AT_RISK_EMOJI = "🟠"

CHAIN_LABELS: dict[ApprovalChain, str] = {
    ApprovalChain.FINAL: "فقط تأیید مدیر",
    ApprovalChain.L1_FINAL: "بررسی مرحلهٔ اول، سپس تأیید مدیر",
    ApprovalChain.NONE: "بدون تأیید (مسئول با «✅ انجام شد» تمام می‌کند)",
}

WEEKDAYS = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"]  # Saturday = 0
DATE_FORMAT = "{weekday} {y}/{m:02d}/{d:02d}"
DATETIME_FORMAT = "{weekday} {y}/{m:02d}/{d:02d} ساعت {hh:02d}:{mm:02d}"
UNIT_MINUTE = "دقیقه"
UNIT_HOUR = "ساعت"
UNIT_DAY = "روز"
DELTA_LEFT = "{n} {unit} مانده"
DELTA_LATE = "{n} {unit} تأخیر"
NO_DEADLINE = "بدون ددلاین"
NO_SERIES = "—"
NO_DESCRIPTION = "—"
SYSTEM_ACTOR = "سیستم"

AUDIT_LABELS: dict[str, str] = {
    "task.created": "ساخته شد",
    "task.started": "شروع شد",
    "task.cancelled": "لغو شد",
    "task.due_changed": "ددلاین تغییر کرد",
    "task.reassigned": "مسئول تغییر کرد",
}

# ---- tasks: card ---------------------------------------------------------------

TASK_CARD = (
    "<b>{code}</b> · {title}\n\n"
    "وضعیت: {status}\n"
    "مسئول: {assignee}\n"
    "ددلاین: {due}\n"
    "سری: {series}\n"
    "زنجیرهٔ تأیید: {chain}\n"
    "زمان تخمینی: {estimate}\n"
    "دور اصلاح: {rounds}\n"
    "سازنده: {creator}"
)
TASK_CARD_DESCRIPTION = "\n\n📝 توضیح:\n{description}"
TASK_CARD_BRIEF = "\n📎 بریف: {count} فایل"
TASK_CARD_LAST_EVENT = "\n\nآخرین رویداد: {event} — {actor}، {when}"
DUE_WITH_DELTA = "{due} ({emoji}{delta})"

BTN_START = "▶️ شروع کار"
BTN_BRIEF = "📎 دریافت بریف"
BTN_CHANGE_DUE = "📅 تغییر ددلاین"
BTN_REASSIGN = "👤 تغییر مسئول"
BTN_CANCEL_TASK = "❌ لغو تسک"
BTN_HISTORY = "📜 تاریخچه"
BTN_BACK_TO_CARD = "↩️ بازگشت به کارت"
BTN_CONFIRM_CANCEL = "✅ بله، لغو شود"
BTN_KEEP_TASK = "↩️ نه"
CONFIRM_CANCEL_TASK = "\n\n⚠️ <b>این تسک لغو شود؟</b> مسئول پیام می‌گیرد."
REASSIGN_PROMPT = "\n\n👤 <b>مسئول جدید را انتخاب کنید:</b>"

TASK_STARTED = "🛠 کار شروع شد."
TASK_CANCELLED = "❌ تسک لغو شد."
TASK_REASSIGNED = "✅ مسئول به {name} تغییر کرد."
TASK_DUE_CHANGED = "✅ ددلاین {code} تغییر کرد: {due}"
TASK_STATE_CHANGED = "وضعیت این تسک عوض شده است. کارت به‌روز شد."
TASK_CODE_NOT_FOUND = "تسکی با کد {code} پیدا نشد."
STALE_BUTTON = "این دکمه دیگر فعال نیست."

HISTORY_HEADER = "📜 <b>تاریخچهٔ {code}</b>\n"
HISTORY_LINE = "\n• {when} — {label} — {actor}"

# ---- tasks: lists --------------------------------------------------------------

MY_TASKS_HEADER = "📋 <b>کارهای من</b> ({count})"
MY_TASKS_EMPTY = "📋 کار بازی ندارید. 🎉"
ALL_TASKS_MENU = "🗂 <b>همهٔ کارها</b>\nکدام فهرست را می‌خواهید؟"
BTN_FILTER_OPEN = "📂 باز"
BTN_FILTER_OVERDUE = "🔴 عقب‌افتاده"
BTN_FILTER_AT_RISK = "🟠 در خطر"
BTN_FILTER_BY_USER = "👤 بر اساس نفر"
BTN_FILTER_BY_SERIES = "🗂 بر اساس سری"
LIST_HEADER_OPEN = "📂 <b>کارهای باز</b> ({count})"
LIST_HEADER_OVERDUE = "🔴 <b>عقب‌افتاده</b> ({count})"
LIST_HEADER_AT_RISK = "🟠 <b>در خطر</b> — ددلاین در ۲۴ ساعت آینده ({count})"
LIST_HEADER_USER = "👤 <b>کارهای باز {name}</b> ({count})"
LIST_HEADER_SERIES = "🗂 <b>سری {name}</b> ({count})"
LIST_EMPTY = "\n\nموردی نیست."
LIST_LINE = "\n{emoji} <b>{code}</b> {title} — {assignee}{delta}"
LIST_LINE_DELTA = " — {delta}"
PICK_PERSON = "👤 کارهای چه کسی؟"
PICK_SERIES = "🗂 کدام سری؟"
BTN_PREV = "« قبلی"
BTN_NEXT = "بعدی »"
PAGE_LABEL = "{page}/{pages}"
BTN_BACK_TO_FILTERS = "↩️ فیلترها"

# ---- tasks: create flow --------------------------------------------------------

NEW_TASK_TITLE = "➕ <b>تسک جدید</b>\n\nعنوان تسک را بنویسید:\n(برای لغو در هر مرحله: /cancel)"
NEW_TASK_DESCRIPTION = (
    "📝 توضیح یا بریف را بفرستید: متن، ویس، عکس، ویدیو یا فایل.\n"
    "اگر توضیحی ندارد، «رد کردن» را بزنید."
)
NEW_TASK_ASSIGNEE = "👤 مسئول این تسک کیست؟"
DUE_DATE_PROMPT = (
    "📅 ددلاین چه روزی است؟\n"
    "یکی از دکمه‌ها را بزنید یا تاریخ را بنویسید، مثلاً <code>1405/08/20</code> "
    "یا <code>8/20 18:30</code>."
)
EDIT_DUE_PROMPT = "📅 ددلاین جدید <b>{code}</b>\n\n" + DUE_DATE_PROMPT
DUE_TIME_PROMPT = (
    "⏰ ساعت ددلاین ({date})؟\n"
    "یکی از دکمه‌ها را بزنید یا ساعت را بنویسید، مثلاً <code>16:30</code>."
)
DUE_PAST_CONFIRM = "⚠️ این زمان گذشته است: {due}\nمطمئنید؟"
BTN_PAST_YES = "✅ بله، همین زمان"
BTN_PAST_NO = "✏️ زمان دیگر"
QUICK_DATE_LABELS = {
    "today": "امروز",
    "tomorrow": "فردا",
    "after": "پس‌فردا",
    "sat": "شنبهٔ آینده",
}
NEW_TASK_ESTIMATE = (
    "⏱ زمان تخمینی این کار چقدر است؟ (اختیاری، ولی کمک می‌کند بار کاری دیده شود)\n"
    "یکی از دکمه‌ها را بزنید یا بنویسید، مثلاً <code>90</code> (دقیقه) یا <code>۱۴ ساعت</code>."
)
ESTIMATE_CHOICES = (15, 30, 60, 120, 240)
BTN_NO_ESTIMATE = "⏭ بدون تخمین"
INVALID_ESTIMATE = "زمان نامعتبر است. نمونه: <code>90</code> یا <code>۱٫۵ ساعت</code> یا <code>1.5h</code>"
NO_ESTIMATE = "—"
DURATION_MINUTES = "{m} دقیقه"
DURATION_HOURS = "{h} ساعت"
DURATION_HOURS_MINUTES = "{h} ساعت و {m} دقیقه"
NEW_TASK_SERIES = "🗂 سری این تسک؟ (اختیاری)"
BTN_NO_SERIES = "بدون سری"
NEW_TASK_CHAIN = "✅ زنجیرهٔ تأیید؟\nپیش‌فرض: <b>فقط تأیید مدیر</b>."
NEW_TASK_CONFIRM = (
    "🧾 <b>بررسی نهایی</b>\n\n"
    "عنوان: {title}\n"
    "مسئول: {assignee}\n"
    "ددلاین: {due}\n"
    "سری: {series}\n"
    "زنجیرهٔ تأیید: {chain}\n"
    "زمان تخمینی: {estimate}\n"
    "توضیح: {description}"
)
NEW_TASK_BRIEF_FILE = "📎 یک فایل"
BTN_SKIP = "⏭ رد کردن"
BTN_CREATE_TASK = "✅ ساخت تسک"
BTN_ABORT = "❌ لغو"
TASK_CREATED = "✅ تسک <b>{code}</b> ساخته شد و برای مسئول ارسال شد."
TASK_CREATED_SELF = "✅ تسک <b>{code}</b> ساخته شد."
SEND_TITLE_AS_TEXT = "لطفاً عنوان را به‌صورت متن بفرستید."
UNSUPPORTED_BRIEF = "این نوع پیام پشتیبانی نمی‌شود. متن، ویس، عکس، ویدیو یا فایل بفرستید."
INVALID_DATE = "تاریخ نامعتبر است. نمونه: <code>1405/08/20</code> یا <code>8/20 18:30</code>"
INVALID_TIME = "ساعت نامعتبر است. نمونه: <code>18:30</code>"
FLOW_EXPIRED = "⌛️ کار نیمه‌تمام قبلی به‌خاطر ۳۰ دقیقه بی‌فعالیتی لغو شد."
FLOW_ABORTED = "لغو شد. ✅"

VALIDATION_MESSAGES: dict[str, str] = {
    "title_empty": "عنوان نمی‌تواند خالی باشد.",
    "title_too_long": "عنوان حداکثر ۲۰۰ کاراکتر است.",
    "description_too_long": "توضیح حداکثر ۳۰۰۰ کاراکتر است.",
    "assignee_inactive": "این کاربر فعال نیست.",
    "series_invalid": "این سری معتبر نیست.",
    "same_due": "ددلاین جدید با قبلی یکی است.",
    "same_assignee": "همین نفر الان مسئول است.",
    "estimate_invalid": "زمان تخمینی نامعتبر است.",
}

# ---- tasks: notifications ------------------------------------------------------

NOTIFY_TASK_ASSIGNED = "📌 <b>تسک جدید برای شما</b>\n\n"
NOTIFY_TASK_DUE_CHANGED = "📅 <b>ددلاین تسک شما تغییر کرد</b>\n\n"
NOTIFY_TASK_UNASSIGNED = "↪️ تسک <b>{code}</b> «{title}» به نفر دیگری سپرده شد."
NOTIFY_TASK_CANCELLED = "❌ تسک <b>{code}</b> «{title}» لغو شد."
