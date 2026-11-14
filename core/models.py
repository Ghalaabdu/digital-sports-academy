"""
نماذج قاعدة البيانات لأكاديمية الرياضة الرقمية.

- User (auth_user): username = البريد (فريد)، email، كلمة مرور مشفّرة، first_name = الاسم الكامل.
- Profile: إحصاءات الطالبة (total_steps, qr_challenge_points ...).
- EmailCode: رموز التحقق وإعادة التعيين (تُخزَّن مشفّرة).
- StepEntry: كل إدخال خطوات مع مصدره وإثباته وحالة اعتماده.
- QRCompletion / QuizAttempt / LabResult: نتائج المحطات.
- KnowledgeBase: محتوى المدرسة الذي يُحقن في المدربة الذكية.
- ChatLog: سجل كل محادثة مع المدربة لمتابعة الجودة.
"""
import hashlib
import secrets

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils import timezone

CLASS_CHOICES = [
    ("أول ثانوي / 1", "أول ثانوي / 1"),
    ("أول ثانوي / 2", "أول ثانوي / 2"),
    ("ثاني ثانوي / علمي 1", "ثاني ثانوي / علمي 1"),
    ("ثاني ثانوي / علمي 2", "ثاني ثانوي / علمي 2"),
    ("ثالث ثانوي / علمي 1", "ثالث ثانوي / علمي 1"),
    ("ثالث ثانوي / إنساني", "ثالث ثانوي / إنساني"),
]

# نقاط محطات الملعب الرقمي — تُحدَّد في الخادم حتى لا يمكن التلاعب بها من المتصفح
QR_STATIONS = {"01": 20, "02": 15, "03": 10, "04": 15, "05": 20, "06": 10, "07": 25, "08": 15}

LAB_SKILLS = [("basketball", "كرة السلة — التصويب"), ("volleyball", "كرة الطائرة — الإرسال"), ("sprint", "العدو — الانطلاق")]


def new_token():
    return secrets.token_urlsafe(24)


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile", verbose_name="المستخدم")
    email_verified = models.BooleanField("البريد مؤكد", default=False)
    class_name = models.CharField("الفصل", max_length=40, choices=CLASS_CHOICES, default=CLASS_CHOICES[2][0])
    total_steps = models.PositiveIntegerField("إجمالي الخطوات", default=0)
    qr_challenge_points = models.PositiveIntegerField("نقاط تحدي QR", default=0)
    quiz_best = models.PositiveSmallIntegerField("أفضل نتيجة مسابقة %", default=0)
    shortcut_token = models.CharField("رمز ربط الآيفون", max_length=64, unique=True, default=new_token)

    class Meta:
        verbose_name = "ملف طالبة"
        verbose_name_plural = "ملفات الطالبات"

    def __str__(self):
        return f"{self.user.first_name} ({self.user.email})"

    def recalc_steps(self):
        total = self.user.step_entries.filter(status=StepEntry.APPROVED).aggregate(s=Sum("steps"))["s"] or 0
        self.total_steps = total
        self.save(update_fields=["total_steps"])

    def recalc_qr(self):
        total = self.user.qr_completions.aggregate(s=Sum("points"))["s"] or 0
        self.qr_challenge_points = total
        self.save(update_fields=["qr_challenge_points"])


class EmailCode(models.Model):
    VERIFY, RESET = "verify", "reset"
    PURPOSES = [(VERIFY, "تأكيد البريد"), (RESET, "إعادة تعيين كلمة المرور")]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="email_codes")
    purpose = models.CharField(max_length=10, choices=PURPOSES)
    code_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    used = models.BooleanField(default=False)

    class Meta:
        verbose_name = "رمز تحقق"
        verbose_name_plural = "رموز التحقق"
        indexes = [models.Index(fields=["user", "purpose", "used"])]

    @staticmethod
    def hash(code: str) -> str:
        return hashlib.sha256(f"{settings.SECRET_KEY}:{code}".encode()).hexdigest()

    @property
    def expired(self):
        return timezone.now() >= self.expires_at


class StepEntry(models.Model):
    MANUAL, SHORTCUT, ADMIN = "manual", "shortcut", "admin"
    SOURCES = [(MANUAL, "إدخال يدوي"), (SHORTCUT, "اختصار الآيفون"), (ADMIN, "إدخال المعلمة")]
    PENDING, APPROVED, REJECTED = "pending", "approved", "rejected"
    STATUSES = [(PENDING, "قيد المراجعة"), (APPROVED, "معتمد"), (REJECTED, "مرفوض")]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="step_entries", verbose_name="الطالبة")
    date = models.DateField("التاريخ")
    steps = models.PositiveIntegerField("الخطوات")
    source = models.CharField("المصدر", max_length=10, choices=SOURCES, default=MANUAL)
    proof = models.ImageField("صورة الإثبات", upload_to="step_proofs/%Y/%m/", blank=True)
    status = models.CharField("الحالة", max_length=10, choices=STATUSES, default=PENDING)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+", verbose_name="راجعته")
    created_at = models.DateTimeField("وقت الإدخال", auto_now_add=True)

    class Meta:
        verbose_name = "إدخال خطوات"
        verbose_name_plural = "إدخالات الخطوات"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.first_name} — {self.steps} ({self.date})"


class QRCompletion(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="qr_completions")
    station_id = models.CharField("المحطة", max_length=4)
    points = models.PositiveSmallIntegerField("النقاط")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "تحدي QR منجز"
        verbose_name_plural = "تحديات QR المنجزة"
        constraints = [models.UniqueConstraint(fields=["user", "station_id"], name="uniq_qr_per_user")]


class QuizAttempt(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="quiz_attempts")
    score = models.PositiveSmallIntegerField("الإجابات الصحيحة")
    total = models.PositiveSmallIntegerField("عدد الأسئلة")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "محاولة مسابقة"
        verbose_name_plural = "محاولات المسابقة"

    @property
    def percent(self):
        return round(self.score * 100 / self.total) if self.total else 0


class LabResult(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="lab_results")
    skill = models.CharField("المهارة", max_length=20, choices=LAB_SKILLS)
    before = models.PositiveSmallIntegerField("قبل %")
    after = models.PositiveSmallIntegerField("بعد %")
    note = models.CharField("ملاحظات", max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "تقرير مختبر"
        verbose_name_plural = "تقارير المختبر"
        ordering = ["-created_at"]

    @property
    def improvement(self):
        return self.after - self.before


class KnowledgeBase(models.Model):
    CATEGORIES = [("exercise", "التمارين"), ("nutrition", "التغذية"), ("first_aid", "الإسعافات الأولية"), ("rules", "قوانين الألعاب"), ("general", "عام")]
    title = models.CharField("العنوان", max_length=150)
    category = models.CharField("التصنيف", max_length=20, choices=CATEGORIES, default="general")
    content = models.TextField("المحتوى")
    is_active = models.BooleanField("مفعّل", default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "معلومة في قاعدة المعرفة"
        verbose_name_plural = "قاعدة المعرفة للمدربة"
        ordering = ["category", "title"]

    def __str__(self):
        return self.title


class ChatLog(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="chat_logs", verbose_name="الطالبة")
    user_message = models.TextField("سؤال الطالبة")
    ai_response = models.TextField("رد المدربة")
    model_name = models.CharField("النموذج", max_length=60, blank=True)
    created_at = models.DateTimeField("الوقت", auto_now_add=True)

    class Meta:
        verbose_name = "محادثة"
        verbose_name_plural = "سجل محادثات المدربة"
        ordering = ["-created_at"]
