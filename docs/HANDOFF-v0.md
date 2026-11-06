# Eventum HQ — v0 Implementation Handoff (for Claude Code)

> نسخهٔ سند: 1.0 — ۱۷ آبان ۱۴۰۵ (2026-11-07)
> وضعیت: آمادهٔ پیاده‌سازی v0
> مرجع تصمیم‌ها: `discovery-log.md` در Project «Eventum management bot»
> توسعه و نگهداری: باربد و فرید، با Claude Code (حدود ۴ ساعت در روز)

---

## 0. قواعد کار برای Claude Code

1. **Milestone به Milestone جلو برو** (بخش ۹). بعد از هر Milestone متوقف شو، خلاصهٔ کار و چک‌لیست تست دستی را بده و منتظر تأیید بمان.
2. **چیزی بیرون از محدودهٔ بخش ۲ نساز.** اگر چیزی لازم به نظر رسید، پیشنهادش را بده، ولی خودت اضافه نکن.
3. **منطق کسب‌وکار در `services/` است و هرگز `aiogram` را import نمی‌کند.** لایهٔ Telegram فقط ورودی را می‌گیرد و خروجی را نمایش می‌دهد.
4. **هر تغییر وضعیت فقط از طریق یک تابع service انجام می‌شود** که مجوز را چک می‌کند و `AuditEvent` می‌نویسد. هیچ handlerی مستقیم دیتابیس را تغییر نمی‌دهد.
5. **مجوز هر عمل در سرور دوباره چک می‌شود.** به اینکه کاربر یک دکمه را دیده اعتماد نکن، چون `callback_data` قابل جعل است.
6. **همهٔ متن‌های رابط کاربری فارسی هستند و در `bot/texts.py` جمع می‌شوند.** متن را داخل handlerها hard-code نکن.
7. **زمان‌ها در دیتابیس UTC هستند.** نمایش و ورودی با تقویم شمسی و منطقهٔ `Asia/Tehran` است. هفته از شنبه شروع می‌شود.
8. **برای هر منطق service تست بنویس** (بخش ۱۰). Milestone بدون تست‌های سبز تمام‌شده حساب نمی‌شود.
9. **قبل از اضافه‌کردن هر dependency خارج از بخش ۶ بپرس.**
10. **`.env`، توکن و فایل دیتابیس هرگز commit نمی‌شوند.**

---

## 1. خلاصهٔ محصول

**Eventum Space** یک مجموعهٔ رسانه‌ای فارسی‌زبان با ۶ عضو است. **Eventum HQ** (`@EventumHQBot`) ربات تلگرامی مدیریت کار و خروجی‌های این تیم است.

**مشکل اصلی:** هیچ رکورد واحدی برای هر کار وجود ندارد. نتیجه این است که:
- معلوم نیست کار دست کیست،
- تأخیر دیر فهمیده می‌شود،
- اصلاحات و کارها گم می‌شوند،
- و فایل نهایی پیدا نمی‌شود.

**هدف v0:** هر آیتم کاری یک رکورد داشته باشد با مسئول، ددلاین، وضعیت، فایل‌ها، تاریخچهٔ اصلاح و تأیید. مدیر هم بدون پرس‌وجو وضعیت را ببیند.

**جایگاه نسبت به Codecks:** لیمینال (شرکت مادر) Codecks را به‌عنوان سیستم اصلی خودش دارد. v0 **مستقل** ساخته می‌شود، ولی آمادهٔ اتصال بعدی به Codecks است (بخش ۷.۸). استفادهٔ واقعی تیم از v0، استدلال اصلی برای گرفتن API token و سرور از لیمینال است.

---

## 2. محدوده

### داخل v0
| # | قابلیت | استفاده‌کننده |
|---|---|---|
| F1 | ورود فقط کاربران تأییدشده + درخواست دسترسی با تأیید Owner | همه |
| F2 | نقش‌ها و capabilityها | همه |
| F3 | تسک عمومی (ad-hoc): ساخت، تخصیص، ددلاین شمسی، زنجیرهٔ تأیید قابل انتخاب | فرید، علی |
| F4 | آیتم ریل: دو تسک موازی (ادیت، کاور) + تحویل عکس‌های کاور + زنجیرهٔ امین ← فرید | امین، سینا، محدثه |
| F5 | تحویل خروجی (فایل یا لینک) و نسخه‌بندی Submission | مجریان کار |
| F6 | بررسی یک‌کلیکی: تأیید یا اصلاح با یادداشت (متن، ویس، عکس) و شمارش دور اصلاح | امین، فرید |
| F7 | تفویض موقت تأیید نهایی از فرید به امین | فرید |
| F8 | ثبت انتشار ریل (لینک‌ها) | باربد |
| F9 | کتابخانهٔ خروجی‌ها: لیست، جست‌وجو و دریافت فایل | همه |
| F10 | تسک تکرارشونده ساده (روزانه یا روزهای مشخص هفته) | فرید، علی |
| F11 | یادآوری ددلاین، هشدار تأخیر، ساعات سکوت | همه |
| F12 | پیام گروه: «برنامهٔ امروز» و «جمع‌بندی هفتگی» | تیم |
| F13 | گزارش صبح شنبه (خصوصی) | فرید (و علی) |
| F14 | Audit Log کامل | سیستم |
| F15 | Offboarding: غیرفعال‌سازی کاربر + انتقال یک‌جای تسک‌ها | فرید |
| F16 | بکاپ خودکار روزانه + ارسال هفتگی بکاپ برای ادمین‌ها + `/backup` | سیستم |

### بیرون از v0 (نساز)
- همگام‌سازی با Codecks (فقط فیلدها و interface آماده باشند)
- Telegram Mini App یا داشبورد وب
- Templateهای چندمرحله‌ای عمومی با وابستگی دلخواه (فقط جریان ریل hard-code شده)
- ذخیرهٔ فوتیج خام، Object Storage، و جست‌وجو در محتوای فایل
- چند زبان، چند سازمان، webhook (v0 با long polling کار می‌کند)
- هوش مصنوعی و تحلیل‌های پیشرفته

---

## 3. کاربران، نقش‌ها و مجوزها

