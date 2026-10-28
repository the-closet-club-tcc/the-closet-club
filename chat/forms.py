from django import forms

from .models import Report


class ReportForm(forms.ModelForm):
    detail = forms.CharField(required=False, max_length=500, strip=True)

    class Meta:
        model = Report
        fields = ['reason', 'detail']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['reason'].error_messages['required'] = 'Pilih alasan laporan.'
        self.fields['reason'].error_messages['invalid_choice'] = 'Pilih alasan laporan.'
        self.fields['detail'].error_messages['max_length'] = 'Keterangan maksimal 500 karakter.'

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('reason') == Report.Reason.OTHER and not cleaned.get('detail'):
            self.add_error('detail', 'Jelaskan laporanmu pada kolom keterangan.')
        return cleaned