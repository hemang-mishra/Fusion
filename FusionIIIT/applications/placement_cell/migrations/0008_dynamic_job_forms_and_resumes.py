from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('academic_information', '0001_initial'),
        ('placement_cell', '0007_announcement_notice_fields'),
    ]

    operations = [
        # ---- JobRole ----
        migrations.CreateModel(
            name='JobRole',
            fields=[
                ('id', models.AutoField(
                    auto_created=True, primary_key=True, serialize=False, verbose_name='ID'
                )),
                ('title', models.CharField(help_text='Role/title name', max_length=200)),
                ('description', models.TextField(blank=True, max_length=2000, null=True)),
                ('seats', models.PositiveIntegerField(
                    default=0, help_text='Number of openings; 0 = unspecified'
                )),
                ('ctc', models.DecimalField(
                    blank=True, decimal_places=2, max_digits=10, null=True,
                    help_text='Role-specific CTC override; falls back to posting CTC if null'
                )),
                ('order', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('job_posting', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='roles',
                    to='placement_cell.JobPosting'
                )),
            ],
            options={'ordering': ['order', 'id']},
        ),

        # ---- StudentResume ----
        migrations.CreateModel(
            name='StudentResume',
            fields=[
                ('id', models.AutoField(
                    auto_created=True, primary_key=True, serialize=False, verbose_name='ID'
                )),
                ('name', models.CharField(
                    help_text="Custom name/type, e.g. 'Backend Resume'", max_length=100
                )),
                ('url', models.URLField(help_text='External resume URL', max_length=1000)),
                ('is_default', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('student', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='saved_resumes',
                    to='academic_information.Student'
                )),
            ],
            options={'ordering': ['-is_default', '-updated_at']},
        ),

        # ---- JobFormField ----
        migrations.CreateModel(
            name='JobFormField',
            fields=[
                ('id', models.AutoField(
                    auto_created=True, primary_key=True, serialize=False, verbose_name='ID'
                )),
                ('label', models.CharField(max_length=300)),
                ('help_text', models.CharField(blank=True, max_length=500, null=True)),
                ('field_type', models.CharField(
                    choices=[
                        ('SHORT_ANSWER', 'Short Answer'),
                        ('LONG_ANSWER', 'Long Answer'),
                        ('NUMBER', 'Number'),
                        ('SINGLE_CHOICE', 'Single Choice'),
                        ('MULTI_CHOICE', 'Multiple Choice'),
                    ],
                    max_length=20
                )),
                ('is_required', models.BooleanField(default=False)),
                ('order', models.PositiveIntegerField(default=0)),
                ('min_value', models.FloatField(blank=True, null=True)),
                ('max_value', models.FloatField(blank=True, null=True)),
                ('max_length', models.PositiveIntegerField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('job_posting', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='form_fields',
                    to='placement_cell.JobPosting',
                    help_text='Posting-level (shared) field; null when role-specific'
                )),
                ('job_role', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='form_fields',
                    to='placement_cell.JobRole',
                    help_text='Role-specific field; null when shared at posting level'
                )),
            ],
            options={'ordering': ['order', 'id']},
        ),

        # ---- JobFormFieldOption ----
        migrations.CreateModel(
            name='JobFormFieldOption',
            fields=[
                ('id', models.AutoField(
                    auto_created=True, primary_key=True, serialize=False, verbose_name='ID'
                )),
                ('label', models.CharField(max_length=300)),
                ('value', models.CharField(blank=True, max_length=300, null=True)),
                ('order', models.PositiveIntegerField(default=0)),
                ('field', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='options',
                    to='placement_cell.JobFormField'
                )),
            ],
            options={'ordering': ['order', 'id']},
        ),

        # ---- JobApplication: new fields ----
        migrations.AddField(
            model_name='jobapplication',
            name='job_role',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='applications',
                to='placement_cell.JobRole',
                help_text='Specific role applied for within the posting (optional)'
            ),
        ),
        migrations.AddField(
            model_name='jobapplication',
            name='resume_url',
            field=models.URLField(
                blank=True, null=True, max_length=1000,
                help_text='External resume URL chosen at apply time'
            ),
        ),
        migrations.AddField(
            model_name='jobapplication',
            name='selected_resume',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='applications',
                to='placement_cell.StudentResume',
                help_text='StudentResume selected from profile at apply time'
            ),
        ),

        # ---- JobApplicationResponse ----
        migrations.CreateModel(
            name='JobApplicationResponse',
            fields=[
                ('id', models.AutoField(
                    auto_created=True, primary_key=True, serialize=False, verbose_name='ID'
                )),
                ('value', models.JSONField(blank=True, default=dict, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('application', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='responses',
                    to='placement_cell.JobApplication'
                )),
                ('field', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='responses',
                    to='placement_cell.JobFormField'
                )),
            ],
            options={'unique_together': {('application', 'field')}},
        ),
    ]
