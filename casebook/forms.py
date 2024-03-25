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
                                    widget=forms.Select(attrs={'class': 'form-select'}))
    interval = forms.IntegerField(label='Интервал между проверками в минутах', min_value=20, initial=20)
    time_delta = forms.IntegerField(label='Давность кейсов в днях', min_value=2, initial=10)


