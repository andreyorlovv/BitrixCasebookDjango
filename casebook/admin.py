from django.contrib import admin
from django.http import HttpResponse

import casebook.tasks
from casebook.forms import ExcelReportForm
from casebook.models import Case, StopList, BlackList, Tasks, InfoDealB24


# Register your models here.
class CaseAdmin(admin.ModelAdmin):
    change_form_template = 'admin/case_view.html'
    change_list_template = 'admin/casebook/Case/change_list.html'

    search_fields = ['case_id']
    list_filter = ['from_task']
    list_display = ('process_date', 'case_id', 'is_success', 'error_message', 'from_task')
    readonly_fields = ['bitrix_lead_id', 'from_task']

    def changelist_view(self, request, *args, **kwargs):

        return super().changelist_view(
            request, *args, **kwargs
        )

    def delete_view(self, request, object_id, extra_context=None):
        if request.method == 'POST':
            case = Case.objects.get(pk=object_id)
            casebook.tasks.delete_lead.apply_async(args=[case.bitrix_lead_id])
        return super().delete_view(
            request, object_id, extra_context=extra_context,
        )

    def change_view(self, request, object_id, form_url="", extra_context=None):
        return super().change_view(
            request, object_id, form_url=form_url, extra_context=extra_context,
        )


class StopListAdmin(admin.ModelAdmin):
    list_display = ('id', 'stopword')
    ordering = ('id',)


class BlackListAdmin(admin.ModelAdmin):
    list_display = ('value', 'type')


class InfoDealB24Admin(admin.ModelAdmin):
    list_display = 'b24_id'
    ordering = 'date_casebook'

admin.site.register(Case, CaseAdmin)
admin.site.register(StopList, StopListAdmin)
admin.site.register(BlackList, BlackListAdmin)
admin.site.register(Tasks)
admin.site.register(InfoDealB24, InfoDealB24Admin)
admin.site.site_header = 'Парсер Casebook'
