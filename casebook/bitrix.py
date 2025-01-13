from datetime import datetime
from types import NoneType

from fast_bitrix24 import Bitrix

from .casebook import Case

courts = {
    'АС Алтайского края': '12606',
    'АС Амурской области': '12607',
    'АС Архангельской области': '12608',
    'АС Астраханской области': '12609',
    'АС Белгородской области': '12585',
    'АС Брянской области': '12611',
    'АС Владимирской области': '12613',
    'АС Волгоградской области': '12614',
    'АС Вологодской области': '12615',
    'АС Воронежской области': '12589',
    'АС города Москвы': '12582',
    'АС города Санкт-Петербурга и Ленинградской обл.': '12592',
    'АС города Севастополя': '12680',
    'АС Еврейской а.о.': '12617',
    'АС Забайкальского края': '12674',
    'АС Запорожской области': '',
    'АС Ивановской области': '12618',
    'АС Иркутской области': '12620',
    'АС Кабардино-Балкарской Республики': '12621',
    'АС Калининградской области': '12622',
    'АС Калужской области': '12624',
    'АС Камчатского края': '12625',
    'АС Карачаево-Черкесской Республики': '12626',
    'АС Кемеровской области': '12628',
    'АС Кировской области': '12629',
    'АС Костромской области': '12631',
    'АС Краснодарского края': '12632',
    'АС Красноярского края': '12633',
    'АС Курганской области': '12634',
    'АС Курской области': '12588',
    'АС Липецкой области': '12635',
    'АС Магаданской области': '12636',
    'АС Московской области': '12590',
    'АС Мурманской области': '12639',
    'АС Нижегородской области': '12640',
    'АС Новгородской области': '12641',
    'АС Новосибирской области': '12642',
    'АС Омской области': '12643',
    'АС Оренбургской области': '12644',
    'АС Орловской области': '12645',
    'АС Пензенской области': '12646',
    'АС Пермского края': '12647',
    'АС Приморского края': '12648',
    'АС Псковской области': '12649',
    'АС Республики Адыгея': '12604',
    'АС Республики Алтай': '12605',
    'АС Республики Башкортостан': '12610',
    'АС Республики Бурятия': '12612',
    'АС Республики Дагестан': '12616',
    'АС Республики Ингушетия': '12619',
    'АС Республики Калмыкия': '12623',
    'АС Республики Карелия': '12627',
    'АС Республики Коми': '12630',
    'АС Республики Крым': '12679',
    'АС Республики Марий Эл': '12637',
    'АС Республики Мордовия': '12638',
    'АС Республики Саха': '12654',
    'АС Республики Северная Осетия': '12657',
    'АС Республики Татарстан': '12661',
    'АС Республики Тыва': '12665',
    'АС Республики Хакасия': '12670',
    'АС Ростовской области': '12650',
    'АС Рязанской области': '12651',
    'АС Самарской области': '12652',
    'АС Саратовской области': '12653',
    'АС Сахалинской области': '12655',
    'АС Свердловской области': '12656',
    'АС Северо-Западного округа': '12594',
    'АС Смоленской области': '12658',
    'АС Ставропольского края': '12659',
    'АС Тамбовской области': '12660',
    'АС Тверской области': '12662',
    'АС Томской области': '12663',
    'АС Тульской области': '12664',
    'АС Тюменской области': '12666',
    'АС Удмуртской Республики': '12667',
    'АС Ульяновской области': '12668',
    'АС Хабаровского края': '12669',
    'АС Ханты-Мансийского АО': '12671',
    'АС Центрального округа': '12587',
    'АС Челябинской области': '12672',
    'АС Чеченской Республики': '12673',
    'АС Чувашской Республики': '12675',
    'АС Чукотского АО': '12676',
    'АС Ямало-Ненецкого АО': '12677',
    'АС Ярославской области': '12678',
    'ААС 19': '12586',
    'ААС 9': '12584',
    'ААС 10': '12591',
    'ААС 13': '12593'
}


class EmptyINN(Exception):
    pass


