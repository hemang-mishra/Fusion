from rest_framework.authtoken.models import Token
from rest_framework import serializers

from applications.placement_cell.models import (
    Achievement, Course, Education, Experience, Has, Patent, Project,
    Publication, Skill, PlacementStatus, NotifyStudent, Reference,
    Conference, Extracurricular, Interest, Coauthor, Coinventor,
    PlacementSchedule, PlacementRecord, StudentRecord, ChairmanVisit,
    StudentPlacement, Role, CompanyDetails, MessageOfficer,
    Company, JobPosting, JobApplication, InterviewSchedule,
    InterviewPanel, JobOffer, Announcement, PlacementPolicy,
    Appeal, PlacementProfile, PlacementProfileAuditLog,
    AlumniProfile, MentorshipProfile, MentorshipSession, JobReferral,
    JobRole, JobFormField, JobFormFieldOption,
    StudentResume, JobApplicationResponse, PlacementClaim,
)


# =============================================
# Legacy Model Serializers (CV / Student Profile)
# =============================================

class SkillSerializer(serializers.ModelSerializer):

    class Meta:
        model = Skill
        fields = ('__all__')

class HasSerializer(serializers.ModelSerializer):
    skill_id = SkillSerializer()

    class Meta:
        model = Has
        fields = ('id', 'skill_id', 'skill_rating')

    def create(self, validated_data):
        skill = validated_data.pop('skill_id')
        skill_id, created = Skill.objects.get_or_create(**skill)
        try:
            has_obj = Has.objects.create(skill_id=skill_id, **validated_data)
        except:
            raise serializers.ValidationError({'skill': 'This skill is already present'})
        return has_obj

class EducationSerializer(serializers.ModelSerializer):

    class Meta:
        model = Education
        fields = ('__all__')

class CourseSerializer(serializers.ModelSerializer):

    class Meta:
        model = Course
        fields = ('__all__')

class ExperienceSerializer(serializers.ModelSerializer):

    class Meta:
        model = Experience
        fields = ('__all__')

class ProjectSerializer(serializers.ModelSerializer):

    class Meta:
        model = Project
        fields = ('__all__')

class AchievementSerializer(serializers.ModelSerializer):

    class Meta:
        model = Achievement
        fields = ('__all__')

class PublicationSerializer(serializers.ModelSerializer):

    class Meta:
        model = Publication
        fields = ('__all__')

class PatentSerializer(serializers.ModelSerializer):

    class Meta:
        model = Patent
        fields = ('__all__')

class ReferenceSerializer(serializers.ModelSerializer):

    class Meta:
        model = Reference
        fields = '__all__'


class ConferenceSerializer(serializers.ModelSerializer):

    class Meta:
        model = Conference
        fields = '__all__'


class ExtracurricularSerializer(serializers.ModelSerializer):

    class Meta:
        model = Extracurricular
        fields = '__all__'


class InterestSerializer(serializers.ModelSerializer):

    class Meta:
        model = Interest
        fields = '__all__'


class CoauthorSerializer(serializers.ModelSerializer):

    class Meta:
        model = Coauthor
        fields = '__all__'


class CoinventorSerializer(serializers.ModelSerializer):

    class Meta:
        model = Coinventor
        fields = '__all__'


# =============================================
# Placement Schedule / Status Serializers
# =============================================

class NotifyStudentSerializer(serializers.ModelSerializer):

    class Meta:
        model = NotifyStudent
        fields = ('__all__')


class RoleSerializer(serializers.ModelSerializer):

    class Meta:
        model = Role
        fields = '__all__'


class CompanyDetailsSerializer(serializers.ModelSerializer):

    class Meta:
        model = CompanyDetails
        fields = '__all__'


class PlacementScheduleSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='notify_id.company_name', read_only=True)
    placement_type = serializers.CharField(source='notify_id.placement_type', read_only=True)
    ctc = serializers.DecimalField(source='notify_id.ctc', max_digits=10, decimal_places=4, read_only=True)
    role_st = serializers.CharField(source='get_role', read_only=True)
    notify_description = serializers.CharField(source='notify_id.description', read_only=True)
    jobID = serializers.IntegerField(source='notify_id.id', read_only=True)

    class Meta:
        model = PlacementSchedule
        fields = (
            'id', 'notify_id', 'title', 'placement_date', 'location',
            'description', 'time', 'role', 'attached_file', 'schedule_at',
            'company_name', 'placement_type', 'ctc', 'role_st',
            'notify_description', 'jobID',
        )
        read_only_fields = ('id',)


