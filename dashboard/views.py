from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.generic import CreateView, DeleteView, ListView, UpdateView, View

from .forms import PortfolioForm, PortfolioTransactionForm, ShareModelForm
from .models import Portfolio, PortfolioTransaction, Share
from .services.graph import get_graph
from .services.portfolio import PortfolioError
from .services.portfolio import buy as portfolio_buy
from .services.portfolio import calculate_portfolio
from .services.portfolio import sell as portfolio_sell


class IsUserAuthenticatedMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_authenticated

    @staticmethod
    def handle_no_permission():
        return redirect("dashboard:index")


class ShareListView(ListView):
    """Список акций"""

    model = Share
    template_name = "dashboard/list.html"
    paginate_by = 100
    ordering = ["name"]


class ShareDetailView(View):
    @staticmethod
    def get(request, pk):
        # get_object_or_404 вместо Share.objects.get: несуществующий pk должен
        # отдавать 404, а не падать с DoesNotExist (500).
        share = get_object_or_404(Share, pk=pk)

        return render(
            request,
            "dashboard/detail.html",
            {"plot_div": get_graph(share), "share": share},
        )


class ShareCreateView(IsUserAuthenticatedMixin, CreateView):
    """Добавление инструмента"""

    template_name = "dashboard/create.html"
    form_class = ShareModelForm
    success_url = reverse_lazy("dashboard:index")


class ShareUpdateView(IsUserAuthenticatedMixin, UpdateView):
    """Редактирование инструмента"""

    model = Share
    template_name = "dashboard/create.html"
    form_class = ShareModelForm
    success_url = reverse_lazy("dashboard:index")


class ShareDeleteView(IsUserAuthenticatedMixin, DeleteView):
    """Удаление задачи"""

    model = Share
    template_name = "dashboard/delete.html"
    success_url = reverse_lazy("dashboard:index")


# ====================================================================
# Виртуальный инвестиционный портфель
# ====================================================================


class PortfolioListView(LoginRequiredMixin, ListView):
    """Список портфелей текущего пользователя."""

    model = Portfolio
    template_name = "dashboard/portfolio_list.html"
    context_object_name = "portfolios"
    ordering = ["name"]

    def get_queryset(self):
        return Portfolio.objects.filter(user=self.request.user)


class PortfolioCreateView(LoginRequiredMixin, CreateView):
    """Создание виртуального портфеля."""

    model = Portfolio
    form_class = PortfolioForm
    template_name = "dashboard/portfolio_form.html"
    success_url = reverse_lazy("dashboard:portfolio_list")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class PortfolioUpdateView(LoginRequiredMixin, UpdateView):
    """Редактирование виртуального портфеля."""

    model = Portfolio
    form_class = PortfolioForm
    template_name = "dashboard/portfolio_form.html"

    def get_queryset(self):
        return Portfolio.objects.filter(user=self.request.user)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs


class PortfolioDeleteView(LoginRequiredMixin, DeleteView):
    """Удаление виртуального портфеля."""

    model = Portfolio
    template_name = "dashboard/portfolio_delete.html"
    success_url = reverse_lazy("dashboard:portfolio_list")

    def get_queryset(self):
        return Portfolio.objects.filter(user=self.request.user)


class PortfolioDetailView(View):
    """Детальная страница портфеля с оценкой и историей операций."""

    @method_decorator(login_required)
    def get(self, request, pk):
        portfolio = get_object_or_404(
            Portfolio.objects.filter(user=request.user), pk=pk
        )

        valuation = calculate_portfolio(portfolio)
        transactions = portfolio.transactions.all()[:50]

        return render(
            request,
            "dashboard/portfolio_detail.html",
            {
                "portfolio": portfolio,
                "valuation": valuation,
                "transactions": transactions,
            },
        )


@login_required
def portfolio_transaction(request, portfolio_pk):
    """
    Проведение сделки: покупка или продажа акции.

    Бизнес-проверки (достаток средств, наличие позиции) делегированы сервисному
    слою; ошибки преобразуются в сообщение об ошибке на форме.
    """
    portfolio = get_object_or_404(
        Portfolio.objects.filter(user=request.user), pk=portfolio_pk
    )

    if request.method == "POST":
        form = PortfolioTransactionForm(request.POST, portfolio=portfolio)
        if form.is_valid():
            share = form.cleaned_data["share"]
            quantity = form.cleaned_data["quantity"]
            price = form.cleaned_data["price"]
            operation = form.cleaned_data["operation"]

            try:
                if operation == PortfolioTransaction.Operation.BUY:
                    portfolio_buy(portfolio, share, quantity, price)
                else:
                    portfolio_sell(portfolio, share, quantity, price)
            except PortfolioError as exc:
                form.add_error(None, str(exc))
            else:
                return redirect("dashboard:portfolio_detail", pk=portfolio.pk)

        return render(
            request,
            "dashboard/portfolio_transaction.html",
            {
                "portfolio": portfolio,
                "form": form,
            },
        )

    form = PortfolioTransactionForm(portfolio=portfolio)
    return render(
        request,
        "dashboard/portfolio_transaction.html",
        {
            "portfolio": portfolio,
            "form": form,
        },
    )
