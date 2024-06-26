import json

from django.contrib.admin import site
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect
from rest_framework.decorators import api_view

import casebook.tasks
from BitrixCasebook import settings
from casebook.forms import SetupParseForm
from casebook.models import Filter, Tasks, BlackList
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
                             last_execution=None
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
    remaining_export_base = requests.get(f'https://export-base.ru/api/balance/?key={settings.EXPORT_BASE_API_KEY}')
    extra_context = {'filters': filters, 'form_create': form_create,
                     'tasks': tasks_to_render, 'remaining_export_base': remaining_export_base.text}
    return site.index(request, extra_context=extra_context)


@login_required(login_url='/login/')
def process_delete_task(request):
    Tasks.objects.get(id=request.GET.get('id')).delete()
    return redirect('/')


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
