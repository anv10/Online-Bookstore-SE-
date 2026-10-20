from django.core.paginator import Paginator
from django.db.models import Avg, Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, render
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


def book_detail(request, pk):
    book = get_object_or_404(Book, pk=pk)
    # Listings that are not approved (status arrives with the seller listing feature) stay hidden.
    if getattr(book, "status", "approved") != "approved":
        raise Http404("Book not found")
    reviews = book.reviews.select_related("user").order_by("-created_at")
    summary = reviews.aggregate(average=Avg("rating"), count=Count("pk"))
    return render(
        request,
        "catalog/detail.html",
        {"book": book, "reviews": reviews, "average_rating": summary["average"], "review_count": summary["count"]},
    )
