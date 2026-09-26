from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("crm", "0003_backfill_phone_digits")]
    operations = [migrations.AddField("contact", "note", models.CharField(max_length=50, blank=True))]
