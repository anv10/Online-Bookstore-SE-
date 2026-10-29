from django import forms

from . import payments


class SensitiveInput(forms.TextInput):
    """Never echo a card value back into the page after a failed submission."""

    def format_value(self, value):
        return ""


class CheckoutForm(forms.Form):
    shipping_address = forms.CharField(
        label="Shipping address",
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "autocomplete": "street-address",
                "placeholder": "Flat, street, city, postal code, country",
            }
        ),
        error_messages={"required": "Shipping address is required."},
    )
    card_number = forms.CharField(
        label="Card number",
        max_length=23,
        widget=SensitiveInput(attrs={"inputmode": "numeric", "autocomplete": "cc-number", "placeholder": "4242 4242 4242 4242"}),
        error_messages={"required": "Invalid card number."},
    )
    card_expiry = forms.CharField(
        label="Expiry date",
        max_length=5,
        widget=SensitiveInput(attrs={"inputmode": "numeric", "autocomplete": "cc-exp", "placeholder": "MM/YY"}),
        error_messages={"required": "Invalid expiry date."},
    )
    card_cvc = forms.CharField(
        label="Security code",
        widget=SensitiveInput(attrs={"inputmode": "numeric", "autocomplete": "cc-csc", "placeholder": "123"}),
        error_messages={"required": "Invalid security code."},
    )

    def clean_shipping_address(self):
        address = self.cleaned_data["shipping_address"].strip()
        if not address:
            raise forms.ValidationError("Shipping address is required.")
        return address

    def clean_card_number(self):
        return self._cleaned_card_field("card_number", payments.clean_number)

    def clean_card_expiry(self):
        return self._cleaned_card_field("card_expiry", payments.clean_expiry)

    def clean_card_cvc(self):
        return self._cleaned_card_field("card_cvc", payments.clean_cvc)

    def _cleaned_card_field(self, field, cleaner):
        try:
            return cleaner(self.cleaned_data[field])
        except payments.PaymentError as error:
            raise forms.ValidationError(str(error)) from error

    def card(self):
        return payments.CardDetails(
            number=self.cleaned_data["card_number"],
            expiry=self.cleaned_data["card_expiry"],
            cvc=self.cleaned_data["card_cvc"],
        )
