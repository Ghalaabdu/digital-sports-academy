"""قواعد التحقق المشتركة: البريد الإلكتروني وكلمة المرور (مطابقة لقواعد الواجهة)."""
import re

from django.core.exceptions import ValidationError

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")
UPPER_RE = re.compile(r"[A-Z]")


def normalize_email(value: str) -> str:
    return (value or "").strip().lower()


def email_error(email: str):
    if not EMAIL_RE.match(email or ""):
        return "صيغة البريد الإلكتروني غير صحيحة (مثال: example@gmail.com)."
    return None


def password_error(password: str):
    password = password or ""
    if len(password) < 8:
        return "كلمة المرور يجب ألا تقل عن 8 أحرف."
    if not UPPER_RE.search(password):
        return "كلمة المرور يجب أن تحتوي على حرف إنجليزي كبير (Capital) واحد على الأقل."
    return None


class UppercaseValidator:
    """يُستخدم أيضاً في لوحة الإدارة عند تغيير كلمات المرور."""

    def validate(self, password, user=None):
        if not UPPER_RE.search(password or ""):
            raise ValidationError("كلمة المرور يجب أن تحتوي على حرف إنجليزي كبير واحد على الأقل.", code="no_upper")

    def get_help_text(self):
        return "يجب أن تحتوي كلمة المرور على حرف إنجليزي كبير واحد على الأقل."
