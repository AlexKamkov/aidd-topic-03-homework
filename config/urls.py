from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("dashboard.urls")),
    # Без завершающего слэша получались битые адреса вида /userlogin/
    path("user/", include("user.urls")),
]
