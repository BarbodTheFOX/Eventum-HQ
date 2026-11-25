# Eventum HQ

ربات تلگرامی مدیریت کار و خروجی‌های تیم Eventum Space.

### سیاست تأیید خروجی‌ها — ۱۴۰۵/۰۹/۰۴

- باربد مدیر و مالک فنی است؛ فرید با نقش داخلی `DIRECTOR` و عنوان «فاندر» تأیید نهایی را انجام می‌دهد.
- همهٔ کارهای جدید، از جمله تکرارشونده‌ها، تأیید فاندر لازم دارند. گزینهٔ بدون تأیید حذف شده؛ کارهای باز قدیمی با زنجیرهٔ `NONE` نیز باید تحویل و بررسی شوند.
- بررسی مرحلهٔ اول فقط کار را به صف فاندر منتقل می‌کند. مالک و نمایندهٔ تفویض نمی‌توانند تأیید نهایی بدهند؛ تفویض از منوی تیم حذف شده است.
- در نبود فاندر فعال، کار در صف تأیید باقی می‌ماند و به مالک منتقل نمی‌شود. فاندر پس از فعال‌شدن می‌تواند صف را ببیند.
- سوابق پایان‌یافتهٔ قبلی بازنویسی نمی‌شوند. عضویت فرید باید توسط باربد با نقش «فاندر» تأیید شود؛ نقش بر اساس نام نمایشی تشخیص داده نمی‌شود.

سند مرجع: [`docs/HANDOFF-v0.md`](docs/HANDOFF-v0.md).

> ⚠️ برای توسعه و تست همیشه از **ربات تست** (مثلاً `@EventumHQTestBot`) استفاده کنید، نه ربات اصلی `@EventumHQBot`.

---

## راه‌اندازی محلی (Windows)

پیش‌نیاز: Python 3.12 و git.

همهٔ دستورها را در PowerShell و داخل پوشهٔ پروژه اجرا کنید.

**۱. ساخت محیط مجازی (فقط بار اول):**
```powershell
py -3.12 -m venv .venv
```

**۲. فعال‌کردن محیط مجازی (هر بار که PowerShell جدید باز می‌کنید):**
```powershell
.\.venv\Scripts\Activate.ps1
```
اگر خطای «running scripts is disabled» دیدید، یک بار این را بزنید و دوباره امتحان کنید:
```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

**۳. نصب وابستگی‌ها (بار اول و هر وقت `pyproject.toml` عوض شد):**
```powershell
pip install -e .[dev]
```

**۴. ساخت فایل تنظیمات (فقط بار اول):**
```powershell
Copy-Item .env.example .env
notepad .env
```
مقادیر را پر کنید:
| کلید | مقدار |
|---|---|
| `BOT_TOKEN` | توکن ربات **تست** از @BotFather |
| `OWNER_TELEGRAM_ID` | شناسهٔ عددی تلگرام OWNER (از @userinfobot) |
| `TELEGRAM_PROXY` | اگر VPN شما proxy محلی دارد، مثلاً `socks5://127.0.0.1:10808`. در حالت TUN خالی بماند. |

**۵. اجرا:**
```powershell
python -m eventum_hq
```
برای توقف: `Ctrl+C`.

**۶. اجرای تست‌ها:**
```powershell
pytest
```

---

## اجرا با Docker

```bash
cp .env.example .env    # و مقادیر را پر کنید
docker compose up -d --build
docker compose logs -f
```
- migrationها هنگام شروع خودکار اجرا می‌شوند.
- دیتابیس، بکاپ‌ها و لاگ‌ها در پوشهٔ `data/` می‌مانند.
- روی سرور (بدون فیلتر) `TELEGRAM_PROXY` را خالی بگذارید.
- در Docker Desktop روی ویندوز، `127.0.0.1` به خود کانتینر اشاره می‌کند؛ به‌جایش از `socks5://host.docker.internal:10808` استفاده کنید و در VPN گزینهٔ «Allow connections from LAN» را روشن کنید.
- به‌روزرسانی: `git pull && docker compose up -d --build`.
- راهنمای کامل سرور، بکاپ و بازیابی: [`docs/OPERATIONS.md`](docs/OPERATIONS.md).

---

## ساختار پروژه

```
src/eventum_hq/
  core/          config، db، logging، زمان، خطاها، migrate
  models/        مدل‌های SQLAlchemy و enumها
  repositories/  دسترسی به دیتابیس
  services/      منطق کسب‌وکار (بدون aiogram)
  bot/           فقط تلگرام: routers، keyboards، texts، middlewares، outbox
  scheduler/     tick هر ۶۰ ثانیه: یادآوری، تأخیر، گزارش، بکاپ
  integrations/  کانال آرشیو تلگرام، آمادگی Codecks
migrations/      Alembic
tests/           unit/ و integration/
data/            دیتابیس، بکاپ و لاگ (در git نیست)
```

## migration جدید
```powershell
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```
