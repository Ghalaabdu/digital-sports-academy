from django.conf import settings
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Profile, QRCompletion, StepEntry


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_profile(sender, instance, created, **kwargs):
    if created:
        # حسابات المعلمات التي تُنشأ من لوحة الإدارة تُعتبر مؤكدة
        Profile.objects.create(user=instance, email_verified=instance.is_staff)


@receiver([post_save, post_delete], sender=StepEntry)
def steps_changed(sender, instance, **kwargs):
    try:
        instance.user.profile.recalc_steps()
    except Exception:  # الحساب نفسه يُحذف الآن
        pass


@receiver([post_save, post_delete], sender=QRCompletion)
def qr_changed(sender, instance, **kwargs):
    try:
        instance.user.profile.recalc_qr()
    except Exception:
        pass
