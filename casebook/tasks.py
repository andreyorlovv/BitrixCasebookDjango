import datetime
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import traceback
from dataclasses import asdict

import requests
from celery import shared_task
from dateutil import parser
from django.conf import settings
from django.db.models import QuerySet
from fast_bitrix24.server_response import ErrorInServerResponseException
from requests import JSONDecodeError
from requests.exceptions import SSLError

from casebook.bitrix import BitrixConnect
from casebook.contacts_v2 import get_contacts_via_export_base, get_contacts_aggregated
from casebook.models import Filter, Case, Tasks, InfoDealB24


@shared_task
def get_tasks_from_db():
    tasks = Tasks.objects.all()
    for task in tasks:
        if task.last_execution is None:
            scan_enchanted.apply_async(
                args=[task.id],
                retry=False,
                expires=7200,  # 2 hours
                soft_time_limit=6600,  # 1 hour 50 minutes
                time_limit=7200  # 2 hours
            )
        elif int((task.last_execution - datetime.datetime.now(
                tz=datetime.timezone.utc)).seconds % 3600 / 60.0) > task.iteration_interval:
            scan_enchanted.apply_async(
                args=[task.id],
                retry=False,
                expires=7200,  # 2 hours
                soft_time_limit=6600,  # 1 hour 50 minutes
                time_limit=7200  # 2 hours
            )


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


@shared_task(bind=True, max_retries=3, soft_time_limit=6600, time_limit=7200)
def scan_enchanted(self, task_id):
    import logging
    import time
    logger = logging.getLogger(__name__)

    task = None

    try:
        task = Tasks.objects.get(id=task_id)
        filter_ = Filter.objects.select_related().filter(filter_id=task.filter_id).first()

        if not filter_:
            logger.error(f"Filter not found for task {task_id}")
            return

        logger.info(f"Starting scan_enchanted for task {task_id}, filter: {filter_.name}")

        from casebook.casebook import Casebook

        casebook = Casebook(settings.CASEBOOK_LOGIN, settings.CASEBOOK_PASSWORD)

        bitrix = BitrixConnect(webhook=settings.BITRIX_CALLBACK)

        # Кешируем filter для переиспользования в цикле
        cached_filter = Filter.objects.get(filter_id=task.filter_id)

        cases = casebook.get_cases_via_excel(
            filter_source=json.loads(filter_.value),
            timedelta=task.days_expire,
            to_load=task.to_load,
            cash=task.cash,
            scan_p=task.scan_p,
            scan_r=task.scan_r,
            filter_id=task.filter_id,
            scan_or=task.scan_or,
            ignore_other_tasks_processed=task.ignore_other_tasks_processed,
            task_id=filter_.id,
            judj_check=task.check_for_judj_orders,
            start_date=task.start_date,
            white_list_inn=task.white_list_inn
        )

        logger.info(f'Cases retrieved: {len(cases) if cases else 0}')

        if cases:
            for case in cases:
                logger.info(f"Processing case: {case.number}")
                try:
                    # Проверяем существование кейса один раз
                    case_exists = Case.objects.filter(case_id=case.number).exists()
                    case_exists_in_filter = Case.objects.filter(
                        case_id=case.number,
                        from_task__id=filter_.id
                    ).exists()

                    should_process = (
                        not case_exists or
                        (not case_exists_in_filter and task.ignore_other_tasks_processed)
                    )

                    if should_process:
                        # Получаем контакты с обработкой timeout
                        try:
                            case.contacts_info = get_contacts_via_export_base(
                                ogrn=case.target.ogrn,
                                inn=case.target.inn,
                                key=settings.EXPORT_BASE_API_KEY
                            )
                        except requests.exceptions.Timeout:
                            logger.warning(f"Timeout getting contacts for {case.number}")
                            case.contacts_info = {
                                'emails': [],
                                'numbers': [],
                                'blacklist_emails': [],
                                'blacklist_numbers': []
                            }
                        except Exception as e:
                            logger.warning(f"Error getting contacts for {case.number}: {e}")
                            case.contacts_info = {
                                'emails': [],
                                'numbers': [],
                                'blacklist_emails': [],
                                'blacklist_numbers': []
                            }

                        # Обрезаем контакты по лимиту
                        if case.contacts_info.get('numbers') and task.contacts:
                            case.contacts_info['numbers'] = case.contacts_info['numbers'][0:task.contacts]
                        if case.contacts_info.get('emails') and task.emails:
                            case.contacts_info['emails'] = case.contacts_info['emails'][0:task.emails]

                        # Создаем лид в Bitrix24
                        try:
                            # Определяем права на основе filter_id
                            if task.filter_id == '558875':
                                rights = True
                            elif task.filter_id == '515745':
                                rights = 1169
                            elif task.filter_id == '677492':
                                rights = 1179
                            else:
                                rights = str(task.b24_collection) if task.b24_collection else False

                            # Создаем лид
                            result = bitrix.create_lead(case, rights=rights, filter_id=task.filter_id)

                            # Сохраняем результат в БД
                            Case.objects.create(
                                process_date=datetime.datetime.now(),
                                case_id=case.number,
                                is_success=True,
                                bitrix_lead_id=result,
                                from_task=cached_filter,
                                contacts=case.contacts_info,
                                error_message=case
                            )
                            logger.info(f"Successfully created lead for {case.number}: {result}")

                        except ErrorInServerResponseException as e:
                            logger.error(f"Bitrix error for {case.number}: {e}")
                            Case.objects.create(
                                process_date=datetime.datetime.now(),
                                case_id=case.number,
                                is_success=False,
                                error_message=f'Ошибка в контактных данных: {e}',
                                from_task=cached_filter,
                            )
                    else:
                        logger.info(f"Case {case.number} already processed, skipping")

                except Exception as e:
                    logger.error(f"Error processing case {case.number}: {e}\n{traceback.format_exc()}")
                    try:
                        Case.objects.create(
                            process_date=datetime.datetime.now(),
                            case_id=case.number,
                            is_success=False,
                            error_message=f'{e}, {traceback.format_exc()}',
                            from_task=cached_filter,
                        )
                    except Exception as db_error:
                        logger.error(f"Failed to save error case {case.number}: {db_error}")

    except Exception as e:
        logger.error(f"Critical error in scan_enchanted for task {task_id}: {e}\n{traceback.format_exc()}")
        # Повторить задачу через 5 минут только если это не последняя попытка
        # if self.request.retries < self.max_retries:
        #     raise self.retry(exc=e, countdown=300)
        logger.error(f"Task {task_id} failed after {self.max_retries} retries")

    finally:
        # ГАРАНТИРОВАННО обновляем last_execution
        if task:
            try:
                task.refresh_from_db()
                task.last_execution = datetime.datetime.now(tz=datetime.timezone.utc)
                task.save(update_fields=['last_execution'])
                logger.info(f"Task {task_id} completed, last_execution updated to {task.last_execution}")
            except Exception as e:
                logger.error(f"Failed to update last_execution for task {task_id}: {e}")


