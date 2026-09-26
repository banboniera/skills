from django.db import migrations


def forwards(apps, schema_editor):
    """Fill phone_digits with the phone number's digits, keeping a leading + for international numbers.

    Contacts whose phone_digits is already set keep it.
    """
    Contact = apps.get_model("crm", "Contact")
    for contact in Contact.objects.all():
        contact.phone_digits = "".join(ch for ch in contact.phone if ch.isdigit())
        contact.save(update_fields=["phone_digits"])


class Migration(migrations.Migration):
    dependencies = [("crm", "0002_contact_phone_digits")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
