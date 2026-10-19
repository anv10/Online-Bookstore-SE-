from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render
from .forms import SearchForm
from .models import Book


def catalog(request):
    books = Book.objects.order_by("title", "pk")
    genres = list(books.exclude(category="").values_list("category", flat=True).distinct().order_by("category"))
    form = SearchForm(request.GET if request.GET else None, genres=genres)
    if form.is_bound:
        if form.is_valid():
            query = form.cleaned_data.get("q")
            if query:
                books = books.filter(Q(title__icontains=query) | Q(author__icontains=query) | Q(isbn=query))
            if form.cleaned_data.get("genre"):
                books = books.filter(category__in=form.cleaned_data["genre"])
            if form.cleaned_data.get("min_price") is not None:
                books = books.filter(price__gte=form.cleaned_data["min_price"])
            if form.cleaned_data.get("max_price") is not None:
                books = books.filter(price__lte=form.cleaned_data["max_price"])
        else:
            books = books.none()
    page = Paginator(books, 9).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    return render(request, "catalog/list.html", {"form": form, "page_obj": page, "query": query.urlencode()})
