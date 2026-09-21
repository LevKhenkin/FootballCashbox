from __future__ import annotations

from datetime import datetime
from io import BytesIO

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.http import HttpRequest, HttpResponse
from django.urls import path
from django.utils import timezone

from openpyxl import Workbook

from .models import Expense, ExpenseContribution, Game, Month, Payment


User = get_user_model()


def _dt(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        if timezone.is_aware(value):
            return timezone.localtime(value).replace(tzinfo=None)
        return value
    return value


def _add_sheet(wb: Workbook, title: str, headers: list[str], rows: list[list[object]]):
    ws = wb.create_sheet(title=title)
    ws.append(headers)
    for row in rows:
        ws.append([_dt(v) for v in row])
    ws.freeze_panes = "A2"


class FootballAdminSite(admin.AdminSite):
    site_header = "Футбольная касса — админка"
    site_title = "Футбольная касса"
    index_title = "Управление"

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "export-excel/",
                self.admin_view(self.export_excel),
                name="export_excel",
            )
        ]
        return custom + urls

    def export_excel(self, request: HttpRequest) -> HttpResponse:
        wb = Workbook()
        # Remove default sheet
        wb.remove(wb.active)

        _add_sheet(
            wb,
            "Месяцы",
            ["id", "year", "month", "hall_fee", "starting_capital", "is_closed", "note"],
            [
                [
                    m.id,
                    m.year,
                    m.month,
                    float(m.hall_fee),
                    float(m.starting_capital),
                    m.is_closed,
                    m.note,
                ]
                for m in Month.objects.order_by("year", "month")
            ],
        )

        _add_sheet(
            wb,
            "Игры",
            ["id", "played_at", "month_id", "place", "cost", "note", "players"],
            [
                [
                    g.id,
                    g.played_at,
                    g.month_id,
                    g.place,
                    float(g.cost),
                    g.note,
                    ", ".join(
                        sorted(
                            g.players.values_list("username", flat=True),
                        )
                    ),
                ]
                for g in Game.objects.select_related("month").prefetch_related("players").order_by(
                    "played_at"
                )
            ],
        )

        _add_sheet(
            wb,
            "Оплаты",
            [
                "id",
                "game_id",
                "player_id",
                "player_username",
                "amount",
                "method",
                "paid_on",
                "status",
                "comment",
                "created_at",
            ],
            [
                [
                    p.id,
                    p.game_id,
                    p.player_id,
                    getattr(p.player, "username", ""),
                    float(p.amount),
                    p.method,
                    p.paid_on,
                    p.status,
                    p.comment,
                    p.created_at,
                ]
                for p in Payment.objects.select_related("player").order_by("created_at")
            ],
        )

        _add_sheet(
            wb,
            "Траты",
            ["id", "month_id", "title", "amount", "spent_on", "paid_by", "comment"],
            [
                [
                    e.id,
                    e.month_id,
                    e.title,
                    float(e.amount),
                    e.spent_on,
                    str(e.paid_by) if e.paid_by else "",
                    e.comment,
                ]
                for e in Expense.objects.select_related("paid_by").order_by("spent_on", "id")
            ],
        )

        _add_sheet(
            wb,
            "Взносы_на_траты",
            [
                "id",
                "expense_id",
                "player_id",
                "player_username",
                "amount",
                "method",
                "paid_on",
                "status",
                "comment",
                "created_at",
            ],
            [
                [
                    c.id,
                    c.expense_id,
                    c.player_id,
                    getattr(c.player, "username", ""),
                    float(c.amount),
                    c.method,
                    c.paid_on,
                    c.status,
                    c.comment,
                    c.created_at,
                ]
                for c in ExpenseContribution.objects.select_related("player").order_by("created_at")
            ],
        )

        _add_sheet(
            wb,
            "Пользователи",
            ["id", "username", "first_name", "last_name", "email", "is_staff", "is_superuser", "is_active", "date_joined"],
            [
                [
                    u.id,
                    u.username,
                    getattr(u, "first_name", ""),
                    getattr(u, "last_name", ""),
                    getattr(u, "email", ""),
                    u.is_staff,
                    u.is_superuser,
                    u.is_active,
                    getattr(u, "date_joined", None),
                ]
                for u in User.objects.order_by("date_joined", "id")
            ],
        )

        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)

        filename = "football_cashbox_export.xlsx"
        resp = HttpResponse(
            buf.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp


admin_site = FootballAdminSite(name="football_admin")

