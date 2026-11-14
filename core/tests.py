"""اختبارات آلية لمسارات المنصة. التشغيل: python manage.py test core -v 2"""
import io
import re
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from PIL import Image

from .models import ChatLog, KnowledgeBase, StepEntry

User = get_user_model()
PW = "StrongPass1"


def code_from_mail(i=-1):
    return re.search(r"\b(\d{6})\b", mail.outbox[i].body).group(1)


def png_file(name="proof.png"):
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), (124, 58, 237)).save(buf, "PNG")
    buf.seek(0)
    buf.name = name
    return buf


@override_settings(CODE_RESEND_SECONDS=0, STEPS_REQUIRE_PROOF=True, GEMINI_API_KEY="")
class FlowTests(TestCase):
    def post(self, url, data=None, client=None):
        return (client or self.client).post(url, data or {}, content_type="application/json")

    def register_and_verify(self, email="sara@gmail.com", name="سارة القحطاني"):
        r = self.post("/register/", {"name": name, "email": email, "password": PW})
        self.assertEqual(r.status_code, 201, r.content)
        code = code_from_mail()
        r = self.post("/verify-email/", {"email": email, "code": code})
        self.assertTrue(r.json()["ok"], r.content)
        return r.json()["user"]

    # ---------------- الصفحة الرئيسية و CSRF
    def test_index_sets_csrf_cookie(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("csrftoken", r.cookies)
        self.assertIn("أكاديمية الرياضة الرقمية", b"".join(r.streaming_content).decode())

    def test_csrf_enforced_and_header_works(self):
        c = Client(enforce_csrf_checks=True)
        r = c.post("/login/", {"email": "a@b.com", "password": "x"}, content_type="application/json")
        self.assertEqual(r.status_code, 403)
        c.get("/")
        token = c.cookies["csrftoken"].value
        r = c.post("/login/", {"email": "nobody@gmail.com", "password": PW}, content_type="application/json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(r.status_code, 404)

    # ---------------- التسجيل والتحقق
    def test_register_validation(self):
        self.assertEqual(self.post("/register/", {"name": "سارة", "email": "bad", "password": PW}).status_code, 400)
        r = self.post("/register/", {"name": "سارة علي", "email": "s@gmail.com", "password": "weakpass1"})
        self.assertIn("حرف إنجليزي كبير", r.json()["error"])
        r = self.post("/register/", {"name": "سارة علي", "email": "s@gmail.com", "password": "Sh0rt"})
        self.assertIn("8 أحرف", r.json()["error"])

    def test_register_sends_real_email_and_verify(self):
        self.post("/register/", {"name": "سارة القحطاني", "email": "Sara@Gmail.com", "password": PW})
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["sara@gmail.com"])
        self.assertTrue(mail.outbox[0].alternatives)  # نسخة HTML
        # لا يمكن الدخول قبل التأكيد
        r = self.post("/login/", {"email": "sara@gmail.com", "password": PW})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["code"], "unverified")
        # رمز خاطئ ثم صحيح
        self.assertEqual(self.post("/verify-email/", {"email": "sara@gmail.com", "code": "000000"}).status_code, 400)
        code = code_from_mail()
        r = self.post("/verify-email/", {"email": "sara@gmail.com", "code": code})
        self.assertTrue(r.json()["ok"])
        me = self.client.get("/api/me/").json()
        self.assertTrue(me["authenticated"])
        self.assertEqual(me["user"]["name"], "سارة القحطاني")
        # التسجيل مرة أخرى بنفس البريد مرفوض
        self.assertEqual(self.post("/register/", {"name": "x y z", "email": "sara@gmail.com", "password": PW}).status_code, 409)

    def test_login_errors(self):
        self.register_and_verify()
        self.post("/logout/")
        r = self.post("/login/", {"email": "nobody@gmail.com", "password": PW})
        self.assertEqual(r.status_code, 404)
        self.assertIn("غير مسجّل", r.json()["error"])
        r = self.post("/login/", {"email": "sara@gmail.com", "password": "WrongPass1"})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.post("/login/", {"email": "sara@gmail.com", "password": PW}).status_code, 200)

    def test_forgot_and_reset_password(self):
        self.register_and_verify()
        self.post("/logout/")
        self.assertEqual(self.post("/forgot-password/", {"email": "none@gmail.com"}).status_code, 404)
        self.assertEqual(self.post("/forgot-password/", {"email": "sara@gmail.com"}).status_code, 200)
        code = code_from_mail()
        r = self.post("/reset-password/", {"email": "sara@gmail.com", "code": code, "password": "weak"})
        self.assertEqual(r.status_code, 400)
        r = self.post("/reset-password/", {"email": "sara@gmail.com", "code": code, "password": "NewPass123"})
        self.assertTrue(r.json()["ok"], r.content)
        self.assertEqual(self.post("/login/", {"email": "sara@gmail.com", "password": "NewPass123"}).status_code, 200)

    # ---------------- الخطوات
    def test_manual_steps_need_proof_and_approval(self):
        self.register_and_verify()
        today = timezone.localdate().isoformat()
        r = self.client.post("/api/steps/", {"steps": 5000, "date": today})
        self.assertEqual(r.json()["code"], "proof_required")
        r = self.client.post("/api/steps/", {"steps": 5000, "date": today, "proof": png_file()})
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["entry_status"], "pending")
        self.assertEqual(r.json()["user"]["steps"], 0)
        # المعلمة تعتمد من لوحة الإدارة
        teacher = User.objects.create_superuser("teacher@school.com", "teacher@school.com", PW)
        admin = Client()
        admin.force_login(teacher)
        entry = StepEntry.objects.get()
        r = admin.post("/admin/core/stepentry/", {"action": "approve", "_selected_action": [entry.pk]})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.client.get("/api/me/").json()["user"]["steps"], 5000)
        week = self.client.get("/api/steps/").json()["week"]
        self.assertEqual(week[-1]["steps"], 5000)

    def test_steps_reject_future_and_old_dates(self):
        self.register_and_verify()
        r = self.client.post("/api/steps/", {"steps": 100, "date": "2000-01-01", "proof": png_file()})
        self.assertEqual(r.status_code, 400)

    def test_iphone_shortcut(self):
        self.register_and_verify()
        info = self.client.get("/api/shortcut/").json()
        self.assertTrue(info["url"].endswith("/api/steps/shortcut/"))
        anon = Client()
        bad = anon.post("/api/steps/shortcut/", {"steps": 100}, content_type="application/json", HTTP_AUTHORIZATION="Bearer nope")
        self.assertEqual(bad.status_code, 401)
        auth = {"HTTP_AUTHORIZATION": "Bearer " + info["token"]}
        r = anon.post("/api/steps/shortcut/", {"steps": "8,421"}, content_type="application/json", **auth)
        self.assertEqual(r.json()["total"], 8421, r.content)
        r = anon.post("/api/steps/shortcut/", {"steps": 3000}, content_type="application/json", **auth)  # أقل: لا يُنقص
        self.assertEqual(r.json()["total"], 8421)
        r = anon.post("/api/steps/shortcut/", {"steps": 9100.0}, content_type="application/json", **auth)
        self.assertEqual(r.json()["total"], 9100)
        # إعادة توليد الرمز تبطل القديم
        self.post("/api/shortcut/")
        self.assertEqual(anon.post("/api/steps/shortcut/", {"steps": 1}, content_type="application/json", **auth).status_code, 401)

    # ---------------- لوحة الشرف والمحطات
    def test_leaderboard_qr_quiz_lab(self):
        self.register_and_verify()
        r = self.post("/api/qr/complete/", {"station_id": "07"})
        self.assertEqual(r.json()["added"], 25)
        r = self.post("/api/qr/complete/", {"station_id": "07"})
        self.assertEqual(r.json()["added"], 0)
        self.assertEqual(r.json()["user"]["qr_points"], 25)
        self.assertEqual(self.post("/api/qr/complete/", {"station_id": "99"}).status_code, 400)

        r = self.post("/api/quiz/", {"score": 8, "total": 10})
        self.assertTrue(r.json()["record"])
        r = self.post("/api/quiz/", {"score": 5, "total": 10})
        self.assertFalse(r.json()["record"])
        self.assertEqual(r.json()["user"]["quiz_best"], 80)

        r = self.post("/api/lab/", {"skill": "basketball", "before": 40, "after": 80, "note": "تحسن"})
        self.assertEqual(r.json()["user"]["lab"][0]["imp"], 40)

        self.post("/api/profile/", {"class_name": "أول ثانوي / 2"})
        rows = self.client.get("/api/leaderboard/?type=qr").json()["rows"]
        self.assertTrue(rows[0]["me"])
        classes = self.client.get("/api/leaderboard/?type=classes").json()["rows"]
        self.assertEqual(len(classes), 6)
        self.assertTrue(any(c["me"] and c["name"] == "أول ثانوي / 2" for c in classes))
        self.assertEqual(Client().get("/api/leaderboard/").status_code, 200)  # متاحة للزوار

    def test_protected_endpoints_require_login(self):
        for url in ["/api/qr/complete/", "/api/quiz/", "/api/lab/", "/api/ai-trainer/", "/api/profile/"]:
            self.assertEqual(self.post(url, {}).status_code, 401, url)
        self.assertEqual(self.client.get("/api/steps/").status_code, 401)

    # ---------------- المدربة الذكية
    def test_ai_trainer_fallback_without_key(self):
        self.register_and_verify()
        r = self.post("/api/ai-trainer/", {"message": "كيف أؤدي السكوات؟"})
        self.assertTrue(r.json()["ok"])
        self.assertFalse(r.json()["live"])

    @override_settings(GEMINI_API_KEY="test-key")
    def test_ai_trainer_uses_gemini_and_logs(self):
        KnowledgeBase.objects.create(title="الإحماء", content="5–10 دقائق", category="exercise")
        self.register_and_verify()
        fake = mock.MagicMock()
        fake.models.generate_content.return_value.text = "1. افتحي قدميكِ بعرض الكتفين 💪"
        with mock.patch("google.genai.Client", return_value=fake):
            r = self.post("/api/ai-trainer/", {"message": "كيف أؤدي السكوات؟"})
        self.assertTrue(r.json()["live"], r.content)
        self.assertIn("الكتفين", r.json()["reply"])
        kwargs = fake.models.generate_content.call_args.kwargs
        self.assertEqual(kwargs["model"], settings.GEMINI_MODEL)
        self.assertIn("الإحماء", kwargs["config"].system_instruction)
        log = ChatLog.objects.get()
        self.assertEqual(log.user_message, "كيف أؤدي السكوات؟")

    @override_settings(GEMINI_API_KEY="test-key", GEMINI_MODEL="busy-model", GEMINI_FALLBACK_MODELS=["backup-model"])
    def test_ai_trainer_falls_back_when_model_busy(self):
        from google.genai import errors
        self.register_and_verify()
        fake = mock.MagicMock()
        ok_resp = mock.MagicMock(text="ردّ من النموذج البديل")
        busy = errors.ServerError(503, {"error": {"code": 503, "message": "high demand", "status": "UNAVAILABLE"}})
        fake.models.generate_content.side_effect = [busy, ok_resp]
        with mock.patch("google.genai.Client", return_value=fake):
            r = self.post("/api/ai-trainer/", {"message": "سؤال"})
        self.assertTrue(r.json()["live"], r.content)
        used = [c.kwargs["model"] for c in fake.models.generate_content.call_args_list]
        self.assertEqual(used, ["busy-model", "backup-model"])

    # ---------------- لوحة الإدارة
    def test_admin_pages_load(self):
        self.register_and_verify()
        teacher = User.objects.create_superuser("t@school.com", "t@school.com", PW)
        c = Client()
        c.force_login(teacher)
        for url in ["/admin/", "/admin/auth/user/", "/admin/core/stepentry/", "/admin/core/knowledgebase/", "/admin/core/chatlog/"]:
            self.assertEqual(c.get(url).status_code, 200, url)
