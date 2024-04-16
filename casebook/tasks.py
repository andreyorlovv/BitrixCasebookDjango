import datetime
import json

from celery import shared_task
from django.conf import settings
from django.db.models import QuerySet
from fast_bitrix24.server_response import ErrorInServerResponseException

from casebook.bitrix import BitrixConnect
from casebook.contacts import get_contacts_via_export_base, get_contacts
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


# @shared_task
# def set_task_for_interval(id_, interval):
#     next_iter = datetime.datetime.now() + datetime.timedelta(minutes=interval)
#     scan_enchanted.apply_async(args=[id_], eta=next_iter)


@shared_task
def update_filters():
    from casebook.casebook import Casebook
    casebook = Casebook(settings.CASEBOOK_LOGIN, settings.CASEBOOK_PASSWORD)
    filters = casebook.filters
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
    try:
        casebook = Casebook(settings.CASEBOOK_LOGIN, settings.CASEBOOK_PASSWORD)
        casebook.headless_auth()
    except Exception as e:
        scan_enchanted.apply_async(args=[task_id], countdown=60)
    bitrix = BitrixConnect(webhook=settings.BITRIX_CALLBACK)

    task = Tasks.objects.get(id=task_id)
    filter_ = Filter.objects.filter(filter_id=task.filter_id).first()
    cases = casebook.get_cases(json.loads(filter_.value), task.days_expire)
    print('Cases get: ', str(len(cases)))
    if cases:
        for case in cases:
            print(case.number)
            try:
                if not Case.objects.filter(case_id=str(case.number)).exists():
                    if 'индивидуальный предприниматель'.upper() in case.respondent.name.upper():
                        case.contacts_info = get_contacts_via_export_base(
                            ogrn=case.respondent.ogrn,
                            key=settings.EXPORT_BASE_API_KEY)
                    else:
                        case.contacts_info = get_contacts(inn=case.respondent.inn, ogrn=case.respondent.ogrn)
                if case.contacts_info.get('emails') == [] and case.contacts_info.get('numbers') == []:
                    case.contacts_info = get_contacts_via_export_base(
                        ogrn=case.respondent.ogrn,
                        key=settings.EXPORT_BASE_API_KEY)
                if case.contacts_info.get('emails') == [] and case.contacts_info.get('numbers') == []:

                    #raise NoContactDataException
                    pass
                if not Case.objects.filter(case_id=case.number).exists():
                    try:
                        if task.filter_id == '558875':
                            result = bitrix.create_lead(case, rights=True) if not Case.objects.filter(
                                case_id=case.number).exists() else print("Уже есть: ", case.number)
                        else:
                            result = bitrix.create_lead(case, rights=False) if not Case.objects.filter(
                                case_id=case.number).exists() else print("Уже есть: ", case.number)
                        print(result)
                        print(type(result))
                        Case.objects.create(
                            process_date=datetime.datetime.now().date(),
                            case_id=case.number,
                            is_success=True,
                            bitrix_lead_id=result
                        )
                    except ErrorInServerResponseException as e:
                        Case.objects.create(
                            process_date=datetime.datetime.now().date(),
                            case_id=case.number,
                            is_success=False,
                            error_message=f'Ошибка в контактных данных  {case.contacts_info} ||| {e}'
                        )
            except Exception as e:
                Case.objects.create(
                    process_date=datetime.datetime.now().date(),
                    case_id=case.number,
                    is_success=False,
                    error_message=f'{e}'
                )
    task.last_execution = datetime.datetime.now().isoformat()
    task.save()
    scan_enchanted.apply_async(
        args=[task.id],
        eta=(datetime.datetime.now(tz=datetime.timezone.utc) + datetime.timedelta(minutes=task.iteration_interval)),
        retry=False,
        expires=600
    )

