from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch, Sum
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ExpenseContributionForm, PaymentForm, ProfileForm
from .models import Expense, ExpenseContribution, Game, Month, Payment, money

ZERO = Decimal("0.00")


@login_required
def game_list(request):
    """Список игр с состоянием сбора денег и личным долгом текущего игрока."""
    month_id = request.GET.get("month")
    games = (
        Game.objects.select_related("month")
        .prefetch_related("players", "payments")
        .order_by("-played_at")
    )
    if month_id:
        games = games.filter(month_id=month_id)

    rows = []
    for game in games:
        is_participant = request.user in game.players.all()
        rows.append(
            {
                "game": game,
                "is_participant": is_participant,
                "my_paid": game.paid_by(request.user) if is_participant else ZERO,
                "my_debt": game.debt_of(request.user) if is_participant else ZERO,
            }
        )

    context = {
        "rows": rows,
        "months": Month.objects.all(),
        "selected_month": month_id or "",
    }
    return render(request, "tracker/game_list.html", context)


@login_required
def game_detail(request, game_id):
    """Кто сколько заплатил по конкретной игре."""
    game = get_object_or_404(
        Game.objects.select_related("month").prefetch_related(
            "players",
            Prefetch("payments", queryset=Payment.objects.select_related("player")),
        ),
        pk=game_id,
    )

    payments = list(game.payments.all())
    rows = []
    for player in game.players.all():
        player_payments = [p for p in payments if p.player_id == player.id]
        confirmed = money(
            sum(
                (
                    p.amount
                    for p in player_payments
                    if p.status == Payment.Status.CONFIRMED
                ),
                ZERO,
            )
        )
        pending = money(
            sum(
                (
                    p.amount
                    for p in player_payments
                    if p.status == Payment.Status.PENDING
                ),
                ZERO,
            )
        )
        rows.append(
            {
                "player": player,
                "confirmed": confirmed,
                "pending": pending,
                "debt": max(money(game.share_per_player - confirmed), ZERO),
                "payments": player_payments,
            }
        )

    # Оплаты от тех, кто не числится участником игры, тоже нельзя терять.
    player_ids = {player.id for player in game.players.all()}
    extra_payments = [p for p in payments if p.player_id not in player_ids]

    context = {
        "game": game,
        "rows": rows,
        "extra_payments": extra_payments,
        "is_participant": request.user in game.players.all(),
    }
    return render(request, "tracker/game_detail.html", context)


@login_required
def payment_create(request, game_id):
    """Игрок вносит данные о своей оплате за игру."""
    game = get_object_or_404(Game.objects.select_related("month"), pk=game_id)

    if request.method == "POST":
        form = PaymentForm(request.POST, game=game, player=request.user)
        if form.is_valid():
            form.save()
            messages.success(
                request, "Оплата записана и ждёт подтверждения администратора."
            )
            return redirect("tracker:game_detail", game_id=game.id)
    else:
        form = PaymentForm(game=game, player=request.user)

    context = {
        "form": form,
        "game": game,
        "my_debt": game.debt_of(request.user),
    }
    return render(request, "tracker/payment_form.html", context)


@login_required
def game_join(request, game_id):
    if request.method != "POST":
        return redirect("tracker:game_detail", game_id=game_id)

    game = get_object_or_404(Game.objects.select_related("month"), pk=game_id)
    if getattr(game.month, "is_closed", False):
        messages.error(request, "Месяц закрыт — записаться на игру уже нельзя.")
        return redirect("tracker:game_detail", game_id=game.id)

    if request.user not in game.players.all():
        game.players.add(request.user)
        messages.success(request, "Вы добавлены в участники игры.")
    else:
        messages.info(request, "Вы уже в списке участников этой игры.")

    next_url = request.POST.get("next") or ""
    if next_url.startswith("/"):
        return redirect(next_url)
    return redirect("tracker:game_detail", game_id=game.id)


@login_required
def my_payments(request):
    """Личная история оплат игрока и текущие долги по играм."""
    payments = (
        Payment.objects.filter(player=request.user)
        .select_related("game", "game__month")
        .order_by("-paid_on", "-created_at")
    )
    contributions = (
        ExpenseContribution.objects.filter(player=request.user)
        .select_related("expense", "expense__month")
        .order_by("-paid_on", "-created_at")
    )
    confirmed_total = money(
        payments.filter(status=Payment.Status.CONFIRMED).aggregate(total=Sum("amount"))[
            "total"
        ]
    )
    pending_total = money(
        payments.filter(status=Payment.Status.PENDING).aggregate(total=Sum("amount"))[
            "total"
        ]
    )
    contributions_confirmed_total = money(
        contributions.filter(status=ExpenseContribution.Status.CONFIRMED).aggregate(
            total=Sum("amount")
        )["total"]
    )
    contributions_pending_total = money(
        contributions.filter(status=ExpenseContribution.Status.PENDING).aggregate(
            total=Sum("amount")
        )["total"]
    )

    my_games = (
        Game.objects.filter(players=request.user)
        .select_related("month")
        .prefetch_related("players", "payments")
        .order_by("-played_at")
    )
    debts = []
    for game in my_games:
        debt = game.debt_of(request.user)
        if debt > ZERO:
            debts.append({"game": game, "debt": debt})

    context = {
        "payments": payments,
        "confirmed_total": confirmed_total,
        "pending_total": pending_total,
        "contributions": contributions,
        "contributions_confirmed_total": contributions_confirmed_total,
        "contributions_pending_total": contributions_pending_total,
        "confirmed_all_total": money(confirmed_total + contributions_confirmed_total),
        "pending_all_total": money(pending_total + contributions_pending_total),
        "debts": debts,
        "debt_total": money(sum((item["debt"] for item in debts), ZERO)),
    }
    return render(request, "tracker/my_payments.html", context)


