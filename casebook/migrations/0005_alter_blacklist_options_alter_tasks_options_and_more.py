# Generated by Django 5.0.3 on 2025-01-21 20:50

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('casebook', '0004_blacklist'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='blacklist',
            options={'verbose_name': 'Черный список', 'verbose_name_plural': 'Черный список'},
        ),
        migrations.AlterModelOptions(
            name='tasks',
            options={'verbose_name': 'Подборка', 'verbose_name_plural': 'Подборки'},
        ),
        migrations.AddField(
            model_name='case',
            name='from_task',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='casebook.filter', verbose_name='создано из подборки'),
        ),
        migrations.AddField(
            model_name='tasks',
            name='cash',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='tasks',
            name='contacts',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='tasks',
            name='emails',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='tasks',
            name='to_load',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='case',
            name='process_date',
            field=models.DateTimeField(verbose_name='Дата обработка'),
        ),
    ]