### 3.1 افراد
| نفر | role | capabilities |
|---|---|---|
| فرید | OWNER | همه |
| علی مرادی | MANAGER | `CREATE_TASK`, `VIEW_ALL_TASKS`, `RECEIVE_OVERDUE_ALERTS`, `RECEIVE_WEEKLY_REPORT` |
| امین زرزا | MEMBER | `CREATE_REEL`, `REVIEW_L1` |
| باربد | MEMBER | `PUBLISH`, `SYSTEM_ADMIN` |
| سینا | MEMBER | — |
| محدثه | MEMBER | — |

- OWNER ضمناً همهٔ capabilityها را دارد، از جمله `APPROVE_FINAL`، `MANAGE_USERS`، `DELEGATE` و `SYSTEM_ADMIN`.
- `SYSTEM_ADMIN` یعنی دریافت هشدار خطا و فایل بکاپ، و اجرای `/backup`.
- همه به‌طور پیش‌فرض این‌ها را دارند: دیدن کارهای خودشان، تحویل کار، و دسترسی به کتابخانهٔ خروجی‌ها.
- capabilityها در DB ذخیره می‌شوند و OWNER از منوی «👥 تیم» تغییرشان می‌دهد.

### 3.2 ماتریس مجوز
| عمل | OWNER | MANAGER | REVIEW_L1 | PUBLISH | MEMBER |
|---|---|---|---|---|---|
| دیدن کارهای خود | ✅ | ✅ | ✅ | ✅ | ✅ |
| دیدن همهٔ کارها | ✅ | ✅ | — | — | — |
| ساخت/ویرایش/تخصیص تسک عمومی | ✅ | ✅ | — | — | — |
| ساخت آیتم ریل | ✅ | — | (`CREATE_REEL`) | — | — |
| بررسی مرحلهٔ اول | ✅ | — | ✅ | — | — |
| تأیید نهایی | ✅ | — | فقط حین تفویض | — | — |
| ثبت انتشار | ✅ | — | — | ✅ | — |
| کتابخانهٔ خروجی‌ها | ✅ | ✅ | ✅ | ✅ | ✅ |
| گزارش شنبه و بار کاری افراد | ✅ | ✅ (کپی) | — | — | — |
| مدیریت کاربران، تفویض، Offboarding | ✅ | — | — | — | — |

**قاعده:** هر کسی که تسکی به او تخصیص داده شده، می‌تواند همان تسک را ببیند و تحویل بدهد، بدون توجه به نقشش.

### 3.3 ورود و ثبت کاربر
- فقط `OWNER_TELEGRAM_ID` در `.env` تعریف می‌شود. بقیه این‌طور وارد می‌شوند:
  1. کاربر `/start` می‌زند.
  2. اگر شناخته‌شده نیست، پیام «درخواست شما برای مدیر ارسال شد» را می‌بیند.
  3. OWNER کارت درخواست را با نام و username و این دکمه‌ها می‌گیرد: `[✅ تأیید به‌عنوان عضو]` `[❌ رد]`.
  4. OWNER بعداً capabilityها را از منوی تیم تنظیم می‌کند.
- کاربر غیرفعال یا ناشناخته به هیچ دستوری جز `/start` جواب نمی‌گیرد. برای هر کاربر ناشناس، حداکثر یک درخواست در ۲۴ ساعت برای OWNER فرستاده می‌شود.
- در گروه، ربات به هیچ دستوری جواب نمی‌دهد و فقط پیام‌های زمان‌بندی‌شده را می‌گذارد. ربات فقط در `TEAM_GROUP_ID` پیام می‌گذارد. اگر به گروه دیگری اضافه شد، خارج می‌شود.

---

## 4. مدل دامنه و جریان‌ها

### 4.1 مفاهیم
- **Series:** سری یا پروژه، مثل «ریل روزانه»، «PURPLE ZONE»، «سری WEEX»، «دوئل تریدرها».
- **ContentItem:** یک آیتم محتوایی. در v0 فقط نوع `REEL`، با زیرنوع `NORMAL` یا `TRIAL`.
- **Task:** واحد کار با یک مسئول. یا به ContentItem وصل است (`EDIT` یا `COVER`) یا مستقل است (`GENERIC`).
- **TaskInput:** ورودی لازم برای انجام کار: تایم‌کدها، متن کاور، عکس‌های کاور، یا بریف.
- **Submission:** هر بار تحویل، یک نسخه است (v1، v2، …).
- **Review:** تصمیم یک بررسی‌کننده روی یک Submission.
- **Output:** خروجی تأییدشدهٔ نهایی در کتابخانه.

### 4.2 کدهای خوانا
- ContentItem: `R-0001`
- Task: `T-0001`

این کدها در همهٔ پیام‌ها و caption آرشیو نمایش داده می‌شوند. کاربر با نوشتن `T-0042` در چت ربات، کارت آن تسک را می‌گیرد (اگر مجوز داشته باشد).

### 4.3 وضعیت‌های Task
```
BLOCKED ──(ورودی رسید)──▶ TODO ──(شروع)──▶ IN_PROGRESS ──(تحویل)──▶ IN_REVIEW
   ▲                       │                     ▲                    │
   │                       └──────(تحویل مستقیم)──┼────────────────────┤
   │                                             │                    ▼
   └───────────── (فقط COVER: منتظر عکس)          └──── CHANGES_REQUESTED ◀── (اصلاح)
                                                                       │
                                               IN_REVIEW ──(تأیید آخرین مرحله)──▶ APPROVED
هر وضعیت باز ──(لغو توسط سازنده/OWNER/MANAGER)──▶ CANCELLED
```
- `IN_REVIEW` همیشه یک `review_stage` دارد: `L1` (منتظر امین) یا `FINAL` (منتظر فرید).
- «شروع کار» اختیاری است. کاربر می‌تواند از `TODO` مستقیم تحویل بدهد.
- وضعیت‌های پایانی: `APPROVED` و `CANCELLED`.

### 4.4 زنجیرهٔ تأیید (`approval_chain`)
| مقدار | معنی | پیش‌فرض برای |
|---|---|---|
| `NONE` | با «انجام شد» توسط مسئول، `APPROVED` می‌شود | — (قابل انتخاب برای تسک عمومی) |
| `FINAL` | فقط تأیید فرید | **تسک عمومی (پیش‌فرض)** |
| `L1_FINAL` | امین، سپس فرید | **EDIT و COVER ریل** |

