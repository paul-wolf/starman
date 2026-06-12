from django.contrib import admin
from django.urls import path
from django.http import FileResponse, Http404
from django.conf import settings

from dish.api import api

def spa(request, path=""):
    index = settings.BASE_DIR / "frontend" / "dist" / "index.html"
    if not index.exists():
        raise Http404("Frontend not built — run: cd frontend && npm run build")
    return FileResponse(open(index, "rb"), content_type="text/html")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
    path("", spa),
    path("<path:path>", spa),
]