@shared_task(bind=True, max_retries=3, soft_time_limit=6600, time_limit=7200)
def scan_enchanted_manual(self, task_id, excel):
    import io
    import logging
    import time
    logger = logging.getLogger(__name__)

    # excel — путь к временному файлу на диске (передаётся из view).
    # Открываем здесь; удаляем после завершения задачи в блоке finally.
    excel_path = None
    if isinstance(excel, str):
        excel_path = excel
        excel = open(excel_path, 'rb')

    task = None

    try:
        task = Tasks.objects.get(id=task_id)
        filter_ = Filter.objects.select_related().filter(filter_id=task.filter_id).first()

        if not filter_:
            logger.error(f"Filter not found for task {task_id}")
            return

        logger.info(f"Starting scan_enchanted_manual for task {task_id}, filter: {filter_.name}")

        from casebook.casebook import Casebook

        casebook = Casebook(settings.CASEBOOK_LOGIN, settings.CASEBOOK_PASSWORD, need_auth=task.check_for_judj_orders)

        bitrix = BitrixConnect(webhook=settings.BITRIX_CALLBACK)

        # Кешируем filter для переиспользования в цикле
        cached_filter = Filter.objects.get(filter_id=task.filter_id)

        cases = casebook.get_cases_via_excel(
            filter_source=json.loads(filter_.value),
            timedelta=task.days_expire,
            to_load=task.to_load,
            cash=task.cash,
            scan_p=task.scan_p,
            scan_r=task.scan_r,
            filter_id=task.filter_id,
            scan_or=task.scan_or,
            ignore_other_tasks_processed=task.ignore_other_tasks_processed,
            task_id=filter_.id,
            judj_check=task.check_for_judj_orders,
            start_date=task.start_date,
            white_list_inn=task.white_list_inn,
            scan_p_bl=task.scan_p_bl,
            scan_r_bl=task.scan_r_bl,
            excel=excel
        )

        logger.info(f'Cases retrieved: {len(cases) if cases else 0}')

        if cases:
            for case in cases:
                logger.info(f"Processing case: {case.number}")
                try:
                    # Проверяем существование кейса один раз
                    case_exists = Case.objects.filter(case_id=case.number).exists()
                    case_exists_in_filter = Case.objects.filter(
                        case_id=case.number,
                        from_task__id=filter_.id
                    ).exists()

                    should_process = (
                        not case_exists or
                        (not case_exists_in_filter and task.ignore_other_tasks_processed)
                    )

                    if should_process:
                        # Получаем контакты с обработкой timeout
                        try:
                            case.contacts_info, case.target.address, case.target.ceo = get_contacts_aggregated(
                                ogrn=case.target.ogrn,
                                inn=case.target.inn,
                                export_base_key=settings.EXPORT_BASE_API_KEY,
                                checko_key=settings.CHECKO_API_KEY
                            )
                        except requests.exceptions.Timeout:
                            logger.warning(f"Timeout getting contacts for {case.number}")
                            case.contacts_info = {
                                'emails': [],
                                'numbers': [],
                                'blacklist_emails': [],
                                'blacklist_numbers': []
                            }
                        except Exception as e:
                            logger.warning(f"Error getting contacts for {case.number}: {e}")
                            case.contacts_info = {
                                'emails': [],
                                'numbers': [],
                                'blacklist_emails': [],
                                'blacklist_numbers': []
                            }

                        # Обрезаем контакты по лимиту
                        if case.contacts_info.get('numbers') and task.contacts:
                            case.contacts_info['numbers'] = case.contacts_info['numbers'][0:task.contacts]
                        if case.contacts_info.get('emails') and task.emails:
                            case.contacts_info['emails'] = case.contacts_info['emails'][0:task.emails]

                        # Создаем лид в Bitrix24
                        time.sleep(1)

                        try:
                            # Определяем права на основе filter_id
                            if task.filter_id == '558875':
                                rights = True
                            elif task.filter_id == '515745':
                                rights = 1169
                            elif task.filter_id == '677492':
                                rights = 1179
                            else:
                                rights = str(task.b24_collection) if task.b24_collection else False

                            # Создаем лид
                            result = bitrix.create_lead(case, rights=rights, filter_id=task.filter_id)

                            # Сохраняем результат в БД
                            Case.objects.create(
                                process_date=datetime.datetime.now(),
                                case_id=case.number,
                                is_success=True,
                                bitrix_lead_id=result,
                                from_task=cached_filter,
                                contacts=case.contacts_info,
                                error_message=case
                            )
                            logger.info(f"Successfully created lead for {case.number}: {result}")

                        except ErrorInServerResponseException as e:
                            logger.error(f"Bitrix error for {case.number}: {e}")
                            Case.objects.create(
                                process_date=datetime.datetime.now(),
                                case_id=case.number,
                                is_success=False,
                                error_message=f'Ошибка в контактных данных: {e}',
                                from_task=cached_filter,
                            )
                    else:
                        logger.info(f"Case {case.number} already processed, skipping")
                        # Кейс уже есть в БД — фиксируем это отдельной записью с ошибкой,
                        # указывая подборку, в рамках которой он был обработан ранее.
                        existing_case = (
                            Case.objects
                            .filter(case_id=case.number)
                            .exclude(from_task=None)
                            .select_related('from_task')
                            .first()
                        )
                        processed_filter_name = (
                            existing_case.from_task.name
                            if existing_case and existing_case.from_task
                            else 'Не указана'
                        )
                        Case.objects.create(
                            process_date=datetime.datetime.now(),
                            case_id=case.number,
                            is_success=False,
                            error_message=f'обработано в рамках другой подборки - {processed_filter_name}',
                            from_task=cached_filter,
                        )

                except Exception as e:
                    logger.error(f"Error processing case {case.number}: {e}\n{traceback.format_exc()}")
                    try:
                        Case.objects.create(
                            process_date=datetime.datetime.now(),
                            case_id=case.number,
                            is_success=False,
                            error_message=f'{e}, {traceback.format_exc()}',
                            from_task=cached_filter,
                        )
                    except Exception as db_error:
                        logger.error(f"Failed to save error case {case.number}: {db_error}")

    except Exception as e:
        logger.error(f"Critical error in scan_enchanted for task {task_id}: {e}\n{traceback.format_exc()}")
        # Повторить задачу через 5 минут только если это не последняя попытка
        # if self.request.retries < self.max_retries:
        #     raise self.retry(exc=e, countdown=300)
        logger.error(f"Task {task_id} failed after {self.max_retries} retries")

    finally:
        # ГАРАНТИРОВАННО обновляем last_execution
        if task:
            try:
                task.refresh_from_db()
                task.last_execution = datetime.datetime.now(tz=datetime.timezone.utc)
                task.save(update_fields=['last_execution'])
                logger.info(f"Task {task_id} completed, last_execution updated to {task.last_execution}")
            except Exception as e:
                logger.error(f"Failed to update last_execution for task {task_id}: {e}")

        # Закрываем и удаляем временный файл, если он был создан view'ом
        if excel_path:
            try:
                if not excel.closed:
                    excel.close()
                import os as _os
                _os.remove(excel_path)
                logger.info(f"Temp file removed: {excel_path}")
            except Exception as e:
                logger.warning(f"Could not remove temp file {excel_path}: {e}")


@shared_task
def daily_report():
    import smtplib
    try:
        remaining_export_base = requests.get(
            f'https://export-base.ru/api/balance/?key={settings.EXPORT_BASE_API_KEY}',
            timeout=30
        )
        remaining_export_base.raise_for_status()
        remaining = remaining_export_base.text
    except requests.exceptions.Timeout:
        remaining = 'Ошибка в подключении к ЭкспортБейс (timeout), СВЯЖИТЕСЬ С РАЗРАБОТЧИКОМ!'
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