**تفویض (F7):** اگر یک `Delegation` فعال از OWNER به کاربری با `REVIEW_L1` وجود داشته باشد (now بین `starts_at` و `ends_at`):
- در زنجیرهٔ `L1_FINAL`، تأیید L1 همان تأیید نهایی است و مرحلهٔ FINAL رد می‌شود.
- در زنجیرهٔ `FINAL`، بررسی به نمایندهٔ تفویض می‌رسد.
- `Review.delegated = true` ثبت می‌شود.
- تفویض در هر زمان توسط OWNER قابل لغو است.
- هنگام شروع و پایان تفویض، هر دو نفر پیام می‌گیرند.

**مسیر بعد از اصلاح:** تحویل مجدد مستقیم به همان مرحله‌ای برمی‌گردد که اصلاح خواسته بود. یعنی اگر فرید اصلاح خواست، نسخهٔ جدید مستقیم به فرید می‌رسد و دوباره از امین رد نمی‌شود. این رفتار با setting `revision_returns_to_requesting_stage = true` قابل تغییر است.

### 4.5 جریان ریل (F4)
1. **امین ریل جدید می‌سازد.** ورودی‌ها:
   - عنوان
   - نوع: عادی یا Trial
   - سری (پیش‌فرض: «ریل روزانه»)
   - تاریخ و ساعت انتشار برنامه‌ریزی‌شده
   - تایم‌کدها (متن)
   - متن کاور (متن)
   - مسئول ادیت (پیش‌فرض سینا) و مسئول کاور (پیش‌فرض محدثه)
2. **سیستم خودکار می‌سازد:**
   - `ContentItem R-xxxx` با وضعیت `IN_PRODUCTION`
   - `Task EDIT` برای سینا، وضعیت `TODO`، با ورودی TIMECODES
   - `Task COVER` برای محدثه، وضعیت `BLOCKED` با دلیل «منتظر عکس‌های سینا»، با ورودی COVER_TEXT
   - یک «تعهد عکس کاور» برای سینا با ددلاین `photos_due_at`
3. **ددلاین‌های پیش‌فرض** نسبت به زمان انتشار تعریف می‌شوند و امین هنگام ساخت می‌تواند تغییرشان دهد. مقادیر در `settings` قابل تنظیم‌اند:
   - `photos_due_at` = ساخت + 4 ساعت (حداکثر تا قبل از `edit_due_at`)
   - `edit_due_at` = انتشار − 6 ساعت
   - `cover_due_at` = انتشار − 6 ساعت
4. **سینا عکس‌ها را تحویل می‌دهد.** از کارت تسک ادیت خودش، دکمهٔ «🖼 ارسال عکس‌های کاور» را می‌زند، یک یا چند عکس یا فایل می‌فرستد و «تمام» را می‌زند. نتیجه:
   - عکس‌ها در آرشیو کپی می‌شوند و `TaskInput COVER_PHOTOS` روی تسک کاور ثبت می‌شود.
   - تسک کاور `TODO` می‌شود و محدثه پیام می‌گیرد، همراه با متن کاور و عکس‌ها.
   - اگر عکس‌ها دیر برسند، تأخیر به اسم سینا (`photos_late`) ثبت می‌شود، نه محدثه. ددلاین کاور هم تا وقتی تسک `BLOCKED` است «در خطر» نمایش داده می‌شود، ولی تأخیر محدثه حساب نمی‌شود.
5. **ادیت و کاور مستقل از هم** از چرخهٔ تحویل، بررسی امین و تأیید فرید می‌گذرند.
6. **وقتی هر دو تسک `APPROVED` شدند:**
   - ContentItem به `READY_TO_PUBLISH` می‌رود.
   - هر کاربر با `PUBLISH` (باربد) کارت «آماده انتشار» را با ویدیو و کاور نهایی (copy از آرشیو) و این دکمه می‌گیرد: `[🚀 ثبت انتشار]`.
7. **باربد انتشار را ثبت می‌کند:** یک یا چند لینک (اینستاگرام، یوتیوب، تلگرام) و زمان انتشار (پیش‌فرض: الان). ContentItem `PUBLISHED` می‌شود.
8. **لغو ریل:** امین (سازنده) یا OWNER می‌تواند ریل را لغو کند. همهٔ تسک‌های باز آن `CANCELLED` می‌شوند و مسئولان پیام می‌گیرند.

### 4.6 تسک عمومی (F3)
- ورودی‌ها:
  - عنوان
  - توضیح (اختیاری؛ متن، ویس یا فایل به‌عنوان BRIEF)
  - مسئول
  - ددلاین
  - سری (اختیاری)
  - زنجیرهٔ تأیید (پیش‌فرض `FINAL`)
- اپیزودهای لانگ‌فرم، تامنیل یوتیوب، رویدادها و کارهای کمپین در v0 همه تسک عمومی هستند.

### 4.7 تحویل (F5)
1. مسئول از کارت تسک «📤 تحویل» را می‌زند.
2. یک یا چند فایل (video, document, photo, audio, voice) یا لینک، به‌اضافهٔ یادداشت اختیاری می‌فرستد و «✅ ارسال برای بررسی» را می‌زند.
3. هر فایل با `copyMessage` به کانال خصوصی آرشیو (`ARCHIVE_CHANNEL_ID`) کپی می‌شود. caption کپی: `#T0042 v2 | عنوان | نام مسئول | تاریخ شمسی`. این‌ها ذخیره می‌شوند: `file_id`، `file_unique_id`، نوع، حجم و `archive_message_id`.
4. فایل‌های بالای ۲۰MB هم پذیرفته می‌شوند، چون ربات دانلودشان نمی‌کند و فقط copy و forward با file_id انجام می‌دهد.
5. **اولین تحویل** `first_submitted_at` را ثبت می‌کند. معیار به‌موقع‌بودن، `first_submitted_at <= due_at` است. زمان صف بررسی هرگز به حساب تأخیر مسئول نوشته نمی‌شود.

### 4.8 بررسی (F6)
1. بررسی‌کننده کارت بررسی را می‌گیرد: کد، عنوان، مسئول، نسخه، دور اصلاح، وضعیت ددلاین، یادداشت، و کپی فایل‌ها. دکمه‌ها: `[✅ تأیید] [✏️ اصلاح لازم است] [📄 جزئیات و تاریخچه]`.
2. **با «اصلاح»:** ربات می‌خواهد یادداشت اصلاح فرستاده شود (یک یا چند پیام متن، ویس یا عکس، سپس «تمام»). نتیجه:
   - تسک `CHANGES_REQUESTED` می‌شود و `revision_round += 1`.
   - مسئول کارت اصلاح را با همهٔ یادداشت‌ها می‌گیرد.
