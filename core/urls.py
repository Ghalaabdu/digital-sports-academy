from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),

    # المصادقة
    path("register/", views.register, name="register"),
    path("verify-email/", views.verify_email, name="verify_email"),
    path("resend-code/", views.resend_code, name="resend_code"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("forgot-password/", views.forgot_password, name="forgot_password"),
    path("reset-password/", views.reset_password, name="reset_password"),

    # بيانات الطالبة
    path("api/me/", views.me, name="me"),
    path("api/profile/", views.update_profile, name="update_profile"),
    path("api/steps/", views.steps, name="steps"),
    path("api/steps/shortcut/", views.steps_shortcut, name="steps_shortcut"),
    path("api/shortcut/", views.shortcut_info, name="shortcut_info"),
    path("api/leaderboard/", views.leaderboard, name="leaderboard"),
    path("api/qr/complete/", views.qr_complete, name="qr_complete"),
    path("api/quiz/", views.quiz_result, name="quiz_result"),
    path("api/lab/", views.lab_result, name="lab_result"),

    # المدربة الذكية
    path("api/ai-trainer/", views.ai_trainer, name="ai_trainer"),
]
