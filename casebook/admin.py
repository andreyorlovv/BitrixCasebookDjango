from django.contrib import admin

from casebook.models import Case, StopList


# Register your models here.
class CaseAdmin(admin.ModelAdmin):
    list_display = ('process_date', 'case_id', 'is_success', 'error_message')


class StopListAdmin(admin.ModelAdmin):
    list_display = ('id', 'stopword')
    ordering = ('id',)

admin.site.register(Case, CaseAdmin)
admin.site.register(StopList, StopListAdmin)
admin.site.site_header = 'Парсер Casebook'
