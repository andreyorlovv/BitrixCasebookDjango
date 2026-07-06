import io
import re

from django.contrib import admin, messages
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import path

import casebook.tasks
from casebook.forms import ExcelReportForm
from casebook.models import Case, StopList, BlackList, Tasks, InfoDealB24, RequestCounter, Filter


# Register your models here.
class CaseAdmin(admin.ModelAdmin):
    change_form_template = 'admin/case_view.html'
    change_list_template = 'admin/casebook/Case/change_list.html'

    search_fields = ['case_id']
    list_filter = ['from_task']
    list_display = ('process_date', 'case_id', 'is_success', 'error_message', 'from_task')
    readonly_fields = ['bitrix_lead_id', 'from_task']

    def changelist_view(self, request, *args, **kwargs):

        return super().changelist_view(
            request, *args, **kwargs
        )

    def delete_view(self, request, object_id, extra_context=None):
        if request.method == 'POST':
            case = Case.objects.get(pk=object_id)
            casebook.tasks.delete_lead.apply_async(args=[case.bitrix_lead_id])
        return super().delete_view(
            request, object_id, extra_context=extra_context,
        )

    def change_view(self, request, object_id, form_url="", extra_context=None):
        return super().change_view(
            request, object_id, form_url=form_url, extra_context=extra_context,
        )


class StopListAdmin(admin.ModelAdmin):
    list_display = ('id', 'stopword')
    ordering = ('id',)

class RequestCounterAdmin(admin.ModelAdmin):
    list_display = ('id', 'date', 'count')

class InfoDealB24Admin(admin.ModelAdmin):
    list_display = ('b24_id',)
    ordering = ('date_casebook',)

class BlackListAdmin(admin.ModelAdmin):
    list_display = ('value', 'type', 'source', 'created_at')
    list_filter = ('type', 'source')
    search_fields = ('value',)
    change_list_template = 'admin/casebook/blacklist/change_list.html'

    def get_urls(self):
        custom_urls = [
            path(
                'upload-inn/',
                self.admin_site.admin_view(self.upload_inn_view),
                name='casebook_blacklist_upload_inn',
            ),
        ]
        return custom_urls + super().get_urls()

    def upload_inn_view(self, request):
        if request.method != 'POST':
            return redirect('..')

        uploaded_file = request.FILES.get('inn_file')
        if not uploaded_file:
            self.message_user(request, 'Файл не выбран.', level=messages.ERROR)
            return redirect('..')

        try:
            inns, invalid_count = self._extract_inns(uploaded_file)
        except Exception as e:
            self.message_user(request, f'Не удалось прочитать файл: {e}', level=messages.ERROR)
            return redirect('..')

        if not inns:
            self.message_user(
                request,
                'В файле не найдено ни одного корректного ИНН (10 или 12 цифр).',
                level=messages.WARNING,
            )
            return redirect('..')

        # Дубликаты считаем только среди уже существующих ИНН в чёрном списке
        existing = set(
            BlackList.objects.filter(type='inn').values_list('value', flat=True)
        )
        to_create = [
            BlackList(value=inn, type='inn', source='excel')
            for inn in inns
            if inn not in existing
        ]
        BlackList.objects.bulk_create(to_create)

        added = len(to_create)
        duplicates = len(inns) - added
        self.message_user(
            request,
            f'Загрузка завершена: добавлено {added}, '
            f'пропущено дубликатов {duplicates}, '
            f'некорректных значений {invalid_count}.',
            level=messages.SUCCESS,
        )
        return redirect('..')

    @staticmethod
    def _extract_inns(uploaded_file):
        """
        Сканирует все ячейки файла и собирает значения, похожие на ИНН
        (10 или 12 цифр). Возвращает (список_уникальных_ИНН, кол-во_некорректных).
        """
        import pandas as pd

        name = uploaded_file.name.lower()
        raw = uploaded_file.read()

        if name.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(io.BytesIO(raw), header=None, dtype=str)
        else:
            df = None
            for encoding in ('utf-8-sig', 'windows-1251'):
                try:
                    df = pd.read_csv(
                        io.BytesIO(raw), header=None, dtype=str,
                        sep=None, engine='python', encoding=encoding,
                    )
                    break
                except (UnicodeDecodeError, UnicodeError):
                    continue
            if df is None:
                raise ValueError('не удалось определить кодировку CSV-файла')

        seen = set()
        inns = []
        invalid_count = 0

        for value in df.values.ravel():
            if value is None:
                continue
            s = str(value).strip()
            if not s or s.lower() == 'nan':
                continue
            # хвост ".0" от числового представления Excel (1434031363.0)
            if s.endswith('.0'):
                s = s[:-2]
            digits = re.sub(r'\D', '', s)
            if not digits:
                continue  # заголовки типа "ИНН" просто пропускаем
            if len(digits) in (10, 12):
                if digits not in seen:
                    seen.add(digits)
                    inns.append(digits)
            else:
                invalid_count += 1

        return inns, invalid_count

admin.site.register(Case, CaseAdmin)
admin.site.register(StopList, StopListAdmin)
admin.site.register(BlackList, BlackListAdmin)
admin.site.register(Tasks)
admin.site.register(InfoDealB24, InfoDealB24Admin)
admin.site.register(RequestCounter, RequestCounterAdmin)
admin.site.register(Filter)
admin.site.site_header = 'Парсер Casebook'
