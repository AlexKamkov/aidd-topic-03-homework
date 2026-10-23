from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from user.models import User


class RegistrationForm(forms.Form):
    """Форма регистрации пользователей"""

    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(
            attrs={"class": "form-control my-3 p-4", "placeholder": "Email"}
        ),
    )
    password1 = forms.CharField(
        required=True,
        widget=forms.PasswordInput(
            attrs={"class": "form-control my-3 p-4", "placeholder": "Пароль"}
        ),
    )
    password2 = forms.CharField(
        required=True,
        widget=forms.PasswordInput(
            attrs={"class": "form-control my-3 p-4", "placeholder": "Повторите пароль"}
        ),
    )

    def clean(self):
        super().clean()
        # Поля могут отсутствовать в cleaned_data, если их собственная валидация
        # не прошла — прямое обращение к ним давало KeyError (500).
        email = self.cleaned_data.get("email")
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")

        errors = []

        if password1 and password2 and password1 != password2:
            errors.append("Введенные пароли не совпадают")
        elif password1:
            validate_password(password1, User(username=email))

        if email:
            # Username в БД хранится в нижнем регистре (см. save()), поэтому
            # проверка дубликата выполняется по нормализованному адресу.
            if User.objects.filter(username__iexact=email).exists():
                errors.append(
                    "Данный e-mail уже зарегистрирован! Введите другой e-mail или"
                    " воспользуйтесь формой авторизации."
                )

        if errors:
            raise ValidationError(errors)

    def save(self):
        # Username нормализуется: AuthView ищет пользователя по email.lower(),
        # и без приведения к нижнему регистру вход не работал бы.
        email = self.cleaned_data["email"].lower()
        password = self.cleaned_data["password1"]
        User.objects.create_user(email, email, password)
        user = authenticate(username=email, password=password)
        return user


class AuthForm(forms.Form):
    """Форма авторизации пользователей"""

    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(
            attrs={"class": "form-control my-3 p-4", "placeholder": "Email"}
        ),
    )
    password = forms.CharField(
        required=True,
        widget=forms.PasswordInput(
            attrs={"class": "form-control my-3 p-4", "placeholder": "Пароль"}
        ),
    )
