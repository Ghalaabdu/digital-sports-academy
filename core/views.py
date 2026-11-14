"""
واجهات API للمنصة. كل الردود JSON بالشكل:
  {"ok": true, ...}  أو  {"ok": false, "error": "رسالة بالعربية", "code": "..."}
الطلبات من الواجهة ترسل ترويسة X-CSRFToken (عدا مسار اختصار الآيفون الذي يستخدم رمزاً خاصاً).
"""
import json
import logging
from datetime import date, timedelta
from functools import wraps

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.core.files.images import get_image_dimensions
from django.db import IntegrityError, transaction
from django.db.models import Count, Sum
from django.http import FileResponse, Http404, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from . import emails
from .gemini import ask_coach
from .models import (
    CLASS_CHOICES, LAB_SKILLS, QR_STATIONS, ChatLog, EmailCode, LabResult, Profile,
    QRCompletion, QuizAttempt, StepEntry,
)
from .validators import email_error, normalize_email, password_error

User = get_user_model()
log = logging.getLogger("core")

CLASS_NAMES = [c[0] for c in CLASS_CHOICES]
SKILL_KEYS = [s[0] for s in LAB_SKILLS]


# ---------------------------------------------------------------- helpers
def ok(status=200, **data):
    return JsonResponse({"ok": True, **data}, status=status, json_dumps_params={"ensure_ascii": False})


def err(message, status=400, code="error", **extra):
    return JsonResponse({"ok": False, "error": message, "code": code, **extra}, status=status,
                        json_dumps_params={"ensure_ascii": False})


def payload(request):
    if request.content_type == "application/json":
        try:
            return json.loads(request.body or b"{}")
        except json.JSONDecodeError:
            return {}
    return request.POST


def api_login_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return err("يجب تسجيل الدخول أولاً.", 401, "auth_required")
        if not request.user.profile.email_verified:
            return err("يجب تأكيد البريد الإلكتروني أولاً.", 403, "unverified")
        return view(request, *args, **kwargs)
    return wrapper


def find_user(email):
    return User.objects.filter(username=email).select_related("profile").first()


def to_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def send_code(user, purpose):
    """يرسل الرمز ويعيد None، أو رد خطأ جاهز."""
    try:
        emails.issue_code(user, purpose)
    except emails.TooSoon as e:
        return err(f"انتظري {e.wait} ثانية قبل طلب رمز جديد.", 429, "too_soon", wait=e.wait)
    except Exception:
        log.exception("Email sending failed")
        return err("تعذّر إرسال البريد الآن، حاولي بعد قليل.", 502, "email_failed")
    return None


def student_rank(profile):
    return Profile.objects.filter(email_verified=True, user__is_staff=False,
                                  total_steps__gt=profile.total_steps).count() + 1


def me_payload(user):
    p = user.profile
    lab = [{"skill": r.skill, "before": r.before, "after": r.after, "imp": r.improvement,
            "note": r.note, "date": r.created_at.date().isoformat()} for r in user.lab_results.all()[:10]]
    return {
        "name": user.first_name or user.email,
        "email": user.email,
        "class_name": p.class_name,
        "steps": p.total_steps,
        "qr_points": p.qr_challenge_points,
        "qr_done": list(user.qr_completions.values_list("station_id", flat=True)),
        "quiz_best": p.quiz_best,
        "lab": lab,
        "chats": user.chat_logs.count(),
        "rank": student_rank(p),
        "is_staff": user.is_staff,
    }


# ---------------------------------------------------------------- الصفحة الرئيسية
@ensure_csrf_cookie
@require_GET
def index(request):
    path = settings.BASE_DIR / "frontend" / "index.html"
    if not path.exists():
        raise Http404("frontend/index.html غير موجود")
    return FileResponse(open(path, "rb"), content_type="text/html; charset=utf-8")


# ---------------------------------------------------------------- المصادقة
@require_POST
def register(request):
    data = payload(request)
    name = (data.get("name") or "").strip()[:150]
    email = normalize_email(data.get("email"))
    password = data.get("password") or ""

    if len(name) < 3:
        return err("أدخلي الاسم الكامل.")
    if (e := email_error(email)) or (e := password_error(password)):
        return err(e)

    user = find_user(email)
    if user and user.profile.email_verified:
        return err("هذا البريد مسجّل مسبقاً، يمكنكِ تسجيل الدخول.", 409, "exists")

    with transaction.atomic():
        if user:  # حساب سابق لم يُؤكَّد: نحدّث بياناته
            user.first_name = name
            user.set_password(password)
            user.save()
        else:
            user = User.objects.create_user(username=email, email=email, password=password, first_name=name)

    failure = send_code(user, EmailCode.VERIFY)
    if failure and failure.status_code != 429:
        return failure
    return ok(201, needs_verification=True, email=email)


