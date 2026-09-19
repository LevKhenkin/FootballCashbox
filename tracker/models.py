from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Sum
from django.utils import timezone


ZERO = Decimal("0.00")


class Month(models.Model):
    """Расчётный месяц: за него выставляется счёт от зала и в нём проходят игры."""

    year = models.PositiveIntegerField("Год")
    month = models.PositiveSmallIntegerField("Месяц")
    hall_fee = models.DecimalField(
        "Счёт за зал",
        max_digits=10,
        decimal_places=2,
        default=ZERO,
        validators=[MinValueValidator(ZERO)],
        help_text="Сумма, которую нужно оплатить залу за месяц. Вносится админом.",
    )
    is_closed = models.BooleanField("Месяц закрыт", default=False)
    note = models.CharField("Комментарий", max_length=255, blank=True)

    class Meta:
        verbose_name = "Месяц"
        verbose_name_plural = "Месяцы"
        ordering = ["-year", "-month"]
        constraints = [
            models.UniqueConstraint(fields=["year", "month"], name="unique_year_month"),
            models.CheckConstraint(
                check=models.Q(month__gte=1) & models.Q(month__lte=12),
                name="month_between_1_and_12",
            ),
        ]

    def __str__(self):
        return f"{self.month:02d}.{self.year}"

    @property
    def expenses_total(self) -> Decimal:
        return self.expenses.aggregate(total=Sum("amount"))["total"] or ZERO

    @property
    def total_due(self) -> Decimal:
        """Сколько всего нужно собрать за месяц: зал + общие траты."""
        return self.hall_fee + self.expenses_total

    @property
    def collected_total(self) -> Decimal:
        return (
            Payment.objects.filter(game__month=self, status=Payment.Status.CONFIRMED)
            .aggregate(total=Sum("amount"))["total"]
            or ZERO
        )

    @property
    def balance(self) -> Decimal:
        """Положительное значение — собрано больше, чем нужно."""
        return self.collected_total - self.total_due


class Game(models.Model):
    """Конкретная игра, за которую скидываются игроки."""

    played_at = models.DateTimeField("Дата и время игры", default=timezone.now)
    month = models.ForeignKey(
        Month,
        verbose_name="Месяц",
        on_delete=models.PROTECT,
        related_name="games",
    )
    place = models.CharField("Место", max_length=120, blank=True)
    cost = models.DecimalField(
        "Стоимость игры",
        max_digits=10,
        decimal_places=2,
        default=ZERO,
        validators=[MinValueValidator(ZERO)],
        help_text="Общая стоимость игры. Делится между участниками.",
    )
    players = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        verbose_name="Участники",
        related_name="games",
        blank=True,
        help_text="Игроки, которые участвовали и должны скинуться.",
    )
    note = models.CharField("Комментарий", max_length=255, blank=True)

    class Meta:
        verbose_name = "Игра"
        verbose_name_plural = "Игры"
        ordering = ["-played_at"]

    def __str__(self):
        label = self.played_at.strftime("%d.%m.%Y %H:%M")
        return f"{label} — {self.place}" if self.place else label

    @property
    def players_count(self) -> int:
        return self.players.count()

    @property
    def share_per_player(self) -> Decimal:
        """Сколько должен внести каждый участник игры."""
        count = self.players_count
        if not count or not self.cost:
            return ZERO
        return (self.cost / count).quantize(Decimal("0.01"))

    @property
    def collected_total(self) -> Decimal:
        return (
            self.payments.filter(status=Payment.Status.CONFIRMED).aggregate(
                total=Sum("amount")
            )["total"]
            or ZERO
        )

    @property
    def pending_total(self) -> Decimal:
        return (
            self.payments.filter(status=Payment.Status.PENDING).aggregate(
                total=Sum("amount")
            )["total"]
            or ZERO
        )

    @property
    def remaining_total(self) -> Decimal:
        return max(self.cost - self.collected_total, ZERO)

    @property
    def is_fully_paid(self) -> bool:
        return self.cost > ZERO and self.collected_total >= self.cost

    def paid_by(self, user) -> Decimal:
        return (
            self.payments.filter(player=user, status=Payment.Status.CONFIRMED).aggregate(
                total=Sum("amount")
            )["total"]
            or ZERO
        )

    def debt_of(self, user) -> Decimal:
        return max(self.share_per_player - self.paid_by(user), ZERO)


class Payment(models.Model):
    """Взнос игрока за конкретную игру."""

    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает подтверждения"
        CONFIRMED = "confirmed", "Подтверждён"
        REJECTED = "rejected", "Отклонён"

    class Method(models.TextChoices):
        CASH = "cash", "Наличные"
        TRANSFER = "transfer", "Перевод"
        OTHER = "other", "Другое"

    game = models.ForeignKey(
        Game, verbose_name="Игра", on_delete=models.CASCADE, related_name="payments"
    )
    player = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Игрок",
        on_delete=models.CASCADE,
        related_name="payments",
    )
    amount = models.DecimalField(
        "Сумма",
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    method = models.CharField(
        "Способ оплаты", max_length=16, choices=Method.choices, default=Method.TRANSFER
    )
    paid_on = models.DateField("Дата оплаты", default=timezone.localdate)
    status = models.CharField(
        "Статус", max_length=16, choices=Status.choices, default=Status.PENDING
    )
    comment = models.CharField("Комментарий", max_length=255, blank=True)
    created_at = models.DateTimeField("Создан", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлён", auto_now=True)

    class Meta:
        verbose_name = "Оплата"
        verbose_name_plural = "Оплаты"
        ordering = ["-paid_on", "-created_at"]

    def __str__(self):
        return f"{self.player} — {self.amount} ({self.game})"


class Expense(models.Model):
    """Общая трата команды, например покупка мяча."""

    title = models.CharField("Назначение", max_length=120)
    amount = models.DecimalField(
        "Сумма",
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    month = models.ForeignKey(
        Month,
        verbose_name="Месяц",
        on_delete=models.PROTECT,
        related_name="expenses",
    )
    spent_on = models.DateField("Дата траты", default=timezone.localdate)
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Кто оплатил",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expenses",
    )
    comment = models.CharField("Комментарий", max_length=255, blank=True)

    class Meta:
        verbose_name = "Общая трата"
        verbose_name_plural = "Общие траты"
        ordering = ["-spent_on"]

    def __str__(self):
        return f"{self.title} — {self.amount}"
