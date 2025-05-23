# Generated by Django 5.0.3 on 2025-02-08 00:08

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('casebook', '0005_alter_blacklist_options_alter_tasks_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='tasks',
            name='scan_p',
            field=models.BooleanField(default=False, verbose_name='Применять стоп-слова на истцов'),
        ),
        migrations.AddField(
            model_name='tasks',
            name='scan_r',
            field=models.BooleanField(default=False, verbose_name='Применять стоп-слова на ответчиков'),
        ),
        migrations.AlterField(
            model_name='case',
            name='case_id',
            field=models.CharField(max_length=64, verbose_name='ID в CaseBook'),
        ),
        migrations.AlterField(
            model_name='tasks',
            name='cash',
            field=models.IntegerField(blank=True, null=True, verbose_name='Минимальная сумма'),
        ),
        migrations.AlterField(
            model_name='tasks',
            name='contacts',
            field=models.IntegerField(blank=True, null=True, verbose_name='Кол-во телефонов'),
        ),
        migrations.AlterField(
            model_name='tasks',
            name='days_expire',
            field=models.IntegerField(verbose_name='Кол-во дней давности'),
        ),
        migrations.AlterField(
            model_name='tasks',
            name='emails',
            field=models.IntegerField(blank=True, null=True, verbose_name='Кол-во email'),
        ),
        migrations.AlterField(
            model_name='tasks',
            name='filter_id',
            field=models.CharField(max_length=64, verbose_name='ID фильтра'),
        ),
        migrations.AlterField(
            model_name='tasks',
            name='iteration_interval',
            field=models.IntegerField(verbose_name='Интервал выполнения задачи (in dev)'),
        ),
        migrations.AlterField(
            model_name='tasks',
            name='last_execution',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Последнее выполнение'),
        ),
        migrations.AlterField(
            model_name='tasks',
            name='to_load',
            field=models.IntegerField(blank=True, null=True, verbose_name='Кого загружать (0 - ответчик, 1 - истец)'),
        ),
    ]
