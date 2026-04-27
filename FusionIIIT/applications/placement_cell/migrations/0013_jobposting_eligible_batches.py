from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('placement_cell', '0012_placement_claim_and_apply_override'),
    ]

    operations = [
        migrations.AddField(
            model_name='jobposting',
            name='eligible_batches',
            field=models.JSONField(
                blank=True,
                default=list,
                null=True,
                help_text=(
                    "List of batch years eligible to apply, e.g. [2023, 2024]. "
                    "If empty, all batches are eligible."
                ),
            ),
        ),
        migrations.AlterField(
            model_name='jobposting',
            name='eligible_batch_from',
            field=models.IntegerField(
                blank=True,
                null=True,
                help_text=(
                    "(Deprecated) Minimum batch year — use eligible_batches instead."
                ),
            ),
        ),
        migrations.AlterField(
            model_name='jobposting',
            name='eligible_batch_to',
            field=models.IntegerField(
                blank=True,
                null=True,
                help_text=(
                    "(Deprecated) Maximum batch year — use eligible_batches instead."
                ),
            ),
        ),
    ]
