#!/bin/bash
# إنشاء حساب المعلمة المسؤولة عن لوحة الإدارة
cd "$(dirname "$0")" || exit 1
source .venv/bin/activate
echo "اكتبي بريدكِ الإلكتروني في خانة Username وفي خانة Email، ثم كلمة مرور (لن تظهر أثناء الكتابة)."
python manage.py createsuperuser
echo "✅ تم. يمكنكِ إغلاق النافذة."
