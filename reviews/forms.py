from django import forms

from .models import Review

RATING_CHOICES = [(value, f"{value} star{'s' if value != 1 else ''}") for value in range(1, 6)]


class ReviewForm(forms.ModelForm):
    rating = forms.TypedChoiceField(
        choices=RATING_CHOICES,
        coerce=int,
        error_messages={
            "required": "Rating must be between 1 and 5.",
            "invalid_choice": "Rating must be between 1 and 5.",
        },
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # FR-10 (Test Plan FR-10_UT02): the review text is mandatory. The model keeps
        # blank=True so existing rows and administrative edits are not broken.
        self.fields["comment"].required = True
        self.fields["comment"].error_messages["required"] = "Review text is required."
        self.fields["comment"].widget.attrs["placeholder"] = "Say what you thought of the book"

    class Meta:
        model = Review
        fields = ["rating", "comment"]
        widgets = {
            "comment": forms.Textarea(attrs={"rows": 4, "maxlength": 2000})
        }
        labels = {"comment": "Review"}

    def clean_comment(self):
        comment = (self.cleaned_data.get("comment") or "").strip()
        if not comment:
            raise forms.ValidationError("Review text is required.")
        if len(comment) > 2000:
            raise forms.ValidationError("Keep your review to 2000 characters or fewer.")
        return comment