3. **با «تأیید»:** تسک به مرحلهٔ بعد یا `APPROVED` می‌رود. در حالت `APPROVED`:
   - یک `Output` در کتابخانه ساخته می‌شود.
   - `completed_at` ثبت می‌شود.
   - مسئول پیام تأیید می‌گیرد.
4. **قفل همزمانی:** اگر کارت بررسی قدیمی باشد (نسخهٔ جدیدتری آمده یا کس دیگری تصمیم گرفته)، دکمه با پیام «این مورد قبلاً بررسی شده» رد می‌شود. چک با `submission_id` و `version` انجام می‌شود.

### 4.9 کتابخانه (F9)
- «📚 کتابخانه» این گزینه‌ها را دارد:
  - ۱۰ خروجی آخر
  - فیلتر نوع: ریل / کاور / سایر
  - فیلتر سری
  - جست‌وجوی متنی: کاربر هر متنی بفرستد، روی عنوان، سری، کد و نام مسئول جست‌وجو می‌شود
- نتایج صفحه‌بندی می‌شوند (۸ تا در هر صفحه) با دکمه برای هر مورد. با زدن دکمه، فایل‌ها با `copyMessage` از آرشیو برای کاربر فرستاده می‌شوند، همراه با اطلاعات و لینک انتشار اگر وجود دارد.
- جست‌وجو: در v0 از `LIKE` روی ستون `search_text` نرمال‌شده استفاده کن. FTS5 لازم نیست.
- **نرمال‌سازی فارسی:** ي ← ی، ك ← ک، حذف نیم‌فاصله و اعراب، تبدیل ارقام فارسی و عربی به لاتین.

### 4.10 تسک تکرارشونده (F10)
- یک Recurrence شامل این‌هاست:
  - template: عنوان، مسئول، توضیح، approval_chain، سری، ساعت ددلاین
  - قانون: `DAILY` یا لیست روزهای هفته
  - زمان ساخت روزانه (پیش‌فرض 08:30)
  - زمان ددلاین در همان روز (پیش‌فرض 18:00)
- هر روز در زمان ساخت، تسک ساخته و به مسئول اعلام می‌شود. ساخت idempotent است، با کلید `(recurrence_id, date)`.
- غیرفعال‌کردن یا ویرایش Recurrence روی تسک‌های ساخته‌شده اثر ندارد.

### 4.11 Offboarding (F15)
OWNER از «👥 تیم»، کاربر را انتخاب و «غیرفعال‌سازی» را می‌زند. نتیجه:
- `is_active = false` می‌شود. تاریخچه و نام او در همهٔ رکوردها باقی می‌ماند.
- لیست تسک‌های باز او نمایش داده می‌شود و «انتقال همه به…» (یک نفر) یا انتقال تک‌به‌تک ممکن است.
- Recurrenceهایی که مسئولشان این کاربر است، علامت‌گذاری می‌شوند تا OWNER مسئول جدید تعیین کند.
- capabilityهای خاص او، مثل `REVIEW_L1` و `PUBLISH`، به OWNER هشدار داده می‌شوند تا جایگزین تعیین شود.

---

## 5. تجربهٔ کاربری تلگرام

### 5.1 اصول
- **همهٔ کارها در چت خصوصی.** گروه فقط پیام‌های زمان‌بندی‌شده را می‌گیرد.
- **منوی اصلی با Reply Keyboard، بسته به capabilityها.** عمل روی آیتم‌ها با Inline Keyboard.
- **هر کارت تسک** شامل: کد، عنوان، سری، مسئول، ددلاین شمسی + «۳ ساعت مانده» یا «۱ روز تأخیر»، وضعیت، دور اصلاح و آخرین رویداد.
- **پیام‌ها کوتاه و فارسی** با ایموجی وضعیت: ⏳ در انتظار، 🔒 مسدود، 🛠 در حال انجام، 👀 در بررسی، ✏️ نیاز به اصلاح، ✅ تأییدشده، ❌ لغوشده، 🔴 عقب‌افتاده، 🟠 در خطر.
- **`/cancel`** هر جریان نیمه‌کاره را لغو می‌کند. جریان‌ها بعد از ۳۰ دقیقه بی‌فعالیتی منقضی می‌شوند.

### 5.2 منوی اصلی بر اساس capability
| دکمه | چه کسانی |
|---|---|
| 📋 کارهای من | همه |
| 📚 کتابخانه | همه |
| ➕ ریل جدید | `CREATE_REEL` |
| 👀 منتظر بررسی من | `REVIEW_L1` |
| ✅ منتظر تأیید من | OWNER (و نمایندهٔ تفویض در زمان تفویض) |
| 🚀 آماده انتشار | `PUBLISH` |
| ➕ تسک جدید | `CREATE_TASK` |
| 🗂 همهٔ کارها | `VIEW_ALL_TASKS` (فیلتر: باز / عقب‌افتاده / در خطر / بر اساس نفر / بر اساس سری) |
| 📊 گزارش | OWNER، MANAGER |
| 👥 تیم | OWNER (کاربران، capabilityها، تفویض، غیرفعال‌سازی، Recurrenceها) |
| ❓ راهنما | همه |

**دستورها:** `/start`، `/menu`، `/my`، `/cancel`، `/help`. فقط برای OWNER و SYSTEM_ADMIN: `/backup`، `/health`.

### 5.3 ورود تاریخ و ساعت
- دکمه‌های سریع: «امروز»، «فردا»، «پس‌فردا»، «شنبهٔ آینده».
- سپس ساعت با دکمه‌های 10:00، 14:00، 18:00، 22:00، یا ورود دستی.
- ورود دستی این فرمت‌ها را می‌پذیرد: `1405/08/20`، `۱۴۰۵/۸/۲۰`، `1405/08/20 18:30`. سال اختیاری است و پیش‌فرض سال جاری است. ارقام فارسی و عربی پذیرفته می‌شوند.
- تاریخ گذشته رد می‌شود، مگر با تأیید صریح.

