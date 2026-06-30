import json
import os
import re

import requests
from requests.exceptions import SSLError

from casebook.models import BlackList


# ---------------------------------------------------------------------------
# Контракт всех функций получения контактов — КОРТЕЖ:
#   (result, address, ceo_name)
# где result:
#   {
#       'numbers':           [<str>, ...],   # валидные телефоны (7XXXXXXXXXX)
#       'emails':            [<str>, ...],   # валидные email
#       'blacklist_numbers': [<str>, ...],   # телефоны, попавшие в ЧС
#       'blacklist_emails':  [<str>, ...],   # email, попавшие в ЧС
#   }
#   address  - <str|None> юр. адрес
#   ceo_name - <str|None> ФИО руководителя
# ---------------------------------------------------------------------------


def _empty_result():
    """Пустой результат в кортежном контракте: (dict, address, ceo_name)."""
    return (
        {
            'numbers': [],
            'emails': [],
            'blacklist_numbers': [],
            'blacklist_emails': [],
        },
        None,
        None,
    )


# ---------------------------------------------------------------------------
# Нормализация и фильтрация по чёрному списку
# ---------------------------------------------------------------------------

def normalize_number(number: str) -> str:
    """Приводит телефон к виду 7XXXXXXXXXX (только цифры)."""
    digits = re.sub(r'\D', '', number or '')
    if digits.startswith('8'):
        digits = '7' + digits[1:]
    return digits


def _load_blacklist():
    """
    Выгружает чёрный список один раз, чтобы не дёргать БД в цикле.
    Возвращает (values, values_lower, email_masks).
    """
    values = set(BlackList.objects.values_list('value', flat=True))
    values_lower = {v.lower() for v in values if v}
    email_masks = [
        m.lower().lstrip('@')
        for m in BlackList.objects.filter(type='email_mask').values_list('value', flat=True)
        if m
    ]
    return values, values_lower, email_masks


def _domain_blacklisted(domain: str, email_masks) -> bool:
    """Домен в ЧС, если равен маске или является её поддоменом."""
    domain = domain.lower()
    return any(domain == mask or domain.endswith('.' + mask) for mask in email_masks)


def _filter_numbers(raw_numbers, bl_values):
    """Нормализует номера и делит на валидные/в чёрном списке."""
    valid, blacklisted = [], []
    for number in raw_numbers:
        number = normalize_number(number)
        if not number:
            continue
        if number in bl_values:
            blacklisted.append(number)
        else:
            valid.append(number)
    return valid, blacklisted


def _filter_emails(raw_emails, bl_values_lower, email_masks):
    """Делит email на валидные/в чёрном списке (точное значение + маска домена)."""
    valid, blacklisted = [], []
    for email in raw_emails:
        email = (email or '').strip()
        if not email:
            continue
        email_norm = email.lower()
        domain = email_norm.rpartition('@')[2]  # часть после последней @
        is_blacklisted = (
            email_norm in bl_values_lower
            or (domain and _domain_blacklisted(domain, email_masks))
        )
        (blacklisted if is_blacklisted else valid).append(email)
    return valid, blacklisted


# ---------------------------------------------------------------------------
# ExportBase
# ---------------------------------------------------------------------------

def get_contacts_via_export_base(key: str, ogrn: str = None, inn: str = None):
    """Контакты из ExportBase API. Возвращает (result, address, ceo_name)."""
    if os.environ.get('local_debug'):
        return _empty_result()

    params = {'key': key}
    if inn:
        params['inn'] = inn
    if ogrn:
        params['ogrn'] = ogrn

    if not inn and not ogrn:
        print("Не указан ни inn, ни ogrn для запроса к export-base")
        return _empty_result()

    try:
        response = requests.get(
            'https://export-base.ru/api/company/', params=params, timeout=30
        )
        response.raise_for_status()
    except requests.exceptions.Timeout:
        print(f"Timeout при запросе к export-base для inn={inn}, ogrn={ogrn}")
        return _empty_result()
    except (SSLError, requests.exceptions.RequestException) as e:
        print(f"Ошибка запроса к export-base: {e}")
        return _empty_result()

    try:
        result_data = response.json()
        data = result_data['companies_data'][0]
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        print(f"Не удалось разобрать ответ export-base: {e}")
        return _empty_result()

    address = data.get('address')
    ceo_name = data.get('ceo_name')

    # Телефоны: стационарный + мобильный, разделители ", "
    raw_numbers = []
    for field in ('stationary_phone', 'mobile_phone'):
        raw = data.get(field) or ''
        raw_numbers += [p.strip() for p in raw.split(',') if p.strip()]

    # Email-адреса (в поле могут быть перечислены через ", ")
    raw_emails = [p.strip() for p in (data.get('email') or '').split(',') if p.strip()]

    bl_values, bl_values_lower, email_masks = _load_blacklist()
    valid_numbers, blacklisted_numbers = _filter_numbers(raw_numbers, bl_values)
    valid_emails, blacklisted_emails = _filter_emails(raw_emails, bl_values_lower, email_masks)

    result = {
        'numbers': list(set(valid_numbers)),
        'emails': list(set(valid_emails)),
        'blacklist_numbers': blacklisted_numbers,
        'blacklist_emails': blacklisted_emails,
    }
    print("ExportBase контакты -", {'numbers': result['numbers'], 'emails': result['emails']})
    return result, address, ceo_name


