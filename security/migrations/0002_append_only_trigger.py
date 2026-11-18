"""Protect the security log in the database itself (SEC-32).

On PostgreSQL a trigger rejects every UPDATE of a security event and every
DELETE of one younger than the 90-day retention period, so neither the ORM nor
raw SQL from the application role can rewrite recent history. TRUNCATE (used
only by the test runner's flush) is not affected.
"""

from django.db import migrations

CREATE = """
CREATE OR REPLACE FUNCTION security_event_guard() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'security events are append-only';
    END IF;
    IF OLD.created_at > now() - interval '90 days' THEN
        RAISE EXCEPTION 'security events are kept for the 90-day retention period';
    END IF;
    RETURN OLD;
END
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS security_event_guard ON security_securityevent;
CREATE TRIGGER security_event_guard BEFORE UPDATE OR DELETE ON security_securityevent
    FOR EACH ROW EXECUTE FUNCTION security_event_guard();
"""

DROP = """
DROP TRIGGER IF EXISTS security_event_guard ON security_securityevent;
DROP FUNCTION IF EXISTS security_event_guard();
"""


def _run(sql):
    def apply(apps, schema_editor):
        if schema_editor.connection.vendor == "postgresql":
            schema_editor.execute(sql)

    return apply


class Migration(migrations.Migration):
    dependencies = [("security", "0001_security_event_and_rate_limits")]

    operations = [migrations.RunPython(_run(CREATE), _run(DROP))]
