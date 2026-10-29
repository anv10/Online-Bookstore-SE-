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

    class Meta:
        model = Review
        fields = ["rating", "comment"]
        widgets = {
            "comment": forms.Textarea(
                attrs={"rows": 4, "maxlength": 2000, "placeholder": "Optional: say what you thought of the book"}
            )
        }
        labels = {"comment": "Review (optional)"}

    def clean_comment(self):
        comment = self.cleaned_data.get("comment", "").strip()
        if len(comment) > 2000:
            raise forms.ValidationError("Keep your review to 2000 characters or fewer.")
        return comment