### 5.4 اعلان‌ها
| رویداد | گیرنده | زمان |
|---|---|---|
| تخصیص تسک / ساخت ریل | مسئول | فوری |
| رسیدن ورودی (رفع BLOCKED) | مسئول | فوری |
| تحویل | بررسی‌کنندهٔ مرحلهٔ جاری | فوری |
| تصمیم بررسی | مسئول (+ سازندهٔ ریل در تأیید نهایی) | فوری |
| آماده انتشار | `PUBLISH` | فوری |
| یادآوری ددلاین | مسئول | ساعت 10:00 روز ددلاین، و ۲ ساعت قبل از ددلاین |
| تأخیر | مسئول + `RECEIVE_OVERDUE_ALERTS` (علی) | یک بار هنگام عبور از ددلاین، سپس روزانه 10:00 در قالب یک پیام خلاصه |
| شروع و پایان تفویض | OWNER + نماینده | فوری |
| خطای سیستم | `SYSTEM_ADMIN` | فوری، حداکثر ۱ پیام در ۱۰ دقیقه برای هر نوع خطا |

**ساعات سکوت:** از 23:00 تا 09:00 تهران، همهٔ اعلان‌ها جز اعلان‌های فوری بررسی برای OWNER در صف می‌مانند و ساعت 09:00 ارسال می‌شوند. فوری‌بودن بررسی برای OWNER با setting قابل تغییر است و پیش‌فرض آن هم در صف ماندن است.

**ضد تکرار:** هر اعلان یک `dedupe_key` دارد، مثلاً `overdue:T-0042:2026-11-10`.

### 5.5 پیام‌های گروه (F12)
- **برنامهٔ امروز:** شنبه تا پنجشنبه ساعت 09:30 (روزها و ساعت در settings).
  - محتوا: تحویل‌های امروز به تفکیک نفر (کد + عنوان + ساعت) و انتشارهای برنامه‌ریزی‌شدهٔ امروز.
  - اگر چیزی نبود، پیام ارسال نمی‌شود.
  - **ممنوع:** تأخیرها، اصلاحات، و هر شمارش عملکرد فردی.
- **جمع‌بندی هفتگی:** پنجشنبه ساعت 18:00.
  - محتوا: تعداد خروجی‌های تأییدشده و منتشرشدهٔ هفته به تفکیک نوع (نه نفر)، و انتشارهای برنامه‌ریزی‌شدهٔ هفتهٔ بعد.

### 5.6 گزارش صبح شنبه (F13)
شنبه 09:00، خصوصی برای OWNER و کپی برای `RECEIVE_WEEKLY_REPORT`. همین گزارش با «📊 گزارش» هم در هر زمان قابل دریافت است:
1. **✅ منتظر تأیید من:** تعداد + لیست با دکمه.
2. **🔴 عقب‌افتاده و 🟠 در خطر** (ددلاین در ۲۴ ساعت آینده و هنوز تحویل نشده): کد، عنوان، مسئول، چند ساعت یا روز، و دلیل (مثلاً BLOCKED: منتظر عکس).
3. **🚀 انتشارهای هفتهٔ پیش رو:** هر ریل یا تسک با تاریخ انتشار + آمادگی (هر دو تسک تأیید شده؟ چه چیزی مانده؟).
4. **👥 بار کاری و کیفیت هر نفر:**
   - تسک‌های باز
   - ددلاین در این هفته
   - تحویل به‌موقع در ۷ روز گذشته (٪)
   - میانگین دور اصلاح در ۷ روز گذشته

   این سه بُعد عمداً جدا هستند: فعالیت (تعداد)، پیشرفت (به‌موقع‌بودن) و کیفیت (دور اصلاح).

---

## 6. معماری فنی

### 6.1 تکنولوژی‌ها
| بخش | انتخاب | دلیل | جایگزین رد‌شده |
|---|---|---|---|
| زبان | Python 3.12 | قابل نگهداری توسط تیم غیرتخصصی، اکوسیستم قوی ربات | Node.js |
| فریم‌ورک ربات | aiogram 3.x | async، FSM داخلی، پایدار و رایج | python-telegram-bot |
| دیتابیس v0 | SQLite در حالت WAL | ۶ کاربر؛ بکاپ با کپی یک فایل؛ صفر سرویس اضافه | PostgreSQL (برای V1) |
| ORM و migration | SQLAlchemy 2.x (async) + aiosqlite + Alembic | انتقال به PostgreSQL فقط با تغییر `DATABASE_URL` | — |
| زمان‌بندی | یک حلقهٔ tick هر ۶۰ ثانیه داخل همان process | DB تنها منبع حقیقت؛ بعد از restart چیزی گم نمی‌شود | APScheduler job store |
| تقویم | jdatetime + zoneinfo | تبدیل شمسی | — |
| تنظیمات | pydantic-settings (`.env`) | type-safe | — |
| تست | pytest + pytest-asyncio | — | — |
| اجرا | Docker + docker compose | قابل‌حمل روی سرور لیمینال | systemd |
| اتصال به تلگرام | **long polling** | بدون نیاز به پورت ورودی، دامنه یا SSL | webhook (V1) |

**Telegram Serverless بررسی و رد شد:** در مستندات فعلی‌اش زمان‌بندی وجود ندارد و endpointهایش از بیرون قابل فراخوانی نیستند. دوباره در V1 بررسی می‌شود.

### 6.2 لایه‌ها
```
bot/            ← فقط Telegram: routers، keyboards، FSM states، texts، formatters
services/       ← منطق کسب‌وکار، state machine، مجوزها، audit (بدون aiogram)
repositories/   ← دسترسی به DB
models/         ← SQLAlchemy models + enums
scheduler/      ← tick: یادآوری، تأخیر، outbox، recurrence، digest، گزارش، بکاپ
integrations/   ← telegram_archive (کپی در کانال آرشیو)، sync (interface + NoopSync)
core/           ← config، time و jalali، normalize فارسی، logging، errors
```
- **Outbox برای اعلان‌ها:** serviceها اعلان را مستقیم نمی‌فرستند. یک ردیف در `notifications` می‌نویسند. tick هر ۶۰ ثانیه ردیف‌های سررسیدشده را می‌فرستد، با رعایت ساعات سکوت و retry با backoff تا ۵ بار. اعلان‌های «فوری» بلافاصله بعد از commit با یک فراخوانی مستقیم flush می‌شوند.
- **Transaction:** هر عمل service یک transaction است: تغییر + audit + outbox با هم commit می‌شوند.
- **FSM:** `MemoryStorage` در v0 کافی است. با restart جریان‌های نیمه‌کاره از بین می‌روند و این قابل قبول است.
- **Rate limit تلگرام:** حداکثر حدود ۲۵ پیام در ثانیه به‌صورت سراسری، کافی برای ۶ نفر. خطای 429 با `retry_after` مدیریت می‌شود.

