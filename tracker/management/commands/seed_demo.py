from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from tracker.models import Expense, ExpenseContribution, Game, Month, Payment


class Command(BaseCommand):
    help = "Создаёт демо-данные: админа, игроков, месяц, игры, оплаты и общую трату."

    def add_arguments(self, parser):
        parser.add_argument("--password", default="football123")

    def handle(self, *args, **options):
        password = options["password"]

        admin, created = User.objects.get_or_create(
            username="admin",
            defaults={"is_staff": True, "is_superuser": True, "first_name": "Админ"},
        )
        if created:
            admin.set_password(password)
            admin.save()

        players = []
        for username, first_name in [
            ("ivan", "Иван"),
            ("petr", "Пётр"),
            ("sergey", "Сергей"),
            ("oleg", "Олег"),
        ]:
            player, player_created = User.objects.get_or_create(
                username=username, defaults={"first_name": first_name}
            )
            if player_created:
                player.set_password(password)
                player.save()
            players.append(player)

        today = timezone.localdate()
        month, _ = Month.objects.get_or_create(
            year=today.year,
            month=today.month,
            defaults={"hall_fee": Decimal("12000.00")},
        )

        now = timezone.now()
        first_game, _ = Game.objects.get_or_create(
            month=month,
            played_at=now - timezone.timedelta(days=7),
            defaults={"place": "Зал №1", "cost": Decimal("4000.00")},
        )
        second_game, _ = Game.objects.get_or_create(
            month=month,
            played_at=now - timezone.timedelta(days=1),
            defaults={"place": "Зал №2", "cost": Decimal("4000.00")},
        )
        first_game.players.set(players)
        second_game.players.set(players[:3])

        if not first_game.payments.exists():
            for player in players[:3]:
                Payment.objects.create(
                    game=first_game,
                    player=player,
                    amount=first_game.share_per_player,
                    status=Payment.Status.CONFIRMED,
                )
        if not second_game.payments.exists():
            Payment.objects.create(
                game=second_game,
                player=players[0],
                amount=second_game.share_per_player,
                status=Payment.Status.PENDING,
            )

        expense, _ = Expense.objects.get_or_create(
            title="Мяч",
            month=month,
            defaults={"amount": Decimal("2500.00"), "paid_by": admin},
        )
        if not expense.contributions.exists():
            ExpenseContribution.objects.create(
                expense=expense,
                player=players[1],
                amount=Decimal("1000.00"),
                status=ExpenseContribution.Status.CONFIRMED,
            )
            ExpenseContribution.objects.create(
                expense=expense,
                player=players[2],
                amount=Decimal("500.00"),
                status=ExpenseContribution.Status.PENDING,
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Демо-данные готовы. Логины: admin / {', '.join(p.username for p in players)}. "
                f"Пароль: {password}"
            )
        )
