"""إنشاء رموز التحقق وإرسالها بالبريد الحقيقي."""
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from .models import EmailCode

log = logging.getLogger("core")

SUBJECTS = {
    EmailCode.VERIFY: "رمز تأكيد حسابكِ في أكاديمية الرياضة الرقمية",
    EmailCode.RESET: "رمز إعادة تعيين كلمة المرور — أكاديمية الرياضة الرقمية",
}


class TooSoon(Exception):
    def __init__(self, wait):
        self.wait = wait


def issue_code(user, purpose):
    """يلغي الرموز السابقة، ينشئ رمزاً جديداً من 6 أرقام ويرسله. يرفع TooSoon عند الطلب المتكرر."""
    last = EmailCode.objects.filter(user=user, purpose=purpose).order_by("-created_at").first()
    if last:
        elapsed = (timezone.now() - last.created_at).total_seconds()
        if elapsed < settings.CODE_RESEND_SECONDS:
            raise TooSoon(int(settings.CODE_RESEND_SECONDS - elapsed) + 1)

    EmailCode.objects.filter(user=user, purpose=purpose, used=False).update(used=True)
    code = f"{secrets.randbelow(900000) + 100000}"
    EmailCode.objects.create(
        user=user,
        purpose=purpose,
        code_hash=EmailCode.hash(code),
        expires_at=timezone.now() + timedelta(minutes=settings.CODE_TTL_MINUTES),
    )

    ctx = {"name": user.first_name or user.email, "code": code, "purpose": purpose, "minutes": settings.CODE_TTL_MINUTES}
    text = render_to_string("emails/code.txt", ctx)
    html = render_to_string("emails/code.html", ctx)
    msg = EmailMultiAlternatives(SUBJECTS[purpose], text, settings.DEFAULT_FROM_EMAIL, [user.email])
    msg.attach_alternative(html, "text/html")
    msg.send(fail_silently=False)
    log.info("Sent %s code to %s", purpose, user.email)


def check_code(user, purpose, code):
    """يعيد None عند النجاح أو رسالة خطأ بالعربية."""
    rec = EmailCode.objects.filter(user=user, purpose=purpose, used=False).order_by("-created_at").first()
    if not rec:
        return "لا يوجد رمز صالح، اطلبي رمزاً جديداً."
    if rec.expired:
        return "انتهت صلاحية الرمز، اطلبي رمزاً جديداً."
    if rec.attempts >= settings.CODE_MAX_ATTEMPTS:
        return "تجاوزتِ عدد المحاولات المسموح، اطلبي رمزاً جديداً."
    if not secrets.compare_digest(rec.code_hash, EmailCode.hash((code or "").strip())):
        rec.attempts += 1
        rec.save(update_fields=["attempts"])
        return "رمز التحقق غير صحيح."
    rec.used = True
    rec.save(update_fields=["used"])
    return None
