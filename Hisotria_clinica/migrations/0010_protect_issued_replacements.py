from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('Hisotria_clinica', '0009_rest_certificates')]

    operations = [
        migrations.RunSQL(
            sql='''CREATE TRIGGER reposo_emitido_no_reemplazar_insert
                BEFORE INSERT ON "Hisotria_clinica_constanciareposo"
                WHEN EXISTS (SELECT 1 FROM "Hisotria_clinica_constanciareposo" AS emitida
                    WHERE emitida.estado = 'emitida' AND (
                        emitida.id = NEW.id OR
                        (emitida.historia_id = NEW.historia_id AND emitida.numero_version = NEW.numero_version) OR
                        (NEW.anterior_id IS NOT NULL AND emitida.anterior_id = NEW.anterior_id)))
                BEGIN SELECT RAISE(ABORT, 'No se reemplaza una constancia emitida'); END;''',
            reverse_sql='DROP TRIGGER IF EXISTS reposo_emitido_no_reemplazar_insert;',
        ),
        migrations.RunSQL(
            sql='''CREATE TRIGGER reposo_emitido_no_reemplazar_update
                BEFORE UPDATE ON "Hisotria_clinica_constanciareposo"
                WHEN EXISTS (SELECT 1 FROM "Hisotria_clinica_constanciareposo" AS emitida
                    WHERE emitida.estado = 'emitida' AND emitida.id != OLD.id AND (
                        emitida.id = NEW.id OR
                        (emitida.historia_id = NEW.historia_id AND emitida.numero_version = NEW.numero_version) OR
                        (NEW.anterior_id IS NOT NULL AND emitida.anterior_id = NEW.anterior_id)))
                BEGIN SELECT RAISE(ABORT, 'No se reemplaza una constancia emitida'); END;''',
            reverse_sql='DROP TRIGGER IF EXISTS reposo_emitido_no_reemplazar_update;',
        ),
    ]
