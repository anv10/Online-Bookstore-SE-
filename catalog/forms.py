from django import forms

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


