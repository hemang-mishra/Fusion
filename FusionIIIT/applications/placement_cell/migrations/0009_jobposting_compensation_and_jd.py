from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('placement_cell', '0008_dynamic_job_forms_and_resumes'),
    ]

    operations = [
        # ---- JobPosting compensation + JD link ----
        migrations.AddField(
            model_name='jobposting',
            name='compensation_type',
            field=models.CharField(
                max_length=30,
                choices=[
                    ('LPA', 'Annual CTC (LPA)'),
                    ('STIPEND_PER_MONTH', 'Stipend (per month)'),
                ],
                default='LPA',
                help_text=(
                    "How `ctc` should be interpreted (annual CTC vs monthly "
                    "stipend)."
                ),
            ),
        ),
        migrations.AddField(
            model_name='jobposting',
            name='internship_duration_months',
            field=models.PositiveSmallIntegerField(
                null=True, blank=True,
                help_text='Duration in months for internships (optional).',
            ),
        ),
        migrations.AddField(
            model_name='jobposting',
            name='jd_link',
            field=models.URLField(
                max_length=1000, blank=True, null=True,
                help_text='Optional external job description link.',
            ),
        ),
        migrations.AlterField(
            model_name='jobposting',
            name='ctc',
            field=models.DecimalField(
                decimal_places=2, max_digits=10,
                help_text=(
                    "Compensation amount. Interpreted as LPA when "
                    "compensation_type='LPA' and as stipend per month when "
                    "compensation_type='STIPEND_PER_MONTH'."
                ),
            ),
        ),
        # ---- JobRole compensation overrides ----
        migrations.AddField(
            model_name='jobrole',
            name='compensation_type',
            field=models.CharField(
                max_length=30,
                choices=[
                    ('LPA', 'Annual CTC (LPA)'),
                    ('STIPEND_PER_MONTH', 'Stipend (per month)'),
                ],
                null=True, blank=True,
                help_text=(
                    'Override for compensation interpretation; falls back to '
                    'posting compensation_type if null.'
                ),
            ),
        ),
        migrations.AddField(
            model_name='jobrole',
            name='internship_duration_months',
            field=models.PositiveSmallIntegerField(
                null=True, blank=True,
                help_text='Role-specific internship duration override (in months).',
            ),
        ),
        migrations.AlterField(
            model_name='jobrole',
            name='ctc',
            field=models.DecimalField(
                decimal_places=2, max_digits=10, null=True, blank=True,
                help_text=(
                    'Role-specific CTC/stipend override; falls back to '
                    'posting CTC if null'
                ),
            ),
        ),
    ]
