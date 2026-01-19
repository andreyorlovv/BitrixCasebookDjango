import logging
import os
from datetime import datetime

from dateutil import parser
from fast_bitrix24 import Bitrix

from .casebook import Case
from .contacts_v2 import get_name
from .models import Case as CaseModel, Filter

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

class LocalPlaceholderB24:

    """
    Для локального дебаггинга
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
    def call(self, method, items, **kwargs):
        self.logger.debug("calling method %s with items %s \n **kwargs = %s" % (method, items, kwargs))

    def get_all(self, method, **kwargs):
        self.logger.debug("calling method %s with kwargs %s" % (method, kwargs))


logging.getLogger('fast_bitrix24').setLevel('INFO')


class BitrixConnect:
    def __init__(self, webhook='https://crm.yk-cfo.ru/rest/782/rl70y07llnky74jv/'):
        if os.environ.get('local_debug') == 'True':
            self.bitrix = LocalPlaceholderB24()
        else:
            self.bitrix = Bitrix(webhook)
    def create_lead(self, case: Case, rights, filter_id):
        if not case.respondent.inn:
            CaseModel.objects.create(
                process_date=datetime.now(),
                case_id=case.number,
                is_success=False,
                error_message=f'Пустой инн (Для разработчиков -> {case.respondent.inn})',
                from_task=Filter.objects.get(filter_id=filter_id)
            )
            return 'Except'

        phones = [{'VALUE': str(phone), 'VALUE_TYPE': 'WORK'}
                  for phone in case.contacts_info['numbers']]
        emails = [{'VALUE': str(email), 'VALUE_TYPE': 'WORK'}
                  for email in case.contacts_info['emails']]
        bl_phones = ' | '.join(str(p) for p in case.contacts_info['blacklist_numbers'])
        bl_emails = ' | '.join(str(e) for e in case.contacts_info['blacklist_emails'])

        # Определяем тип ответчика: 896 = ИП, 898 = ООО
        respondent_type = 896 if len(case.respondent.inn) == 12 else 898

        # Определяем тип прав: 893 = исключительные, 894 = неисключительные
        if isinstance(rights, bool):
            rights_type = 893 if rights else 894
        elif isinstance(rights, (int, str)):
            rights_type = rights
        else:
            rights_type = 894

        # Базовые поля лида
        fields = {
            "TITLE": case.number,
            "UF_CRM_1703238484214": case.url,
            "STATUS_ID": "UC_0LLO5N",
            "COMPANY_TITLE": case.respondent.name,
            "UF_CRM_1702365701": case.number,
            "UF_CRM_1702366987": courts.get(case.court),
            "UF_CRM_1702365740": case.reg_date.isoformat(),
            "UF_CRM_1702365922": case.plaintiff.name,
            "UF_CRM_1702365965": case.sum_,
            "PHONE": phones,
            "EMAIL": emails,
            "UF_CRM_1703235529": respondent_type,
            "UF_CRM_1703234971": rights_type,
            "UF_CRM_1707995533": case.respondent.inn,
            "ASSIGNED_BY_ID": 1690,
            "ADDRESS": case.respondent.address,
            "UF_CRM_1759395470157": bl_phones,
            "UF_CRM_1759395435927": bl_emails,
        }

        # Добавляем ФИО если удалось получить
        name = get_name(case.respondent.ogrn)
        if name is not None:
            if len(name) >= 4:
                full_name = name.split(' ')
                if len(full_name) >= 3:
                    fields["LAST_NAME"] = full_name[0]
                    fields["NAME"] = full_name[1]
                    fields["SECOND_NAME"] = full_name[2]
            elif 'Индивидуальный предприниматель' in case.respondent.name:
                name_parts = case.respondent.name.split()
                if len(name_parts) >= 5:
                    fields["LAST_NAME"] = name_parts[2]
                    fields["NAME"] = name_parts[3]
                    fields["SECOND_NAME"] = name_parts[4]

        if case.case_type is not None:
            fields['UF_CRM_1765382316'] = case.case_type
        if case.case_category is not None:
            fields['UF_CRM_1765382357'] = case.case_category

        result = self.bitrix.call('crm.lead.add', items={"fields": fields})
        return result

    def delete_lead(self, lead_id):
        self.bitrix.call('crm.lead.delete',
                         {'id': f'{lead_id}'})

    def get_cases(self, filter_):
        result = self.bitrix.get_all('crm.deal.list',
                                     {'select': ['*', 'UF_*'],
                                      'filter': {'CLOSED': 'N'} | filter_,
                                      })
        return result

    def add_comment_case(self, deal, event):
        id_ = deal['ID']

        comment = f"[Kad.Arbitr] {parser.parse(event['registrationDate']).date()} - {event['type']} - {event['contentTypes'][0]['value']} \n"
        try:
            comment += f"Заявитель: {event['reasonDocumentInfo']['declarers'][0]['shortName']}"
        except KeyError as e:
            pass
        file = f'https://casebook.ru/File/PdfDocument/{event["caseId"]}/{event["id"]}/{event["fileName"]}' if event.get(
            'fileName') else 'Нет файла'

        result = self.bitrix.call('bizproc.workflow.start',
                                  {
                                            "TEMPLATE_ID": 482,
                                            "DOCUMENT_ID": ["crm", "CCrmDocumentDeal", id_],
                                            "PARAMETERS": {"text": comment + ' \n ' + file}
                                  }
        )

        result = self.bitrix.call('crm.timeline.comment.add',
                                  {
                                      'fields': {
                                          'ENTITY_ID': id_,
                                          'ENTITY_TYPE': 'deal',
                                          'COMMENT': comment + ' \n ' + file,
                                      }
                                  })
        return result
