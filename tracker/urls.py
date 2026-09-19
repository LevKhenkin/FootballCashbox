from django.urls import path

from . import views


app_name = "tracker"

urlpatterns = [
    path("", views.game_list, name="game_list"),
    path("games/<int:game_id>/", views.game_detail, name="game_detail"),
    path("games/<int:game_id>/pay/", views.payment_create, name="payment_create"),
    path("my/payments/", views.my_payments, name="my_payments"),
    path("summary/", views.summary, name="summary"),
]