@require_POST
def verify_email(request):
    data = payload(request)
    email = normalize_email(data.get("email"))
    user = find_user(email)
    if not user:
        return err("هذا البريد غير مسجّل.", 404, "not_found")
    if user.profile.email_verified:
        login(request, user)
        return ok(user=me_payload(user))
    if (e := emails.check_code(user, EmailCode.VERIFY, data.get("code"))):
        return err(e, 400, "bad_code")
    user.profile.email_verified = True
    user.profile.save(update_fields=["email_verified"])
    login(request, user)
    return ok(user=me_payload(user))


@require_POST
def resend_code(request):
    data = payload(request)
    email = normalize_email(data.get("email"))
    purpose = EmailCode.RESET if data.get("purpose") == "reset" else EmailCode.VERIFY
    user = find_user(email)
    if not user:
        return err("هذا البريد غير مسجّل.", 404, "not_found")
    if purpose == EmailCode.VERIFY and user.profile.email_verified:
        return err("البريد مؤكَّد مسبقاً، يمكنكِ تسجيل الدخول.", 400, "already_verified")
    if (failure := send_code(user, purpose)):
        return failure
    return ok()


@require_POST
def login_view(request):
    data = payload(request)
    email = normalize_email(data.get("email"))
    password = data.get("password") or ""
    if (e := email_error(email)):
        return err(e)
    if not password:
        return err("أدخلي كلمة المرور.")
    user = find_user(email)
    if not user:
        return err("هذا البريد غير مسجّل في المنصة. يمكنكِ إنشاء حساب جديد.", 404, "not_found")
    if authenticate(request, username=email, password=password) is None:
        return err("كلمة المرور غير صحيحة، حاولي مرة أخرى.", 401, "wrong_password")
    if not user.profile.email_verified:
        send_code(user, EmailCode.VERIFY)  # نتجاهل "انتظري" هنا
        return err("حسابكِ يحتاج إلى تأكيد البريد. أرسلنا لكِ رمز التحقق.", 403, "unverified", email=email)
    login(request, user)
    return ok(user=me_payload(user))


@require_POST
def logout_view(request):
    logout(request)
    return ok()


@require_POST
def forgot_password(request):
    email = normalize_email(payload(request).get("email"))
    if (e := email_error(email)):
        return err(e)
    user = find_user(email)
    if not user:
        return err("لا يوجد حساب مسجّل بهذا البريد.", 404, "not_found")
    if (failure := send_code(user, EmailCode.RESET)):
        return failure
    return ok(email=email)


@require_POST
def reset_password(request):
    data = payload(request)
    email = normalize_email(data.get("email"))
    password = data.get("password") or ""
    user = find_user(email)
    if not user:
        return err("لا يوجد حساب مسجّل بهذا البريد.", 404, "not_found")
    if (e := password_error(password)):
        return err(e)
    if (e := emails.check_code(user, EmailCode.RESET, data.get("code"))):
        return err(e, 400, "bad_code")
    user.set_password(password)
    user.save()
    # من يستلم رمز البريد يملك البريد، فنعتبره مؤكَّداً
    if not user.profile.email_verified:
        user.profile.email_verified = True
        user.profile.save(update_fields=["email_verified"])
    return ok()


# ---------------------------------------------------------------- الملف الشخصي
@require_GET
def me(request):
    u = request.user
    if not u.is_authenticated or not u.profile.email_verified:
        return ok(authenticated=False)
    return ok(authenticated=True, user=me_payload(u))


@require_POST
@api_login_required
def update_profile(request):
    cls = (payload(request).get("class_name") or "").strip()
    if cls not in CLASS_NAMES:
        return err("الفصل غير صحيح.")
    p = request.user.profile
    p.class_name = cls
    p.save(update_fields=["class_name"])
    return ok(user=me_payload(request.user))


