from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("crm", "0001_initial")]
    operations = [migrations.AddField("contact", "phone_digits", models.CharField(max_length=20, blank=True))]
