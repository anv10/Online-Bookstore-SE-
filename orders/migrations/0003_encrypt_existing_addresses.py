from cryptography.fernet import InvalidToken
from django.db import migrations

from bookstore.fields import _fernet


def encrypt_existing(apps, schema_editor):
    fernet = _fernet()
    cursor = schema_editor.connection.cursor()
    cursor.execute("SELECT id, shipping_address FROM orders_order")
    for pk, value in cursor.fetchall():
        try:
            fernet.decrypt(value.encode())
            continue  # already encrypted
        except InvalidToken:
            pass
        cursor.execute(
            "UPDATE orders_order SET shipping_address = %s WHERE id = %s",
            [fernet.encrypt(value.encode()).decode(), pk],
        )


def decrypt_existing(apps, schema_editor):
    fernet = _fernet()
    cursor = schema_editor.connection.cursor()
    cursor.execute("SELECT id, shipping_address FROM orders_order")
    for pk, value in cursor.fetchall():
        try:
            plain = fernet.decrypt(value.encode()).decode()
        except InvalidToken:
            continue
        cursor.execute("UPDATE orders_order SET shipping_address = %s WHERE id = %s", [plain, pk])


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0002_encrypt_shipping_address"),
    ]

    operations = [
        migrations.RunPython(encrypt_existing, decrypt_existing),
    ]
