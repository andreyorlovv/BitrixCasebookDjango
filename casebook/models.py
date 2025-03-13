from email.policy import default

from django.db import models


# Create your models here.

class Filter(models.Model):
    name = models.CharField(max_length=64)
    value = models.JSONField()
    filter_id = models.CharField(max_length=128)

    def __str__(self):
        return self.name


class Case(models.Model):
    process_date = models.DateTimeField(verbose_name="Дата обработка")
    case_id = models.CharField(max_length=64, verbose_name="ID в CaseBook")
    is_success = models.BooleanField(default=False, verbose_name="Успешно выполнено?")
    error_message = models.TextField(blank=True, null=True, verbose_name="Ошибка, если не успешно")
    bitrix_lead_id = models.CharField(blank=True, null=True, verbose_name="ID лида в Б24")
    from_task = models.ForeignKey("Filter", on_delete=models.CASCADE, blank=True, null=True, verbose_name='создано из подборки')

    def __str__(self):
        return self.case_id

    class Meta:
        verbose_name = "Обработанное дело"
        verbose_name_plural = "Обработанные дела"
        db_table = 'processed_case'


class StopList(models.Model):
    stopword = models.CharField(max_length=128, verbose_name='Стоп-слово')

    class Meta:
        verbose_name = 'Стоп-слов'
        verbose_name_plural = 'Стоп-слова   '
        db_table = 'stopwords'


class Tasks(models.Model):
    days_expire = models.IntegerField(verbose_name='Кол-во дней давности')
    iteration_interval = models.IntegerField(verbose_name='Интервал выполнения задачи (in dev)')
    filter_id = models.CharField(max_length=64, verbose_name='ID фильтра')
    last_execution = models.DateTimeField(blank=True, null=True, verbose_name='Последнее выполнение')
    to_load = models.IntegerField(blank=True, null=True, verbose_name='Кого загружать (0 - ответчик, 1 - истец)')
    cash = models.IntegerField(blank=True, null=True, verbose_name='Минимальная сумма')
    scan_p = models.BooleanField(default=False, verbose_name='Применять стоп-слова на истцов')
    scan_r = models.BooleanField(default=False, verbose_name='Применять стоп-слова на ответчиков')
    scan_or = models.BooleanField(default=False, verbose_name='Применять стоп-слова на поле `OtherRespondent`')
    regex_p = models.CharField(default=None, null=True, blank=True, verbose_name='Регулярное выражение для истцов (в разработке)')
    regex_r = models.CharField(default=None, null=True, blank=True, verbose_name='Регулярное выражение для ответчиков (в разработке)')
    ignore_other_tasks_processed = models.BooleanField(default=False, verbose_name='Игнорировать кейсы обработки других подборок')
    contacts = models.IntegerField(blank=True, null=True, verbose_name='Кол-во телефонов')
    emails = models.IntegerField(blank=True, null=True, verbose_name='Кол-во email')

    def __str__(self):
        return f'{Filter.objects.get(filter_id=self.filter_id).name} - {self.last_execution}'

    class Meta:
        verbose_name = 'Подборка'
        verbose_name_plural = 'Подборки'


class BlackList(models.Model):
    value = models.CharField(max_length=255, verbose_name='Значение')
    type = models.CharField(max_length=32, verbose_name="Тип",
                            choices=[
                                ('inn', 'Организация'),
                                ('email', 'эл.почта'),
                                ('phone', 'Номер телефона'),
                                ('email_mask', 'Домен эл.почты')
                            ])

    def __str__(self):
        return f'{self.value} | {self.type}'

    class Meta:
        verbose_name = 'Черный список'
        verbose_name_plural = 'Черный список'
