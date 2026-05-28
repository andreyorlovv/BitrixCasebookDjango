import datetime
import io
import json
import os

import xlsxwriter

from django.contrib.admin import site
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect
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
    extra_context = {'filters': filters, 'form_create': form_create,
                     'tasks': tasks_to_render, 'remaining_export_base': remaining_export_base}
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
    Принимает POST с файлом (CSV windows-1251/; или XLSX) и task_id.
    CSV от Casebook передаётся в задачу как есть (bytes).
    XLSX конвертируется в CSV windows-1251 с ; чтобы get_cases_via_excel
    читал его теми же параметрами, что и при автоматической выгрузке.
    """
    if request.method != 'POST':
        return redirect('/')

    task_id = request.POST.get('task_id')
    uploaded_file = request.FILES.get('excel_file')

    if not task_id or not uploaded_file:
        return redirect('/')

    filename = uploaded_file.name.lower()
    file_bytes = uploaded_file.read()

    if filename.endswith('.xlsx') or filename.endswith('.xls'):
        # XLSX → конвертируем в CSV windows-1251 с ; (родной формат Casebook)
        try:
            import pandas as pd
            df = pd.read_excel(io.BytesIO(file_bytes))
            csv_buffer = io.BytesIO()
            df.to_csv(csv_buffer, index=False, sep=';', encoding='windows-1251')
            file_bytes = csv_buffer.getvalue()
        except Exception:
            return redirect('/')

    # CSV (родной формат Casebook: windows-1251, ;) передаём байты напрямую
    casebook.tasks.scan_enchanted_manual.apply_async(
        args=(task_id, file_bytes),
        expires=7200,
        soft_time_limit=6600,
        time_limit=7200,
    )

    return redirect('/')


@login_required(login_url='/login/')
def process_delete_task(request):
    Tasks.objects.get(id=request.GET.get('id')).delete()
    return redirect('/')


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
        'Ссылка на лид в Б24', 'Контакты'
    ]
    for col, header in enumerate(headers):
        worksheet.write(0, col, header)

    row = 1
    for item in queryset:
        worksheet.write(row, 0, item.id)
        worksheet.write(row, 1, item.case_id)
        p_date = item.process_date.strftime('%d.%m.%Y') if item.process_date else ''
        worksheet.write(row, 2, p_date)
        worksheet.write(row, 3, 'Да' if item.is_success else 'Нет')
        worksheet.write(row, 4, item.error_message or '')
        task_name = item.from_task.name if item.from_task else 'Не указана'
        worksheet.write(row, 5, task_name)
        lead_url = f'https://crm.yk-cfo.ru/crm/lead/details/{item.bitrix_lead_id}' if item.bitrix_lead_id else 'Не загружено'
        worksheet.write(row, 6, lead_url)
        worksheet.write(row, 7, item.contacts if item.contacts else 'Не загружено')
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
