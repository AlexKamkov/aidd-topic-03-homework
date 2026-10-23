from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect, render
from django.views.generic import View

from .forms import AuthForm, RegistrationForm


class AuthView(View):
    """Авторизация"""

    @staticmethod
    def get(request):
        # В контекст передаётся экземпляр формы, а не класс: иначе шаблон
        # рендерит repr поля вместо <input>.
        return render(request, "user/auth.html", {"form": AuthForm()})

    @staticmethod
    def post(request):
        form = AuthForm(request.POST)
        if not form.is_valid():
            return render(
                request,
                "user/auth.html",
                {"form": form, "error": "Введите корректный email и пароль."},
            )

        user = authenticate(
            request,
            username=form.cleaned_data["email"].lower(),
            password=form.cleaned_data["password"],
        )

        if user is not None:
            login(request, user)
            return redirect("dashboard:index")
        else:
            return render(
                request,
                "user/auth.html",
                {
                    "form": form,
                    "error": "Неверный логин или пароль! Повторите попытку.",
                },
            )


class RegistrationView(View):
    """Регистрация"""

    @staticmethod
    def get(request):
        # В контекст передаётся экземпляр формы, а не класс.
        return render(request, "user/registration.html", {"form": RegistrationForm()})

    @staticmethod
    def _first_error(form):
        """Безопасно достаёт первую ошибку валидации формы."""
        all_errors = form.errors.get("__all__", [])
        if all_errors:
            return all_errors[0]
        for messages in form.errors.values():
            if messages:
                return messages[0]
        return "Ошибка валидации формы."

    @staticmethod
    def post(request):
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("dashboard:index")
        else:
            # Исходный код обращался к form.errors["__all__"].data[0], что
            # падало с KeyError, когда ошибка относилась к конкретному полю.
            return render(
                request,
                "user/registration.html",
                {"form": form, "error": RegistrationView._first_error(form)},
            )


class LogoutView(View):
    """Выход"""

    @staticmethod
    def get(request):
        logout(request)
        return redirect("dashboard:index")
