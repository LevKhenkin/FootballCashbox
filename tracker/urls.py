from django.urls import path

from . import views


app_name = "tracker"

urlpatterns = [
    path("", views.game_list, name="game_list"),
    path("games/<int:game_id>/", views.game_detail, name="game_detail"),
    path("games/<int:game_id>/pay/", views.payment_create, name="payment_create"),
    path("games/<int:game_id>/join/", views.game_join, name="game_join"),
    path("expenses/", views.expense_list, name="expense_list"),
    path("expenses/<int:expense_id>/", views.expense_detail, name="expense_detail"),
    path(
        "expenses/<int:expense_id>/contribute/",
        views.expense_contribute,
        name="expense_contribute",
    ),
    path("my/payments/", views.my_payments, name="my_payments"),
    path("summary/", views.summary, name="summary"),
    path("profile/", views.profile, name="profile"),
    path("signup/", views.signup, name="signup"),
]
