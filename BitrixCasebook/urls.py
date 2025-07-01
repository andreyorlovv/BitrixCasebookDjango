"""
URL configuration for BitrixCasebook project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.template.backends import django
from django.urls import path
from django.views.decorators.csrf import csrf_exempt

from casebook import views
from casebook.admin import CaseAdmin

urlpatterns = [
    path('add_to_black_list/', csrf_exempt(views.add_to_blacklist), name='add to BL'),
    path('download_xlsx/', views.download_xlsx_view, name='download'),
    path('delete_task/', views.process_delete_task, name='delete_task'),
    path('process_task/', views.process_task, name='process_task'),
    path('update_filters/', views.update_filters, name='update_filters'),
    path('', views.custom_index, name='admin_custom_index'),
    path('', admin.site.urls),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
]