class PlacementStatusSerializer(serializers.ModelSerializer):
    notify_id = NotifyStudentSerializer()
    student_name = serializers.SerializerMethodField()
    student_roll = serializers.SerializerMethodField()

    class Meta:
        model = PlacementStatus
        fields = (
            'id', 'notify_id', 'unique_id', 'invitation', 'placed',
            'timestamp', 'no_of_days', 'student_name', 'student_roll',
        )

    def get_student_name(self, obj):
        try:
            user = obj.unique_id.id.user
            return '{} {}'.format(user.first_name, user.last_name)
        except Exception:
            return ''

    def get_student_roll(self, obj):
        try:
            return obj.unique_id.id.id
        except Exception:
            return ''


# =============================================
# Placement Records / Statistics Serializers
# =============================================

class PlacementRecordSerializer(serializers.ModelSerializer):

    class Meta:
        model = PlacementRecord
        fields = '__all__'


class StudentRecordSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    student_roll = serializers.SerializerMethodField()
    company_name = serializers.CharField(source='record_id.name', read_only=True)
    year = serializers.IntegerField(source='record_id.year', read_only=True)
    ctc = serializers.DecimalField(source='record_id.ctc', max_digits=5, decimal_places=2, read_only=True)
    placement_type = serializers.CharField(source='record_id.placement_type', read_only=True)
    department = serializers.SerializerMethodField()

    class Meta:
        model = StudentRecord
        fields = (
            'id', 'record_id', 'unique_id', 'student_name', 'student_roll',
            'company_name', 'year', 'ctc', 'placement_type', 'department',
        )

    def get_student_name(self, obj):
        try:
            user = obj.unique_id.id.user
            return '{} {}'.format(user.first_name, user.last_name)
        except Exception:
            return ''

    def get_student_roll(self, obj):
        try:
            return obj.unique_id.id.id
        except Exception:
            return ''

    def get_department(self, obj):
        try:
            return obj.unique_id.id.department.name
        except Exception:
            return ''


# =============================================
# Student Placement / Debar Serializers
# =============================================

class StudentPlacementSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    student_roll = serializers.SerializerMethodField()

    class Meta:
        model = StudentPlacement
        fields = '__all__'

    def get_student_name(self, obj):
        try:
            user = obj.unique_id.id.user
            return '{} {}'.format(user.first_name, user.last_name)
        except Exception:
            return ''

    def get_student_roll(self, obj):
        try:
            return obj.unique_id.id.id
        except Exception:
            return ''


# =============================================
# Chairman Visit Serializers
# =============================================

class ChairmanVisitSerializer(serializers.ModelSerializer):

    class Meta:
        model = ChairmanVisit
        fields = '__all__'


class MessageOfficerSerializer(serializers.ModelSerializer):

    class Meta:
        model = MessageOfficer
        fields = '__all__'


# =============================================
# PCMS Serializers (Company, Jobs, Applications, etc.)
# =============================================

class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = '__all__'
        read_only_fields = ('approval_status', 'approved_by', 'created_at', 'updated_at')


class CompanyListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for company listings."""
    class Meta:
        model = Company
        fields = ('id', 'name', 'domain', 'website', 'approval_status')


# ---- Dynamic Job Form Serializers ----

class JobFormFieldOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobFormFieldOption
        fields = ('id', 'label', 'value', 'order')


class JobFormFieldSerializer(serializers.ModelSerializer):
    options = JobFormFieldOptionSerializer(many=True, required=False)

    class Meta:
        model = JobFormField
        fields = (
            'id', 'job_posting', 'job_role', 'label', 'help_text',
            'field_type', 'is_required', 'order',
            'min_value', 'max_value', 'max_length',
            'options',
        )
        read_only_fields = ('job_posting', 'job_role')


class JobRoleSerializer(serializers.ModelSerializer):
    form_fields = JobFormFieldSerializer(many=True, required=False)

    class Meta:
        model = JobRole
        fields = (
            'id', 'job_posting', 'title', 'description', 'seats',
            'ctc', 'compensation_type', 'internship_duration_months',
            'order', 'created_at', 'form_fields',
        )
        read_only_fields = ('job_posting', 'created_at')


class StudentResumeSerializer(serializers.ModelSerializer):
    class Meta:
        model = StudentResume
        fields = ('id', 'student', 'name', 'url', 'is_default',
                  'created_at', 'updated_at')
        read_only_fields = ('student', 'created_at', 'updated_at')


class JobApplicationResponseSerializer(serializers.ModelSerializer):
    field_label = serializers.CharField(source='field.label', read_only=True)
    field_type = serializers.CharField(source='field.field_type', read_only=True)

    class Meta:
        model = JobApplicationResponse
        fields = ('id', 'application', 'field', 'field_label',
                  'field_type', 'value', 'created_at')
        read_only_fields = ('application', 'created_at')


class JobPostingSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    total_applications = serializers.IntegerField(read_only=True)
    is_deadline_passed = serializers.BooleanField(read_only=True)
    required_skills = SkillSerializer(many=True, read_only=True)
    roles = JobRoleSerializer(many=True, required=False)
    form_fields = JobFormFieldSerializer(many=True, required=False)

    class Meta:
        model = JobPosting
        fields = '__all__'
        read_only_fields = ('posted_by', 'created_at', 'updated_at')

    # ---- Nested write helpers ----

    @staticmethod
    def _create_field(field_data, *, posting=None, role=None):
        options = field_data.pop('options', [])
        # Strip read-only fk fields if present
        field_data.pop('job_posting', None)
        field_data.pop('job_role', None)
        field = JobFormField.objects.create(
            job_posting=posting, job_role=role, **field_data
        )
        for idx, opt in enumerate(options):
            JobFormFieldOption.objects.create(
                field=field,
                label=opt.get('label', ''),
                value=opt.get('value'),
                order=opt.get('order', idx),
            )
        return field

    def _apply_nested(self, posting, roles_data, fields_data):
        # Posting-level shared fields
        for idx, fdata in enumerate(fields_data):
            fdata.setdefault('order', idx)
            self._create_field(fdata, posting=posting)
        # Roles + role-specific fields
        for r_idx, rdata in enumerate(roles_data):
            role_fields = rdata.pop('form_fields', [])
            rdata.pop('job_posting', None)
            rdata.setdefault('order', r_idx)
            role = JobRole.objects.create(job_posting=posting, **rdata)
            for f_idx, fdata in enumerate(role_fields):
                fdata.setdefault('order', f_idx)
                self._create_field(fdata, role=role)

    def create(self, validated_data):
        roles_data = validated_data.pop('roles', [])
        fields_data = validated_data.pop('form_fields', [])
        posting = super().create(validated_data)
        self._apply_nested(posting, roles_data, fields_data)
        return posting

    def update(self, instance, validated_data):
        roles_data = validated_data.pop('roles', None)
        fields_data = validated_data.pop('form_fields', None)
        posting = super().update(instance, validated_data)
        # Replace nested structure when explicitly provided
        if roles_data is not None or fields_data is not None:
            if fields_data is not None:
                posting.form_fields.all().delete()
            if roles_data is not None:
                posting.roles.all().delete()
            self._apply_nested(
                posting,
                roles_data if roles_data is not None else [],
                fields_data if fields_data is not None else [],
            )
        return posting


class JobPostingListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for job listing pages."""
    company_name = serializers.CharField(source='company.name', read_only=True)
    total_applications = serializers.IntegerField(read_only=True)
    role_titles = serializers.SerializerMethodField()

    class Meta:
        model = JobPosting
        fields = ('id', 'title', 'company', 'company_name', 'job_type', 'ctc',
                  'compensation_type', 'internship_duration_months', 'jd_link',
                  'location', 'application_deadline', 'is_active',
                  'total_applications', 'role_titles')

    def get_role_titles(self, obj):
        return [r.title for r in obj.roles.all()]


class JobApplicationSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    student_roll = serializers.CharField(source='student.id.id', read_only=True)
    job_title = serializers.CharField(source='job_posting.title', read_only=True)
    company_name = serializers.CharField(source='job_posting.company.name', read_only=True)
    role_title = serializers.CharField(source='job_role.title', read_only=True)
    responses = JobApplicationResponseSerializer(many=True, read_only=True)

    # Compensation context for the listing UI ----------------------------------
    posting_ctc = serializers.DecimalField(
        source='job_posting.ctc', max_digits=10, decimal_places=2, read_only=True
    )
    posting_compensation_type = serializers.CharField(
        source='job_posting.compensation_type', read_only=True
    )
    posting_job_type = serializers.CharField(
        source='job_posting.job_type', read_only=True
    )
    posting_internship_duration_months = serializers.IntegerField(
        source='job_posting.internship_duration_months', read_only=True
    )
    posting_jd_link = serializers.URLField(
        source='job_posting.jd_link', read_only=True
    )
    role_ctc = serializers.DecimalField(
        source='job_role.ctc', max_digits=10, decimal_places=2, read_only=True
    )
    role_compensation_type = serializers.CharField(
        source='job_role.compensation_type', read_only=True
    )
    # Offer details (only present once an offer has been extended)
    offer_ctc = serializers.SerializerMethodField()
    offer_status = serializers.SerializerMethodField()
    offer_designation = serializers.SerializerMethodField()

    class Meta:
        model = JobApplication
        fields = '__all__'
        read_only_fields = ('applied_at', 'updated_at')

    def get_student_name(self, obj):
        user = obj.student.id.user
        return '{} {}'.format(user.first_name, user.last_name)

    def _offer(self, obj):
        return getattr(obj, 'offer', None)

    def get_offer_ctc(self, obj):
        offer = self._offer(obj)
        return str(offer.ctc_offered) if offer else None

    def get_offer_status(self, obj):
        offer = self._offer(obj)
        return offer.status if offer else None

    def get_offer_designation(self, obj):
        offer = self._offer(obj)
        return offer.designation_offered if offer else None


class InterviewScheduleSerializer(serializers.ModelSerializer):
    job_title = serializers.CharField(source='job_posting.title', read_only=True)
    company_name = serializers.CharField(source='job_posting.company.name', read_only=True)
    panelist_count = serializers.SerializerMethodField()

    class Meta:
        model = InterviewSchedule
        fields = '__all__'
        read_only_fields = ('created_by', 'created_at', 'end_time', 'reschedule_count')

    def get_panelist_count(self, obj):
        return obj.panelists.count()


class InterviewPanelSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    student_roll = serializers.SerializerMethodField()

    class Meta:
        model = InterviewPanel
        fields = '__all__'

    def get_student_name(self, obj):
        user = obj.application.student.id.user
        return '{} {}'.format(user.first_name, user.last_name)

    def get_student_roll(self, obj):
        return obj.application.student.id.id


class JobOfferSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    company_name = serializers.CharField(
        source='application.job_posting.company.name', read_only=True
    )
    job_title = serializers.CharField(
        source='application.job_posting.title', read_only=True
    )
    posting_compensation_type = serializers.CharField(
        source='application.job_posting.compensation_type', read_only=True
    )
    posting_job_type = serializers.CharField(
        source='application.job_posting.job_type', read_only=True
    )
    posting_internship_duration_months = serializers.IntegerField(
        source='application.job_posting.internship_duration_months',
        read_only=True
    )
    is_deadline_passed = serializers.BooleanField(read_only=True)
    response_deadline = serializers.DateTimeField(required=False)

    class Meta:
        model = JobOffer
        fields = '__all__'
        read_only_fields = ('extended_at', 'responded_at')

    def get_student_name(self, obj):
        user = obj.application.student.id.user
        return '{} {}'.format(user.first_name, user.last_name)


class AnnouncementSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Announcement
        fields = '__all__'
        read_only_fields = ('created_by', 'created_at', 'updated_at')

    def get_created_by_name(self, obj):
        if obj.created_by:
            return '{} {}'.format(obj.created_by.first_name, obj.created_by.last_name)
        return ''

    def validate(self, attrs):
        publish_at = attrs.get('publish_at')
        expires_at = attrs.get('expires_at')
        visibility_scope = attrs.get('visibility_scope')
        visibility_targets = attrs.get('visibility_targets')

        if self.instance:
            publish_at = publish_at or self.instance.publish_at
            expires_at = expires_at if 'expires_at' in attrs else self.instance.expires_at
            visibility_scope = visibility_scope or self.instance.visibility_scope
            visibility_targets = (
                visibility_targets if 'visibility_targets' in attrs else self.instance.visibility_targets
            )

        if publish_at and expires_at and expires_at <= publish_at:
            raise serializers.ValidationError(
                {'expires_at': 'Expiry must be after publish time.'}
            )

        if visibility_scope == 'SPECIFIC_BATCH' and not visibility_targets:
            raise serializers.ValidationError(
                {'visibility_targets': 'Provide visibility targets for specific batch visibility.'}
            )

        if visibility_scope == 'ALL':
            attrs['visibility_targets'] = ''

        return attrs


class PlacementPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = PlacementPolicy
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class AppealSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    student_roll = serializers.SerializerMethodField()
    company_name = serializers.SerializerMethodField()
    job_title = serializers.SerializerMethodField()

    class Meta:
        model = Appeal
        fields = '__all__'
        read_only_fields = ('status', 'remarks', 'created_at', 'resolved_at', 'student_name', 'student_roll', 'company_name', 'job_title')

    def get_student_name(self, obj):
        try:
            return '{} {}'.format(obj.application.student.id.user.first_name, obj.application.student.id.user.last_name)
        except Exception:
            return ''

    def get_student_roll(self, obj):
        try:
            return str(obj.application.student.id.id)
        except Exception:
            return ''

    def get_company_name(self, obj):
        try:
            return obj.application.job_posting.company.name
        except Exception:
            return ''

    def get_job_title(self, obj):
        try:
            return obj.application.job_posting.title
        except Exception:
            return ''


class PlacementProfileAuditLogSerializer(serializers.ModelSerializer):
    changed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = PlacementProfileAuditLog
        fields = ['id', 'changed_at', 'changed_by', 'changed_by_name', 'changes']

    def get_changed_by_name(self, obj):
        return f"{obj.changed_by.first_name} {obj.changed_by.last_name}".strip() if obj.changed_by else None

class PlacementProfileSerializer(serializers.ModelSerializer):
    audit_logs = PlacementProfileAuditLogSerializer(many=True, read_only=True)
    username = serializers.CharField(source='student.id.user.username', read_only=True)
    first_name = serializers.CharField(source='student.id.user.first_name', read_only=True)
    last_name = serializers.CharField(source='student.id.user.last_name', read_only=True)
    is_complete = serializers.BooleanField(read_only=True)
    missing_required_fields = serializers.SerializerMethodField()

    class Meta:
        model = PlacementProfile
        fields = [
            'id', 'student', 'username', 'first_name', 'last_name', 'resume',
            'about_me', 'linkedin_url', 'github_url', 'portfolio_url',
            'professional_email', 'achievements', 'certifications',
            'apply_override', 'apply_override_remarks',
            'is_complete', 'missing_required_fields', 'audit_logs',
        ]
        # Students cannot toggle their own override; only TPO can flip it
        # via the Placement Status admin tab.
        read_only_fields = [
            'student', 'username', 'first_name', 'last_name',
            'apply_override', 'apply_override_remarks',
        ]

    def get_missing_required_fields(self, obj):
        return obj.missing_required_fields()


class PlacementClaimSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    student_roll = serializers.CharField(source='student.id.id', read_only=True)
    verified_by_name = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()
    # The viewset always sets `student` server-side: for student-submitted
    # claims it's auto-derived from the request user, for TPO-created claims
    # it's validated explicitly in ``perform_create``. Making it optional here
    # keeps the student-facing form free of an unused "student" field.
    student = serializers.PrimaryKeyRelatedField(
        queryset=PlacementClaim._meta.get_field('student').related_model.objects.all(),
        required=False,
    )

    class Meta:
        model = PlacementClaim
        fields = [
            'id', 'student', 'student_name', 'student_roll',
            'kind', 'company_name', 'role_title', 'location',
            'compensation_amount', 'duration_months',
            'start_date', 'end_date', 'source', 'proof_link', 'notes',
            'status', 'verification_remarks', 'verified_at',
            'related_offer',
            'created_by', 'created_by_name',
            'verified_by', 'verified_by_name',
            'created_at', 'updated_at',
        ]
        read_only_fields = (
            'created_by', 'created_by_name',
            'verified_by', 'verified_by_name',
            'verified_at', 'created_at', 'updated_at', 'related_offer',
        )

    def _user_name(self, user):
        if not user:
            return None
        full = '{} {}'.format(user.first_name or '', user.last_name or '').strip()
        return full or user.username

    def get_student_name(self, obj):
        try:
            return self._user_name(obj.student.id.user)
        except Exception:  # pragma: no cover
            return None

    def get_verified_by_name(self, obj):
        return self._user_name(obj.verified_by)

    def get_created_by_name(self, obj):
        return self._user_name(obj.created_by)

    def validate_resume(self, value):
        from django.core.exceptions import ValidationError
        if not value:
            return value

        # Max size 5MB
        if value.size > 5 * 1024 * 1024:
            raise ValidationError("Resume file size cannot exceed 5MB.")

        # Check extensions
        import os
        ext = os.path.splitext(value.name)[1].lower()
        valid_extensions = ['.pdf', '.jpg', '.jpeg', '.png']
        if ext not in valid_extensions:
            raise ValidationError("Only pdf, jpg, jpeg, and png formats are allowed.")
        return value


