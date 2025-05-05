import dataclasses
import datetime
import os
import sys
import time
import json

import urllib3
from django.conf import settings

from casebook import models
from casebook.models import StopList, BlackList, Filter
from casebook.models import Case as CaseModel


class GetOutOfLoop(Exception):
    pass


@dataclasses.dataclass
class Side:
    name: str
    inn: str
    ogrn: str
    address: str | None = None


@dataclasses.dataclass
class Case:
    sum_: float
    plaintiff: Side
    respondent: Side
    court: str
    url: str
    number: str
    reg_date: datetime.date
    _type: dict
    contacts_info: dict = dataclasses.field(default_factory=dict)
    error: str = None


class BlackListException(Exception):
    pass


class Casebook:
    def __init__(self, login, password):
        self.headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ('
                                      'KHTML, like Gecko) Chrome/118.0.5993.2470 '
                                      'YaBrowser/23.11.0.2470'
                                      'Yowser/2.5 Safari/537.36'}
        self.auth_email = None
        self.auth_token = None
        self.login = login
        self.password = password
        self.http_client = urllib3.PoolManager()
        self.filters = None
        self.headless_auth(login, password)
        self.http_client.headers.update(self.headers)

        # self.get_filters()

    def headless_auth(self, login: str = None, password: str = None):
            http_client = self.http_client
            if login is None and password is None:
                login = self.login
                password = self.password

            body = f'''
                        {{
                            "systemName": "Sps",
                            "username": "{login}",
                            "password": "{password}"
                        }}
                        '''

            http_client.headers.update({'Content-Type': 'application/json',
                                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.5993.2470 YaBrowser/23.11.0.2470 Yowser/2.5 Safari/537.36'})

            response = http_client.request('POST', 'https://casebook.ru/api/Account/LogOn', f'{body}')

            # asp_token = re.search(r"(?<=ASPXAUTH=)\w{64}", response.headers['Set-Cookie']).group()

            response_token = http_client.request('GET',
                                                 f'https://casebook.ru/ms/webassembly/Wasm/api/v1/protection.js?_={round(time.time() * 1000)}',
                                                 headers={
                                                     'Cookie': response.headers['Set-Cookie']
                                                 })

            print("Статус запроса JWT токена = " + str(response_token.status))

            token_list = response_token.headers['set-cookie'].split(';')
            
            token = None

            for line in token_list:
                if '.AuthToken=' in line:
                    token = line.split('.AuthToken=')[1]

            if token is None:
                raise Exception('Не получили JWT токен от кейсбука')

            # token = response_token.headers['set-cookie'].split(';')[0].split('=')[1]

            self.auth_token = token
            self.auth_email = login

            self.headers = {
                'cookie': f'.AuthToken={self.auth_token};'
                          f' .AuthEmail={self.auth_email}',
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                              'Chrome/118.0.5993.2470 YaBrowser/23.11.0.2470 Yowser/2.5 Safari/537.36',
                'content-type': 'application/json'
            }

    def get_filters(self):
        self.headless_auth()
        response = self.http_client.request('GET', 'https://casebook.ru/ms/UserData/SavedSearch/List',
                                            headers=self.headers)
        
        try:
            serialized = json.loads(response.data)
            self.filters = [
            {"name": filter_['name'], "id": filter_["id"], "filter": json.loads(filter_['serializedRequest'])}
            for filter_ in serialized['result']]
            return self.filters
        except json.decoder.JSONDecodeError:
            self.headless_auth()
        
    def get_cases(self, filter_source, timedelta, to_load, cash=None, scan_p=False, scan_r=True, filter_id=None,
                  scan_or=False, ignore_other_tasks_processed=False, task_id=None):
        import ast
        serialized = None
        i = 0
        filter_ = filter_source['filter']
        for filter__ in filter_['items']:
            try:
                if filter__['filter']['type'] == 'CaseStartDate':
                    filter_['items'][i]['filter']['value'] = {
                        'from': (datetime.datetime.now().date() - datetime.timedelta(days=timedelta)).strftime(
                            '%Y-%m-%d'),
                        'to': datetime.datetime.now().date().strftime('%Y-%m-%d')
                    }
                else:
                    i += 1
            except KeyError:
                i += 1
        query = filter_
        query['page'] = 1
        query['count'] = 30
        query['isNeedStat'] = True
        query = str(query)
        response = self.http_client.request('POST', 'https://casebook.ru/ms/Search/Cases/Search',
                                            body=query.replace('None', 'null')
                                            .replace("'", '"')
                                            .replace('True', 'true')
                                            .replace('False', 'false'),
                                            headers=self.headers)
        print(f"Статус запроса кол-ва страниц - {response.status}")
        serialized = json.loads(response.data)
        pages = serialized['result']['pagesCount']
        cases = []
        result = []
        for page in range(1, pages + 1):
            serialized_page = None
            curr_query = filter_
            curr_query['page'] = page
            curr_query['count'] = 30
            curr_query['isNeedStat'] = True
            curr_query = str(curr_query)
            response = self.http_client.request('POST', 'https://casebook.ru/ms/Search/Cases/Search',
                                                body=curr_query.replace('None', 'null')
                                                .replace("'", '"')
                                                .replace('True', 'true')
                                                .replace('False', 'false'),
                                                headers=self.headers)
            print(f"Статус запроса {page}-ой страницы - {response.status}")
            try:
                serialized_page = json.loads(response.data)
                print(response.data, ' ---||---', response.status)
            except Exception as e:
                print(response.data)
                print(e)
                continue
            for case in serialized_page['result']['items']:
                cases.append(case)
        for case in cases:
            if cash:
                if case['claimSum'] <= cash and not CaseModel.objects.filter(case_id=case['caseNumber'], from_task__id=task_id).exists():
                    import casebook
                    models.Case.objects.create(
                        process_date=datetime.datetime.now(),
                        case_id=case['caseNumber'],
                        is_success=False,
                        error_message=f'Сумма дела меньше целевой: {cash} > {case["claimSum"]}',
                        from_task=Filter.objects.get(filter_id=filter_id),
                    )
            if len(case['sides']) > 2:
                _respondent = 0
                _plaintiff = 0
                _other = 0
                for side in case['sides']:
                    if side['nSideTypeEnum'] == 'Other':
                        _other += 1
                    elif side['nSideTypeEnum'] == 'Plaintiff':
                        _plaintiff += 1
                    elif side['nSideTypeEnum'] == 'Respondent':
                        _respondent += 1
                    else:
                        _other += 1
                try:
                    if _respondent > 1:
                        import casebook
                        models.Case.objects.create(
                            process_date=datetime.datetime.now(),
                            case_id=case['caseNumber'],
                            is_success=False,
                            error_message='больше одного ответчика, отфильтровано',
                            from_task=Filter.objects.get(filter_id=filter_id)
                        )
                        cases.remove(case)
                except Exception as e:
                    pass
        cases_to_process = []
        for case in cases:
            if not CaseModel.objects.filter(case_id=case['caseNumber']).exists():
                cases_to_process.append(case)
            elif not CaseModel.objects.filter(case_id=case['caseNumber'], from_task__id=task_id).exists() and ignore_other_tasks_processed:
                    cases_to_process.append(case)
        cases = cases_to_process
        company_black_list = BlackList.objects.filter(type='inn')
        for case in cases:
            try:
                plaintiff = None
                respondent = None
                for side in case['sides']:
                    address = side.get('address', 'Адрес не передан с кейсбука')
                    if side['typeEnum'] == "Plaintiff":
                        plaintiff = Side(
                            name=side['name'],
                            inn=side['inn'],
                            ogrn=side['ogrn'],
                            address=address,
                        )
                    elif side['typeEnum'] == "Respondent":
                        respondent = Side(
                            name=side['name'],
                            inn=side['inn'],
                            ogrn=side['ogrn'],
                            address=address,
                        )
                    # Создание 2х сущностей, истец ответчик
                    if plaintiff:
                        try:
                            if BlackList.objects.filter(value=side['inn']).exists():
                                raise BlackListException(f"{side['inn']} в черном списке")
                            else: pass
                        except BlackListException as e:
                            models.Case.objects.create(
                                process_date=datetime.datetime.now(),
                                case_id=case['caseNumber'],
                                is_success=False,
                                error_message=f'Ошибка: {e}',
                                from_task=Filter.objects.get(filter_id=filter_id)
                            )
                        if side['inn'] in company_black_list:
                            raise BlackListException(f"{side['inn']} в черном списке")
                    if respondent and scan_r:
                        stoplist = StopList.objects.all()
                        for stopword in stoplist:
                            if stopword.stopword.upper() in respondent.name.upper():
                                models.Case.objects.create(
                                    process_date=datetime.datetime.now(),
                                    case_id=case['caseNumber'],
                                    is_success=False,
                                    error_message=f'Встретилось стоп слово: {stopword.stopword}',
                                    from_task=Filter.objects.get(filter_id=filter_id)
                                )
                                raise GetOutOfLoop
                    if side['nSideTypeEnum'] == 'OtherRespondent' and scan_or:
                        stoplist = StopList.objects.all()
                        for stopword in stoplist:
                            if stopword.stopword.upper() in side['name'].upper():
                                models.Case.objects.create(
                                    process_date=datetime.datetime.now(),
                                    case_id=case['caseNumber'],
                                    is_success=False,
                                    error_message=f'Встретилось стоп слово: {stopword.stopword}; type - OtherRespondent',
                                    from_task=Filter.objects.get(filter_id=filter_id)
                                )
                                raise GetOutOfLoop
                    if plaintiff and scan_p:
                        stoplist = StopList.objects.all()
                        for stopword in stoplist:
                            if stopword.stopword.upper() in plaintiff.name.upper():
                                models.Case.objects.create(
                                    process_date=datetime.datetime.now(),
                                    case_id=case['caseNumber'],
                                    is_success=False,
                                    error_message=f'Встретилось стоп слово: {stopword.stopword}',
                                    from_task = Filter.objects.get(filter_id=filter_id)
                                )
                                raise GetOutOfLoop
                if to_load == 1: plaintiff, respondent = respondent, plaintiff
                case_ = Case(
                    plaintiff=plaintiff,
                    respondent=respondent,
                    court=case['instancesInternal'][0]['court'],
                    url=f'https://casebook.ru/card/case/{case["caseId"]}',
                    number=case['caseNumber'],
                    reg_date=datetime.datetime.fromisoformat(case['startDate']).date(),
                    _type={
                        "caseTypeM": case['caseTypeMCode'],
                        "caseTypeENG": case['caseType']
                    },
                    sum_=case['claimSum']
                )
                result.append(case_)
            except UnboundLocalError:
                models.Case.objects.create(
                    process_date=datetime.datetime.now().date(),
                    case_id=case['caseNumber'],
                    is_success=False,
                    error_message=f'Ошибка: {case}',
                    from_task=Filter.objects.get(filter_id=filter_id)
                )
            except BlackListException as e:
                models.Case.objects.create(
                    process_date=datetime.datetime.now().date(),
                    case_id=case['caseNumber'],
                    is_success=False,
                    error_message=f'Ошибка: {e}',
                    from_task = Filter.objects.get(filter_id=filter_id)
                )
            except GetOutOfLoop:
                pass
        return result


if __name__ == '__main__':
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'BitrixCasebook.settings')

    login = os.environ.get('CASEBOOK_LOGIN')
    password = os.environ.get('CASEBOOK_PASSWORD')

    casebook_api = Casebook(login, password)

    print(casebook_api.get_filters())
