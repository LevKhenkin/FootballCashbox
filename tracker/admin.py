from django.contrib import admin

from .models import Expense, ExpenseContribution, Game, Month, Payment


class ExpenseInline(admin.TabularInline):
    model = Expense
    extra = 0


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    autocomplete_fields = ["player"]


class ExpenseContributionInline(admin.TabularInline):
    model = ExpenseContribution
    extra = 0
    autocomplete_fields = ["player"]


@admin.register(Month)
class MonthAdmin(admin.ModelAdmin):
    list_display = [
        "__str__",
        "hall_fee",
        "starting_capital",
        "expenses_total",
        "total_due",
        "collected_total",
        "balance",
        "is_closed",
    ]
    list_filter = ["year", "is_closed"]
    inlines = [ExpenseInline]

    @admin.display(description="Общие траты")
    def expenses_total(self, obj):
        return obj.expenses_total

    @admin.display(description="Нужно собрать")
    def total_due(self, obj):
        return obj.total_due

    @admin.display(description="Собрано")
    def collected_total(self, obj):
        return obj.collected_total

    @admin.display(description="Баланс")
    def balance(self, obj):
        return obj.balance


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = [
        "__str__",
        "month",
        "cost",
        "players_count",
        "share_per_player",
        "collected_total",
        "remaining_total",
    ]
    list_filter = ["month", "place"]
    search_fields = ["place", "note"]
    date_hierarchy = "played_at"
    filter_horizontal = ["players"]
    inlines = [PaymentInline]

    @admin.display(description="Игроков")
    def players_count(self, obj):
        return obj.players_count

    @admin.display(description="Доля с игрока")
    def share_per_player(self, obj):
        return obj.share_per_player

    @admin.display(description="Собрано")
    def collected_total(self, obj):
        return obj.collected_total

    @admin.display(description="Осталось собрать")
    def remaining_total(self, obj):
        return obj.remaining_total


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["player", "game", "amount", "method", "paid_on", "status"]
    list_filter = ["status", "method", "game__month", "paid_on"]
    search_fields = ["player__username", "player__first_name", "player__last_name", "comment"]
    autocomplete_fields = ["player", "game"]
    actions = ["confirm_payments", "reject_payments"]

    @admin.action(description="Подтвердить выбранные оплаты")
    def confirm_payments(self, request, queryset):
        updated = queryset.update(status=Payment.Status.CONFIRMED)
        self.message_user(request, f"Подтверждено оплат: {updated}")

    @admin.action(description="Отклонить выбранные оплаты")
    def reject_payments(self, request, queryset):
        updated = queryset.update(status=Payment.Status.REJECTED)
        self.message_user(request, f"Отклонено оплат: {updated}")


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "amount",
        "month",
        "spent_on",
        "paid_by",
        "collected_total",
        "remaining_total",
    ]
    list_filter = ["month", "spent_on"]
    search_fields = ["title", "comment"]
    inlines = [ExpenseContributionInline]

    @admin.display(description="Собрано")
    def collected_total(self, obj):
        return obj.collected_total

    @admin.display(description="Осталось собрать")
    def remaining_total(self, obj):
        return obj.remaining_total


@admin.register(ExpenseContribution)
class ExpenseContributionAdmin(admin.ModelAdmin):
    list_display = ["player", "expense", "amount", "method", "paid_on", "status"]
    list_filter = ["status", "method", "expense__month", "paid_on"]
    search_fields = [
        "player__username",
        "player__first_name",
        "player__last_name",
        "comment",
        "expense__title",
    ]
    autocomplete_fields = ["player", "expense"]
    actions = ["confirm_contributions", "reject_contributions"]

    @admin.action(description="Подтвердить выбранные взносы")
    def confirm_contributions(self, request, queryset):
        updated = queryset.update(status=ExpenseContribution.Status.CONFIRMED)
        self.message_user(request, f"Подтверждено взносов: {updated}")

    @admin.action(description="Отклонить выбранные взносы")
    def reject_contributions(self, request, queryset):
        updated = queryset.update(status=ExpenseContribution.Status.REJECTED)
        self.message_user(request, f"Отклонено взносов: {updated}")
