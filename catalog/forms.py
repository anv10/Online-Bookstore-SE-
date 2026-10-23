from pathlib import Path

from django import forms
from PIL import Image, UnidentifiedImageError

from .models import Book, BookImage

class SearchForm(forms.Form):
    q = forms.CharField(required=False, max_length=255, label="Title, author or ISBN")
    genre = forms.MultipleChoiceField(required=False, widget=forms.CheckboxSelectMultiple)
    min_price = forms.DecimalField(required=False, min_value=0, max_digits=8, decimal_places=2)
    max_price = forms.DecimalField(required=False, min_value=0, max_digits=8, decimal_places=2)

    def __init__(self, *args, genres=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["genre"].choices = [(g, g) for g in genres]

    def clean(self):
        data = super().clean()
        low, high = data.get("min_price"), data.get("max_price")
        if low is not None and high is not None and low > high:
            raise forms.ValidationError("Minimum price cannot exceed maximum price.")
        if self.is_bound and not any([data.get("q"), data.get("genre"), low is not None, high is not None]) and "q" in self.data:
            raise forms.ValidationError("Enter a search term or choose a filter.")
        return data


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class ImagesField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        if not data:
            return []
        files = data if isinstance(data, (list, tuple)) else [data]
        if len(files) > 5:
            raise forms.ValidationError("Upload up to five images per listing.")
        for upload in files:
            super().clean(upload, initial)
            if upload.size > 2 * 1024 * 1024:
                raise forms.ValidationError("Each image must be no larger than 2 MB.")
            if Path(upload.name).suffix.lower() not in {".png", ".jpg", ".jpeg"}:
                raise forms.ValidationError("Use PNG or JPEG images.")
            try:
                image = Image.open(upload)
                if image.format not in {"PNG", "JPEG"} or image.width * image.height > 20_000_000:
                    raise forms.ValidationError("Use PNG/JPEG images up to 20 megapixels.")
                image.verify()
            except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
                raise forms.ValidationError("Upload a valid PNG or JPEG image.")
            finally:
                upload.seek(0)
        return files


class ListingForm(forms.ModelForm):
    category = forms.CharField(max_length=100, label="Genre")
    images = ImagesField(required=False, label="Images (up to 5 PNG/JPEG files, 2 MB each)")

    class Meta:
        model = Book
        fields = ["title", "author", "isbn", "category", "price", "condition", "stock", "description"]
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}

    def clean_isbn(self):
        value = self.cleaned_data["isbn"].replace("-", "").replace(" ", "")
        if not value.isascii():
            raise forms.ValidationError("Enter a valid ISBN-10 or ISBN-13, including its check digit.")
        valid = False
        if len(value) == 13 and value.isdigit():
            valid = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(value)) % 10 == 0
        if len(value) == 10 and value[:9].isdigit() and (value[-1].isdigit() or value[-1] == "X"):
            digits = [int(c) for c in value[:9]] + [10 if value[-1] == "X" else int(value[-1])]
            valid = sum((10-i)*d for i, d in enumerate(digits)) % 11 == 0
        if not valid:
            raise forms.ValidationError("Enter a valid ISBN-10 or ISBN-13, including its check digit.")
        return value


class EditListingForm(ListingForm):
    remove_images = forms.ModelMultipleChoiceField(
        queryset=BookImage.objects.none(), required=False, widget=forms.CheckboxSelectMultiple, label="Remove images"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["images"].label = "Add images (up to 5 PNG/JPEG files in total, 2 MB each)"
        self.fields["remove_images"].queryset = self.instance.images.all()
        self.fields["remove_images"].label_from_instance = lambda image: Path(image.image.name).name

    def clean(self):
        data = super().clean()
        removed = data.get("remove_images")
        kept = self.instance.images.count() - (len(removed) if removed else 0)
        if kept + len(data.get("images") or []) > 5:
            raise forms.ValidationError("A listing can have at most five images in total.")
        return data