# @shared_task
# def scan(task_id):
#     from casebook.casebook import Casebook
#     try:
#         casebook = Casebook(settings.CASEBOOK_LOGIN, settings.CASEBOOK_PASSWORD)
#         casebook.headless_auth()
#     except Exception as e:
#         scan.apply_async(args=[task_id], countdown=60)
#
#     bitrix = BitrixConnect(webhook=settings.BITRIX_CALLBACK)
#
#     task = Tasks.objects.get(id=task_id)
#     filter_ = Filter.objects.filter(filter_id=task.filter_id).first()
#     cases = casebook.get_cases(json.loads(filter_.value), task.days_expire)
#
#     print('Cases get: ', str(len(cases)))
#
#     if cases:
#         processed_cases = []
#         for case in cases:
#             try:
#                 print(case.number)
#                 if not Case.objects.filter(case_id=str(case.number)).exists():
#                     if 'индивидуальный предприниматель'.upper() in case.respondent.name.upper():
#                         case.contacts_info = get_contacts_via_export_base(
#                             ogrn=case.respondent.ogrn,
#                             key=settings.EXPORT_BASE_API_KEY)
#                     else:
#                         case.contacts_info = get_contacts(inn=case.respondent.inn, ogrn=case.respondent.ogrn)
#                     processed_cases.append(case)
#             except Exception as e:
#                 Case.objects.create(
#                     process_date=datetime.datetime.now().date(),
#                     case_id=case.number,
#                     is_success=False,
#                     error_message=f'{e}'
#                 )
#                 pass
#         cases = processed_cases
#         print('Processed Cases: ', str(len(cases)))
#         with_contacts = []
#         for case in cases:
#             try:
#                 if case.contacts_info.get('emails') == [] and case.contacts_info.get('numbers') == []:
#                     case.contacts_info = get_contacts_via_export_base(
#                         ogrn=case.respondent.ogrn,
#                         key=settings.EXPORT_BASE_API_KEY)
#             #     if case.contacts_info.get('emails') == [] and case.contacts_info.get('numbers') == []:
#             #         Case.objects.create(
#             #             process_date=datetime.datetime.now().date(),
#             #             case_id=case.number,
#             #             is_success=False,
#             #             error_message=f'Не найдены контактные данные:  {case.contacts_info}'
#             #         )
#             #     else:
#             #         with_contacts.append(case)
#             except Exception as e:
#                 Case.objects.create(
#                     process_date=datetime.datetime.now().date(),
#                     case_id=case.number,
#                     is_success=False,
#                     error_message=f'{e}'
#                 )
#                 pass
#         # cases = with_contacts
#         print('Load to b24')
#         for case in cases:
#             print(case.contacts_info)
#         for case in cases:
#             if not Case.objects.filter(case_id=case.number).exists():
#                 try:
#                     if task.filter_id == '558875':
#                         err = bitrix.create_lead(case, rights=True) if not Case.objects.filter(
#                             case_id=case.number).exists() else print("Уже есть: ", case.number)
#                     else:
#                         err = bitrix.create_lead(case, rights=False) if not Case.objects.filter(
#                             case_id=case.number).exists() else print("Уже есть: ", case.number)
#                     if err:
#                         print(err)
#                     Case.objects.create(
#                         process_date=datetime.datetime.now().date(),
#                         case_id=case.number,
#                         is_success=True
#                     )
#                 except ErrorInServerResponseException as e:
#                     Case.objects.create(
#                         process_date=datetime.datetime.now().date(),
#                         case_id=case.number,
#                         is_success=False,
#                         error_message=f'Ошибка в контактных данных  {case.contacts_info}'
#                     )
#             else:
#                 pass
#     task.last_execution = datetime.datetime.now().isoformat()
#     task.save()
#     scan.apply_async(
#         args=[task.id],
#         eta=(datetime.datetime.now(tz=datetime.timezone.utc) + datetime.timedelta(minutes=task.iteration_interval)),
#         retry=False,
#         expires=600
#     )


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