### 6.3 امنیت
- Whitelist بر اساس `telegram_id` و `is_active`. یک middleware برای همهٔ updateها.
- مجوز هر عمل در service چک می‌شود (`PermissionDenied` ← پیام فارسی).
- `callback_data` فقط شامل action + id است و هرگز به آن اعتماد نمی‌شود. وضعیت از DB دوباره خوانده می‌شود.
- کانال آرشیو خصوصی است و فقط ربات و OWNER عضو آن‌اند. بقیه فایل‌ها را فقط از طریق ربات می‌گیرند.
- توکن و IDها فقط در `.env`. لاگ‌ها هرگز توکن یا محتوای فایل را ثبت نمی‌کنند.
- privacy mode ربات روشن می‌ماند، چون ربات نیازی به خواندن پیام‌های گروه ندارد.
- در اولین اجرا، `OWNER_TELEGRAM_ID` باید تنظیم شده باشد، وگرنه برنامه با خطای واضح متوقف می‌شود.

### 6.4 مدیریت خطا و مانیتورینگ
- Error handler سراسری aiogram کارهای زیر را انجام می‌دهد:
  - لاگ با traceback
  - پیام «مشکلی پیش آمد، به مدیر سیستم اطلاع داده شد» به کاربر
  - هشدار rate-limited به `SYSTEM_ADMIN`
- لاگ ساختاریافته به stdout و فایل چرخشی `data/logs/` (حداکثر ۷ فایل ۱۰MB).
- `/health`: uptime، آخرین tick موفق، حجم DB، آخرین بکاپ، تعداد outbox معوق.
- **Heartbeat:** اگر tick بیش از ۵ دقیقه اجرا نشده باشد، در اولین فرصت به SYSTEM_ADMIN هشدار داده می‌شود.
- docker compose با `restart: unless-stopped`.

### 6.5 بکاپ (F16)
- **روزانه 04:00:** بکاپ آنلاین با `sqlite3 backup API` به `data/backups/eventum-YYYYMMDD.db`. ۱۴ نسخهٔ آخر نگه داشته می‌شود.
- **هفتگی (جمعه 04:30):** فایل بکاپ (gzip) به چت خصوصی SYSTEM_ADMINها فرستاده می‌شود. این نسخهٔ خارج از سرور است. اگر حجم بیش از ۴۵MB شد، هشدار داده و فقط محلی نگه داشته می‌شود.
- `/backup` همین کار را فوری انجام می‌دهد.
- **بازیابی:** توقف کانتینر، جایگزینی `data/eventum.db`، و اجرای دوباره. باید در `docs/OPERATIONS.md` نوشته شود.
- **محدودیت آگاهانه:** فایل‌ها (ویدیو و عکس) فقط در کانال آرشیو تلگرام هستند. بکاپ DB فقط ارجاع‌ها (`file_id`) را دارد. فایل‌های مستر باید جای دیگری هم نگه داشته شوند. حل کامل این مسئله در V1 است.

### 6.6 آمادگی برای Codecks
- ستون‌های nullable روی `tasks` و `content_items`: `external_source`، `external_id`، `external_synced_at`.
- `integrations/sync.py`: یک Protocol به اسم `TaskSyncPort` با متدهای `on_task_created/updated/status_changed` و پیاده‌سازی `NoopSync`. serviceها بعد از commit آن را صدا می‌زنند.
- Audit Log کامل است تا بعداً بشود تاریخچه را به Codecks backfill کرد.
- مدل وضعیت‌ها عمداً کوچک و قابل نگاشت نگه داشته شده.

---

## 7. مدل داده (SQLite / SQLAlchemy)

> همهٔ جدول‌ها: `id INTEGER PK`، `created_at`، `updated_at` (UTC). زمان‌ها `DateTime(timezone=True)` هستند.
> Foreign key روشن است (`PRAGMA foreign_keys=ON`).

```
users
  telegram_id BIGINT UNIQUE NOT NULL
  full_name TEXT, username TEXT NULL
  role ENUM(OWNER, MANAGER, MEMBER)
  capabilities JSON  -- ["CREATE_REEL","REVIEW_L1",...]
  is_active BOOL, deactivated_at NULL
  access_status ENUM(PENDING, APPROVED, REJECTED)

series
  name TEXT UNIQUE, kind ENUM(REEL, LONGFORM, CAMPAIGN, OTHER), is_active BOOL

content_items
  code TEXT UNIQUE            -- R-0001
  type ENUM(REEL), subtype ENUM(NORMAL, TRIAL)
  title TEXT, series_id FK NULL, created_by FK users
  planned_publish_at DATETIME NULL
  status ENUM(IN_PRODUCTION, READY_TO_PUBLISH, PUBLISHED, CANCELLED)
  photos_due_at DATETIME NULL, photos_delivered_at NULL, photos_late BOOL
  published_at NULL, published_by FK NULL, publish_links JSON
  external_source, external_id, external_synced_at  -- NULL

tasks
  code TEXT UNIQUE            -- T-0001
  content_item_id FK NULL
  kind ENUM(EDIT, COVER, GENERIC)
  title TEXT, description TEXT NULL
  series_id FK NULL
  assignee_id FK users, created_by FK users
  status ENUM(BLOCKED, TODO, IN_PROGRESS, IN_REVIEW, CHANGES_REQUESTED, APPROVED, CANCELLED)
  review_stage ENUM(L1, FINAL) NULL
  approval_chain ENUM(NONE, FINAL, L1_FINAL)
  blocked_reason TEXT NULL
  due_at DATETIME NULL
  first_submitted_at NULL, completed_at NULL
  revision_round INT DEFAULT 0
  recurrence_id FK NULL, recurrence_date DATE NULL   -- UNIQUE(recurrence_id, recurrence_date)
  external_source, external_id, external_synced_at
  INDEX(assignee_id, status), INDEX(status, due_at)

task_inputs
  task_id FK NULL, content_item_id FK NULL
  kind ENUM(TIMECODES, COVER_TEXT, COVER_PHOTOS, BRIEF)
  text TEXT NULL, attachments JSON   -- [{file_id, file_unique_id, type, archive_message_id, size}]
  provided_by FK users, provided_at

submissions
  task_id FK, version INT   -- UNIQUE(task_id, version)
  submitted_by FK, note TEXT NULL
  attachments JSON, links JSON
  submitted_at

reviews
  submission_id FK, stage ENUM(L1, FINAL)
  reviewer_id FK, decision ENUM(APPROVED, CHANGES_REQUESTED)
  note_text TEXT NULL, note_attachments JSON
  delegated BOOL, decided_at

outputs
  task_id FK UNIQUE, submission_id FK, content_item_id FK NULL
  output_type ENUM(REEL_VIDEO, REEL_COVER, OTHER)
  title TEXT, series_id FK NULL, owner_id FK users (مسئول)
  approved_at, search_text TEXT   -- نرمال‌شده
  INDEX(approved_at)

delegations
  from_user_id FK, to_user_id FK, starts_at, ends_at, revoked_at NULL

recurrences
  title, description, assignee_id FK, series_id FK NULL
  approval_chain, rule ENUM(DAILY, WEEKDAYS), weekdays JSON  -- [0..6], 0=شنبه
  create_time TIME, due_time TIME, is_active BOOL, created_by FK

notifications            -- outbox
  chat_id BIGINT, kind TEXT, payload JSON
  dedupe_key TEXT UNIQUE, urgent BOOL
  scheduled_at, sent_at NULL, attempts INT, last_error TEXT NULL
  status ENUM(PENDING, SENT, FAILED, CANCELLED)
  INDEX(status, scheduled_at)

audit_events
  actor_id FK NULL (NULL = system), action TEXT   -- e.g. task.created, task.submitted, review.approved
  entity_type TEXT, entity_id INT, data JSON (before/after/extra), at
  INDEX(entity_type, entity_id)

settings
  key TEXT PK, value JSON
```

