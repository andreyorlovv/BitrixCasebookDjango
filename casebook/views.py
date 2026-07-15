import datetime
import io
import json
import os
import re
import tempfile

import xlsxwriter

from django.contrib.admin import site
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils import timezone
from requests.exceptions import SSLError
from rest_framework.decorators import api_view

import casebook.tasks
from BitrixCasebook import settings
from casebook.forms import SetupParseForm
from casebook.models import Filter, Tasks, BlackList, Case
from casebook.tasks import get_tasks_from_db


@login_required(login_url='/login/')
def custom_index(request):
    import datetime
    if request.method == "POST":
        form = SetupParseForm(request.POST)
        import ast
        select_data = ast.literal_eval(form.data['select'])
        Tasks.objects.create(days_expire=form.data['time_delta'],
                             iteration_interval=form.data['interval'],
                             filter_id=select_data['filter_id'],
                             to_load=form.data['to_load'],
                             cash=form.data['cash'] if form.data['cash'] else None,
                             contacts=form.data['contacts'],
                             emails=form.data['emails'],
                             last_execution=None,
                             scan_r=True if form.data.get('scan_r') == 'on' else False,
                             scan_p=True if form.data.get('scan_p') == 'on' else False,
                             )
        get_tasks_from_db.apply_async()
    filters = Filter.objects.all()
    form_create = SetupParseForm()
    tasks = Tasks.objects.all()
    tasks_to_render = []
    for task in tasks:
        tasks_to_render.append({
            'task_id': task.id,
            'filter': task.filter_id,
            'time_delta': datetime.date.today() - datetime.timedelta(task.days_expire),
            'interval': task.iteration_interval,
            'name': Filter.objects.filter(filter_id=task.filter_id).first().name
        })
    import requests
    try:
        remaining_export_base = requests.get(
            f'https://export-base.ru/api/balance/?key={settings.EXPORT_BASE_API_KEY}',
            timeout=15
        )
        remaining_export_base.raise_for_status()
        remaining_export_base = remaining_export_base.text
    except requests.exceptions.Timeout:
        remaining_export_base = 'Ошибка в подключении к ЭкспортБейс (timeout), СВЯЖИТЕСЬ С РАЗРАБОТЧИКОМ!'
    except SSLError as e:
        remaining_export_base = 'Ошибка в подключении к ЭкспортБейс, СВЯЖИТЕСЬ С РАЗРАБОТЧИКОМ, СКОРЕЕ ВСЕГО ПРОБЕЛМА ЕСТЬ И В ПОЛУЧЕНГИИ КОНТАКТНЫХ ДАННЫХ!!!!'
    except Exception as e:
        if os.environ.get('local_debug') == 'True':
            remaining_export_base = 'Локальное окружение, взаимодействия с ExportBase отключено'

    from django.core.cache import cache
    remaining_checko = cache.get('checko_balance')
    if remaining_checko is None:
        try:
            checko_resp = requests.get(
                'https://api.checko.ru/v2/company',
                params={'key': settings.CHECKO_API_KEY, 'inn': '7707083893'},
                timeout=15,
            )
            checko_resp.raise_for_status()
            remaining_checko = (checko_resp.json().get('meta') or {}).get('balance')
            if remaining_checko is not None:
                cache.set('checko_balance', remaining_checko, timeout=600)  # 10 мин
        except requests.exceptions.Timeout:
            remaining_checko = 'Ошибка подключения к Checko (timeout)'
        except SSLError:
            remaining_checko = 'Ошибка подключения к Checko (SSL)'
        except Exception as e:
            print(e)
            remaining_checko = ('Локальное окружение, Checko отключён'
                                if os.environ.get('local_debug') == 'True' else None)

    extra_context = {'filters': filters, 'form_create': form_create,
                     'tasks': tasks_to_render,
                     'remaining_export_base': remaining_export_base,
                     'remaining_checko': remaining_checko}
    return site.index(request, extra_context=extra_context)


@login_required(login_url='/login/')
def process_task(request):
    task_id = request.GET.get('task_id')
    casebook.tasks.scan_enchanted.apply_async(
        args=(task_id,),
        expires=7200,
        soft_time_limit=6600,
        time_limit=7200
    )
    return redirect('/')


@login_required(login_url='/login/')
def upload_excel_for_task(request):
    """
    Сохраняет загруженный файл во временный файл на диске,
    передаёт в Celery только путь — чтобы не превышать лимит брокера.
    XLSX конвертируется в CSV (windows-1251, ;) перед сохранением.
    """
    if request.method != 'POST':
        return redirect('/')

    task_id = request.POST.get('task_id')
    uploaded_file = request.FILES.get('excel_file')

    if not task_id or not uploaded_file:
        return redirect('/')

    filename = uploaded_file.name.lower()

    # Папка для временных файлов — берём из настроек или /tmp
    upload_dir = getattr(settings, 'CASEBOOK_UPLOAD_DIR', tempfile.gettempdir())
    os.makedirs(upload_dir, exist_ok=True)

    try:
        if filename.endswith('.xlsx') or filename.endswith('.xls'):
            # XLSX → конвертируем в CSV windows-1251 с ; (родной формат Casebook)
            import pandas as pd
            df = pd.read_excel(io.BytesIO(uploaded_file.read()))
            tmp = tempfile.NamedTemporaryFile(
                delete=False, suffix='.csv', dir=upload_dir
            )
            df.to_csv(tmp.name, index=False, sep=';', encoding='windows-1251')
            tmp_path = tmp.name
            tmp.close()
        else:
            # CSV — пишем на диск чанками, не грузим всё в память
            tmp = tempfile.NamedTemporaryFile(
                delete=False, suffix='.csv', dir=upload_dir
            )
            for chunk in uploaded_file.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name
            tmp.close()

    except Exception:
        return redirect('/')

    casebook.tasks.scan_enchanted_manual.apply_async(
        args=(task_id, tmp_path),
        expires=7200,
        soft_time_limit=6600,
        time_limit=7200,
    )

    return redirect('/')


