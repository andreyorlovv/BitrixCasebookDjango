from _datetime import datetime, timedelta

import django.http


def expire_middleware(get_response):
    def middleware(request):
        if datetime.today() - datetime(2024, 4, 16) >= timedelta(days=0):
            return django.http.HttpResponse(status=502)
        response = get_response(request)

        return response

    return middleware