@login_required
def summary(request):
    """Сводка по месяцам: счёт зала, общие траты и кто сколько должен в целом."""
    month_id = request.GET.get("month")
    months = Month.objects.prefetch_related("expenses", "games__players")
    selected_month = None
    if month_id:
        selected_month = months.filter(pk=month_id).first()

    scope_games = (
        Game.objects.select_related("month")
        .prefetch_related("players", "payments")
        .order_by("-played_at")
    )
    if selected_month:
        scope_games = scope_games.filter(month=selected_month)

    per_player = {}
    for game in scope_games:
        for player in game.players.all():
            row = per_player.setdefault(
                player.id,
                {
                    "player": player,
                    "games": 0,
                    "due": ZERO,
                    "paid_games": ZERO,
                    "paid_expenses": ZERO,
                    "paid_all": ZERO,
                    "debt": ZERO,
                },
            )
            row["games"] += 1
            row["due"] += game.share_per_player
            row["paid_games"] += game.paid_by(player)

    scope_contribs = ExpenseContribution.objects.filter(
        status=ExpenseContribution.Status.CONFIRMED
    ).select_related("expense", "player")
    if selected_month:
        scope_contribs = scope_contribs.filter(expense__month=selected_month)
    for c in scope_contribs:
        row = per_player.setdefault(
            c.player_id,
            {
                "player": c.player,
                "games": 0,
                "due": ZERO,
                "paid_games": ZERO,
                "paid_expenses": ZERO,
                "paid_all": ZERO,
                "debt": ZERO,
            },
        )
        row["paid_expenses"] += c.amount

    for row in per_player.values():
        row["due"] = money(row["due"])
        row["paid_games"] = money(row["paid_games"])
        row["paid_expenses"] = money(row["paid_expenses"])
        row["paid_all"] = money(row["paid_games"] + row["paid_expenses"])
        row["debt"] = max(money(row["due"] - row["paid_games"]), ZERO)

    players_rows = sorted(
        per_player.values(), key=lambda row: (-row["debt"], str(row["player"]))
    )

    months_rows = []
    for month in months:
        months_rows.append(
            {
                "month": month,
                "hall_fee": month.hall_fee,
                "expenses_total": month.expenses_total,
                "total_due": month.total_due,
                "collected": month.collected_total,
                "balance": month.balance,
            }
        )

    context = {
        "months": months,
        "months_rows": months_rows,
        "players_rows": players_rows,
        "selected_month": selected_month,
        "selected_month_id": month_id or "",
        "total_due": money(sum((row["due"] for row in players_rows), ZERO)),
        "total_paid_games": money(sum((row["paid_games"] for row in players_rows), ZERO)),
        "total_paid_expenses": money(
            sum((row["paid_expenses"] for row in players_rows), ZERO)
        ),
        "total_paid_all": money(sum((row["paid_all"] for row in players_rows), ZERO)),
        "total_debt": money(sum((row["debt"] for row in players_rows), ZERO)),
    }
    return render(request, "tracker/summary.html", context)


@login_required
def expense_list(request):
    month_id = request.GET.get("month")
    expenses = Expense.objects.select_related("month").prefetch_related("contributions")
    if month_id:
        expenses = expenses.filter(month_id=month_id)
    expenses = expenses.order_by("-spent_on")

    rows = []
    for expense in expenses:
        my_paid = money(
            expense.contributions.filter(
                player=request.user, status=ExpenseContribution.Status.CONFIRMED
            ).aggregate(total=Sum("amount"))["total"]
        )
        rows.append({"expense": expense, "my_paid": my_paid})

    context = {
        "rows": rows,
        "months": Month.objects.all(),
        "selected_month": month_id or "",
    }
    return render(request, "tracker/expense_list.html", context)


@login_required
def expense_detail(request, expense_id):
    expense = get_object_or_404(
        Expense.objects.select_related("month").prefetch_related(
            Prefetch(
                "contributions",
                queryset=ExpenseContribution.objects.select_related("player"),
            )
        ),
        pk=expense_id,
    )

    contributions = list(expense.contributions.all())
    context = {
        "expense": expense,
        "contributions": contributions,
        "my_confirmed": money(
            sum(
                (
                    c.amount
                    for c in contributions
                    if c.player_id == request.user.id
                    and c.status == ExpenseContribution.Status.CONFIRMED
                ),
                ZERO,
            )
        ),
    }
    return render(request, "tracker/expense_detail.html", context)


@login_required
def expense_contribute(request, expense_id):
    expense = get_object_or_404(Expense.objects.select_related("month"), pk=expense_id)

    if request.method == "POST":
        form = ExpenseContributionForm(
            request.POST, expense=expense, player=request.user
        )
        if form.is_valid():
            form.save()
            messages.success(
                request, "Взнос записан и ждёт подтверждения администратора."
            )
            return redirect("tracker:expense_detail", expense_id=expense.id)
    else:
        form = ExpenseContributionForm(expense=expense, player=request.user)

    context = {"form": form, "expense": expense}
    return render(request, "tracker/expense_contribution_form.html", context)


@login_required
def profile(request):
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Профиль обновлён.")
            return redirect("tracker:profile")
    else:
        form = ProfileForm(instance=request.user)

    return render(request, "tracker/profile.html", {"form": form})
