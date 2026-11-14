#!/bin/bash
# ================================================================
#  أكاديمية الرياضة الرقمية — تثبيت واختبار تلقائي على الماك
#  افتحيه بالنقر المزدوج من Finder. النتائج تُحفظ في setup_log.txt
# ================================================================
cd "$(dirname "$0")" || exit 1
LOG="$PWD/setup_log.txt"
{
  echo "== START $(date)"
  PY=""
  for c in python3.13 python3.12 python3.11 python3; do
    if command -v "$c" >/dev/null 2>&1; then PY="$(command -v $c)"; break; fi
  done
  echo "python: $PY ($($PY --version 2>&1))"
  [ -d .venv ] || "$PY" -m venv .venv
  source .venv/bin/activate
  python -m pip install -q --upgrade pip
  echo "== pip install"
  pip install -q -r requirements.txt && echo "pip OK"
  if [ ! -f .env ]; then
    sed -e 's/^DB_ENGINE=postgres/DB_ENGINE=sqlite/' .env.example > .env
    echo "created .env (sqlite for local testing)"
  fi
  echo "== makemigrations";  python manage.py makemigrations core
  echo "== migrate";         python manage.py migrate --noinput
  echo "== seed";            python manage.py seed_knowledge
  echo "== check";           python manage.py check
  echo "== tests";           python manage.py test core -v 2
  echo "== EXIT $?"
  echo "== END $(date)"
} > "$LOG" 2>&1
echo ""
echo "✅ انتهى. النتائج محفوظة في: $LOG"
echo "يمكنكِ إغلاق هذه النافذة."
