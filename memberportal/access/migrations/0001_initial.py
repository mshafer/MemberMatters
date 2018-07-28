# Generated by Django 2.0.7 on 2018-07-28 05:44

import datetime
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='DoorLog',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateTimeField(default=datetime.datetime.now)),
            ],
        ),
        migrations.CreateModel(
            name='Doors',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=20, unique=True, verbose_name='Door Name')),
                ('description', models.CharField(max_length=100, verbose_name='Door Description/Location')),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True, unique=True, verbose_name='IP Address of Door')),
                ('last_seen', models.DateTimeField(null=True)),
                ('all_members', models.BooleanField(default=False, verbose_name='Members have access by default')),
            ],
        ),
        migrations.AddField(
            model_name='doorlog',
            name='door',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='access.Doors'),
        ),
    ]