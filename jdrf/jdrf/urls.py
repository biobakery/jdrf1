"""jdrf URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/1.11/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  url(r'^$', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  url(r'^$', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.conf.urls import url, include
    2. Add a URL to urlpatterns:  url(r'^blog/', include('blog.urls'))
"""
from django.conf.urls import url, include

from django.contrib import admin

from django.views.generic import TemplateView

from django.contrib.auth import views as auth_views

from pages import views

urlpatterns = [
    url(r'^admin/', admin.site.urls),
    url(r'^$', TemplateView.as_view(template_name='index.html')),
    url(r'^login/', auth_views.LoginView.as_view(template_name='login.html'),name="login"),
    url(r'^logout/', auth_views.LogoutView.as_view(next_page="login"),name="logout"),
    url(r'^upload/', views.upload_files,name="upload"),
    url(r'^metadata/sample', views.upload_sample_metadata,name="upload_sample_metadata"),
    url(r'^metadata/study', views.upload_study_metadata,name="upload_study_metadata"),
    url(r'^files/(?P<file_name>.*)/delete$', views.delete_file,name="delete_file"),
    url(r'^files/delete$', views.delete_files,name="delete_files"),
    url(r'^files/(?P<file_name>.*)/rename$', views.rename_file,name="rename_file"),
    url(r'^metadata/', views.upload_metadata, name="upload_metadata"),
    url(r'^term/(?P<ontology_name>.*)/(?P<term_query>.*)/', views.search_ontology, name="search_ontology"),
    url(r'^process/', views.process_files,name="process"),
    url(r'^download/$', views.download_files,name="download"),
    url(r'^about/', TemplateView.as_view(template_name='about.html'),name="about"),
    url(r'^download-file/(?P<file_name>.*)/$', views.download_file, name="download_file")
]
