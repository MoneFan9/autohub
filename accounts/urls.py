from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

app_name = "accounts"
urlpatterns = [
    path("", views.home, name="home"),
    path("inscription/", views.signup, name="signup"),
    path("connexion/", views.MemberLoginView.as_view(), name="login"),
    path("deconnexion/", LogoutView.as_view(), name="logout"),
    path("mot-de-passe/", views.password_change, name="password"),
    path("securite/", views.security, name="security"),
    path("devenir-vendeur/", views.become_seller, name="become_seller"),
    path("reservations/<str:reference>/annuler/", views.cancel, name="cancel"),
]