# ---------------------------------------------------------------- الخطوات
def week_series(user):
    today = timezone.localdate()
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    rows = (user.step_entries.filter(status=StepEntry.APPROVED, date__gte=days[0])
            .values("date").annotate(s=Sum("steps")))
    by_day = {r["date"]: r["s"] for r in rows}
    return [{"date": d.isoformat(), "steps": by_day.get(d, 0)} for d in days]


@api_login_required
def steps(request):
    user = request.user
    if request.method == "GET":
        recent = [{"id": e.id, "date": e.date.isoformat(), "steps": e.steps, "source": e.source,
                   "status": e.status, "status_label": e.get_status_display()}
                  for e in user.step_entries.all()[:10]]
        return ok(week=week_series(user), recent=recent, total=user.profile.total_steps,
                  require_proof=settings.STEPS_REQUIRE_PROOF)
    if request.method != "POST":
        return err("طريقة غير مدعومة.", 405)

    n = to_int(request.POST.get("steps"))
    if not n or n < 1 or n > settings.STEPS_MAX_PER_ENTRY:
        return err(f"أدخلي عدداً صحيحاً بين 1 و {settings.STEPS_MAX_PER_ENTRY:,}.")
    try:
        day = date.fromisoformat(request.POST.get("date") or "")
    except ValueError:
        return err("التاريخ غير صحيح.")
    today = timezone.localdate()
    if day > today or day < today - timedelta(days=6):
        return err("يمكن تسجيل خطوات آخر 7 أيام فقط.")

    proof = request.FILES.get("proof")
    if proof:
        if proof.size > 8 * 1024 * 1024:
            return err("حجم الصورة كبير (الحد 8 ميجابايت).")
        w, h = get_image_dimensions(proof)
        if not w or not h:
            return err("الملف المرفق ليس صورة صالحة.")
    elif settings.STEPS_REQUIRE_PROOF:
        return err("أرفقي لقطة شاشة من تطبيق الصحة كإثبات.", 400, "proof_required")

    status = StepEntry.PENDING if settings.STEPS_REQUIRE_PROOF else StepEntry.APPROVED
    StepEntry.objects.create(user=user, date=day, steps=n, source=StepEntry.MANUAL,
                             proof=proof or "", status=status)
    user.profile.refresh_from_db()
    msg = "أُرسلت خطواتكِ للمراجعة، وستُضاف بعد اعتماد المعلمة." if status == StepEntry.PENDING else "تمت إضافة الخطوات."
    return ok(201, message=msg, entry_status=status, user=me_payload(user))


