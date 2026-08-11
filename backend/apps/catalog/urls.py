from django.urls import path

from apps.catalog.views import CategoryListView, ServiceDetailView, ServiceListView

urlpatterns = [
    path("categories/", CategoryListView.as_view(), name="categories"),
    path("services/", ServiceListView.as_view(), name="services"),
    path("services/<slug:slug>/", ServiceDetailView.as_view(), name="service-detail"),
]
