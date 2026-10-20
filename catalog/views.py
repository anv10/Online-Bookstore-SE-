from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render
from .forms import SearchForm
from .models import Book


def catalog(request):
    books = Book.objects.order_by("title", "pk")
    form = SearchForm(request.GET if request.GET else None)
    if form.is_bound:
        if form.is_valid():
            query = form.cleaned_data.get("q")
            if query:
                books = books.filter(Q(title__icontains=query) | Q(author__icontains=query) | Q(isbn=query))
        else:
            books = books.none()
    page = Paginator(books, 9).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    return render(request, "catalog/list.html", {"form": form, "page_obj": page, "query": query.urlencode()})
