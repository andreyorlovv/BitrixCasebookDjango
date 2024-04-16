from django.db import models


# Create your models here.

class Filter(models.Model):
    name = models.CharField(max_length=64)
    value = models.JSONField()
    filter_id = models.CharField(max_length=128)


class Case(models.Model):
    process_date = models.DateField(verbose_name="Дата обработка")
    case_id = models.CharField(max_length=32, verbose_name="ID в CaseBook")
    is_success = models.BooleanField(default=False, verbose_name="Успешно выполнено?")
    error_message = models.TextField(blank=True, null=True, verbose_name="Ошибка, если не успешно")
    bitrix_lead_id = models.CharField(blank=True, null=True, verbose_name="ID лида в Б24")

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
    days_expire = models.IntegerField()
    iteration_interval = models.IntegerField()
    filter_id = models.CharField(max_length=64)
    last_execution = models.DateTimeField(blank=True, null=True)


class BlackList(models.Model):
    value = models.CharField(max_length=255, verbose_name='Значение', unique=True)
    type = models.CharField(max_length=32, verbose_name="Тип",
                            choices=[
                                ('inn', 'Организация'),
                                ('email', 'эл.почта'),
                                ('phone', 'Номер телефона')
                            ])

    def __str__(self):
        return f'{self.value} | {self.type}'

    class Meta:
        verbose_name = 'Черный список'
        verbose_name_plural = 'Черный список'
