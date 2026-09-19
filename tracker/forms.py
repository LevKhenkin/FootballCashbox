from django import forms

from .models import Payment


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
