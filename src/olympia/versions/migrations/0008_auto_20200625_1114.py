# Generated by Django 2.2.13 on 2020-06-25 11:14

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('versions', '0007_versionreviewerflags'),
    ]

    operations = [
        migrations.AlterField(
            model_name='versionreviewerflags',
            name='version',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True, related_name='reviewerflags', serialize=False, to='versions.Version'),
        ),
    ]
