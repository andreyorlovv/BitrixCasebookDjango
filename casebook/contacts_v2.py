import datetime
import json
from typing import Tuple, List, Any

import requests
import re
from bs4 import BeautifulSoup
from lxml import etree
import sqlite3

from casebook.models import BlackList


def find_phone(text):
    lines = text.split('\n')
    for line in lines:
        if "+7" in line:
            return line


def find_mail(text):
    lines = text.split('\n')
    for line in lines:
        if "@" in line:
            return line


def process_string(input_string, number_list):
    try:
        pattern = re.compile(r'\+7\s\d{3}\s\d{3}-\d{2}-\d{2}|\+8\s\d{3}\s\d{3}-\d{2}-\d{2}')
        matches = pattern.findall(input_string)
        for match in matches:
            number_list.append(match)
        return number_list
    except Exception as e:
        pass


def process_email_string(input_string, email_list):
    try:
        if not isinstance(input_string, str):
            input_string = str(input_string)
        domain_pattern = re.compile(r'([^\s]+?\.(com|ru|net|org|gov|edu|int|mil|co|uk|de|fr|es|it|nl|ca|au|jp|us))')
        matches = domain_pattern.findall(input_string)
        email = [f"{match[0]}" for match in matches]
        email_list.extend(email)
        return email_list
    except Exception as e:
        pass


def remove_duplicates(input_list):
    try:
        unique_list = list(set(input_list))
        return unique_list
    except Exception as e:
        pass


def process_checko_phone(ogrn):
    url = f"https://checko.ru/company/{ogrn}/contacts"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.102 Safari/537.36"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        phone_pattern = re.compile(r'\+7 \d{3} \d{3}-\d{2}-\d{2}')
        phones = phone_pattern.findall(soup.text)
        return phones


def process_checko_email(ogrn):
    url = f"https://checko.ru/company/{ogrn}/contacts"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.102 Safari/537.36"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        email_pattern = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')
        emails = email_pattern.findall(soup.text)
        emails = list(set(emails))
        return emails


def get_name(ogrn: str) -> str:
    inn = str(ogrn)
    url = f"https://checko.ru/company/{ogrn}"
    headers = {
        'User-Agent': 'Mozila/5.0(Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/91.0.4472.124 Safari/537.36'}
    try:
        response = requests.get(url, headers=headers)
        soup2 = BeautifulSoup(response.text, "html.parser")
        dom = etree.HTML(str(soup2))
        return dom.xpath("/html/body/main/div[2]/div/article/div/div[4]/div[2]/div[1]/div/div[2]/a")[0].text
    except Exception as e:
        pass


def process_sbis_base(inn):
    try:
        connection = sqlite3.connect('contacts.sqlite')
        cursor = connection.cursor()
        result = cursor.execute(f'SELECT email, phones FROM contacts_contact WHERE inn={inn}').fetchone()
        return json.loads(result[0]), json.loads(result[1])
    except Exception as e:
        pass


def process_listorg(ogrn, inn):
    """
    Маленькое лимитирование по количеству запросов, пасс
    """

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.102 Safari/537.36"
    }
    response = requests.get(f"https://www.list-org.com/search?val={ogrn}&type=all&sort=", headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    company_tag = soup.find('a', href=lambda x: x and '/company/' in x)  # , name=lambda x: x and '/company/' in x)
    if company_tag:
        company_link = company_tag['href']
        full_link = f"https://www.list-org.com{company_link}"  # Формируем полный URL
    else:
        return None
    response = requests.get(full_link, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    pattern = re.compile(r"\+7\s?\(?\d{3,5}\)?\s?\d{1,3}-\d{2}-\d{2}")
    phones = pattern.findall(soup.text)
    return phones


def get_contacts(inn, ogrn):
    number_list = []
    email_list = []

    number_list.extend(process_checko_phone(ogrn))
    email_list.extend(process_checko_email(ogrn))
    
    print(f'(0) -> {number_list} | {email_list}')

    try:
        numbers_from_sbis, email_from_sbis = process_sbis_base(inn)
    except Exception as e:
        print(e)
    
    number_list.extend(numbers_from_sbis)
    email_list.extend(email_from_sbis)
    
    print(f'(1) -> {number_list} | {email_list}')
    
    valid_numbers = []

    for number in number_list:
        number = number.replace('+7', '7')
        number = number.replace(' ', '')
        number = number.replace('(', '')
        number = number.replace(')', '')
        number = number.replace('-', '')
        if not BlackList.objects.filter(number=number).exists():
            print(f'{number}')
        valid_numbers.append(number)  # if (number[0] == '7' and len(number) == 10) or (len(number) == 9) else None
            
    print(f'(2) -> {number_list} | {email_list}')

    result_email = []
    for email in email_list:
        if not BlackList.objects.filter(email=email).exists():
            print(email)
    
            
    print(f'(3) -> {number_list} | {email_list}')

    result_numbers = list(set(valid_numbers))
    result_email = list(set(email_list))

    print("Полученные контакты -", {'numbers': result_numbers,
                                    'emails': result_email})
    
    return {'numbers': result_numbers,
            'emails': result_email}


def get_contacts_via_export_base(key: str, ogrn: str = None, inn: str = None):
    number_list = []
    email_list = []

    if ogrn and inn:
        url = f'https://export-base.ru/api/company/?inn={inn}&ogrn={ogrn}&key={key}'
    elif ogrn:
        url = f'https://export-base.ru/api/company/?ogrn={ogrn}&key={key}'
    elif inn:
        url = f'https://export-base.ru/api/company/?inn={inn}&key={key}'
    else:
        return {'numbers': number_list,
                'emails': email_list}
    response = requests.get(url)

    result_data = json.loads(response.text)
    try:
        data = result_data['companies_data'][0]
    except IndexError as e:
        return get_contacts(ogrn=ogrn, inn=inn)
    except Exception as e:
        return get_contacts(ogrn=ogrn, inn=inn)
    number_list += data['stationary_phone'].split(', +')
    number_list += data['mobile_phone'].split(', +')

    valid_numbers = []

    for number in number_list:
        valid_numbers.append(number[:17])

    number_list = valid_numbers

    email_list.append(data['email'].split(', ')[0])

    number_list = filter(None, number_list)
    email_list = filter(None, email_list)

    number_list = list(set(number_list))
    email_list = list(set(email_list))

    valid_numbers = []

    for number in number_list:
        number = number.replace('+7', '7')
        number = number.replace(' ', '')
        number = number.replace('(', '')
        number = number.replace(')', '')
        number = number.replace('-', '')
        if not BlackList.objects.filter(number=number).exists():
            print(f'{number}')
        valid_numbers.append(number)  # if (number[0] == '7' and len(number) == 10) or (len(number) == 9) else None

    result_email = []
    for email in email_list:
        if not BlackList.objects.filter(email=email).exists():
            print(email)

    print("Полученные контакты -", {'numbers': result_numbers,
                                    'emails': result_email})
    
    return {'numbers': valid_numbers,
            'emails': result_email}


# if __name__ == "__main__":
#     print(get_name('1105250003044'))
