from django.db import migrations


def grant_placement_access(apps, schema_editor):
    """
    Ensure placement officer, placement chairman, and student designations
    have placement_cell=True in ModuleAccess so the sidebar link shows up.
    """
    ModuleAccess = apps.get_model('globals', 'ModuleAccess')

    designations = ['placement officer', 'placement chairman', 'student']
    for designation in designations:
        obj, created = ModuleAccess.objects.get_or_create(
            designation=designation,
        )
        if not obj.placement_cell:
            obj.placement_cell = True
            obj.save(update_fields=['placement_cell'])


def revoke_placement_access(apps, schema_editor):
    """Reverse: set placement_cell=False for these designations."""
    ModuleAccess = apps.get_model('globals', 'ModuleAccess')
    ModuleAccess.objects.filter(
        designation__in=['placement officer', 'placement chairman']
    ).update(placement_cell=False)


class Migration(migrations.Migration):

    dependencies = [
        ('globals', '0005_moduleaccess_database'),
    ]

    operations = [
        migrations.RunPython(grant_placement_access, revoke_placement_access),
    ]
