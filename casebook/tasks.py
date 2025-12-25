import datetime
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import traceback


import requests
from celery import shared_task
from dateutil import parser
from django.conf import settings
from django.db.models import QuerySet
from fast_bitrix24.server_response import ErrorInServerResponseException
from requests import JSONDecodeError
from requests.exceptions import SSLError

from casebook.bitrix import BitrixConnect
from casebook.contacts_v2 import get_contacts_via_export_base, get_contacts
from casebook.models import Filter, Case, Tasks, InfoDealB24


@shared_task
def get_tasks_from_db():
    tasks = Tasks.objects.all()
    for task in tasks:
        if task.last_execution is None:
            scan_enchanted.apply_async(args=[task.id], retry=False, expires=6200)
        elif int((task.last_execution - datetime.datetime.now(
                tz=datetime.timezone.utc)).seconds % 3600 / 60.0) > task.iteration_interval:
            scan_enchanted.apply_async(args=[task.id], retry=False, expires=6200)


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

    print(filter_.name)

    cases = casebook.get_cases(filter_source=json.loads(filter_.value),
                               timedelta=task.days_expire, to_load=task.to_load, cash=task.cash,
                               scan_p=task.scan_p, scan_r=task.scan_r, filter_id=task.filter_id, scan_or=task.scan_or,
                               ignore_other_tasks_processed=task.ignore_other_tasks_processed, task_id=filter_.id, judj_check=task.check_for_judj_orders)
    print('Cases get: ', str(len(cases)))
    if cases:
        for case in cases:
            print(case.number)
            try:
                if not Case.objects.filter(case_id=str(case.number)).exists() or (not Case.objects.filter(case_id=case.number, from_task__id=filter_.id).exists() and task.ignore_other_tasks_processed):
                        case.contacts_info = {'emails': [], 'numbers': [], 'blacklist_emails': [], 'blacklist_numbers': []}
                        case.contacts_info = get_contacts_via_export_base(ogrn=case.respondent.ogrn, inn=case.respondent.inn,
                                                                          key=settings.EXPORT_BASE_API_KEY)
                if case.contacts_info['numbers'] and task.contacts:
                    case.contacts_info['numbers'] = case.contacts_info['numbers'][0:task.contacts]
                if case.contacts_info['emails'] and task.emails:
                    case.contacts_info['emails'] = case.contacts_info['emails'][0:task.emails]
                if not Case.objects.filter(case_id=case.number).exists() or (not Case.objects.filter(case_id=case.number, from_task__id=filter_.id).exists() and task.ignore_other_tasks_processed):
                    try:
                        if task.filter_id == '558875':
                            result = bitrix.create_lead(case, rights=True, filter_id=task.filter_id) if not Case.objects.filter(
                                case_id=case.number).exists() or not Case.objects.filter(case_id=case.number, from_task_id=filter_.id) else print("Уже есть: ", case.number)
                        elif task.filter_id == '515745':
                            result = bitrix.create_lead(case, rights=1169, filter_id=task.filter_id) if not Case.objects.filter(
                                case_id=case.number).exists() or (not Case.objects.filter(case_id=case.number, from_task_id=filter_.id) and task.ignore_other_tasks_processed) else print("Уже есть: ", case.number)
    
                        elif task.filter_id == '677492':
                            result = bitrix.create_lead(case, rights=1179, filter_id=task.filter_id) if not Case.objects.filter(
                                case_id=case.number).exists() or (not Case.objects.filter(case_id=case.number, from_task__id=filter_.id) and task.ignore_other_tasks_processed) else print("Уже есть: ", case.number)
                        else:
                            result = bitrix.create_lead(case, rights=str(task.b24_collection) if task.b24_collection else False, filter_id=task.filter_id) if not Case.objects.filter(
                                case_id=case.number).exists() or (not Case.objects.filter(case_id=case.number, from_task__id=filter_.id) and task.ignore_other_tasks_processed) else print("Уже есть: ", case.number)
                        print(result)
                        print(type(result))
                        Case.objects.create(
                            process_date=datetime.datetime.now(),
                            case_id=case.number,
                            is_success=True,
                            bitrix_lead_id=result,
                            from_task=Filter.objects.get(filter_id=task.filter_id),
                            contacts=case.contacts_info
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
                    error_message=f'{e}, {traceback.format_exc()} \n\n {e.__traceback__} \n\n\n ,\n\n\n {case}',
                    from_task=Filter.objects.get(filter_id=task.filter_id),
                )
    task.last_execution = datetime.datetime.now(tz=datetime.timezone.utc).isoformat()
    task.save()
    # scan_enchanted.apply_async(
    #     args=[task.id],
    #     eta=(datetime.datetime.now(tz=datetime.timezone.utc) + datetime.timedelta(minutes=task.iteration_interval)),
    #     retry=False,
    #     expires=7200
    # )