**Settings پیش‌فرض** (seed در migration اول):
`timezone=Asia/Tehran`، `quiet_hours=["23:00","09:00"]`، `daily_digest={days:[0..5], time:"09:30"}`، `weekly_summary={day:5, time:"18:00"}`، `saturday_report_time="09:00"`، `reminder_time="10:00"`، `reminder_before_hours=2`، `reel_offsets={photos_after_create_h:4, edit_before_publish_h:6, cover_before_publish_h:6}`، `default_due_time="18:00"`، `revision_returns_to_requesting_stage=true`، `owner_review_urgent_in_quiet_hours=false`.

**Seed:** سری‌های «ریل روزانه»، «Trial Reels»، «PURPLE ZONE»، «سری WEEX»، «دوئل تریدرها»، «ERANTE».

---

## 8. ساختار پروژه
```
eventum-hq/
├─ CLAUDE.md
├─ README.md                  ← راه‌اندازی محلی و Docker (فارسی)
├─ docs/
│  ├─ HANDOFF-v0.md           ← همین سند
│  └─ OPERATIONS.md           ← استقرار، به‌روزرسانی، بکاپ و بازیابی (در M6)
├─ .env.example
├─ pyproject.toml
├─ Dockerfile
├─ docker-compose.yml
├─ alembic.ini
├─ migrations/
├─ src/eventum_hq/
│  ├─ __main__.py             ← راه‌اندازی bot + scheduler
│  ├─ core/ (config.py, timeutil.py, jalali.py, normalize.py, logging.py, errors.py)
│  ├─ models/
│  ├─ repositories/
│  ├─ services/ (users.py, permissions.py, tasks.py, reels.py, submissions.py,
│  │             reviews.py, delegations.py, outputs.py, recurrences.py,
│  │             notifications.py, reports.py, audit.py, backup.py)
│  ├─ scheduler/ (tick.py, jobs/*.py)
│  ├─ integrations/ (telegram_archive.py, sync.py)
│  └─ bot/ (routers/*.py, keyboards/*.py, states.py, texts.py, formatters.py, middlewares.py)
├─ tests/ (unit/, integration/, conftest.py)
└─ data/                      ← volume؛ git-ignored (eventum.db, backups/, logs/)
```

**`.env.example`:**
```
BOT_TOKEN=
OWNER_TELEGRAM_ID=
TEAM_GROUP_ID=
ARCHIVE_CHANNEL_ID=
DATABASE_URL=sqlite+aiosqlite:///data/eventum.db
TELEGRAM_PROXY=            # فقط توسعهٔ محلی در ایران، مثلاً socks5://127.0.0.1:10808
LOG_LEVEL=INFO
```

---

## 9. Milestoneها

تخمین بر اساس ۴ ساعت در روز با Claude Code است. بعد از هر Milestone: تست‌ها سبز، دمو، و تأیید باربد یا فرید.

| M | محتوا | تخمین | معیار تکمیل |
|---|---|---|---|
| **M0 — پایه** | ساختار پروژه، config، logging، DB + Alembic + seed، middleware whitelist، `/start` و جریان درخواست دسترسی، منوی خالی بر اساس capability، Docker | 4–6h | کاربر ناشناس رد می‌شود و درخواستش به OWNER می‌رسد؛ OWNER تأیید می‌کند و کاربر منو را می‌بیند؛ اجرا هم محلی و هم با `docker compose up` |
| **M1 — تسک عمومی** | ساخت تسک (FSM با ورود تاریخ شمسی)، «کارهای من»، «همهٔ کارها» با فیلتر، کارت تسک، شروع، لغو، ویرایش ددلاین و مسئول، audit، دسترسی با کد `T-xxxx` | 8–10h | فرید یا علی تسک می‌سازد، مسئول پیام فوری می‌گیرد، تغییرات در audit ثبت می‌شود |
| **M2 — تحویل و بررسی** | کانال آرشیو، Submission با نسخه، زنجیره‌های `NONE/FINAL/L1_FINAL`، اصلاح با یادداشت چندپیامی، قفل همزمانی، تفویض، ساخت Output | 10–12h | سناریوی کامل: تحویل، اصلاح، تحویل v2، تأیید، و ظاهرشدن در Output؛ تفویض مرحلهٔ FINAL را حذف می‌کند |
| **M3 — جریان ریل** | ساخت ریل توسط امین، دو تسک، BLOCKED و تحویل عکس توسط سینا، ددلاین‌های نسبی، `READY_TO_PUBLISH`، ثبت انتشار توسط باربد، لغو ریل | 8–10h | یک ریل واقعی از ساخت تا انتشار در ربات طی شود |
| **🎯 دمو برای لیمینال** | بعد از M3 (حدود ۸ تا ۱۰ روز کاری) | — | — |
| **M4 — کتابخانه** | لیست، فیلتر، جست‌وجوی نرمال‌شده، صفحه‌بندی، ارسال فایل از آرشیو | 4–6h | هر خروجی تأییدشده با جست‌وجوی بخشی از عنوان پیدا و دریافت می‌شود |
| **M5 — زمان‌بندی و گزارش‌ها** | tick، outbox، ساعات سکوت، یادآوری، تأخیر، Recurrence، برنامهٔ امروز، جمع‌بندی هفتگی، گزارش شنبه، بکاپ روزانه و هفتگی، heartbeat | 10–12h | همهٔ زمان‌بندی‌ها با «ساعت جعلی» در تست‌ها پوشش داده شوند؛ یک هفتهٔ واقعی اجرا شود |
| **M6 — آماده‌سازی و پایلوت** | Offboarding، `/health`، `/backup`، error handler و هشدار، `OPERATIONS.md`، استقرار روی سرور، پایلوت ۷ روزه با تیم | 6–8h | چک‌لیست بخش ۱۱ کامل؛ تیم یک هفته ریل‌ها و تسک‌ها را فقط در ربات مدیریت کند |

