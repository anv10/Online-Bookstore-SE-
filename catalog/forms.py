from django import forms

class SearchForm(forms.Form):
    q = forms.CharField(required=False, max_length=255, label="Title, author or ISBN")

    def clean_q(self):
        q = self.cleaned_data["q"].strip()
        if not q and "q" in self.data:
            raise forms.ValidationError("Enter a search term.")
        return q
