from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm


User = get_user_model()


class SignUpForm(UserCreationForm):
    first_name = forms.CharField(label="Имя", max_length=150, required=False)
    last_name = forms.CharField(label="Фамилия", max_length=150, required=False)
    email = forms.EmailField(label="Email", required=False)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "email", "password1", "password2")
        labels = {"username": "Логин"}

    def save(self, commit=True):
        user = super().save(commit=False)
        user.first_name = (self.cleaned_data.get("first_name") or "").strip()
        user.last_name = (self.cleaned_data.get("last_name") or "").strip()
        user.email = (self.cleaned_data.get("email") or "").strip()
        # Ensure player role (no staff/superuser flags).
        user.is_staff = False
        user.is_superuser = False
        if commit:
            user.save()
        return user

