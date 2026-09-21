from decimal import Decimal

from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase
from django.test.utils import override_settings
from django.urls import reverse

from .models import Expense, ExpenseContribution, Game, Month, Payment


class BaseData(TestCase):
    def setUp(self):
        self.month = Month.objects.create(year=2026, month=9, hall_fee=Decimal("12000"))
        self.game = Game.objects.create(
            month=self.month, place="Зал №1", cost=Decimal("3000")
        )
        self.alice = User.objects.create_user("alice", password="pass12345")
        self.bob = User.objects.create_user("bob", password="pass12345")
        self.game.players.add(self.alice, self.bob)


class GameCalculationTests(BaseData):
    def test_share_is_split_between_participants(self):
        self.assertEqual(self.game.share_per_player, Decimal("1500.00"))

    def test_indivisible_cost_is_covered_by_rounded_up_shares(self):
        game = Game.objects.create(month=self.month, cost=Decimal("4000"))
        carol = User.objects.create_user("carol", password="pass12345")
        game.players.add(self.alice, self.bob, carol)

        self.assertEqual(game.share_per_player, Decimal("1333.34"))
        for player in (self.alice, self.bob, carol):
            Payment.objects.create(
                game=game,
                player=player,
                amount=game.share_per_player,
                status=Payment.Status.CONFIRMED,
            )
        self.assertEqual(game.remaining_total, Decimal("0.00"))
        self.assertTrue(game.is_fully_paid)

    def test_totals_are_rounded_to_kopecks(self):
        Payment.objects.create(
            game=self.game,
            player=self.alice,
            amount=Decimal("1500"),
            status=Payment.Status.CONFIRMED,
        )
        for value in (
            self.game.collected_total,
            self.game.remaining_total,
            self.game.paid_by(self.alice),
            self.month.collected_total,
            self.month.balance,
        ):
            self.assertEqual(value.as_tuple().exponent, -2, msg=value)

    def test_share_is_zero_without_participants(self):
        empty_game = Game.objects.create(month=self.month, cost=Decimal("1000"))
        self.assertEqual(empty_game.share_per_player, Decimal("0.00"))

    def test_only_confirmed_payments_reduce_debt(self):
        Payment.objects.create(
            game=self.game, player=self.alice, amount=Decimal("1500")
        )
        self.assertEqual(self.game.debt_of(self.alice), Decimal("1500.00"))
        self.assertEqual(self.game.pending_total, Decimal("1500"))

        self.game.payments.update(status=Payment.Status.CONFIRMED)
        self.assertEqual(self.game.debt_of(self.alice), Decimal("0.00"))
        self.assertEqual(self.game.collected_total, Decimal("1500"))
        self.assertEqual(self.game.remaining_total, Decimal("1500"))

    def test_game_is_fully_paid_when_everyone_paid(self):
        for player in (self.alice, self.bob):
            Payment.objects.create(
                game=self.game,
                player=player,
                amount=Decimal("1500"),
                status=Payment.Status.CONFIRMED,
            )
        self.assertTrue(self.game.is_fully_paid)
        self.assertEqual(self.game.remaining_total, Decimal("0.00"))


class MonthTotalsTests(BaseData):
    def test_total_due_includes_hall_fee_and_expenses(self):
        Expense.objects.create(
            title="Мяч", amount=Decimal("2500"), month=self.month, paid_by=self.alice
        )
        self.assertEqual(self.month.expenses_total, Decimal("2500"))
        self.assertEqual(self.month.total_due, Decimal("14500"))

    def test_balance_tracks_confirmed_payments(self):
        Payment.objects.create(
            game=self.game,
            player=self.alice,
            amount=Decimal("1500"),
            status=Payment.Status.CONFIRMED,
        )
        self.assertEqual(self.month.collected_total, Decimal("1500"))
        self.assertEqual(self.month.balance, Decimal("-10500"))

    def test_collected_total_includes_expense_contributions(self):
        expense = Expense.objects.create(title="Мяч", amount=Decimal("2500"), month=self.month)
        ExpenseContribution.objects.create(
            expense=expense,
            player=self.alice,
            amount=Decimal("1000"),
            status=ExpenseContribution.Status.CONFIRMED,
        )
        self.assertEqual(self.month.collected_total, Decimal("1000.00"))