@shared_task
def daily_report():
    import smtplib
    try:
        remaining_export_base = requests.get(f'https://export-base.ru/api/balance/?key={settings.EXPORT_BASE_API_KEY}')
        remaining_export_base.raise_for_status()
        remaining = remaining_export_base.text
    except SSLError as e:
        remaining = 'Ошибка в подключении к ЭкспортБейс, СВЯЖИТЕСЬ С РАЗРАБОТЧИКОМ, СКОРЕЕ ВСЕГО ПРОБЕЛМА ЕСТЬ И В ПОЛУЧЕНГИИ КОНТАКТНЫХ ДАННЫХ!!!!'
    if int(remaining) <= 100 or remaining == 'Ошибка в подключении к ЭкспортБейс, СВЯЖИТЕСЬ С РАЗРАБОТЧИКОМ, СКОРЕЕ ВСЕГО ПРОБЕЛМА ЕСТЬ И В ПОЛУЧЕНГИИ КОНТАКТНЫХ ДАННЫХ!!!!':
        message = f'''
        ВНИМАНИЕ! Заканчиваются токены export-base, текущий остаток - {remaining}
        
        Необходимо пополнить баланс.
        '''
        msg = MIMEMultipart()

        password = "sjednvonplnzfgat"
        msg['From'] = "druni.adler@yandex.ru"
        msg['To'] = "director@yk-cfo.ru"
        msg['Subject'] = "Токены EXPORT-BASE.RU"

        msg.attach(MIMEText(message, 'plain'))
        server = smtplib.SMTP('smtp.yandex.ru: 587')
        server.starttls()
        server.login(msg['From'], password)
        server.sendmail(msg['From'], msg['To'], msg.as_string())
        server.quit()


@shared_task
def updates_info_about_case():
    from casebook.casebook import Casebook
    casebook = Casebook(settings.CASEBOOK_LOGIN, settings.CASEBOOK_PASSWORD)
    bitrix = BitrixConnect(webhook=settings.BITRIX_CALLBACK)
    deals = bitrix.get_cases({
        '@STAGE_ID': ['C2:UC_WM14DA', 'C2:UC_UNGBSA', 'C2:NEW', 'C2:UC_UMRJ10', 'C2:PREPAYMENT_INVOICE']
    })

    for deal in deals:
        try:
            try:
                case = casebook.find_case(deal['UF_CRM_1599834564'])
            except json.decoder.JSONDecodeError as e:
                continue
            instances = casebook.get_instances(case['id'])
            for instance in instances:
                if not InfoDealB24.objects.filter(instance_id=instance['instance_id'], case_id=instance['case_id']).exists():
                    InfoDealB24.objects.create(
                        b24_id=deal['ID'],
                        case_id=instance['case_id'],
                        instance_id=instance['instance_id'],
                    )
                events = casebook.get_history(instance['case_id'], instance['instance_id'])
                if not InfoDealB24.objects.filter(last_record_id=events[0]['id']).exists():
                    for event in reversed(events):
                        if not InfoDealB24.objects.filter(instance_id=instance['instance_id'],
                                                          case_id=instance['case_id'],
                                                          date_casebook__gte=parser.parse(event['registrationDate']))\
                                .exists():
                            bitrix.add_comment_case(deal, event)
                            InfoDealB24.objects.filter(case_id=instance['case_id'], instance_id=instance['instance_id']).update(
                                last_record_id=event['id'], date_casebook=parser.parse(event['registrationDate'])
                            )

        except KeyError as e:
            print(e)


