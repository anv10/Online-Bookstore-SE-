"""Encrypt phone numbers at rest (SEC-17).

The phone column becomes an encrypted text column; a keyed hash in
``phone_digest`` takes over lookup and uniqueness. Existing numbers are
encrypted in place, and the migration can be reversed.
"""

from cryptography.fernet import InvalidToken
from django.db import migrations, models

import bookstore.fields
from bookstore.fields import _fernet


def encrypt_existing(apps, schema_editor):
    from accounts.models import phone_digest

    fernet = _fernet()
    cursor = schema_editor.connection.cursor()
    cursor.execute("SELECT id, phone FROM accounts_user WHERE phone IS NOT NULL AND phone <> ''")
    for pk, value in cursor.fetchall():
        try:
            plain = fernet.decrypt(value.encode()).decode()
        except InvalidToken:
            plain = value
        cursor.execute(
            "UPDATE accounts_user SET phone = %s, phone_digest = %s WHERE id = %s",
            [fernet.encrypt(plain.encode()).decode(), phone_digest(plain), pk],
        )


def decrypt_existing(apps, schema_editor):
    fernet = _fernet()
    cursor = schema_editor.connection.cursor()
    cursor.execute("SELECT id, phone FROM accounts_user WHERE phone IS NOT NULL")
    for pk, value in cursor.fetchall():
        try:
            plain = fernet.decrypt(value.encode()).decode()
        except InvalidToken:
            continue
        cursor.execute("UPDATE accounts_user SET phone = %s WHERE id = %s", [plain, pk])


class Migration(migrations.Migration):
    dependencies = [("accounts", "0005_passwordresetotp")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="phone_digest",
            field=models.CharField(blank=True, editable=False, max_length=64, null=True),
        ),
        migrations.AlterField(
            model_name="user",
            name="phone",
            field=bookstore.fields.EncryptedTextField(blank=True, null=True),
        ),
        migrations.RunPython(encrypt_existing, decrypt_existing),
        migrations.AlterField(
            model_name="user",
            name="phone_digest",
            field=models.CharField(blank=True, editable=False, max_length=64, null=True, unique=True),
        ),
    ]
