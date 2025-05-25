import datetime
import io
import json
import xlsxwriter

from django.contrib.admin import site
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect
from requests import RequestException
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
        remaining_export_base = requests.get(f'https://export-base.ru/api/balance/?key={settings.EXPORT_BASE_API_KEY}')
        remaining_export_base.raise_for_status()
    except SSLError as e:
        print(e)
        remaining_export_base = 'Ошибка в подключении к ЭкспортБейс, СВЯЖИТЕСЬ С РАЗРАБОТЧИКОМ, СКОРЕЕ ВСЕГО ПРОБЕЛМА ЕСТЬ И В ПОЛУЧЕНГИИ КОНТАКТНЫХ ДАННЫХ!!!!'
    extra_context = {'filters': filters, 'form_create': form_create,
                     'tasks': tasks_to_render, 'remaining_export_base': remaining_export_base.text}
    return site.index(request, extra_context=extra_context)


@login_required(login_url='/login/')
def process_delete_task(request):
    Tasks.objects.get(id=request.GET.get('id')).delete()
    return redirect('/')


@login_required(login_url='/login/')
@staff_member_required
def download_xlsx_view(request):
    queryset = Case.objects.all()
    if request.GET.get('from') or request.GET.get('to'):
        queryset = queryset.filter(process_date__range=[request.GET.get('from'), request.GET.get('to')])
    output = io.BytesIO()

    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    worksheet = workbook.add_worksheet()
    row = 0
    col = 0
    worksheet.write(row, col, 'id кейса')
    worksheet.write(row, col + 1, 'Номер дела в арбитре')
    worksheet.write(row, col + 2, 'Дата обработки')
    worksheet.write(row, col + 3, 'Успешно обработано (?)')
    worksheet.write(row, col + 4, 'Ошибка, если есть')
    worksheet.write(row, col + 5, 'Подборка')
    worksheet.write(row, col + 6, 'Ссылка на лид в Б24')
    row = 1
    for item in queryset:
        worksheet.write(row, col, item.id)
        worksheet.write(row, col + 1, item.case_id)
        worksheet.write(row, col + 2, item.process_date.strftime('%d.%m.%Y'))
        worksheet.write(row, col + 3, 'Да' if item.is_success else 'Нет')
        worksheet.write(row, col + 4, item.error_message)
        worksheet.write(row, col + 5, item.from_task.name)
        worksheet.write(row, col + 6, f'https://crm.yk-cfo.ru/crm/lead/details/{item.bitrix_lead_id}' if item.bitrix_lead_id else 'Не загружено')
        row += 1
    workbook.close()

    output.seek(0)

    print(workbook.filename)

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                            content=output.read())
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