@login_required(login_url='/login/')
def process_delete_task(request):
    Tasks.objects.get(id=request.GET.get('id')).delete()
    return redirect('/')


# Поля стороны в дампе объекта Case, который сохраняется в error_message успешных дел:
# ...target=Side(name='...', inn='...', ogrn='...', ...), other_side=Side(name='...', inn='...', ...)...
_SIDE_STR = r"(None|'.*?'|\".*?\")"


def _extract_side(dump, field):
    """Возвращает (наименование, ИНН) стороны `field` ('target' | 'other_side'),
    распарсенные из строкового дампа объекта Case в поле error_message.
    Если дампа нет или он не распознан (например, это реальный текст ошибки) — ('', '')."""
    if not dump:
        return '', ''

    match = re.search(
        field + r"=Side\(name=" + _SIDE_STR + r", inn=" + _SIDE_STR,
        dump,
    )
    if not match:
        return '', ''

    def _clean(value):
        if not value or value == 'None':
            return ''
        return value[1:-1]  # снимаем обрамляющие кавычки из repr-строки

    return _clean(match.group(1)), _clean(match.group(2))


@login_required(login_url='/login/')
@staff_member_required
def download_xlsx_view(request):
    queryset = Case.objects.all().select_related('from_task')

    date_from = request.GET.get('from')
    date_to = request.GET.get('to')

    if date_from or date_to:
        queryset = queryset.filter(process_date__range=[date_from, date_to])

    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    worksheet = workbook.add_worksheet()

    headers = [
        'id кейса', 'Номер дела в арбитре', 'Дата обработки',
        'Успешно обработано (?)', 'Ошибка, если есть', 'Подборка',
        'Ссылка на лид в Б24', 'Контакты',
        'Целевая сторона (наименование)', 'Целевая сторона (ИНН)',
        'Контрагент (наименование)', 'Контрагент (ИНН)',
    ]
    for col, header in enumerate(headers):
        worksheet.write(0, col, header)

    row = 1
    for item in queryset:
        worksheet.write(row, 0, item.id)
        worksheet.write(row, 1, item.case_id)
        # process_date хранится в UTC (USE_TZ=True) — переводим в локальную зону
        # (Europe/Moscow), иначе даты возле полуночи уезжают на сутки назад.
        p_date = timezone.localtime(item.process_date).strftime('%d.%m.%Y') if item.process_date else ''
        worksheet.write(row, 2, p_date)
        worksheet.write(row, 3, 'Да' if item.is_success else 'Нет')
        # У успешных дел в error_message лежит дамп объекта, а не текст ошибки —
        # в колонку «Ошибка» его не выводим.
        worksheet.write(row, 4, '' if item.is_success else (item.error_message or ''))
        task_name = item.from_task.name if item.from_task else 'Не указана'
        worksheet.write(row, 5, task_name)
        lead_url = f'https://crm.yk-cfo.ru/crm/lead/details/{item.bitrix_lead_id}' if item.bitrix_lead_id else 'Не загружено'
        worksheet.write(row, 6, lead_url)
        worksheet.write(row, 7, item.contacts if item.contacts else 'Не загружено')

        target_name, target_inn = _extract_side(item.error_message, 'target')
        other_name, other_inn = _extract_side(item.error_message, 'other_side')
        worksheet.write(row, 8, target_name)
        worksheet.write(row, 9, target_inn)
        worksheet.write(row, 10, other_name)
        worksheet.write(row, 11, other_inn)
        row += 1

    workbook.close()
    output.seek(0)

    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        content=output.read()
    )
    response['Content-Disposition'] = f"attachment; filename={datetime.datetime.now().strftime('%Y%m%d-%H%M')}.xlsx"
    return response


@api_view(['POST'])
def add_to_blacklist(request):
    if request.method == 'POST':
        body_json = json.loads(request.body)
        response_body = []
        for item in body_json:
            new_bl = BlackList(
                value=item['value'],
                type=item['type']
            )
            new_bl.save()
            response_body.append(
                {
                    'id': new_bl.id,
                    'value': new_bl.value,
                    'type': new_bl.type
                }
            )
        return HttpResponse(status=201, content=json.dumps(response_body))


def update_filters(request):
    casebook.tasks.update_filters.apply_async()
    return redirect('/')