@csrf_exempt
@require_POST
def steps_shortcut(request):
    """يستقبل الخطوات من اختصار الآيفون. الترويسة: Authorization: Bearer <token>
    الجسم JSON: {"steps": 8421, "date": "2026-11-14"} (التاريخ اختياري = اليوم)."""
    auth = request.headers.get("Authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    data = payload(request)
    token = token or (data.get("token") or "")
    profile = Profile.objects.select_related("user").filter(shortcut_token=token).first() if token else None
    if not profile or not profile.email_verified:
        return err("رمز الربط غير صالح.", 401, "bad_token")

    # الاختصار قد يرسل الرقم بفواصل أو كسور
    raw = str(data.get("steps", "")).replace(",", "").replace("٬", "").strip()
    try:
        n = int(float(raw))
    except ValueError:
        return err("عدد الخطوات غير صحيح.")
    if n < 0 or n > settings.STEPS_MAX_PER_ENTRY:
        return err("عدد الخطوات غير منطقي.")
    try:
        day = date.fromisoformat(str(data.get("date"))[:10]) if data.get("date") else timezone.localdate()
    except ValueError:
        day = timezone.localdate()
    if day > timezone.localdate():
        return err("لا يمكن تسجيل خطوات لتاريخ مستقبلي.")

    entry, created = StepEntry.objects.get_or_create(
        user=profile.user, date=day, source=StepEntry.SHORTCUT,
        defaults={"steps": n, "status": StepEntry.APPROVED},
    )
    if not created and n > entry.steps:  # تطبيق الصحة يعطي إجمالي اليوم، فنأخذ الأكبر
        entry.steps = n
        entry.save(update_fields=["steps"])
    profile.refresh_from_db()
    return ok(date=day.isoformat(), steps_today=entry.steps, total=profile.total_steps)


@api_login_required
def shortcut_info(request):
    p = request.user.profile
    if request.method == "POST":  # إعادة توليد الرمز (يبطل الاختصار القديم)
        from .models import new_token
        p.shortcut_token = new_token()
        p.save(update_fields=["shortcut_token"])
    return ok(token=p.shortcut_token, url=request.build_absolute_uri("/api/steps/shortcut/"))


# ---------------------------------------------------------------- لوحة الشرف
@require_GET
def leaderboard(request):
    kind = request.GET.get("type", "students")
    me_id = request.user.id if request.user.is_authenticated else None
    base = Profile.objects.filter(email_verified=True, user__is_staff=False).select_related("user")

    if kind == "classes":
        my_cls = request.user.profile.class_name if me_id else None
        agg = {r["class_name"]: r for r in base.values("class_name").annotate(steps=Sum("total_steps"), n=Count("id"))}
        rows = [{"name": c, "sub": f"{agg.get(c, {}).get('n', 0)} طالبة مشاركة",
                 "value": agg.get(c, {}).get("steps") or 0, "me": c == my_cls} for c in CLASS_NAMES]
        rows.sort(key=lambda r: -r["value"])
        return ok(rows=rows, unit="خطوة")

    field, unit = ("qr_challenge_points", "نقطة") if kind == "qr" else ("total_steps", "خطوة")
    top = base.order_by(f"-{field}", "user__first_name")[:10]
    rows = [{"name": p.user.first_name, "sub": p.class_name, "value": getattr(p, field), "me": p.user_id == me_id}
            for p in top]
    my_rank = None
    if me_id and not any(r["me"] for r in rows) and hasattr(request.user, "profile"):
        mp = request.user.profile
        if mp.email_verified:
            my_rank = {"rank": base.filter(**{f"{field}__gt": getattr(mp, field)}).count() + 1,
                       "name": request.user.first_name, "value": getattr(mp, field)}
    return ok(rows=rows, unit=unit, my_rank=my_rank)


# ---------------------------------------------------------------- المحطات
@require_POST
@api_login_required
def qr_complete(request):
    sid = str(payload(request).get("station_id") or "").zfill(2)
    if sid not in QR_STATIONS:
        return err("محطة غير معروفة.")
    try:
        with transaction.atomic():
            QRCompletion.objects.create(user=request.user, station_id=sid, points=QR_STATIONS[sid])
        added = QR_STATIONS[sid]
    except IntegrityError:
        added = 0
    request.user.profile.refresh_from_db()
    return ok(added=added, user=me_payload(request.user))


@require_POST
@api_login_required
def quiz_result(request):
    data = payload(request)
    score, total = to_int(data.get("score"), -1), to_int(data.get("total"), 0)
    if not (1 <= total <= 50) or not (0 <= score <= total):
        return err("نتيجة غير صحيحة.")
    attempt = QuizAttempt.objects.create(user=request.user, score=score, total=total)
    p = request.user.profile
    record = attempt.percent > p.quiz_best
    if record:
        p.quiz_best = attempt.percent
        p.save(update_fields=["quiz_best"])
    return ok(percent=attempt.percent, record=record, user=me_payload(request.user))


@require_POST
@api_login_required
def lab_result(request):
    data = payload(request)
    skill = data.get("skill")
    before, after = to_int(data.get("before"), -1), to_int(data.get("after"), -1)
    if skill not in SKILL_KEYS or not (0 <= before <= 100) or not (0 <= after <= 100):
        return err("بيانات التقرير غير صحيحة.")
    LabResult.objects.create(user=request.user, skill=skill, before=before, after=after,
                             note=(data.get("note") or "")[:300])
    return ok(201, user=me_payload(request.user))


# ---------------------------------------------------------------- المدربة الذكية
@require_POST
@api_login_required
def ai_trainer(request):
    message = (payload(request).get("message") or "").strip()
    if not message:
        return err("اكتبي سؤالكِ أولاً.")
    if len(message) > 500:
        return err("السؤال طويل، اختصريه إلى 500 حرف.")
    recent = ChatLog.objects.filter(student=request.user, created_at__gte=timezone.now() - timedelta(minutes=10)).count()
    if recent >= 20:
        return err("أرسلتِ أسئلة كثيرة خلال وقت قصير، خذي استراحة قصيرة ثم عودي 🙂", 429, "rate_limited")

    reply, live = ask_coach(request.user, message)
    if live:
        ChatLog.objects.create(student=request.user, user_message=message, ai_response=reply,
                               model_name=settings.GEMINI_MODEL)
    return ok(reply=reply, live=live)
