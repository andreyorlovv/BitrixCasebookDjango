FROM python:3.10

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /code

COPY requirements.txt /code/
RUN pip install --no-cache-dir -r requirements.txt

RUN pip install gunicorn

COPY . /code/

RUN apt-get update && apt-get install -y supervisor
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

#CMD ["gunicorn", "--bind", "0.0.0.0:8000", "your_project_name.wsgi:application"]

#RUN python manage.py migrate
#
#RUN python manage.py loaddata stoplist.json

EXPOSE 8000

CMD ["supervisord", "-n"]