# =============================================
# Alumni Network Serializers
# =============================================

class AlumniProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    email = serializers.CharField(source='user.email', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = AlumniProfile
        fields = [
            'id', 'user', 'username', 'full_name', 'email',
            'graduation_year', 'programme', 'department',
            'current_company', 'current_designation',
            'linkedin_url', 'phone', 'bio',
            'verification_document', 'approval_status',
            'approved_by', 'rejection_remarks',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'user', 'approval_status', 'approved_by',
            'rejection_remarks', 'created_at', 'updated_at',
        ]

    def get_full_name(self, obj):
        return f"{obj.user.first_name} {obj.user.last_name}".strip()


class AlumniProfileListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for alumni listings (student view)."""
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = AlumniProfile
        fields = [
            'id', 'full_name', 'graduation_year', 'programme',
            'department', 'current_company', 'current_designation',
            'linkedin_url', 'bio',
        ]

    def get_full_name(self, obj):
        return f"{obj.user.first_name} {obj.user.last_name}".strip()


class MentorshipProfileSerializer(serializers.ModelSerializer):
    alumni_name = serializers.CharField(source='alumni.full_name', read_only=True)
    alumni_company = serializers.CharField(source='alumni.current_company', read_only=True)
    alumni_designation = serializers.CharField(source='alumni.current_designation', read_only=True)
    alumni_linkedin = serializers.URLField(source='alumni.linkedin_url', read_only=True)
    alumni_graduation_year = serializers.IntegerField(source='alumni.graduation_year', read_only=True)
    alumni_department = serializers.CharField(source='alumni.department', read_only=True)

    class Meta:
        model = MentorshipProfile
        fields = [
            'id', 'alumni', 'alumni_name', 'alumni_company',
            'alumni_designation', 'alumni_linkedin',
            'alumni_graduation_year', 'alumni_department',
            'is_available', 'topics', 'availability_slots',
            'max_sessions_per_month', 'bio',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['alumni', 'created_at', 'updated_at']


class MentorshipSessionSerializer(serializers.ModelSerializer):
    mentor_name = serializers.CharField(source='mentor.alumni.full_name', read_only=True)
    mentor_company = serializers.CharField(source='mentor.alumni.current_company', read_only=True)
    student_name = serializers.SerializerMethodField()
    student_roll = serializers.SerializerMethodField()

    class Meta:
        model = MentorshipSession
        fields = [
            'id', 'mentor', 'student', 'mentor_name', 'mentor_company',
            'student_name', 'student_roll',
            'topic', 'message', 'scheduled_date', 'scheduled_time',
            'duration_minutes', 'meeting_link', 'status', 'mentor_notes',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['student', 'created_at', 'updated_at']

    def get_student_name(self, obj):
        try:
            u = obj.student.id.user
            return f"{u.first_name} {u.last_name}".strip()
        except Exception:
            return ''

    def get_student_roll(self, obj):
        try:
            return obj.student.id.id
        except Exception:
            return ''


class JobReferralSerializer(serializers.ModelSerializer):
    posted_by_name = serializers.CharField(source='posted_by.full_name', read_only=True)
    posted_by_company = serializers.CharField(source='posted_by.current_company', read_only=True)
    is_deadline_passed = serializers.BooleanField(read_only=True)

    class Meta:
        model = JobReferral
        fields = [
            'id', 'posted_by', 'posted_by_name', 'posted_by_company',
            'company_name', 'role_title', 'description',
            'location', 'referral_link', 'ctc_range',
            'eligible_programmes', 'eligible_branches',
            'is_active', 'deadline', 'is_deadline_passed',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['posted_by', 'created_at', 'updated_at']
