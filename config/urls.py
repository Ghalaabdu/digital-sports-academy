from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "لوحة إدارة أكاديمية الرياضة الرقمية"
admin.site.site_title = "أكاديمية الرياضة الرقمية"
admin.site.index_title = "إدارة المنصة"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("core.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
