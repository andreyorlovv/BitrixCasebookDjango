import datetime
import json
from typing import Tuple, List, Any

import requests
import re
from bs4 import BeautifulSoup


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


def process_two_phone(ogrn):
    links_list = []
    url2 = "https://checko.ru/company/" + ogrn + "?extra=contacts"
    headers = {
        'User-Agent': 'Mozila/5.0(Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    try:
        response_two_0 = requests.get(url2, headers=headers)
        soup2 = BeautifulSoup(response_two_0.text, "html.parser")
        main_element = soup2.find("main", class_="extra-sidebar-page")
        if main_element:
            links = main_element.find_all("a", class_="black-link no-underline")
            if links:
                for link in links[:10]:
                    print(link)
                    links_list.append(link["href"][5:])
            return links_list

        # await process_string(find_phone(info_two.text), number_list)
        # await process_email_string(find_mail(info_two.text), email_list)
    except Exception as e:
        pass


def process_two_email(ogrn):
    links_list = list()
    email_regex = re.compile(
        r"""^(?!\.)(?![_])(?!.*@.*@)(?!.*\.\.)(?!.*@)(?!.*\.)[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.a-zA-Z0-9\:\?[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$""",
        re.IGNORECASE)
    url2 = "https://checko.ru/company/" + ogrn + "?extra=contacts"
    headers = {
        'User-Agent': 'Mozila/5.0(Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    try:
        response_two_0 = requests.get(url2, headers=headers)
        soup2 = BeautifulSoup(response_two_0.text, "html.parser")
        main_element = soup2.find("main", class_="extra-sidebar-page")
        if main_element:
            links = main_element.find_all("a", class_="link", rel="nofollow")
            if links:
                for link in links[1:10]:
                    email = link["href"][7:].replace('\xa0', '')
                    if email_regex.match(email):
                        links_list.append(email)
                email = None
            return links_list

        # await process_string(find_phone(info_two.text), number_list)
        # await process_email_string(find_mail(info_two.text), email_list)
    except Exception as e:
        pass


def get_name(inn: str):
    inn = str(inn)
    url = f"https://checko.ru/company/{inn}"
    headers = {
        'User-Agent': 'Mozila/5.0(Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    try:
        response = requests.get(url, headers=headers)
        soup2 = BeautifulSoup(response.text, "html.parser")
        name = soup2.find('meta', {"property": "og:title"})
        return str(name).split(' - ')[1].replace('Директор ', '').split(' ')
    except Exception as e:
        pass


def process_three(ogrn):
    url3 = "https://companium.ru/id/" + ogrn
    headers = {
        'User-Agent': 'Mozila/5.0(Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    try:
        response_three_0 = requests.get(url3, headers=headers)
        soup3 = BeautifulSoup(response_three_0.text, "html.parser")
        info_three = soup3.find("div", class_="row gy-3 gx-5")
        return info_three.text
        # await process_string(find_phone(info_three.text), number_list)
        # await process_email_string(find_mail(info_three.text), email_list)
    except Exception as e:
        pass


def process_four(ogrn):
    url4 = "https://vbankcenter.ru/contragent/" + ogrn
    headers = {
        'User-Agent': 'Mozila/5.0(Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    try:
        response_four_0 = requests.get(url4, headers=headers)
        soup4 = BeautifulSoup(response_four_0.text, "html.parser")
        info_four = soup4.find("div", class_="requisites-ul-item grid items-start gap-y-4 gap-x-12")
        info_four = info_four.find_all("section")
        return info_four
        # await process_string(find_phone(info_four[3].find("gweb-copy",
        #                                                   class_="gweb-copy relative inline-block mb-0 py-0 copy-available "
        #                                                          "z-10 cursor-pointer copy-right-padding").text),
        #                      number_list)
        # await process_email_string(find_mail(info_four[3].find("a").text), email_list)
    except Exception as e:
        pass


def get_contacts(inn, ogrn):
    number_list = []
    email_list = []

    # three_res = process_three(ogrn)
    # four_res = process_four(ogrn)
    try:
        number_list.extend(process_two_phone(ogrn))
        email_list.extend(process_two_email(ogrn))
    except TypeError:
        pass
    try:
        pass  # process_string(find_phone(three_res), number_list)
    except Exception as e:
        pass
    try:
        pass  # process_email_string(find_mail(three_res), email_list)
    except Exception as e:
        pass

    valid_numbers = []

    for number in number_list:
        number = number.replace('+7', '7')
        valid_numbers.append(number)

    # number_list = list(set(number_list))
    # email_list = list(set(email_list))

    return {'numbers': valid_numbers,
            'emails': email_list}


def get_contacts_via_export_base(key: str, ogrn: str = None, inn: str = None):
    from casebook.models import BlackList

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
        valid_numbers.append(number)

    result_numbers = []

    black_list_number = BlackList.objects.filter(type='phone')

    for number in valid_numbers:
        if number in black_list_number:
            pass
        else:
            result_numbers.append(number)

    result_email = []
    black_list_email = BlackList.objects.filter(type='email')

    for email in email_list:
        if email in black_list_email:
            pass
        else:
            result_email.append(email)

    return {'numbers': result_numbers,
            'emails': result_email}


class EmptyCompanyCredentialsException(Exception):
    def __str__(self):
        return 'Не предоставлены данные для запроса контактных данных'


def complex_get_contacts(ogrn=None, inn=None):
    if ogrn is None and inn is None:
        raise EmptyCompanyCredentialsException()

#
# if __name__ == '__main__':
#     print(get_name("1167746610745"))
#
