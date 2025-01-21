import jazzmin.widgets
from django import forms

from casebook.models import Filter


def get_choices():
    filters = Filter.objects.all()
    choices = tuple()
    for filter_ in filters:
        select = (filter_.filter_id, filter_.name)
        choices = choices + (select,)
    return choices


class SetupParseForm(forms.Form):
    # select = forms.ChoiceField(choices=get_choices(), label='Выбрать фильтр',
    #                            widget=forms.Select(attrs={'class': 'form-select'}))
    select = forms.ModelChoiceField(queryset=Filter.objects.values('name', 'filter_id').all(), label='Выбрать фильтр',
                                    widget=forms.Select(attrs={'class': 'form-select', 'style': 'border-radius: 5px; padding: 5px'}))
    interval = forms.IntegerField(label='Интервал между проверками в минутах', min_value=20, initial=20)
    time_delta = forms.IntegerField(label='Давность кейсов в днях', min_value=2, initial=10)
    to_load = forms.ChoiceField(label='Кого загружать как клиента в Б24',
                                choices={0: 'Ответчик', 1: 'Истец'}, required=True,
                                initial=0, widget=forms.Select(attrs={'class': 'form-select', 'style': 'border-radius: 5px; padding: 5px'}))
    scan_r = forms.BooleanField(label='Стоп слова по ответчикам', initial=True, required=False)
    scan_p = forms.BooleanField(label='Стоп слова по истцам', initial=False, required=False)
    cash = forms.IntegerField(label='Сумма иска (от)', min_value=0, initial=300000, required=False)
    contacts = forms.IntegerField(label='Количество номеров к загрузке', min_value=0, initial=20)
    emails = forms.IntegerField(label='Количество email-ов к загрузке', min_value=0, initial=20)



class ExcelReportForm(forms.Form):
    start_date = forms.DateField(label='с')
    end_date = forms.DateField(label='по')
