from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Expense, Game, Month, Payment


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


class ViewTests(BaseData):
    def test_pages_require_login(self):
        response = self.client.get(reverse("tracker:game_list"))
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
        self.assertEqual(response.context["confirmed_total"], Decimal("500"))
        self.assertEqual(response.context["debt_total"], Decimal("1000.00"))
