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
    MenuItem.DAILY_REPORT: "📝 گزارش روزانه",
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
    Role.OWNER: "مدیر (مالک ربات)",
    Role.DIRECTOR: "فاندر",
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
    "هر کار تیم این‌جا یک رکورد دارد: مسئول، ددلاین، وضعیت، فایل‌ها و تاریخچهٔ اصلاح و تأیید.\n\n"
    "<b>کار روزانهٔ شما</b>\n"
    "1️⃣ «📋 کارهای من»: روی هر کار بزنید تا کارتش باز شود.\n"
    "2️⃣ «▶️ شروع کار» (اختیاری) را بزنید و کار را انجام دهید.\n"
    "3️⃣ «📤 تحویل»: فایل یا لینک را بفرستید (هر تعداد)، یادداشت اختیاری، بعد «✅ ارسال برای بررسی».\n"
    "4️⃣ اگر اصلاح خواستند، یادداشت‌ها برایتان می‌آید؛ نسخهٔ جدید را از همان کارت تحویل دهید.\n"
    "5️⃣ بعد از تأیید، اگر کار مرحلهٔ آپلود یا انتشار دارد، «🏁 انجام شد» را بزنید.\n\n"
    "<b>نکته‌ها</b>\n"
    "• یادآوری ددلاین ساعت ۱۰ روز ددلاین و ۲ ساعت قبل از آن می‌آید.\n"
    "• از ۲۳ تا ۹ صبح ربات پیامی نمی‌فرستد؛ پیام‌ها ساعت ۹ می‌رسند.\n"
    "• فایل نهایی هر کار تأییدشده را در «📚 کتابخانه» پیدا کنید.\n"
    "• «📝 گزارش روزانه» (برای مدیر): یادداشت آخر شب را بفرستید تا گزارش روزانهٔ تیم ساخته شود.\n"
    "• برای دیدن یک تسک یا ریل، کدش را بفرستید؛ مثلاً <code>T-0012</code> یا <code>R-0003</code>.\n"
    "• تاریخ را این‌طور بنویسید: <code>1405/08/25 18:00</code> (سال و ساعت اختیاری‌اند).\n\n"
    "<b>دستورها</b>\n"
    "/menu — منوی اصلی\n"
    "/my — کارهای من\n"
    "/cancel — لغو کار نیمه‌تمام\n"
    "/help — همین راهنما\n\n"
    "دکمه‌های منو بر اساس نقش شما نمایش داده می‌شوند."
)
HELP_ADMIN = (
    "\n\n<b>مدیر سیستم</b>\n"
    "/health — وضعیت ربات، زمان‌بندی و بکاپ\n"
    "/backup — گرفتن بکاپ همین الان و دریافت فایل آن"
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
    ApprovalChain.FINAL: "فقط تأیید فاندر",
    ApprovalChain.L1_FINAL: "بررسی مرحلهٔ اول، سپس تأیید فاندر",
    ApprovalChain.NONE: "تأیید فاندر الزامی است (کار قدیمی)",
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
    "task.submitted": "تحویل شد",
    "review.approved": "تأیید شد",
    "review.changes_requested": "اصلاح خواسته شد",
    "task.done": "انجام شد",
    "task.unblocked": "عکس‌های کاور رسید",
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
BTN_BRIEF = "📎 دریافت فایل‌های ورودی"
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
TIME_PROMPT = (  # same picker when the time is not a deadline (publish time, delegation end)
    "⏰ چه ساعتی ({date})؟\n"
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
FOUNDER_APPROVAL_REQUIRED = "تأیید نهایی خروجی‌ها فقط با فاندر است و قابل تفویض نیست."
NEW_TASK_CHAIN = "✅ زنجیرهٔ تأیید؟\nپیش‌فرض: <b>فقط تأیید فاندر</b>."
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
    "reel_task_cancel": "تسک‌های ریل فقط با «❌ لغو ریل» از کارت ریل لغو می‌شوند.",
    "links_invalid": "لینک نامعتبر است. لینک باید با https:// شروع شود.",
    "photos_empty": "حداقل یک عکس یا فایل بفرستید.",
    "photos_after_edit": "ددلاین عکس‌ها نباید بعد از ددلاین ادیت باشد.",
    "reel_inputs_missing": "تایم‌کدها و متن کاور لازم است.",
    "delegation_end_past": "زمان پایان تفویض باید در آینده باشد.",
    "delegate_invalid": "این نفر نمی‌تواند نمایندهٔ تفویض باشد.",
    "notes_empty": "حداقل یک یادداشت (متن، ویس یا عکس) بفرستید.",
    "note_too_long": "یادداشت حداکثر ۳۰۰۰ کاراکتر است.",
    "submission_too_big": "تعداد فایل یا لینک بیش از حد است.",
    "submission_empty": "حداقل یک فایل یا لینک بفرستید.",
}

# ---- tasks: notifications ------------------------------------------------------

NOTIFY_TASK_ASSIGNED = "📌 <b>تسک جدید برای شما</b>\n\n"
NOTIFY_TASK_DUE_CHANGED = "📅 <b>ددلاین تسک شما تغییر کرد</b>\n\n"
NOTIFY_TASK_UNASSIGNED = "↪️ تسک <b>{code}</b> «{title}» به نفر دیگری سپرده شد."
NOTIFY_TASK_CANCELLED = "❌ تسک <b>{code}</b> «{title}» لغو شد."

# ---- M2: delivery ----------------------------------------------------------------

STAGE_LABELS = {"L1": "مرحلهٔ اول", "FINAL": "تأیید نهایی"}
STATUS_WITH_STAGE = "{status} — {stage}"
TASK_CARD_VERSION = "\n📦 آخرین نسخه: v{version}"

BTN_SUBMIT = "📤 تحویل"
BTN_MARK_DONE = "✅ انجام شد"
BTN_FINISH = "🏁 انجام شد (بعد از آپلود)"
BTN_SEND_FOR_REVIEW = "✅ ارسال برای بررسی"
SUBMIT_PROMPT = (
    "📤 <b>تحویل {code}</b>\n\n"
    "فایل‌ها (ویدیو، عکس، فایل، صدا، ویس) یا لینک‌ها را بفرستید. "
    "می‌توانید یک یادداشت متنی هم بنویسید.\n"
    "در آخر «✅ ارسال برای بررسی» را بزنید."
)
SUBMIT_COLLECTED = "دریافت شد ✅ — تا الان: {files} فایل، {links} لینک{note}"
SUBMIT_COLLECTED_NOTE = "، با یادداشت"
SUBMIT_EMPTY = "حداقل یک فایل یا لینک بفرستید."
SUBMIT_UNSUPPORTED = "این نوع پیام قابل تحویل نیست. فایل، عکس، ویدیو، صدا، ویس یا لینک بفرستید."
SUBMIT_DONE = "✅ نسخهٔ v{version} از {code} برای بررسی ارسال شد."
ARCHIVE_NOT_CONFIGURED = (
    "⚠️ کانال آرشیو هنوز تنظیم نشده، پس فایل قابل تحویل نیست.\n"
    "به مدیر سیستم (باربد) خبر بدهید. تحویل فقط با لینک فعلاً ممکن است."
)
ARCHIVE_COPY_FAILED = (
    "⚠️ کپی فایل در کانال آرشیو ممکن نشد. مطمئن شوید ربات در کانال آرشیو ادمین است و دوباره امتحان کنید."
)
ARCHIVE_CAPTION = "#{code_tag} v{version} | {title} | {assignee} | {date}"
DONE_OK = "🏁 تسک {code} انجام شد."

# ---- M2: review ------------------------------------------------------------------

REVIEW_CARD = (
    "👀 <b>بررسی {code}</b> · {title}\n\n"
    "مسئول: {assignee}\n"
    "نسخه: v{version} · دور اصلاح: {rounds}\n"
    "مرحله: {stage}\n"
    "ددلاین: {due}\n"
    "سری: {series}"
)
REVIEW_CARD_NOTE = "\n\n📝 یادداشت مسئول:\n{note}"
REVIEW_CARD_LINKS = "\n\n🔗 لینک‌ها:\n{links}"
REVIEW_CARD_FILES = "\n\n📎 {count} فایل (پایین همین پیام)"
REVIEW_APPROVED_SUFFIX = "\n\n✅ <b>تأیید شد</b> توسط {actor}"
REVIEW_CHANGES_SUFFIX = "\n\n✏️ <b>اصلاح خواسته شد</b> توسط {actor}"
REVIEW_ALREADY_DONE = "این مورد قبلاً بررسی شده است."
BTN_APPROVE = "✅ تأیید"
BTN_REQUEST_CHANGES = "✏️ اصلاح لازم است"
BTN_DETAILS = "📄 جزئیات و تاریخچه"
NOTES_PROMPT = (
    "✏️ <b>یادداشت اصلاح برای {code}</b>\n\n"
    "یک یا چند پیام بفرستید: متن، ویس یا عکس. در آخر «✅ تمام» را بزنید."
)
NOTES_COLLECTED = "دریافت شد ✅ — {count} یادداشت"
NOTES_EMPTY = "حداقل یک یادداشت (متن، ویس یا عکس) بفرستید."
NOTES_UNSUPPORTED = "برای یادداشت متن، ویس، عکس یا فایل بفرستید."
BTN_NOTES_DONE = "✅ تمام"
CHANGES_SENT = "✏️ درخواست اصلاح برای {code} ارسال شد."
APPROVED_OK = "✅ تأیید شد."
QUEUE_L1_HEADER = "👀 <b>منتظر بررسی من</b> ({count})"
QUEUE_FINAL_HEADER = "✅ <b>منتظر تأیید من</b> ({count})"
QUEUE_EMPTY = "موردی در صف نیست. 🎉"

# ---- M2: notifications ------------------------------------------------------------

NOTIFY_REVIEW_REQUESTED = "🔔 <b>یک مورد منتظر بررسی شماست</b>\n\n"
NOTIFY_L1_APPROVED = "👍 مرحلهٔ اول تسک <b>{code}</b> «{title}» تأیید شد و برای تأیید نهایی رفت."
NOTIFY_APPROVED = (
    "✅ <b>تسک {code} تأیید نهایی شد</b>\n\n"
    "بعد از آپلود یا انتشار، روی کارت «🏁 انجام شد» را بزنید.\n\n"
)
NOTIFY_APPROVED_FINAL = "✅ <b>تسک {code} تأیید نهایی شد.</b>\n\n"
NOTIFY_CHANGES = "✏️ <b>برای {code} اصلاح خواسته شد</b> (دور {round})\n\n"
NOTIFY_CHANGES_NOTE = "📝 یادداشت:\n{note}\n\n"
NOTIFY_CHANGES_FILES = "📎 {count} یادداشت صوتی/تصویری پایین همین پیام است.\n\n"
NOTIFY_TASK_DONE = "🏁 تسک <b>{code}</b> «{title}» انجام شد."
NOTIFY_DELEGATION_STARTED = (
    "🔁 <b>تفویض تأیید نهایی شروع شد</b>\n\n"
    "از: {from_name}\nبه: {to_name}\nتا: {ends}"
)
NOTIFY_DELEGATION_REVOKED = "⛔️ <b>تفویض تأیید نهایی لغو شد</b>\n\nاز: {from_name}\nبه: {to_name}"

# ---- M2: team menu and delegation ----------------------------------------------------

TEAM_MENU = "👥 <b>تیم</b>\n\n{delegation}"
TEAM_NO_DELEGATION = "فعال نیست"
TEAM_DELEGATION_ACTIVE = "{to_name} تا {ends}"
TEAM_MORE_SOON = "\n\nتغییر نقش، دسترسی‌ها و ظرفیت هفتگی افراد در نسخه‌های بعدی اضافه می‌شود."
BTN_NEW_DELEGATION = "🔁 تفویض جدید"
BTN_REVOKE_DELEGATION = "⛔️ لغو تفویض"
DELEGATION_PICK = "🔁 تأیید نهایی به چه کسی تفویض شود؟"
DELEGATION_NO_CANDIDATES = "کسی با دسترسی «بررسی مرحلهٔ اول» نیست."
DELEGATION_END_PROMPT = "📅 تفویض تا کی باشد؟\n" + "یکی از دکمه‌ها را بزنید یا تاریخ را بنویسید، مثلاً <code>1405/08/25 18:00</code>."
DELEGATION_CREATED = "✅ تأیید نهایی تا {ends} به {name} تفویض شد."
DELEGATION_REVOKED = "⛔️ تفویض لغو شد."
DELEGATION_ALREADY_ENDED = "این تفویض قبلاً تمام یا لغو شده است."

# ---- channel / group id helper -----------------------------------------------------

CHANNEL_ID_HELP = (
    "📢 ربات به کانال «{title}» اضافه شد.\n"
    "شناسهٔ این کانال: <code>{chat_id}</code>\n\n"
    "اگر این کانال آرشیو است، این عدد را جلوی <code>ARCHIVE_CHANNEL_ID=</code> در فایل .env بگذارید "
    "و ربات را دوباره اجرا کنید. ربات باید در کانال <b>ادمین</b> باشد."
)
GROUP_ID_HELP = (
    "👥 ربات به گروه «{title}» اضافه شد.\n"
    "شناسهٔ این گروه: <code>{chat_id}</code>\n\n"
    "اگر این گروه تیم است، این عدد را جلوی <code>TEAM_GROUP_ID=</code> در فایل .env بگذارید "
    "و ربات را دوباره اجرا کنید. بعد از آن، ربات از هر گروه دیگری خارج می‌شود."
)

# ---- M3: reels -----------------------------------------------------------------------

SUBTYPE_LABELS = {"NORMAL": "🎞 ریل عادی", "TRIAL": "🧪 Trial"}
CONTENT_STATUS_LABELS = {
    "IN_PRODUCTION": "🛠 در حال تولید",
    "READY_TO_PUBLISH": "🚀 آماده انتشار",
    "PUBLISHED": "✅ منتشر شده",
    "CANCELLED": "❌ لغوشده",
}
REEL_TASK_KIND_LABELS = {"EDIT": "🎬 ادیت", "COVER": "🖼 کاور"}
BLOCKED_REASONS = {"waiting_cover_photos": "منتظر عکس‌های کاور از ادیتور"}
INPUT_TIMECODES = "\n\n⏱ <b>تایم‌کدها:</b>\n{text}"
INPUT_COVER_TEXT = "\n\n🖋 <b>متن کاور:</b>\n{text}"
INPUT_COVER_PHOTOS = "\n🖼 عکس‌های کاور: {count} فایل"
TASK_CARD_REEL = "\n{kind} ریل <b>{code}</b> · انتشار: {publish}"
TASK_CARD_BLOCKED = "\n🔒 {reason}"
TASK_CARD_PHOTOS_DUE = "\n🖼 عکس‌های کاور: تا {due} — {state}"
PHOTOS_NOT_SENT = "⏳ ارسال‌نشده"
PHOTOS_SENT = "✅ ارسال شد"
PHOTOS_SENT_LATE = "✅ ارسال شد (با تأخیر)"
BTN_INPUT_FILES = "📎 دریافت فایل‌های ورودی"
BTN_SEND_COVER_PHOTOS = "🖼 ارسال عکس‌های کاور"

NEW_REEL_TITLE = "➕ <b>ریل جدید</b>\n\nعنوان ریل را بنویسید:\n(برای لغو در هر مرحله: /cancel)"
NEW_REEL_SUBTYPE = "نوع ریل؟"
NEW_REEL_EDIT_TYPE = "نوع ادیت؟ (فقط برای زمان تخمینی)"
BTN_EDIT_NORMAL = "نرمال"
BTN_EDIT_MOTION = "با موشن"
NEW_REEL_SERIES = "🗂 سری این ریل؟"
DEFAULT_MARK = "⭐ "
NEW_REEL_PUBLISH_PROMPT = (
    "📅 زمان انتشار برنامه‌ریزی‌شده؟\n"
    "یکی از دکمه‌ها را بزنید یا بنویسید، مثلاً <code>1405/08/20 20:00</code>."
)
NEW_REEL_TIMECODES = "⏱ تایم‌کدها را بفرستید (متن):"
NEW_REEL_COVER_TEXT = "🖋 متن کاور را بفرستید:"
NEW_REEL_EDIT_ASSIGNEE = "🎬 مسئول ادیت؟ (⭐ = پیش‌فرض)"
NEW_REEL_COVER_ASSIGNEE = "🖼 مسئول کاور؟ (⭐ = پیش‌فرض)"
NEW_REEL_CONFIRM = (
    "🧾 <b>بررسی نهایی ریل</b>\n\n"
    "عنوان: {title}\n"
    "نوع: {subtype}\n"
    "سری: {series}\n"
    "انتشار: {publish}\n\n"
    "🎬 ادیت: {editor} — ددلاین {edit_due} — {edit_est}\n"
    "🖼 کاور: {designer} — ددلاین {cover_due} — {cover_est}\n"
    "📸 عکس‌های کاور از ادیتور تا: {photos_due}\n\n"
    "⏱ تایم‌کدها: {timecodes}\n"
    "🖋 متن کاور: {cover_text}"
)
BTN_CREATE_REEL = "✅ ساخت ریل"
BTN_CHANGE_DEADLINES = "📅 تغییر ددلاین‌ها"
BTN_CHANGE_ESTIMATES = "⏱ تغییر زمان‌های تخمینی"
BTN_BACK = "↩️ بازگشت"
PICK_DEADLINE = "کدام ددلاین؟"
PICK_ESTIMATE = "زمان تخمینی کدام؟"
DEADLINE_KEY_LABELS = {"photos": "📸 عکس‌های کاور", "edit": "🎬 ادیت", "cover": "🖼 کاور"}
DEADLINE_PROMPT = "📅 ددلاین جدید «{label}»؟\n" + "یکی از دکمه‌ها را بزنید یا تاریخ را بنویسید."
ESTIMATE_PROMPT = "⏱ زمان تخمینی «{label}»؟\nیکی از دکمه‌ها را بزنید یا بنویسید، مثلاً <code>90</code>."
REEL_CREATED = "✅ ریل <b>{code}</b> ساخته شد. مسئولان پیام گرفتند."
REEL_TEXT_REQUIRED = "لطفاً متن بفرستید."

REEL_CARD = (
    "🎬 <b>{code}</b> · {title}\n\n"
    "نوع: {subtype}\n"
    "سری: {series}\n"
    "وضعیت: {status}\n"
    "انتشار برنامه‌ریزی‌شده: {publish}\n"
    "🖼 عکس‌های کاور: {photos}\n"
    "سازنده: {creator}"
)
REEL_CARD_TASK = "\n{kind}: <b>{code}</b> — {status} — {assignee}"
REEL_CARD_PUBLISHED = "\n\n✅ منتشر شد: {when}\n🔗 {links}"
REEL_PHOTOS_PENDING = "تا {due} — ⏳ ارسال‌نشده"
REEL_PHOTOS_DONE = "✅ ارسال شد"
REEL_PHOTOS_DONE_LATE = "✅ ارسال شد (با تأخیر)"
BTN_OPEN_EDIT = "🎬 تسک ادیت"
BTN_OPEN_COVER = "🖼 تسک کاور"
BTN_PUBLISH = "🚀 ثبت انتشار"
BTN_CANCEL_REEL = "❌ لغو ریل"
CONFIRM_CANCEL_REEL = "\n\n⚠️ <b>این ریل و همهٔ تسک‌های بازش لغو شود؟</b>"
REEL_CANCELLED_OK = "❌ ریل لغو شد."
REEL_CODE_NOT_FOUND = "ریلی با کد {code} پیدا نشد."
READY_HEADER = "🚀 <b>آماده انتشار</b> ({count})"
READY_EMPTY = "ریلی آماده انتشار نیست."

PHOTOS_PROMPT = (
    "🖼 <b>عکس‌های کاور {code}</b>\n\n"
    "یک یا چند عکس یا فایل بفرستید، بعد «✅ تمام» را بزنید."
)
PHOTOS_COLLECTED = "دریافت شد ✅ — {count} فایل"
PHOTOS_EMPTY = "حداقل یک عکس یا فایل بفرستید."
PHOTOS_DONE = "✅ عکس‌ها برای مسئول کاور فرستاده شد."
ARCHIVE_PHOTOS_CAPTION = "#{code_tag} عکس کاور | {title} | {sender} | {date}"

PUBLISH_PROMPT = (
    "🚀 <b>ثبت انتشار {code}</b>\n\n"
    "لینک‌های انتشار را بفرستید (اینستاگرام، یوتیوب، تلگرام؛ یک یا چند پیام).\n"
    "بعد یکی از دکمه‌ها را بزنید."
)
PUBLISH_COLLECTED = "دریافت شد ✅ — {count} لینک"
PUBLISH_NO_LINKS = "حداقل یک لینک بفرستید."
BTN_PUBLISH_NOW = "✅ ثبت — همین الان منتشر شد"
BTN_PUBLISH_OTHER_TIME = "📅 زمان دیگر"
PUBLISH_TIME_PROMPT = "📅 کی منتشر شد؟\nیکی از دکمه‌ها را بزنید یا بنویسید، مثلاً <code>1405/08/20 20:00</code>."
PUBLISHED_OK = "✅ انتشار {code} ثبت شد."

NOTIFY_REEL_PHOTOS_READY = "🖼 <b>عکس‌های کاور ریل {reel_code} رسید.</b> می‌توانید کاور را شروع کنید.\n\n"
NOTIFY_REEL_TASK_APPROVED = "✅ {kind} ریل <b>{reel_code}</b> «{title}» تأیید نهایی شد."
NOTIFY_REEL_READY = "🚀 <b>ریل {reel_code} آماده انتشار است.</b>\n\n"
NOTIFY_REEL_PUBLISHED = "✅ <b>ریل {reel_code} منتشر شد.</b>\n\n"
NOTIFY_REEL_CANCELLED = "❌ ریل <b>{reel_code}</b> «{title}» لغو شد و تسک شما بسته شد."

# ---- M5: reminders, overdue, reports, recurrences, backups ----------------------------

NOTIFY_REMINDER_DAY = "⏰ <b>یادآوری:</b> ددلاین <b>{code}</b> امروز است.\n\n"
NOTIFY_REMINDER_SOON = "⏰ <b>ددلاین {code} نزدیک است.</b>\n\n"
NOTIFY_OVERDUE = "🔴 <b>ددلاین {code} گذشت.</b> اگر کار آماده است، از همین کارت تحویل بدهید.\n\n"
NOTIFY_OVERDUE_WATCH = "🔴 <b>ددلاین گذشت:</b> {code} · {title}\nمسئول: {assignee}"
OVERDUE_DAILY_MINE = "🔴 <b>کارهای عقب‌افتادهٔ شما ({count})</b>"
OVERDUE_DAILY_ALL = "🔴 <b>کارهای عقب‌افتادهٔ تیم ({count})</b>"
OVERDUE_LINE = "\n• {code} · {title} — {assignee} — {delta}"
OVERDUE_LINE_MINE = "\n• {code} · {title} — {delta}"

HEARTBEAT_ALERT = (
    "⚠️ <b>زمان‌بندی ربات {minutes} دقیقه کار نکرده بود</b> (از {since}).\n"
    "احتمالاً ربات یا سرور خاموش یا قطع بوده. یادآوری‌ها و گزارش‌ها از الان ادامه پیدا می‌کنند."
)
BACKUP_WEEKLY_CAPTION = "🗄 بکاپ هفتگی دیتابیس Eventum HQ — {date}"
BACKUP_TOO_BIG = (
    "⚠️ بکاپ هفتگی {size} مگابایت است و برای فرستادن در تلگرام بزرگ است؛ "
    "فقط روی سرور نگه داشته شد:\n<code>{path}</code>"
)

DAILY_PLAN_TITLE = "📅 <b>برنامهٔ امروز — {date}</b>"
DAILY_PLAN_PERSON = "\n\n👤 <b>{name}</b>"
DAILY_PLAN_TASK = "\n• {code} · {title} — ساعت {time}"
DAILY_PLAN_PUBLISHES = "\n\n🚀 <b>انتشارهای امروز</b>"
DAILY_PLAN_PUBLISH = "\n• {code} · {title} — ساعت {time}"

WEEKLY_SUMMARY_TITLE = "📊 <b>جمع‌بندی هفته</b>"
WEEKLY_SUMMARY_OUTPUTS = "\n\n✅ خروجی‌های تأییدشده: {total}"
WEEKLY_SUMMARY_OUTPUT_LINE = "\n• {label}: {count}"
WEEKLY_SUMMARY_PUBLISHED = "\n🚀 ریل‌های منتشرشده: {count}"
WEEKLY_SUMMARY_NEXT = "\n\n📅 <b>انتشارهای هفتهٔ بعد</b>"
WEEKLY_SUMMARY_NEXT_LINE = "\n• {code} · {title} — {when}"
WEEKLY_SUMMARY_NOTHING_NEXT = "\nهنوز چیزی برنامه‌ریزی نشده."
OUTPUT_TYPE_LABELS = {"REEL_VIDEO": "ویدیوی ریل", "REEL_COVER": "کاور ریل", "OTHER": "سایر"}

REPORT_TITLE = "📊 <b>گزارش — {date}</b>"
REPORT_APPROVALS = "\n\n✅ <b>منتظر تأیید من ({count})</b>"
REPORT_OVERDUE = "\n\n🔴 <b>عقب‌افتاده ({count})</b>"
REPORT_AT_RISK = "\n\n🟠 <b>در خطر ({count})</b>"
REPORT_TASK_LINE = "\n• {code} · {title} — {assignee} — {delta}{reason}"
REPORT_APPROVAL_LINE = "\n• {code} · {title} — {assignee}"
REPORT_REASON = " ({reason})"
REPORT_PUBLISHES = "\n\n🚀 <b>انتشارهای هفتهٔ پیش رو ({count})</b>"
REPORT_PUBLISH_LINE = "\n• {code} · {title} — {when} — {readiness}"
REPORT_READY = "✅ آماده"
REPORT_MISSING = "مانده: {items}"
REPORT_PEOPLE = "\n\n👥 <b>بار کاری و کیفیت</b>"
REPORT_PERSON = (
    "\n\n<b>{name}</b>"
    "\n• کارهای باز: {open} ({open_time})"
    "\n• ددلاین این هفته: {week} ({week_time}){over}"
    "\n• باز بدون زمان تخمینی: {no_estimate}"
    "\n• تحویل به‌موقع (۷ روز اخیر): {on_time}"
    "\n• میانگین دور اصلاح (۷ روز اخیر): {revisions}"
)
REPORT_OVER_CAPACITY = " ⚠️ بیش از ظرفیت"
REPORT_EMPTY = "\nچیزی نیست ✅"
REPORT_NO_DATA = "—"
REPORT_PERCENT = "{n}٪"

BTN_RECURRENCES = "🔁 کارهای تکراری"
BTN_NEW_RECURRENCE = "➕ کار تکراری جدید"
BTN_STOP_RECURRENCE = "⛔️ توقف: {title}"
BTN_BACK_TO_TEAM = "↩️ بازگشت به تیم"
BTN_RULE_DAILY = "هر روز"
BTN_RULE_WEEKDAYS = "روزهای مشخص هفته"
BTN_WEEKDAYS_DONE = "✅ تأیید روزها"
BTN_CREATE_RECURRENCE = "✅ ساخت کار تکراری"
RECURRENCES_TITLE = "🔁 <b>کارهای تکراری</b>"
RECURRENCES_EMPTY = "\n\nهنوز کار تکراری فعالی نیست."
RECURRENCE_LINE = "\n\n• <b>{title}</b>\n  👤 {assignee} — {rule}\n  🕗 ساخت {create} · ⏰ ددلاین {due}"
RULE_DAILY_LABEL = "هر روز"
RULE_WEEKDAYS_LABEL = "{days}"
NEW_RECURRENCE_TITLE = "🔁 <b>کار تکراری جدید</b>\n\nعنوان کار را بنویسید:\n(برای لغو در هر مرحله: /cancel)"
NEW_RECURRENCE_ASSIGNEE = "👤 مسئول این کار کیست؟"
NEW_RECURRENCE_RULE = "📆 کِی تکرار شود؟"
NEW_RECURRENCE_WEEKDAYS = "📆 روزها را انتخاب کنید (چندتایی)، بعد «تأیید روزها» را بزنید:"
NEW_RECURRENCE_CREATE_TIME = (
    "🕗 تسک هر روز چه ساعتی ساخته و برای مسئول فرستاده شود؟\n"
    "یکی از دکمه‌ها را بزنید یا ساعت را بنویسید، مثلاً <code>08:30</code>."
)
NEW_RECURRENCE_DUE_TIME = (
    "⏰ ددلاین همان روز چه ساعتی باشد؟\n"
    "یکی از دکمه‌ها را بزنید یا ساعت را بنویسید، مثلاً <code>18:00</code>."
)
NEW_RECURRENCE_SUMMARY = (
    "📝 <b>بررسی نهایی کار تکراری</b>\n\n"
    "عنوان: {title}\nمسئول: {assignee}\nتکرار: {rule}\n"
    "ساخت: ساعت {create}\nددلاین: ساعت {due}\n"
    "زنجیرهٔ تأیید: {chain}\nزمان تخمینی: {estimate}"
)
RECURRENCE_CREATED = "✅ کار تکراری «{title}» ساخته شد. اولین تسک در زمان ساخت بعدی فرستاده می‌شود."
RECURRENCE_STOPPED = "⛔️ کار تکراری «{title}» متوقف شد. تسک‌هایی که قبلاً ساخته شده‌اند دست‌نخورده می‌مانند."
WEEKDAYS_REQUIRED = "حداقل یک روز را انتخاب کنید."

VALIDATION_MESSAGES.update({
    "weekdays_invalid": "حداقل یک روز هفته را انتخاب کنید.",
    "due_before_create": "ساعت ددلاین باید بعد از ساعت ساخت باشد.",
    "assignee_invalid": "این مسئول دیگر فعال نیست. نفر دیگری را انتخاب کنید.",
})

# ---- 📚 library (F9, M4) ------------------------------------------------------

LIBRARY_HOME = (
    "📚 <b>کتابخانهٔ خروجی‌ها</b>\n\n"
    "همهٔ کارهای تأییدشدهٔ نهایی این‌جا هستند.\n"
    "🔎 برای جست‌وجو، هر متنی بفرستید: بخشی از عنوان، نام سری، کد (مثلاً <code>T-0012</code>) "
    "یا نام مسئول.\n"
    "یا یکی از دکمه‌ها را بزنید:"
)
BTN_LIB_RECENT = "🆕 ۱۰ خروجی آخر"
BTN_LIB_KIND_REEL = "🎬 ریل"
BTN_LIB_KIND_COVER = "🖼 کاور"
BTN_LIB_KIND_OTHER = "📄 سایر"
BTN_LIB_BY_SERIES = "🗂 بر اساس سری"
BTN_LIB_HOME = "↩️ کتابخانه"
BTN_LIB_BACK_TO_LIST = "↩️ بازگشت به لیست"
LIB_KIND_TITLES = {
    "reel": "🎬 ریل‌ها",
    "cover": "🖼 کاورها",
    "other": "📄 سایر خروجی‌ها",
}
LIB_TYPE_ICONS = {
    "REEL_VIDEO": "🎬",
    "REEL_COVER": "🖼",
    "OTHER": "📄",
}
LIB_TYPE_LABELS = {
    "REEL_VIDEO": "ویدیوی ریل",
    "REEL_COVER": "کاور ریل",
    "OTHER": "سایر",
}
LIB_RECENT_TITLE = "🆕 ۱۰ خروجی آخر"
LIB_SERIES_TITLE = "🗂 سری «{name}»"
LIB_SEARCH_TITLE = "🔎 نتیجهٔ جست‌وجوی «{query}»"
LIB_LIST_HEADER = "<b>{title}</b> — {count} مورد"
LIB_LIST_LINE = "\n{n}. {icon} <b>{code}</b> · {title}\n    👤 {owner} — {date}"
LIB_EMPTY = "\n\nچیزی پیدا نشد."
LIB_EMPTY_LIBRARY = "\n\nهنوز هیچ خروجی تأییدشده‌ای در کتابخانه نیست."
LIB_SEARCH_EMPTY_HINT = "\n\nبخش کوتاه‌تری از عنوان یا نام را امتحان کنید."
LIB_PICK_SERIES = "🗂 سری را انتخاب کنید:"
LIB_NO_SERIES = "هنوز خروجی‌ای با سری مشخص ثبت نشده است."
LIB_SEARCH_EXPIRED = "این جست‌وجو منقضی شده است. دوباره متن را بفرستید."
LIB_DETAIL = (
    "{icon} <b>{code}</b> · {title}\n\n"
    "نوع: {type}\n"
    "سری: {series}\n"
    "مسئول: {owner}\n"
    "تأیید نهایی: {approved}\n"
    "نسخه: v{version}"
)
LIB_DETAIL_REEL = "\nریل: <b>{code}</b>"
LIB_DETAIL_PUBLISHED = "\n\n🚀 <b>منتشرشده</b> — {when}\n🔗 {links}"
LIB_DETAIL_LINKS = "\n\n🔗 <b>لینک‌های تحویل</b>\n{links}"
LIB_DETAIL_FILES = "\n\n📎 {count} فایل در پیام‌های بعدی 👇"
LIB_DETAIL_NO_FILES = "\n\n(این خروجی فایل ندارد.)"
LIB_FILE_FAILED = "⚠️ ارسال یکی از فایل‌ها ممکن نشد."
LIB_NOT_FOUND = "این خروجی پیدا نشد."
# ---- 👤 team members and offboarding (F15, M6) -------------------------------------

BTN_MEMBERS = "👤 اعضای تیم"
BTN_HANDOVERS = "⚠️ تحویل کار اعضای غیرفعال ({count})"
TEAM_ORPHAN_RECURRENCES = "\n\n⚠️ {count} کار تکراری مسئول فعال ندارد و تا تعیین مسئول جدید ساخته نمی‌شود."
TEAM_PENDING_HANDOVERS = "\n\n⚠️ کارهای باز {count} عضو غیرفعال هنوز به کسی سپرده نشده است."
MEMBERS_TITLE = "👤 <b>اعضای فعال تیم</b> ({count})\nبرای دیدن جزئیات یا غیرفعال‌سازی، روی نام بزنید."
MEMBERS_HANDOVER_TITLE = "⚠️ <b>اعضای غیرفعالی که کار باز دارند</b>\nروی نام بزنید تا کارهایشان را بسپارید."
MEMBER_BUTTON = "{name} — {role} · {open}"
MEMBER_CARD = (
    "👤 <b>{name}</b>\n"
    "نقش: {role}\n"
    "نام کاربری: {username}\n"
    "وضعیت: {status}\n"
    "دسترسی‌ها: {caps}\n\n"
    "📋 کارهای باز: {open}\n"
    "🔁 کارهای تکراری: {recurrences}"
)
MEMBER_STATUS_ACTIVE = "✅ فعال"
MEMBER_STATUS_INACTIVE = "⛔️ غیرفعال از {when}"
MEMBER_NO_CAPS = "—"
MEMBER_TASK_LINE = "\n• {code} · {title} — {status}"
MEMBER_REC_LINE = "\n• 🔁 {title}"
BTN_DEACTIVATE = "⛔️ غیرفعال‌سازی"
BTN_DEACTIVATE_YES = "⛔️ بله، غیرفعال کن"
BTN_BACK_TO_MEMBERS = "↩️ بازگشت به اعضا"
BTN_TRANSFER_ALL = "📦 انتقال همهٔ کارها به…"
BTN_TRANSFER_TASK = "📋 {code} · {title}"
BTN_TRANSFER_REC = "🔁 {title}"
DEACTIVATE_CONFIRM = (
    "⛔️ <b>غیرفعال‌سازی {name}</b>\n\n"
    "• دیگر به ربات دسترسی ندارد و پیامی از ربات نمی‌گیرد.\n"
    "• نام و تاریخچهٔ کارهایش در همهٔ سوابق می‌ماند.\n"
    "• بعد از غیرفعال‌سازی، کارهای بازش را به نفر دیگری می‌سپارید.\n\n"
    "مطمئن هستید؟"
)
DEACTIVATED_DONE = "✅ <b>{name}</b> غیرفعال شد."
DEACTIVATED_DELEGATION = "\n🔁 تفویض فعالی که به او مربوط بود لغو شد."
CAPS_WARNING = "\n\n⚠️ <b>این دسترسی‌ها حالا هیچ عضو فعال دیگری ندارد:</b>\n{caps}\nبرای تعیین جایگزین به مالک ربات خبر بدهید."
CAPS_COVERED = "\n\nدسترسی‌های خاص او را عضو دیگری هم دارد. ✅"
HANDOVER_TITLE = "\n\n📦 <b>کارهای باز برای سپردن</b> ({tasks} تسک، {recs} کار تکراری)"
HANDOVER_NOTHING = "\n\nکار بازی برای سپردن ندارد. ✅"
HANDOVER_HINT = "\nهمه را یک‌جا بسپارید یا روی هر مورد بزنید."
HANDOVER_PICK_ALL = "📦 همهٔ {count} تسک باز {name} به چه کسی سپرده شود؟"
HANDOVER_PICK_TASK = "📋 تسک <b>{code}</b> به چه کسی سپرده شود؟"
HANDOVER_PICK_REC = "🔁 کار تکراری «{title}» از این به بعد با چه کسی باشد؟"
HANDOVER_ALL_DONE = "✅ {count} تسک به <b>{name}</b> سپرده شد و به او اطلاع داده شد."
HANDOVER_TASK_DONE = "✅ تسک <b>{code}</b> به <b>{name}</b> سپرده شد."
HANDOVER_REC_DONE = "✅ کار تکراری «{title}» از این به بعد با <b>{name}</b> است."
HANDOVER_NO_TARGETS = "عضو فعال دیگری برای سپردن کار نیست."
NOTIFY_USER_DEACTIVATED = (
    "⛔️ <b>{name}</b> ({role}) توسط {actor} غیرفعال شد.\n"
    "کارهای باز: {open} · کارهای تکراری: {recs}"
)
NOTIFY_USER_DEACTIVATED_CAPS = "\n⚠️ این دسترسی‌ها حالا هیچ عضو فعال دیگری ندارد:\n{caps}"

CAPABILITY_LABELS: dict[str, str] = {
    "APPROVE_FINAL": "تأیید نهایی",
    "DELEGATE": "تفویض",
    "MANAGE_USERS": "مدیریت تیم",
    "CREATE_TASK": "ساخت تسک",
    "VIEW_ALL_TASKS": "دیدن همهٔ کارها",
    "RECEIVE_OVERDUE_ALERTS": "دریافت هشدار تأخیر",
    "RECEIVE_WEEKLY_REPORT": "دریافت گزارش هفتگی",
    "CREATE_REEL": "ساخت ریل",
    "REVIEW_L1": "بررسی مرحلهٔ اول",
    "PUBLISH": "ثبت انتشار",
    "SYSTEM_ADMIN": "مدیر سیستم (هشدار خطا و بکاپ)",
}

VALIDATION_MESSAGES.update({
    "deactivate_self": "نمی‌توانید خودتان را غیرفعال کنید.",
    "deactivate_owner": "مالک ربات را نمی‌شود غیرفعال کرد.",
    "handover_active_user": "این کار مال یک عضو فعال است؛ از کارت خود تسک مسئول را عوض کنید.",
    "backup_disabled": "بکاپ فقط با دیتابیس SQLite روی همین سرور ممکن است.",
    "no_targets": HANDOVER_NO_TARGETS,
})
ALREADY_INACTIVE = "این عضو قبلاً غیرفعال شده است."
TASK_NOT_OPEN = "این تسک دیگر باز نیست."

# ---- /health, /backup, errors (M6) ----------------------------------------------------

HEALTH = (
    "🩺 <b>وضعیت ربات</b> — {now}\n\n"
    "⏱ روشن از: {uptime}\n"
    "🔁 آخرین tick: {tick}\n"
    "🗃 حجم دیتابیس: {db_size}\n"
    "🗄 آخرین بکاپ: {backup}\n"
    "📨 اعلان‌های در صف: {pending}\n"
    "❗️ اعلان‌های ناموفق (۲۴ ساعت): {failed}\n"
    "👥 اعضای فعال: {users}"
)
HEALTH_TICK_OK = "✅ {when}"
HEALTH_TICK_LATE = "⚠️ {when} (بیش از ۵ دقیقه پیش)"
HEALTH_NEVER = "هنوز نه"
HEALTH_UNKNOWN = "نامعلوم"
HEALTH_MB = "{mb} مگابایت"
HEALTH_UPTIME = "{days} روز و {hours} ساعت و {minutes} دقیقه"
BACKUP_STARTED = "🗄 در حال گرفتن بکاپ…"
BACKUP_MANUAL_CAPTION = "🗄 بکاپ دستی دیتابیس Eventum HQ — {date}"
BACKUP_TOO_BIG_MANUAL = (
    "⚠️ بکاپ گرفته شد، ولی {size} مگابایت است و از راه تلگرام فرستاده نمی‌شود. روی سرور است:\n<code>{path}</code>"
)
ERROR_REPORTED = "⚠️ مشکلی پیش آمد. به مدیر سیستم اطلاع داده شد. لطفاً کمی بعد دوباره امتحان کنید."
NOTIFY_SYSTEM_ERROR = (
    "🚨 <b>خطا در ربات</b>\n"
    "نوع: <code>{error}</code>\n"
    "محل: <code>{where}</code>\n"
    "پیام: <code>{message}</code>\n\n"
    "جزئیات کامل در لاگ <code>data/logs/</code> است. "
    "تا ۱۰ دقیقه هشدار تکراری از همین نوع فرستاده نمی‌شود."
)
ALL_CAPABILITIES_LABEL = "همه (مالک ربات)"

# ---- M7: daily operations report (📝 گزارش روزانه) -------------------------------

DAILY_HOME = (
    "📝 <b>گزارش روزانه — {date}</b>\n"
    "یادداشت‌های ثبت‌شدهٔ امروز: {count}\n\n"
    "یادداشت‌هایتان را همین‌جا بفرستید؛ می‌توانید در چند پیام بفرستید. "
    "کار ربات (ریل‌های منتشرشده، تحویل‌ها، تأخیرها و ریل‌های بدون کاور) خودکار به گزارش اضافه می‌شود.\n\n"
    "<b>شکل نوشتن</b>\n"
    "• خطی که با <code>#</code> شروع شود یک بخش است: "
    "<code>#انتشار</code>، <code>#ویدیو</code>، <code>#باز</code>، <code>#ساعت</code> یا هر اسم دیگر.\n"
    "• خطی که با <code>:</code> تمام شود زیرعنوان است، مثل <code>اینستاگرام:</code>\n"
    "• بقیهٔ خط‌ها هر کدام یک بند می‌شوند. <code>اقدام بعدی: …</code> عنوانش پررنگ می‌شود.\n"
    "• زیر <code>#ساعت</code> هر خط یک نفر است: <code>امین ۶</code> یا <code>محدثه: مرخصی</code>\n\n"
    "<b>نمونه</b>\n"
    "<pre>#انتشار\nاینستاگرام:\n۱ پست کاروسل منتشر شد\n#ویدیو\nاقدام بعدی: تکمیل اطلاعات انتشار\n"
    "#ساعت\nامین ۶</pre>\n"
    "یادداشت‌های قبل از ساعت ۵ صبح هم برای گزارش دیروز حساب می‌شوند."
)
DAILY_NOTE_SAVED = "✅ ثبت شد. یادداشت‌های امروز: {count}\nادامه بدهید، یا «👁 پیش‌نمایش» را بزنید."
DAILY_NOTES_EMPTY = "هنوز یادداشتی برای امروز ثبت نشده است."
DAILY_NOTES_TITLE = "🗒 <b>یادداشت‌های {date}</b>\n"
DAILY_NOTE_LINE = "\n<b>{n}. {author}</b> — {time}\n{text}\n"
DAILY_CLEAR_CONFIRM = "🗑 همهٔ یادداشت‌هایی که <b>خودتان</b> امروز نوشته‌اید ({count} تا) پاک شوند؟ یادداشت‌های بقیه می‌ماند."
DAILY_CLEARED = "🗑 {count} یادداشت پاک شد."
DAILY_NOTHING_TO_CLEAR = "یادداشتی از شما برای امروز نیست."
DAILY_NOTHING_TO_REPORT = "هنوز چیزی برای گزارش امروز نیست: نه یادداشتی ثبت شده و نه کاری در ربات."
DAILY_PREVIEW_HINT = "👆 پیش‌نمایش گزارش. اگر درست است «✅ نهایی‌کردن» را بزنید، وگرنه یادداشت اضافه کنید."
DAILY_FINAL_DONE = "✅ گزارش نهایی شد. پیام بالا را می‌توانید فوروارد کنید."
DAILY_RICH_FALLBACK = "ℹ️ تلگرام قالب جدید گزارش را نپذیرفت؛ همان گزارش با قالب ساده فرستاده شد."
BTN_DAILY_PREVIEW = "👁 پیش‌نمایش"
BTN_DAILY_LIST = "🗒 یادداشت‌ها"
BTN_DAILY_CLEAR = "🗑 پاک‌کردن یادداشت‌های من"
BTN_DAILY_CLEAR_YES = "🗑 بله، پاک شود"
BTN_DAILY_FINAL = "✅ نهایی‌کردن"
BTN_DAILY_ADD = "✍️ افزودن یادداشت"
BTN_DAILY_BACK = "↩️ برگشت"

# the report itself (rich message, Markdown); English parts are part of the team's report style
DAILY_BRAND = "EVENTUM SPACE"
DAILY_TITLE = "DAILY OPERATIONS REPORT"
# U+2066/U+2069 isolate the English date, so an RTL line does not show "November 2026 13"
DAILY_DATE_LINE = "{weekday} {d} {month} {y} | ⁦{gd} {gmonth} {gy}⁩"
DAILY_SECTION_TITLES = {
    "PUBLISHING": "Content & Publishing — انتشار محتوا",
    "VIDEO": "Weekly Video — ویدیوی هفتگی",
    "NOTES": "Notes — یادداشت‌ها",
    "PRODUCTION": "Production — تولید و تحویل",
    "PENDING": "Pending & Follow-ups — موارد باز",
    "HOURS": "Team Working Hours — ساعات کاری تیم",
}
DAILY_SECTION_HEADING = "{n:02d} | {title}"
DAILY_FROM_BOT = "ثبت‌شده در ربات"
DAILY_AUTO_PUBLISHED = "ریل «{title}» ({code}) منتشر شد."
DAILY_AUTO_OUTPUTS = "خروجی‌های تأییدشدهٔ امروز: {items}"
DAILY_AUTO_OUTPUT_PART = "{n} {label}"
DAILY_AUTO_DELIVERED = "{name}: {n} تحویل ({codes})"
DAILY_AUTO_OVERDUE = "{code} «{title}» — {name}، {delta}"
DAILY_AUTO_AWAITING = "{n} کار منتظر تأیید نهایی است."
DAILY_AUTO_NO_COVER = "ریل «{title}» ({code}) هنوز کاور تأییدشده ندارد."
DAILY_HOURS_HEADER = "| # | نام | ساعت کاری |"
DAILY_HOURS_TOTAL = "جمع"
DAILY_HOURS_VALUE = "{n} ساعت"
DAILY_HASHTAGS = "#گزارش_روزانه #{weekday} #{d}_{month}_{y}"
JALALI_MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
                 "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
ENGLISH_MONTHS = ["January", "February", "March", "April", "May", "June",
                  "July", "August", "September", "October", "November", "December"]

VALIDATION_MESSAGES.update({
    "daily_note_empty": "یادداشت خالی است.",
    "daily_note_too_long": "این یادداشت خیلی بلند است (حداکثر ۴۰۰۰ نویسه). آن را در چند پیام بفرستید.",
    "daily_notes_full": "برای امروز به سقف ۶۰ یادداشت رسیدید. یادداشت‌های قبلی را در یک پیام جمع کنید.",
})
