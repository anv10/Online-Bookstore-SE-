from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from catalog.models import Book

from security import events

from . import content_filter
from .forms import ReviewForm
from .models import Review
from .services import has_delivered_purchase


def _visible_book(pk):
    return get_object_or_404(Book, pk=pk, status=Book.Status.APPROVED)


@login_required
@require_http_methods(["GET", "POST"])
def submit_review(request, pk):
    book = _visible_book(pk)
    review = Review.objects.filter(book=book, user=request.user).first()

    # A buyer gets one review per item. Submitting again is refused, and only the
    # "Edit your review" link (which carries ?edit=1) may change the existing one
    # (Test Plan FR-10_IT03).
    editing = request.GET.get("edit") == "1" or request.POST.get("edit") == "1"
    if review is not None and not editing:
        if request.method == "POST":
            messages.error(request, "You have already reviewed this item.")
        return redirect("book_detail", pk=book.pk)

    if review is None and not has_delivered_purchase(request.user, book):
        messages.error(request, "You must purchase this book to review it.")
        return redirect("book_detail", pk=book.pk)

    is_edit = review is not None
    form = ReviewForm(request.POST or None, instance=review)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                review = form.save(commit=False)
                review.book = book
                review.user = request.user
                flagged = content_filter.reasons(review.comment)
                review.status = Review.Status.HELD if flagged else Review.Status.PUBLISHED
                review.held_reason = ", ".join(flagged)
                review.save()
        except IntegrityError:
            # The unique constraint is the final guard if the same buyer submits twice concurrently.
            messages.error(request, "You have already reviewed this item.")
            return redirect("book_detail", pk=book.pk)
        if review.status == Review.Status.HELD:
            events.record(events.Kind.REVIEW_HELD, request, detail=f"review {review.pk}: {review.held_reason}")
            messages.info(request, "Thanks. Your review will appear once a moderator has checked it.")
            return redirect("book_detail", pk=book.pk)
        messages.success(request, "Your review was updated." if is_edit else "Thanks for your review.")
        return redirect("book_detail", pk=book.pk)
    return render(request, "reviews/form.html", {"book": book, "form": form, "review": review})
