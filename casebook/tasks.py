import datetime
import json

from celery import shared_task
from django.conf import settings
from django.db.models import QuerySet
from fast_bitrix24.server_response import ErrorInServerResponseException

from casebook.bitrix import BitrixConnect
from casebook.contacts_v2 import get_contacts_via_export_base, get_contacts
from casebook.models import Filter, Case, Tasks


@shared_task
def get_tasks_from_db():
    tasks = Tasks.objects.all()
    for task in tasks:
        if task.last_execution is None:
            scan_enchanted.apply_async(args=[task.id], retry=False, expires=600)
        elif int((task.last_execution - datetime.datetime.now(
                tz=datetime.timezone.utc)).seconds % 3600 / 60.0) > task.iteration_interval:
            scan_enchanted.apply_async(args=[task.id], retry=False, expires=600)


@shared_task
def update_filters():
    from casebook.casebook import Casebook
    casebook = Casebook(settings.CASEBOOK_LOGIN, settings.CASEBOOK_PASSWORD)
    filters = casebook.get_filters()
    
    for filter_ in filters:
        filters_db = Filter.objects.filter(filter_id=filter_['id']).first()
        if filters_db is None:
            new = Filter(name=filter_['name'],
                         filter_id=filter_['id'],
                         value=json.dumps(filter_))
            new.save()
        else:
            filters_db = Filter.objects.filter(filter_id=filter_['id']).first()
            filters_db.value = json.dumps(filter_)
            filters_db.name = filter_['name']
            filters_db.save()


class NoContactDataException(Exception):
    def __init__(self):
        self.message = 'Не найдены контактные данные'

    def __str__(self):
        return "Не найдены контактные данные"


@shared_task
def delete_lead(lead_id):
    bitrix = BitrixConnect(webhook=settings.BITRIX_CALLBACK)
    bitrix.delete_lead(lead_id)


@shared_task
def scan_enchanted(task_id):
    from casebook.casebook import Casebook
    #try:
    casebook = Casebook(settings.CASEBOOK_LOGIN, settings.CASEBOOK_PASSWORD)
    casebook.headless_auth(settings.CASEBOOK_LOGIN, settings.CASEBOOK_PASSWORD)
    #except Exception as e:
    #    scan_enchanted.apply_async(args=[task_id], countdown=60)
    bitrix = BitrixConnect(webhook=settings.BITRIX_CALLBACK)

    task = Tasks.objects.get(id=task_id)
    filter_ = Filter.objects.filter(filter_id=task.filter_id).first()
    cases = casebook.get_cases(filter_source=json.loads(filter_.value),
                               timedelta=task.days_expire, to_load=task.to_load, cash=task.cash,
                               scan_p=task.scan_p, scan_r=task.scan_r, filter_id=task.filter_id, scan_or=task.scan_or,
                               ignore_other_tasks_processed=task.ignore_other_tasks_processed, task_id=filter_.id)
    print('Cases get: ', str(len(cases)))
    if cases:
        for case in cases:
            print(case.number)
            try:
                if not Case.objects.filter(case_id=str(case.number)).exists():
                    if 'индивидуальный предприниматель'.upper() in case.respondent.name.upper():
                        try:
                            case.contacts_info = {'emails': [], 'numbers': []}
                            case.contacts_info = get_contacts_via_export_base(ogrn=case.respondent.ogrn,
                                                                              key=settings.EXPORT_BASE_API_KEY)
                        except Exception as e:
                            case.contacts_info = {'emails': [], 'numbers': []}
                            case.contacts_info = get_contacts(inn=case.respondent.inn, ogrn=case.respondent.ogrn)
                    else:
                        case.contacts_info = {'emails': [], 'numbers': []}
                        case.contacts_info = get_contacts(inn=case.respondent.inn, ogrn=case.respondent.ogrn)
                if case.contacts_info.get('emails') == [] and case.contacts_info.get('numbers') == []:
                    case.contacts_info = {'emails': [], 'numbers': []}
                    case.contacts_info = get_contacts_via_export_base(ogrn=case.respondent.ogrn,
                                                                      key=settings.EXPORT_BASE_API_KEY)
                if case.contacts_info['numbers'] and task.contacts:
                    case.contacts_info['numbers'] = case.contacts_info['numbers'][0:task.contacts]
                if case.contacts_info['emails'] and task.emails:
                    case.contacts_info['emails'] = case.contacts_info['emails'][0:task.emails]
                if not Case.objects.filter(case_id=case.number).exists():
                    try:
                        if task.filter_id == '558875':
                            result = bitrix.create_lead(case, rights=True, filter_id=task.filter_id) if not Case.objects.filter(
                                case_id=case.number).exists() or not Case.objects.filter(case_id=case.number, from_task_id=filter_.id) else print("Уже есть: ", case.number)
                        elif task.filter_id == '515745':
                            result = bitrix.create_lead(case, rights=1169, filter_id=task.filter_id) if not Case.objects.filter(
                                case_id=case.number).exists() or (not Case.objects.filter(case_id=case.number, from_task_id=filter_.id) and task.ignore_other_tasks_processed) else print("Уже есть: ", case.number)
    
                        elif task.filter_id == '677492':
                            result = bitrix.create_lead(case, rights=1164, filter_id=task.filter_id) if not Case.objects.filter(
                                case_id=case.number).exists() or (not Case.objects.filter(case_id=case.number, from_task_id=filter_.id) and task.ignore_other_tasks_processed) else print("Уже есть: ", case.number)
                        else:
                            result = bitrix.create_lead(case, rights=False, filter_id=task.filter_id) if not Case.objects.filter(
                                case_id=case.number).exists() or (not Case.objects.filter(case_id=case.number, from_task_id=filter_.id) and task.ignore_other_tasks_processed) else print("Уже есть: ", case.number)
                        print(result)
                        print(type(result))
                        Case.objects.create(
                            process_date=datetime.datetime.now(),
                            case_id=case.number,
                            is_success=True,
                            bitrix_lead_id=result,
                            from_task=Filter.objects.get(filter_id=task.filter_id),
                        )
                    except ErrorInServerResponseException as e:
                        Case.objects.create(
                            process_date=datetime.datetime.now(),
                            case_id=case.number,
                            is_success=False,
                            error_message=f'Ошибка в контактных данных  {case.contacts_info} ||| {e}',
                            from_task=Filter.objects.get(filter_id=task.filter_id),
                        )
            except Exception as e:
                Case.objects.create(
                    process_date=datetime.datetime.now(),
                    case_id=case.number,
                    is_success=False,
                    error_message=f'{e}',
                    from_task=Filter.objects.get(filter_id=task.filter_id),
                )
    task.last_execution = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
    task.save()
    scan_enchanted.apply_async(
        args=[task.id],
        eta=(datetime.datetime.now(tz=datetime.timezone.utc) + datetime.timedelta(minutes=task.iteration_interval)),
        retry=False,
        expires=600
    )


@shared_task
def daily_report():
    queryset = Case.objects.filter(process_date=datetime.datetime.now(tz=datetime.timezone.utc))
    report = f'''
    Отчет о работе бота за {datetime.datetime.now().date} \n
    Обработано кейсов:
    - {queryset.count()} всего взято в обработку, из них
    {queryset.filter(is_success=True).count()} признаны валидными и ушли в обработку.
    '''
    pass