class ViewTests(BaseData):
    def test_pages_require_login(self):
        response = self.client.get(reverse("tracker:game_list"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

        response = self.client.get(reverse("tracker:profile"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

    def test_player_can_record_own_payment(self):
        self.client.force_login(self.alice)
        response = self.client.post(
            reverse("tracker:payment_create", args=[self.game.pk]),
            {
                "amount": "1500",
                "method": Payment.Method.TRANSFER,
                "paid_on": "2026-09-19",
                "comment": "перевод",
            },
        )
        self.assertRedirects(
            response, reverse("tracker:game_detail", args=[self.game.pk])
        )
        payment = Payment.objects.get()
        self.assertEqual(payment.player, self.alice)
        self.assertEqual(payment.game, self.game)
        self.assertEqual(payment.status, Payment.Status.PENDING)

    def test_player_can_join_game(self):
        carol = User.objects.create_user("carol", password="pass12345")
        self.assertNotIn(carol, self.game.players.all())

        self.client.force_login(carol)
        response = self.client.post(reverse("tracker:game_join", args=[self.game.pk]))
        self.assertRedirects(response, reverse("tracker:game_detail", args=[self.game.pk]))
        self.game.refresh_from_db()
        self.assertIn(carol, self.game.players.all())

    def test_player_cannot_join_game_in_closed_month(self):
        closed_month = Month.objects.create(year=2026, month=8, hall_fee=Decimal("0.00"), is_closed=True)
        closed_game = Game.objects.create(month=closed_month, cost=Decimal("1000"))
        dave = User.objects.create_user("dave", password="pass12345")

        self.client.force_login(dave)
        response = self.client.post(reverse("tracker:game_join", args=[closed_game.pk]))
        self.assertRedirects(response, reverse("tracker:game_detail", args=[closed_game.pk]))
        self.assertNotIn(dave, closed_game.players.all())

    def test_game_detail_lists_every_participant(self):
        self.client.force_login(self.alice)
        response = self.client.get(reverse("tracker:game_detail", args=[self.game.pk]))
        self.assertEqual(response.status_code, 200)
        rows = {row["player"].username: row for row in response.context["rows"]}
        self.assertEqual(set(rows), {"alice", "bob"})
        self.assertEqual(rows["bob"]["debt"], Decimal("1500.00"))

    def test_summary_aggregates_debts_per_player(self):
        Payment.objects.create(
            game=self.game,
            player=self.alice,
            amount=Decimal("1500"),
            status=Payment.Status.CONFIRMED,
        )
        self.client.force_login(self.alice)
        response = self.client.get(reverse("tracker:summary"))
        self.assertEqual(response.status_code, 200)
        rows = {row["player"].username: row for row in response.context["players_rows"]}
        self.assertEqual(rows["alice"]["debt"], Decimal("0.00"))
        self.assertEqual(rows["bob"]["debt"], Decimal("1500.00"))
        self.assertEqual(response.context["total_debt"], Decimal("1500.00"))

    def test_my_payments_shows_history_and_debts(self):
        Payment.objects.create(
            game=self.game,
            player=self.bob,
            amount=Decimal("500"),
            status=Payment.Status.CONFIRMED,
        )
        self.client.force_login(self.bob)
        response = self.client.get(reverse("tracker:my_payments"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["confirmed_total"], Decimal("500.00"))
        self.assertEqual(response.context["debt_total"], Decimal("1000.00"))

    def test_player_can_contribute_to_expense(self):
        expense = Expense.objects.create(title="Мяч", amount=Decimal("2500"), month=self.month)
        self.client.force_login(self.alice)
        response = self.client.post(
            reverse("tracker:expense_contribute", args=[expense.pk]),
            {
                "amount": "1000",
                "method": ExpenseContribution.Method.TRANSFER,
                "paid_on": "2026-09-19",
                "comment": "на мяч",
            },
        )
        self.assertRedirects(response, reverse("tracker:expense_detail", args=[expense.pk]))
        c = ExpenseContribution.objects.get()
        self.assertEqual(c.player, self.alice)
        self.assertEqual(c.expense, expense)
        self.assertEqual(c.status, ExpenseContribution.Status.PENDING)

    def test_profile_can_update_user_fields(self):
        self.client.force_login(self.alice)
        response = self.client.post(
            reverse("tracker:profile"),
            {
                "first_name": "Иван",
                "last_name": "Иванов",
                "email": "ivan@example.com",
                "username": "alice",
            },
        )
        self.assertRedirects(response, reverse("tracker:profile"))
        self.alice.refresh_from_db()
        self.assertEqual(self.alice.first_name, "Иван")
        self.assertEqual(self.alice.last_name, "Иванов")
        self.assertEqual(self.alice.email, "ivan@example.com")

    def test_signup_creates_player_user(self):
        response = self.client.post(
            reverse("tracker:signup"),
            {
                "username": "newplayer",
                "first_name": "Новый",
                "last_name": "Игрок",
                "email": "player@example.com",
                "password1": "StrongPass123!@#",
                "password2": "StrongPass123!@#",
            },
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="newplayer")
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.email, "player@example.com")

    def test_password_reset_sends_email_when_email_present(self):
        self.alice.email = "alice@example.com"
        self.alice.save(update_fields=["email"])
        response = self.client.post(
            reverse("password_reset"),
            {"email": "alice@example.com"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("reset", mail.outbox[0].body.lower())

    def test_login_page_hides_reset_link_without_smtp(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Восстановить")

    @override_settings(EMAIL_HOST="smtp.example.com")
    def test_login_page_shows_reset_link_with_smtp(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Восстановить")