**جمع:** حدود ۵۰ تا ۶۴ ساعت، یعنی ۳ تا ۴ هفته با ۴ ساعت در روز.

---

## 10. تست‌ها

### 10.1 خودکار (pytest)
تست‌های واحد روی serviceها با SQLite در حافظه و یک `Clock` قابل تزریق. **هیچ فراخوانی واقعی تلگرام در تست‌ها نیست.** `TelegramArchive` و ارسال پیام mock می‌شوند.

حداقل پوشش:
- **State machine:** هر انتقال مجاز و هر انتقال غیرمجاز (باید خطا بدهد).
- **ماتریس مجوز بخش ۳.۲:** یک تست پارامتری برای هر خانه.
- **زنجیره‌های تأیید:** `NONE`، `FINAL`، `L1_FINAL`؛ مسیر بعد از اصلاح در هر مرحله؛ تفویض فعال، منقضی و لغوشده.
- **جریان ریل:** ساخت دو تسک؛ BLOCKED تا رسیدن عکس؛ `photos_late`؛ `READY_TO_PUBLISH` فقط وقتی هر دو تأیید شده‌اند؛ لغو.
- **به‌موقع‌بودن:** `first_submitted_at` در برابر `due_at`؛ زمان صف بررسی تأخیر مسئول حساب نمی‌شود.
- **jalali و normalize:** ورود تاریخ با ارقام فارسی، بدون سال، با ساعت، تاریخ نامعتبر؛ نرمال‌سازی ی و ک و نیم‌فاصله.
- **Outbox:** ساعات سکوت، dedupe، retry، و فوری در برابر صف‌شده.
- **Recurrence:** ساخت idempotent، روزهای هفته با شنبه = 0.
- **گزارش‌ها:** محاسبهٔ عقب‌افتاده، در خطر، ٪ به‌موقع، میانگین دور اصلاح.
- **Offboarding:** انتقال تسک‌ها؛ تاریخچه دست‌نخورده می‌ماند.

### 10.2 تست دستی (در پایان هر Milestone)
Claude Code برای هر Milestone یک چک‌لیست سناریو به فارسی تحویل می‌دهد. این چک‌لیست با دو یا سه اکانت تلگرام واقعی و یک گروه و کانال تست اجرا می‌شود. **ربات تست جدا** (مثلاً `EventumHQTestBot`) با `.env` جدا اجرا شود و روی ربات اصلی تست نشود.

---

## 11. استقرار

### 11.1 توسعهٔ محلی (Windows)
- Python 3.12، `python -m venv .venv`، `pip install -e .[dev]`، کپی `.env.example` به `.env`.
- دسترسی به `api.telegram.org` از ایران نیاز به VPN یا proxy دارد. `TELEGRAM_PROXY` را تنظیم کن (aiogram با `aiohttp-socks`).
- اجرا: `python -m eventum_hq`. تست: `pytest`.

### 11.2 Production (سرور لیمینال)
**نیاز از لیمینال:**
- Linux (Ubuntu 22.04 یا 24.04)
- Docker و docker compose
- 1 vCPU، 1GB RAM، حدود 10GB دیسک
- دسترسی خروجی HTTPS به `api.telegram.org`
- دسترسی SSH برای باربد و فرید

**هیچ پورت ورودی لازم نیست** (long polling)، پس اثر امنیتی روی سرور لیمینال حداقل است.

**اجرا:**
```
git clone … && cd eventum-hq
cp .env.example .env   # پرکردن مقادیر
docker compose up -d --build
```
- migrationها هنگام startup خودکار اجرا می‌شوند (`alembic upgrade head`).
- به‌روزرسانی: `git pull && docker compose up -d --build`.

### 11.3 چک‌لیست قبل از پایلوت
- [ ] ربات اصلی و ربات تست جدا هستند
- [ ] کانال آرشیو خصوصی ساخته شده و ربات در آن ادمین است
- [ ] ربات به گروه Eventum Space اضافه شده، privacy mode روشن است و `TEAM_GROUP_ID` درست است
- [ ] هر ۶ نفر وارد شده‌اند و capabilityها مطابق بخش ۳.۱ تنظیم شده‌اند
- [ ] یک بکاپ دستی گرفته و بازیابی آن یک بار تست شده
- [ ] هشدار خطا به SYSTEM_ADMIN می‌رسد (با یک خطای عمدی تست شود)
- [ ] `/health` سالم است و tick کار می‌کند
- [ ] تیم یک راهنمای یک‌صفحه‌ای فارسی (پیام `/help`) دیده است

---

## 12. تصمیم‌های پیش‌فرض که بعد از پایلوت بازبینی می‌شوند

| تصمیم | پیش‌فرض v0 |
|---|---|
| تحویل مجدد بعد از اصلاح فرید | مستقیم به فرید |
| روزهای «برنامهٔ امروز» | شنبه تا پنجشنبه |
| فاصله‌های ددلاین ریل | عکس: ساخت + ۴ ساعت · ادیت و کاور: انتشار − ۶ ساعت |
| Trial Reel | همان جریان ریل، با `subtype=TRIAL` |
| امین تسک عمومی بسازد؟ | خیر (با دادن `CREATE_TASK` ممکن می‌شود) |
| علی کپی گزارش شنبه بگیرد؟ | بله |
| ساعات سکوت | ۲۳:۰۰ تا ۰۹:۰۰ |