class BitrixConnect:
    def __init__(self, webhook='https://crm.yk-cfo.ru/rest/1690/eruxj0nx7ria5j0q/'):
        self.bitrix = Bitrix(webhook)

    def create_lead(self, case: Case, rights):
        emails = []
        phones = []

        if case.respondent.inn is None or case.respondent.inn == '':
            from casebook.models import Case as CaseModel
            CaseModel.objects.create(
                process_date=datetime.now(),
                case_id=case.number,
                is_success=False,
                error_message=f'Пустой инн (Для разработчиков -> {case.respondent.inn})',
            )
            return 'Except'
        for phone in case.contacts_info['numbers']:
            phones.append({'VALUE': str(phone), 'VALUE_TYPE': 'WORK'})
        for email in case.contacts_info['emails']:
            emails.append({'VALUE': str(email), 'VALUE_TYPE': 'WORK'})

        UF_CRM_1703235529 = 896 if len(case.respondent.inn) == 12 else 898
        if type(rights) == bool:
            UF_CRM_1703234971 = 893 if rights == True else 894
        elif type(rights) == int:
            UF_CRM_1703234971 = rights
        # UF_CRM_1703235529 = "Исключительные права" if rights else "Неисключительные права"
        # UF_CRM_1703234971 = "Ответчик - ИП" if len(case.respondent.inn) == 12 else "Ответчик - ООО"
        from casebook.contacts_v2 import get_name
        name = get_name(case.respondent.ogrn)

        if type(name) != NoneType:
            if len(name) < 4:
                print("Не удалось найти ФИО")
                items = {"fields": {
                    "TITLE": case.number,
                    "UF_CRM_1703238484214": case.url,
                    "STATUS_ID": "UC_0LLO5N",
                    "COMPANY_TITLE": case.respondent.name,
                    "UF_CRM_1702365701": case.number,
                    "UF_CRM_1702366987": courts.get(case.court),
                    "UF_CRM_1702365740": case.reg_date.isoformat(),
                    "UF_CRM_1702365922": f'{case.plaintiff.name}',
                    "UF_CRM_1702365965": case.sum_,
                    "PHONE": phones,
                    "EMAIL": emails,
                    "UF_CRM_1703235529": UF_CRM_1703235529,
                    "UF_CRM_1703234971": UF_CRM_1703234971,
                    "UF_CRM_1707995533": case.respondent.inn,
                    "ASSIGNED_BY_ID": 9
                }}
            else:
                full_name = name.split(' ')
                items = {"fields": {
                    "TITLE": case.number,
                    "UF_CRM_1703238484214": case.url,
                    "STATUS_ID": "UC_0LLO5N",
                    "COMPANY_TITLE": case.respondent.name,
                    "UF_CRM_1702365701": case.number,
                    "UF_CRM_1702366987": courts.get(case.court),
                    "UF_CRM_1702365740": case.reg_date.isoformat(),
                    "UF_CRM_1702365922": f'{case.plaintiff.name}',
                    "UF_CRM_1702365965": case.sum_,
                    "PHONE": phones,
                    "EMAIL": emails,
                    "UF_CRM_1703235529": UF_CRM_1703235529,
                    "UF_CRM_1703234971": UF_CRM_1703234971,
                    "UF_CRM_1707995533": case.respondent.inn,
                    "ASSIGNED_BY_ID": 9,
                    "LAST_NAME": full_name[0],
                    "NAME": full_name[1],
                    "SECOND_NAME": full_name[2],
                }}
        else:
            items = {"fields": {
                "TITLE": case.number,
                "UF_CRM_1703238484214": case.url,
                "STATUS_ID": "UC_0LLO5N",
                "COMPANY_TITLE": case.respondent.name,
                "UF_CRM_1702365701": case.number,
                "UF_CRM_1702366987": courts.get(case.court),
                "UF_CRM_1702365740": case.reg_date.isoformat(),
                "UF_CRM_1702365922": f'{case.plaintiff.name}',
                "UF_CRM_1702365965": case.sum_,
                "PHONE": phones,
                "EMAIL": emails,
                "UF_CRM_1703235529": UF_CRM_1703235529,
                "UF_CRM_1703234971": UF_CRM_1703234971,
                "UF_CRM_1707995533": case.respondent.inn,
                "ASSIGNED_BY_ID": 9
            }}

        result = '' # self.bitrix.call('crm.lead.add',
                    #              items=items)
        print(items)

        return result

    def delete_lead(self, lead_id):
        self.bitrix.call('crm.lead.delete',
                         {'id': f'{lead_id}'})
