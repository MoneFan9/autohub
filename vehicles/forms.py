from django import forms

from .models import Report


class ReportForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = ["reason", "message", "contact"]
        labels = {"contact": "Votre téléphone ou e-mail (facultatif)"}
        widgets = {"message": forms.Textarea(attrs={"rows": 3}), "reason": forms.Select}

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("label_suffix", "")
        super().__init__(*args, **kwargs)
        self.fields["reason"].choices = [("", "Choisissez un motif")] + list(Report.Reason.choices)
