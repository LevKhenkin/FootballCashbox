from django import forms
from django.contrib.auth import get_user_model

from .models import ExpenseContribution, Payment

User = get_user_model()


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ["amount", "method", "paid_on", "comment"]
        widgets = {
            "paid_on": forms.DateInput(attrs={"type": "date"}),
            "comment": forms.TextInput(attrs={"placeholder": "Например: перевёл на карту"}),
        }

    def __init__(self, *args, game=None, player=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.game = game
        self.player = player
        if game is not None and not self.initial.get("amount"):
            debt = game.debt_of(player) if player is not None else game.share_per_player
            if debt:
                self.fields["amount"].initial = debt

    def save(self, commit=True):
        payment = super().save(commit=False)
        if self.game is not None:
            payment.game = self.game
        if self.player is not None:
            payment.player = self.player
        if commit:
            payment.save()
        return payment


class ExpenseContributionForm(forms.ModelForm):
    class Meta:
        model = ExpenseContribution
        fields = ["amount", "method", "paid_on", "comment"]
        widgets = {
            "paid_on": forms.DateInput(attrs={"type": "date"}),
            "comment": forms.TextInput(attrs={"placeholder": "Например: перевёл на карту"}),
        }

    def __init__(self, *args, expense=None, player=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.expense = expense
        self.player = player
        if expense is not None and not self.initial.get("amount"):
            if expense.remaining_total:
                self.fields["amount"].initial = expense.remaining_total

    def save(self, commit=True):
        contribution = super().save(commit=False)
        if self.expense is not None:
            contribution.expense = self.expense
        if self.player is not None:
            contribution.player = self.player
        if commit:
            contribution.save()
        return contribution


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "username"]
        labels = {
            "first_name": "Имя",
            "last_name": "Фамилия",
            "email": "Email",
            "username": "Логин",
        }
        widgets = {
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "username": forms.TextInput(attrs={"autocomplete": "username"}),
        }

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip()
        return email
