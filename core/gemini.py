"""المدربة الذكية: تبني السياق من قاعدة المعرفة وتستدعي Google Gemini."""
import logging

from django.conf import settings

from .models import ChatLog, KnowledgeBase

log = logging.getLogger("core")

BASE_RULES = """أنتِ «مدربة أكاديمية الرياضة الرقمية»، مدربة لياقة ذكية لطالبات المرحلة الثانوية في مدرسة سعودية للبنات، وتعملين بإشراف معلمة التربية البدنية.
أسلوبكِ: عربية فصحى مبسطة، خطاب بصيغة المؤنث، مشجّع ولطيف وواضح. الإجابة قصيرة (أقل من 150 كلمة)، بنقاط مرقمة عند الحاجة، مع رمز تعبيري أو اثنين على الأكثر.
قواعد السلامة (إلزامية):
- لا تقدّمي تشخيصاً طبياً ولا أدوية. عند الإصابة أو الأعراض المقلقة (دوخة، ألم في الصدر، ضيق تنفس شديد، ألم حاد) وجّهي فوراً لمعلمة التربية البدنية أو ممرضة المدرسة.
- لا تقترحي حميات قاسية ولا أرقام سعرات ولا أوزاناً مستهدفة؛ ركّزي على التغذية المتوازنة والطاقة والصحة.
- اعتمدي على «قاعدة المعرفة المدرسية» أدناه أولاً، ولا تتعارضي معها.
- إن خرج السؤال عن الرياضة والصحة واللياقة، أعيدي الطالبة بلطف إلى مواضيع المنصة."""

FALLBACK = (
    "عذراً يا بطلة، المدربة الذكية غير متاحة الآن 🙏 "
    "تذكّري: الإحماء 5–10 دقائق قبل أي نشاط، واشربي الماء قبل الحصة وأثناءها وبعدها. "
    "حاولي مرة أخرى بعد قليل، أو اسألي معلمة التربية البدنية."
)


def build_system_prompt():
    items = KnowledgeBase.objects.filter(is_active=True)
    kb = "\n".join(f"- [{i.get_category_display()}] {i.title}: {i.content}" for i in items)
    return f"{BASE_RULES}\n\nقاعدة المعرفة المدرسية:\n{kb or '- (لا توجد معلومات إضافية)'}"


def model_chain():
    """النموذج الأساسي ثم البدائل عند الضغط المؤقت على خوادم Google."""
    chain = [settings.GEMINI_MODEL] + list(settings.GEMINI_FALLBACK_MODELS)
    return list(dict.fromkeys(m for m in chain if m))


def ask_coach(user, message: str) -> tuple[str, bool]:
    """يعيد (الرد، هل_نجح_الاتصال)."""
    if not settings.GEMINI_API_KEY:
        log.warning("GEMINI_API_KEY is not set")
        return FALLBACK, False
    try:
        from google import genai
        from google.genai import errors, types
    except ImportError:
        log.exception("google-genai is not installed")
        return FALLBACK, False

    client = genai.Client(api_key=settings.GEMINI_API_KEY,
                          http_options=types.HttpOptions(timeout=settings.GEMINI_TIMEOUT_MS))
    contents = []
    recent = list(ChatLog.objects.filter(student=user).order_by("-created_at")[:4])[::-1]
    for h in recent:
        contents.append(types.Content(role="user", parts=[types.Part(text=h.user_message)]))
        contents.append(types.Content(role="model", parts=[types.Part(text=h.ai_response)]))
    contents.append(types.Content(role="user", parts=[types.Part(text=message)]))
    config = types.GenerateContentConfig(
        system_instruction=build_system_prompt(),
        temperature=0.6,
        max_output_tokens=2048,
    )

    for model in model_chain():
        try:
            resp = client.models.generate_content(model=model, contents=contents, config=config)
            text = (resp.text or "").strip()
            if text:
                return text, True
            log.warning("Empty Gemini reply from %s", model)
        except errors.APIError as e:
            # 429/5xx: ضغط مؤقت أو نموذج غير متاح — نجرّب البديل التالي
            log.warning("Gemini %s failed (%s): %s", model, getattr(e, "code", "?"), str(e)[:200])
            if getattr(e, "code", None) not in (404, 429, 500, 503, 504):
                break
        except Exception:
            log.exception("Gemini request failed for %s", model)
    return FALLBACK, False
