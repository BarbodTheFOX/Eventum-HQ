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

TEAM_MENU = "👥 <b>تیم</b>\n\n🔁 تفویض تأیید نهایی: {delegation}"
TEAM_NO_DELEGATION = "فعال نیست"
TEAM_DELEGATION_ACTIVE = "{to_name} تا {ends}"
TEAM_MORE_SOON = "\n\nمدیریت کاربران، نقش‌ها و ظرفیت هفتگی در نسخه‌های بعدی اضافه می‌شود."
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
