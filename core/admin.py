"""لوحة الإدارة للمعلمات: اعتماد الخطوات، إدارة قاعدة المعرفة، متابعة المحادثات."""
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html

from .models import ChatLog, KnowledgeBase, LabResult, Profile, QRCompletion, QuizAttempt, StepEntry

User = get_user_model()


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    readonly_fields = ("total_steps", "qr_challenge_points", "quiz_best", "shortcut_token")
    fields = ("email_verified", "class_name", "total_steps", "qr_challenge_points", "quiz_best", "shortcut_token")


admin.site.unregister(User)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """قائمة الطالبات والمعلمات مع إحصاءاتهن."""
    inlines = [ProfileInline]
    list_display = ("first_name", "email", "class_name", "steps", "qr_points", "verified", "is_staff", "date_joined")
    list_filter = ("is_staff", "profile__email_verified", "profile__class_name")
    search_fields = ("first_name", "email")
    ordering = ("-date_joined",)

    @admin.display(description="الفصل")
    def class_name(self, obj):
        return getattr(getattr(obj, 'profile', None), 'class_name', '—')

    @admin.display(description="الخطوات", ordering="profile__total_steps")
    def steps(self, obj):
        return f"{obj.profile.total_steps:,}"

    @admin.display(description="نقاط QR", ordering="profile__qr_challenge_points")
    def qr_points(self, obj):
        return obj.profile.qr_challenge_points

    @admin.display(description="مؤكد", boolean=True)
    def verified(self, obj):
        return obj.profile.email_verified


@admin.register(StepEntry)
class StepEntryAdmin(admin.ModelAdmin):
    list_display = ("student", "class_name", "date", "steps_fmt", "source", "status", "proof_thumb", "created_at")
    list_filter = ("status", "source", "date", "user__profile__class_name")
    search_fields = ("user__first_name", "user__email")
    list_select_related = ("user", "user__profile")
    readonly_fields = ("proof_large", "created_at", "reviewed_by")
    actions = ["approve", "reject"]
    date_hierarchy = "date"

    @admin.display(description="الطالبة", ordering="user__first_name")
    def student(self, obj):
        return obj.user.first_name

    @admin.display(description="الفصل")
    def class_name(self, obj):
        return obj.user.profile.class_name

    @admin.display(description="الخطوات", ordering="steps")
    def steps_fmt(self, obj):
        return f"{obj.steps:,}"

    @admin.display(description="الإثبات")
    def proof_thumb(self, obj):
        if not obj.proof:
            return "—"
        return format_html('<a href="{0}" target="_blank"><img src="{0}" style="height:56px;border-radius:8px"></a>', obj.proof.url)

    @admin.display(description="صورة الإثبات")
    def proof_large(self, obj):
        if not obj.proof:
            return "لا توجد صورة"
        return format_html('<a href="{0}" target="_blank"><img src="{0}" style="max-height:420px;border-radius:12px"></a>', obj.proof.url)

    def _set_status(self, request, queryset, status, label):
        count = 0
        for entry in queryset.select_related("user"):
            entry.status = status
            entry.reviewed_by = request.user
            entry.save()  # يحفّز إعادة حساب إجمالي الخطوات
            count += 1
        self.message_user(request, f"تم {label} {count} إدخال.", messages.SUCCESS)

    @admin.action(description="اعتماد الإدخالات المحددة ✅")
    def approve(self, request, queryset):
        self._set_status(request, queryset, StepEntry.APPROVED, "اعتماد")

    @admin.action(description="رفض الإدخالات المحددة ❌")
    def reject(self, request, queryset):
        self._set_status(request, queryset, StepEntry.REJECTED, "رفض")


@admin.register(KnowledgeBase)
class KnowledgeBaseAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "is_active", "updated_at")
    list_filter = ("category", "is_active")
    list_editable = ("is_active",)
    search_fields = ("title", "content")


@admin.register(ChatLog)
class ChatLogAdmin(admin.ModelAdmin):
    list_display = ("student", "short_q", "created_at", "model_name")
    list_filter = ("created_at",)
    search_fields = ("student__first_name", "student__email", "user_message", "ai_response")
    readonly_fields = ("student", "user_message", "ai_response", "model_name", "created_at")

    @admin.display(description="السؤال")
    def short_q(self, obj):
        return obj.user_message[:70]

    def has_add_permission(self, request):
        return False


@admin.register(QRCompletion)
class QRCompletionAdmin(admin.ModelAdmin):
    list_display = ("user", "station_id", "points", "created_at")
    list_filter = ("station_id",)


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ("user", "score", "total", "created_at")


@admin.register(LabResult)
class LabResultAdmin(admin.ModelAdmin):
    list_display = ("user", "skill", "before", "after", "created_at")
    list_filter = ("skill",)
