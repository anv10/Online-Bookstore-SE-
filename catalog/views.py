from django.core.paginator import Paginator
from django.db.models import Avg, Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, render
from .forms import SearchForm
from .models import Book, BookImage
from .forms import ListingForm
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import redirect


def catalog(request):
    books = Book.objects.filter(status=Book.Status.APPROVED, seller__is_active=True).select_related("seller").prefetch_related("images").order_by("title", "pk")
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


@login_required
def listing_add(request):
    if not request.user.has_perm("catalog.add_book"):
        raise PermissionDenied
    form = ListingForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            book = form.save(commit=False)
            book.seller = request.user
            book.status = Book.Status.PENDING
            book.save()
            for upload in form.cleaned_data["images"]:
                BookImage.objects.create(book=book, image=upload)
        messages.success(request, "Listing saved as Pending approval. It will be public after admin approval.")
        return redirect("seller_listings")
    return render(request, "catalog/add.html", {"form": form})


@login_required
def seller_listings(request):
    if not request.user.has_perm("catalog.add_book"):
        raise PermissionDenied
    return render(request, "catalog/seller_listings.html", {"books": Book.objects.filter(seller=request.user).order_by("-created_at")})


def book_detail(request, pk):
    book = get_object_or_404(Book, pk=pk)
    # Listings that are not approved (status arrives with the seller listing feature) stay hidden.
    if book.status != Book.Status.APPROVED or (book.seller and not book.seller.is_active):
        raise Http404("Book not found")
    reviews = book.reviews.select_related("user").order_by("-created_at")
    summary = reviews.aggregate(average=Avg("rating"), count=Count("pk"))
    return render(
        request,
        "catalog/detail.html",
        {"book": book, "reviews": reviews, "average_rating": summary["average"], "review_count": summary["count"]},
    )

