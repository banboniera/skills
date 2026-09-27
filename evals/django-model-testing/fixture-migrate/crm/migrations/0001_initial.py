from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = []
    operations = [
        migrations.CreateModel(
            "Contact",
            [
                ("id", models.BigAutoField(primary_key=True)),
                ("name", models.CharField(max_length=100)),
                ("phone", models.CharField(max_length=30)),
            ],
        ),
    ]
