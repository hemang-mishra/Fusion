from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('placement_cell', '0006_auto_20260415_2035'),
    ]

    operations = [
        migrations.AddField(
            model_name='announcement',
            name='expires_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='announcement',
            name='notice_type',
            field=models.CharField(
                choices=[('PLACEMENT', 'Placement'), ('POLICY', 'Policy'), ('GENERAL', 'General')],
                default='GENERAL',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='announcement',
            name='priority',
            field=models.CharField(
                choices=[('HIGH', 'High'), ('NORMAL', 'Normal')],
                default='NORMAL',
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name='announcement',
            name='publish_at',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AddField(
            model_name='announcement',
            name='visibility_scope',
            field=models.CharField(
                choices=[('ALL', 'All'), ('SPECIFIC_BATCH', 'Specific Batch')],
                default='ALL',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='announcement',
            name='visibility_targets',
            field=models.CharField(
                blank=True,
                help_text='Comma-separated targets when visibility_scope is SPECIFIC_BATCH',
                max_length=200,
                null=True,
            ),
        ),
    ]
