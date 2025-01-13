# Generated by Django 5.0.3 on 2025-01-13 20:31

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
        migrations.AddField(
            model_name='tasks',
            name='cash',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='tasks',
            name='to_load',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='case',
            name='case_id',
            field=models.CharField(max_length=64, verbose_name='ID в CaseBook'),
        ),
    ]