# ---------------------------------------------------------------------------
# Checko
# ---------------------------------------------------------------------------

def _extract_checko_address(data):
    ur_addr = data.get('ЮрАдрес')
    if isinstance(ur_addr, dict):
        return ur_addr.get('АдресРФ')
    if isinstance(ur_addr, str):
        return ur_addr
    return None


def _extract_checko_ceo(data):
    rukovod = data.get('Руковод')
    if isinstance(rukovod, list):
        for person in rukovod:
            if isinstance(person, dict) and person.get('ФИО'):
                return person['ФИО']
    return None


def get_contacts_via_checko(key: str, ogrn: str = None, inn: str = None):
    """Контакты из Checko API (v2/company). Возвращает (result, address, ceo_name)."""
    if os.environ.get('local_debug'):
        return _empty_result()

    params = {'key': key}
    if inn:
        params['inn'] = inn
    elif ogrn:
        params['ogrn'] = ogrn
    else:
        print("Не указан ни inn, ни ogrn для запроса к Checko")
        return _empty_result()

    try:
        response = requests.get(
            'https://api.checko.ru/v2/company', params=params, timeout=30
        )
        response.raise_for_status()
    except requests.exceptions.Timeout:
        print(f"Timeout при запросе к Checko для inn={inn}, ogrn={ogrn}")
        return _empty_result()
    except (SSLError, requests.exceptions.RequestException) as e:
        print(f"Ошибка запроса к Checko: {e}")
        return _empty_result()

    try:
        payload = response.json()
    except json.JSONDecodeError as e:
        print(f"Не удалось разобрать ответ Checko: {e}")
        return _empty_result()

    meta = payload.get('meta') or {}
    if meta.get('status') != 'ok':
        print(f"Checko вернул статус != ok: {meta.get('message')}")
        return _empty_result()

    data = payload.get('data') or {}
    contacts = data.get('Контакты') or {}
    raw_phones = contacts.get('Тел') or []
    raw_emails = contacts.get('Емэйл') or []

    bl_values, bl_values_lower, email_masks = _load_blacklist()
    valid_numbers, blacklisted_numbers = _filter_numbers(raw_phones, bl_values)
    valid_emails, blacklisted_emails = _filter_emails(raw_emails, bl_values_lower, email_masks)

    result = {
        'numbers': list(set(valid_numbers)),
        'emails': list(set(valid_emails)),
        'blacklist_numbers': blacklisted_numbers,
        'blacklist_emails': blacklisted_emails,
    }
    print("Checko контакты -", {'numbers': result['numbers'], 'emails': result['emails']})
    return result, _extract_checko_address(data), _extract_checko_ceo(data)


# ---------------------------------------------------------------------------
# Агрегатор
# ---------------------------------------------------------------------------

def _merge_contact_results(*results):
    """Объединяет несколько словарей-результатов, схлопывая дубликаты."""
    numbers, emails, bl_numbers, bl_emails = set(), set(), set(), set()
    for r in results:
        if not r:
            continue
        numbers.update(r.get('numbers') or [])
        emails.update(r.get('emails') or [])
        bl_numbers.update(r.get('blacklist_numbers') or [])
        bl_emails.update(r.get('blacklist_emails') or [])

    # номер/email, валидный хотя бы в одном источнике, не считаем чёрным
    bl_numbers -= numbers
    bl_emails -= emails

    return {
        'numbers': list(numbers),
        'emails': list(emails),
        'blacklist_numbers': list(bl_numbers),
        'blacklist_emails': list(bl_emails),
    }


def get_contacts_aggregated(export_base_key: str, checko_key: str,
                            ogrn: str = None, inn: str = None):
    """
    Последовательный вызов обоих сервисов с объединением результата.
    Сначала ExportBase, затем Checko.
    Возвращает (result, address, ceo_name) — единый кортежный контракт.
    """
    if os.environ.get('local_debug'):
        return _empty_result()

    eb_result, eb_address, eb_ceo = get_contacts_via_export_base(
        export_base_key, ogrn=ogrn, inn=inn
    )
    checko_result, checko_address, checko_ceo = get_contacts_via_checko(
        checko_key, ogrn=ogrn, inn=inn
    )

    merged = _merge_contact_results(eb_result, checko_result)

    # address/ceo_name берём из первого непустого источника (приоритет ExportBase)
    address = checko_address or eb_address
    ceo_name = checko_ceo or eb_ceo

    return merged, address, ceo_name