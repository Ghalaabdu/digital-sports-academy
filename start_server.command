#!/bin/bash
# تشغيل المنصة على جهازك — اتركي النافذة مفتوحة طوال الاستخدام
cd "$(dirname "$0")" || exit 1
source .venv/bin/activate
python manage.py migrate --noinput >/dev/null
echo "🚀 المنصة تعمل الآن على: http://127.0.0.1:8000"
echo "   لوحة الإدارة:        http://127.0.0.1:8000/admin"
echo "   لإيقافها: أغلقي هذه النافذة"
(sleep 2; open "http://127.0.0.1:8000") &
python manage.py runserver 127.0.0.1:8000
