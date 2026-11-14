#!/bin/bash
# اختبار شامل: الاختبارات الآلية + إرسال بريد حقيقي + سؤال حقيقي للمدربة الذكية
cd "$(dirname "$0")" || exit 1
source .venv/bin/activate
{
echo "== UNIT TESTS"; python manage.py test core 2>&1 | tail -4
python -u - <<'PY'
import os, time, logging, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
logging.getLogger("core").setLevel(logging.WARNING)
from django.conf import settings
from django.core.mail import send_mail
from django.contrib.auth import get_user_model
from core.gemini import ask_coach, model_chain
print("== EMAIL")
try:
    send_mail("اختبار — أكاديمية الرياضة الرقمية", "رسالة اختبار من المنصة ✅", settings.DEFAULT_FROM_EMAIL, [settings.EMAIL_HOST_USER])
    print("EMAIL: OK")
except Exception as e:
    print("EMAIL: FAIL", type(e).__name__, str(e)[:200])
print("== GEMINI chain:", model_chain())
u, _ = get_user_model().objects.get_or_create(username="connection-test@local", defaults={"email": "connection-test@local"})
t = time.time()
reply, live = ask_coach(u, "كيف أؤدي تمرين السكوات بطريقة صحيحة؟")
print(f"GEMINI live={live} ({time.time()-t:.1f}s)")
print(reply[:600])
u.delete()
PY
echo "== END"
} > connections_log.txt 2>&1
echo "✅ انتهى"
