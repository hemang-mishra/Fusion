"""
REST API views for the Placement Cell Management System (PCMS).
Provides endpoints for:
  - User role checking
  - Placement schedule CRUD (legacy)
  - Student records, invitation status, debarred students
  - Placement statistics & records
  - CV data retrieval
  - Company, job posting, application, offer, announcement CRUD (PCMS)
  - Interview & policy management
  - Dashboard, reports, calendar, timeline
"""
import datetime
import logging

from datetime import date
from io import BytesIO

from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Max, Min, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import TokenAuthentication
from rest_framework.response import Response

from applications.globals.models import ExtraInfo, HoldsDesignation
from applications.academic_information.models import Student

from applications.placement_cell.models import (
    Achievement, ChairmanVisit, Course, Education, Experience, Conference,
    Has, NotifyStudent, Patent, PlacementRecord, Extracurricular, Reference,
    PlacementSchedule, PlacementStatus, Project, Publication, Interest,
    Skill, StudentPlacement, StudentRecord, Role, CompanyDetails,
    Company, JobPosting, JobApplication, InterviewSchedule,
    InterviewPanel, JobOffer, Announcement, PlacementPolicy,
    Coauthor, Coinventor, Appeal, PlacementProfile, PlacementProfileAuditLog,
    AlumniProfile, MentorshipProfile, MentorshipSession, JobReferral,
)

from applications.placement_cell.api.serializers import (
    SkillSerializer, HasSerializer, EducationSerializer, CourseSerializer,
    ExperienceSerializer, ProjectSerializer, AchievementSerializer,
    PublicationSerializer, PatentSerializer, ReferenceSerializer,
    ConferenceSerializer, ExtracurricularSerializer, InterestSerializer,
    NotifyStudentSerializer, RoleSerializer, CompanyDetailsSerializer,
    PlacementScheduleSerializer, PlacementStatusSerializer,
    PlacementRecordSerializer, StudentRecordSerializer,
    StudentPlacementSerializer, ChairmanVisitSerializer,
    CompanySerializer, CompanyListSerializer,
    JobPostingSerializer, JobPostingListSerializer,
    JobApplicationSerializer,
    InterviewScheduleSerializer, InterviewPanelSerializer,
    JobOfferSerializer,
    AnnouncementSerializer,
    PlacementPolicySerializer, PlacementProfileSerializer,
    AppealSerializer,
    AlumniProfileSerializer, AlumniProfileListSerializer,
    MentorshipProfileSerializer, MentorshipSessionSerializer,
    JobReferralSerializer,
)

# Import business logic services
from applications.placement_cell.services import (
    is_tpo_or_chairman, is_chairman, is_officer, is_student, is_alumni,
    get_student, get_alumni_profile, get_user_roles,
    check_invitation_date, create_placement_schedule, update_student_invitation,
    delete_placement_schedule, get_all_students_with_placement_info, get_student_cv_data,
    build_cv_context, get_placement_status_list, update_student_placement_status,
    get_placement_records, get_placement_year_statistics, get_student_records,
    get_debarred_students, debar_student, undebar_student, get_student_debar_status,
    register_company, get_all_companies, check_eligibility, check_duplicate_application,
    check_placement_policy, create_job_application, update_job_application_status,
    process_offer_response, expire_pending_offers, get_placement_statistics,
    get_student_application_summary, get_placement_report_data, get_interview_schedules,
    create_interview_schedule, get_interview_details, get_placement_policies,
    create_or_update_policy, toggle_policy_active, get_all_roles, create_or_get_role,
    get_form_field_config, get_active_announcements,
    approve_alumni, reject_alumni,
    check_interview_conflicts, validate_reschedule,
)


logger = logging.getLogger('django.server')


# =============================================
# HELPER FUNCTIONS (Backwards compatibility)
# =============================================

def _is_tpo_or_chairman(user):
    """Check if user is TPO or Placement Chairman."""
    return is_tpo_or_chairman(user)


def _is_chairman(user):
    """Check if user is Placement Chairman."""
    return is_chairman(user)


def _is_officer(user):
    """Check if user is Placement Officer (TPO)."""
    return is_officer(user)


def _is_student(user):
    """Check if user is a student."""
    return is_student(user)


def _get_student(user):
    """Get the Student object for a user. Returns None if not a student."""
    return get_student(user)


def _check_invitation_date(placementstatus_qs):
    """Expire pending invitations past their deadline."""
    return check_invitation_date(placementstatus_qs)


# =============================================
# 1. ROLE & AUTH
# =============================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([TokenAuthentication])
def user_roles_api(request):
    """Return the user's placement roles."""
    return Response(get_user_roles(request.user))


# =============================================
# 2. PLACEMENT SCHEDULE (Legacy)
# =============================================

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([TokenAuthentication])
def placement_schedule_api(request):
    """
    GET: List all placement schedules.
         For students, includes their invitation status per schedule.
    POST: Create a new placement schedule (officer/chairman only).
    """
    user = request.user

    if request.method == 'GET':
        schedules = PlacementSchedule.objects.select_related('notify_id', 'role').all().order_by('-schedule_at')
        data = PlacementScheduleSerializer(schedules, many=True).data

        # For students, attach invitation status
        if is_student(user):
            student = get_student(user)
            if student:
                for item in data:
                    try:
                        ps = PlacementStatus.objects.get(
                            unique_id=student, notify_id=item['notify_id']
                        )
                        item['check'] = ps.invitation
                    except PlacementStatus.DoesNotExist:
                        item['check'] = 'PENDING'
        return Response(data)

    elif request.method == 'POST':
        if not is_tpo_or_chairman(user):
            return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)

        company_name = request.data.get('company_name', '')
        placement_date = request.data.get('placement_date')
        location = request.data.get('location', '')
        ctc = request.data.get('ctc', 0)
        time_val = request.data.get('time')
        placement_type = request.data.get('placement_type', 'PLACEMENT')
        role_offered = request.data.get('role', '')
        description = request.data.get('description', '')
        schedule_at = request.data.get('schedule_at')
        attached_file = request.FILES.get('attached_file')

        schedule = create_placement_schedule(
            company_name, placement_date, location, ctc, time_val,
            placement_type, role_offered, description, schedule_at, attached_file
        )

        return Response(
            PlacementScheduleSerializer(schedule).data,
            status=status.HTTP_201_CREATED
        )


@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
@authentication_classes([TokenAuthentication])
def placement_schedule_detail_api(request, schedule_id):
    """
    PUT: Update invitation status (student accepts/declines).
    DELETE: Delete a placement schedule (officer/chairman only).
    """
    user = request.user

    if request.method == 'PUT':
        # Student updating invitation status
        student = get_student(user)
        if not student:
            return Response({'error': 'Student profile not found'}, status=status.HTTP_404_NOT_FOUND)

        schedule = get_object_or_404(PlacementSchedule, id=schedule_id)
        invitation_action = request.data.get('invitation', '')

        ps = update_student_invitation(student, schedule, invitation_action)
        if ps:
            return Response({'status': ps.invitation})

        return Response({'error': 'Invalid action. Use ACCEPTED or REJECTED.'}, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        if not is_tpo_or_chairman(user):
            return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)

        schedule = get_object_or_404(PlacementSchedule, id=schedule_id)
        if delete_placement_schedule(schedule):
            return Response({'status': 'deleted'})
        return Response({'error': 'Failed to delete'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# =============================================
# 3. STUDENT RECORDS & CV
# =============================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([TokenAuthentication])
def student_records_api(request):
    """List all students with profile/placement info."""
    data = get_all_students_with_placement_info()
    return Response(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([TokenAuthentication])
def cv_data_api(request, username):
    """Get student CV data as JSON."""
    target_user = get_object_or_404(User, username=username)
    cv_data = get_student_cv_data(target_user)

    # Serialize querysets to dicts
    from applications.placement_cell.api.serializers import (
        HasSerializer, EducationSerializer, ReferenceSerializer,
        CourseSerializer, ExperienceSerializer, ProjectSerializer,
        AchievementSerializer, ExtracurricularSerializer,
        ConferenceSerializer, PublicationSerializer, PatentSerializer
    )

    cv_data['skills'] = HasSerializer(cv_data['skills'], many=True).data
    cv_data['education'] = EducationSerializer(cv_data['education'], many=True).data
    cv_data['references'] = ReferenceSerializer(cv_data['references'], many=True).data
    cv_data['courses'] = CourseSerializer(cv_data['courses'], many=True).data
    cv_data['experiences'] = ExperienceSerializer(cv_data['experiences'], many=True).data
    cv_data['projects'] = ProjectSerializer(cv_data['projects'], many=True).data
    cv_data['achievements'] = AchievementSerializer(cv_data['achievements'], many=True).data
    cv_data['extracurriculars'] = ExtracurricularSerializer(cv_data['extracurriculars'], many=True).data
    cv_data['conferences'] = ConferenceSerializer(cv_data['conferences'], many=True).data
    cv_data['publications'] = PublicationSerializer(cv_data['publications'], many=True).data
    cv_data['patents'] = PatentSerializer(cv_data['patents'], many=True).data

    # Merge PlacementProfile social links so the frontend can build a rich resume
    try:
        from applications.globals.models import ExtraInfo as _ExtraInfo
        from applications.academic_information.models import Student as _Student
        _profile = _ExtraInfo.objects.get(user=target_user)
        _student = _Student.objects.get(id=_profile)
        pp = PlacementProfile.objects.get(student=_student)
        cv_data['linkedin_url']  = pp.linkedin_url or ''
        cv_data['github_url']    = pp.github_url or ''
        cv_data['portfolio_url'] = pp.portfolio_url or ''
        # Prefer PlacementProfile about_me if set, else fall back to ExtraInfo
        if pp.about_me:
            cv_data['profile']['about_me'] = pp.about_me
    except Exception:
        cv_data.setdefault('linkedin_url', '')
        cv_data.setdefault('github_url', '')
        cv_data.setdefault('portfolio_url', '')

    return Response(cv_data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([TokenAuthentication])
def generate_cv_api(request):
    """Generate PDF CV for download."""
    from xhtml2pdf import pisa
    from django.template.loader import render_to_string

    username = request.data.get('username', request.user.username)
    target_user = get_object_or_404(User, username=username)

    achievementcheck = request.data.get('achievementcheck', '1')
    educationcheck = request.data.get('educationcheck', '1')
    publicationcheck = request.data.get('publicationcheck', '1')
    patentcheck = request.data.get('patentcheck', '1')
    internshipcheck = request.data.get('internshipcheck', '1')
    projectcheck = request.data.get('projectcheck', '1')
    coursecheck = request.data.get('coursecheck', '1')
    skillcheck = request.data.get('skillcheck', '1')
    extracurricularcheck = request.data.get('extracurricularcheck', '1')
    conferencecheck = request.data.get('conferencecheck', '1')
    reference_list = request.data.getlist('reference_checkbox_list', [])

    context = build_cv_context(
        target_user, achievementcheck, educationcheck, publicationcheck,
        patentcheck, internshipcheck, projectcheck, coursecheck,
        skillcheck, extracurricularcheck, conferencecheck, reference_list
    )

    html = render_to_string('placementModule/cv.html', context)
    result = BytesIO()
    pdf = pisa.pisaDocument(BytesIO(html.encode('UTF-8')), result)
    if not pdf.err:
        response = HttpResponse(result.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = 'attachment; filename="cv_{}.pdf"'.format(username)
        return response
    return Response({'error': 'Failed to generate PDF'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# =============================================
# 4. INVITATION / APPLICATION STATUS
# =============================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([TokenAuthentication])
def student_applications_api(request, job_id):
    """Get students who applied/were invited for a specific placement schedule."""
    if not is_tpo_or_chairman(request.user):
        return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)

    statuses = get_placement_status_list(notify_id=job_id)
    return Response(PlacementStatusSerializer(statuses, many=True).data)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
@authentication_classes([TokenAuthentication])
def update_student_application_api(request, pk):
    """Update a student's application/invitation status."""
    if not _is_tpo_or_chairman(request.user):
        return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)

    ps = get_object_or_404(PlacementStatus, id=pk)
    new_invitation = request.data.get('invitation')
    new_placed = request.data.get('placed')

    if new_invitation:
        ps.invitation = new_invitation
    if new_placed:
        ps.placed = new_placed
    ps.timestamp = timezone.now()
    ps.save()

    return Response(PlacementStatusSerializer(ps).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([TokenAuthentication])
def invitation_status_api(request):
    """View invitation statuses with optional filters."""
    if not _is_tpo_or_chairman(request.user):
        return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)

    placement_type = request.query_params.get('placement_type', '')
    company = request.query_params.get('company', '')
    student_name = request.query_params.get('student_name', '')
    roll = request.query_params.get('roll', '')
    page = request.query_params.get('page', 1)

    qs = PlacementStatus.objects.select_related(
        'unique_id', 'unique_id__id', 'unique_id__id__user', 'notify_id'
    )

    if placement_type:
        qs = qs.filter(notify_id__placement_type=placement_type)
    if company:
        qs = qs.filter(notify_id__company_name__icontains=company)
    if student_name:
        qs = qs.filter(
            unique_id__id__user__first_name__icontains=student_name
        )
    if roll:
        qs = qs.filter(unique_id__id__id__icontains=roll)

    qs = qs.order_by('-timestamp')

    paginator = Paginator(qs, 30)
    page_obj = paginator.get_page(page)

    return Response({
        'results': PlacementStatusSerializer(page_obj.object_list, many=True).data,
        'count': paginator.count,
        'num_pages': paginator.num_pages,
        'current_page': page_obj.number,
    })


# =============================================
# 5. PLACEMENT STATISTICS & RECORDS
# =============================================

@api_view(['GET', 'POST', 'DELETE'])
@permission_classes([IsAuthenticated])
@authentication_classes([TokenAuthentication])
def placement_statistics_api(request):
    """
    GET: Get placement records/statistics.
    POST: Add a new placement record (officer/chairman only).
    DELETE: Delete a placement record (officer/chairman only).
    """
    if request.method == 'GET':
        placement_type = request.query_params.get('placement_type', '')
        year = request.query_params.get('year', '')
        name = request.query_params.get('name', '')

        records = get_placement_records(placement_type, year, name)
        data = PlacementRecordSerializer(records, many=True).data
        year_stats = get_placement_year_statistics()

        return Response({
            'records': data,
            'year_stats': year_stats,
        })

    elif request.method == 'POST':
        if not is_tpo_or_chairman(request.user):
            return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)

        serializer = PlacementRecordSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        if not is_tpo_or_chairman(request.user):
            return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)

        record_id = request.data.get('record_id')
        if not record_id:
            return Response({'error': 'record_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            PlacementRecord.objects.filter(id=record_id).delete()
            return Response({'status': 'deleted'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET', 'POST', 'DELETE'])
@permission_classes([IsAuthenticated])
@authentication_classes([TokenAuthentication])
def manage_records_api(request):
    """
    GET: List student records with optional filters.
    POST: Add a student to a placement record.
    DELETE: Remove a student record.
    """
    if request.method == 'GET':
        placement_type = request.query_params.get('placement_type', '')
        year = request.query_params.get('year', '')
        company = request.query_params.get('company', '')

        records = get_student_records(placement_type, year, company)
        return Response(StudentRecordSerializer(records, many=True).data)

    elif request.method == 'POST':
        if not is_tpo_or_chairman(request.user):
            return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)

        serializer = StudentRecordSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        if not is_tpo_or_chairman(request.user):
            return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)

        record_id = request.data.get('record_id')
        if not record_id:
            return Response({'error': 'record_id is required'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            StudentRecord.objects.filter(id=record_id).delete()
            return Response({'status': 'deleted'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# =============================================
# 6. DEBARRED STUDENTS
# =============================================

@api_view(['GET', 'POST', 'DELETE'])
@permission_classes([IsAuthenticated])
@authentication_classes([TokenAuthentication])
def debarred_students_api(request):
    """
    GET: List debarred students.
    POST: Debar a student (officer/chairman).
    DELETE: Undebar a student (officer/chairman).
    """
    if request.method == 'GET':
        debarred = get_debarred_students()
        return Response(StudentPlacementSerializer(debarred, many=True).data)

    elif request.method == 'POST':
        if not is_tpo_or_chairman(request.user):
            return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)

        roll_no = request.data.get('roll_no', '')
        if not roll_no:
            return Response({'error': 'roll_no is required'}, status=status.HTTP_400_BAD_REQUEST)

        sp = debar_student(roll_no)
        if sp:
            return Response({'status': 'debarred', 'roll_no': roll_no})
        return Response({'error': 'Student not found'}, status=status.HTTP_404_NOT_FOUND)

    elif request.method == 'DELETE':
        if not is_tpo_or_chairman(request.user):
            return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)

        roll_no = request.data.get('roll_no', '')
        if not roll_no:
            return Response({'error': 'roll_no is required'}, status=status.HTTP_400_BAD_REQUEST)

        sp = undebar_student(roll_no)
        if sp:
            return Response({'status': 'undebarred', 'roll_no': roll_no})
        return Response({'error': 'Student not found'}, status=status.HTTP_404_NOT_FOUND)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([TokenAuthentication])
def debarred_status_api(request, roll_no):
    """Get debar status for a specific student."""
    status_data = get_student_debar_status(roll_no)
    if status_data:
        return Response(status_data)
    return Response({'error': 'Student not found'}, status=status.HTTP_404_NOT_FOUND)


# =============================================
# 7. FIELDS & RESTRICTIONS (TPO)
# =============================================

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([TokenAuthentication])
def manage_fields_api(request):
    """Manage custom form fields (roles)."""
    if request.method == 'GET':
        roles = get_all_roles()
        return Response(RoleSerializer(roles, many=True).data)

    elif request.method == 'POST':
        if not is_tpo_or_chairman(request.user):
            return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)

        role_name = request.data.get('role', '')
        if not role_name:
            return Response({'error': 'role is required'}, status=status.HTTP_400_BAD_REQUEST)

        role_obj, created = create_or_get_role(role_name)
        return Response(
            RoleSerializer(role_obj).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([TokenAuthentication])
def form_fields_api(request):
    """Get form field configuration (roles, companies, skills)."""
    config = get_form_field_config()

    return Response({
        'roles': RoleSerializer(config['roles'], many=True).data,
        'companies': CompanyDetailsSerializer(config['companies'], many=True).data,
        'skills': SkillSerializer(config['skills'], many=True).data,
    })


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([TokenAuthentication])
def restrictions_api(request):
    """Manage placement restrictions (policies)."""
    if request.method == 'GET':
        policies = PlacementPolicy.objects.all()
        return Response(PlacementPolicySerializer(policies, many=True).data)

    elif request.method == 'POST':
        if not _is_tpo_or_chairman(request.user):
            return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)

        serializer = PlacementPolicySerializer(data=request.data)
        if serializer.is_valid():
            # Deactivate all existing policies first
            PlacementPolicy.objects.update(is_active=False)
            serializer.save(is_active=True)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# =============================================
# 8. COMPANY REGISTRATION (Legacy)
# =============================================

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([TokenAuthentication])
def company_registration_api(request):
    """
    GET: Get registered companies (legacy CompanyDetails).
    POST: Register a new company (legacy CompanyDetails).
    """
    if request.method == 'GET':
        companies = get_all_companies()
        return Response(CompanyDetailsSerializer(companies, many=True).data)

    elif request.method == 'POST':
        if not is_tpo_or_chairman(request.user):
            return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)

        company_name = request.data.get('company_name', '')
        if not company_name:
            return Response({'error': 'company_name is required'}, status=status.HTTP_400_BAD_REQUEST)

        obj, created = register_company(company_name)
        return Response(
            CompanyDetailsSerializer(obj).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )


# =============================================
# 9. APPLY FOR PLACEMENT (Student)
# =============================================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([TokenAuthentication])
def apply_for_placement_api(request):
    """Student applies/responds to a placement schedule invitation."""
    user = request.user
    student = get_student(user)
    if not student:
        return Response({'error': 'Student profile not found'}, status=status.HTTP_404_NOT_FOUND)

    notify_id = request.data.get('notify_id')
    invitation_response = request.data.get('invitation', 'ACCEPTED')

    if not notify_id:
        return Response({'error': 'notify_id is required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        notify = NotifyStudent.objects.get(id=notify_id)
    except NotifyStudent.DoesNotExist:
        return Response({'error': 'Placement event not found'}, status=status.HTTP_404_NOT_FOUND)

    ps, created = PlacementStatus.objects.get_or_create(
        unique_id=student,
        notify_id=notify,
        defaults={'invitation': invitation_response}
    )

    if not created:
        ps.invitation = invitation_response
        ps.timestamp = timezone.now()
        ps.save()

    return Response(PlacementStatusSerializer(ps).data)


# =============================================
# 10. CALENDAR & TIMELINE
# =============================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([TokenAuthentication])
def calendar_events_api(request):
    """Get placement calendar events."""
    schedules = PlacementSchedule.objects.select_related('notify_id', 'role').all()
    events = []
    for s in schedules:
        events.append({
            'id': s.id,
            'title': s.title,
            'date': str(s.placement_date),
            'time': str(s.time) if s.time else '',
            'location': s.location,
            'description': s.description,
            'company_name': s.notify_id.company_name,
            'placement_type': s.notify_id.placement_type,
            'role': s.get_role,
        })
    return Response(events)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([TokenAuthentication])
def timeline_api(request, job_id):
    """Get the placement timeline / history for a specific placement event."""
    try:
        notify = NotifyStudent.objects.get(id=job_id)
    except NotifyStudent.DoesNotExist:
        return Response({'error': 'Placement event not found'}, status=status.HTTP_404_NOT_FOUND)

    schedules = PlacementSchedule.objects.filter(notify_id=notify).order_by('placement_date')
    statuses = PlacementStatus.objects.select_related(
        'unique_id', 'unique_id__id', 'unique_id__id__user'
    ).filter(notify_id=notify)

    return Response({
        'event': NotifyStudentSerializer(notify).data,
        'schedules': PlacementScheduleSerializer(schedules, many=True).data,
        'statuses': PlacementStatusSerializer(statuses, many=True).data,
    })


# =============================================
# 11. NEXT ROUND & DOWNLOAD
# =============================================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([TokenAuthentication])
def next_round_api(request):
    """Create a next round schedule for an existing placement event."""
    if not _is_tpo_or_chairman(request.user):
        return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)

    notify_id = request.data.get('notify_id')
    placement_date = request.data.get('placement_date')
    location = request.data.get('location', '')
    time_val = request.data.get('time')
    description = request.data.get('description', '')
    role_name = request.data.get('role', '')

    if not notify_id:
        return Response({'error': 'notify_id is required'}, status=status.HTTP_400_BAD_REQUEST)

    notify = get_object_or_404(NotifyStudent, id=notify_id)
    role_obj, _ = Role.objects.get_or_create(role=role_name)

    schedule = PlacementSchedule.objects.create(
        notify_id=notify,
        title=notify.company_name,
        description=description,
        placement_date=placement_date,
        role=role_obj,
        location=location,
        time=time_val,
    )

    return Response(PlacementScheduleSerializer(schedule).data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([TokenAuthentication])
def download_applications_api(request, job_id):
    """Download applications as Excel for a specific placement event."""
    import xlwt

    if not _is_tpo_or_chairman(request.user):
        return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)

    statuses = PlacementStatus.objects.select_related(
        'unique_id', 'unique_id__id', 'unique_id__id__user', 'notify_id'
    ).filter(notify_id=job_id)

    wb = xlwt.Workbook(encoding='utf-8')
    ws = wb.add_sheet('Applications')

    # Headers
    headers = ['S.No', 'Roll No', 'Student Name', 'Company', 'Invitation', 'Placed']
    for col, header in enumerate(headers):
        ws.write(0, col, header)

    for row, ps in enumerate(statuses, 1):
        ws.write(row, 0, row)
        ws.write(row, 1, ps.unique_id.id.id if ps.unique_id and ps.unique_id.id else '')
        try:
            name = '{} {}'.format(
                ps.unique_id.id.user.first_name,
                ps.unique_id.id.user.last_name
            )
        except Exception:
            name = ''
        ws.write(row, 2, name)
        ws.write(row, 3, ps.notify_id.company_name if ps.notify_id else '')
        ws.write(row, 4, ps.invitation)
        ws.write(row, 5, ps.placed)

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.ms-excel'
    )
    response['Content-Disposition'] = 'attachment; filename="applications_{}.xls"'.format(job_id)
    return response


# =============================================
# 12. CHAIRMAN VISITS
# =============================================

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([TokenAuthentication])
def visits_api(request):
    """List/create chairman visits."""
    if request.method == 'GET':
        visits = ChairmanVisit.objects.all().order_by('-visiting_date')
        return Response(ChairmanVisitSerializer(visits, many=True).data)

    elif request.method == 'POST':
        if not is_chairman(request.user):
            return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)

        serializer = ChairmanVisitSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# =============================================
# PCMS VIEWSETS (Company, Jobs, Applications, Offers, Announcements)
# These are carried forward from the existing api/views.py
# =============================================

class CompanyViewSet(viewsets.ModelViewSet):
    """API endpoint for Company CRUD."""
    permission_classes = [IsAuthenticated]
    serializer_class = CompanySerializer
    queryset = Company.objects.all()

    def get_queryset(self):
        if is_tpo_or_chairman(self.request.user):
            return Company.objects.all()
        return Company.objects.filter(approval_status='APPROVED')

    def get_serializer_class(self):
        if self.action == 'list':
            return CompanyListSerializer
        return CompanySerializer

    def perform_create(self, serializer):
        serializer.save(registered_by=self.request.user)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        if not is_tpo_or_chairman(request.user):
            return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)
        company = self.get_object()
        company.approval_status = 'APPROVED'
        company.approved_by = request.user
        company.save()
        return Response({'status': 'approved'})

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        if not is_tpo_or_chairman(request.user):
            return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)
        company = self.get_object()
        company.approval_status = 'REJECTED'
        company.approved_by = request.user
        company.save()
        return Response({'status': 'rejected'})


class JobPostingViewSet(viewsets.ModelViewSet):
    """API endpoint for Job Posting CRUD."""
    permission_classes = [IsAuthenticated]
    serializer_class = JobPostingSerializer
    queryset = JobPosting.objects.all()

    def get_queryset(self):
        if is_tpo_or_chairman(self.request.user):
            return JobPosting.objects.select_related('company').all()
        return JobPosting.objects.select_related('company').filter(is_active=True)

    def get_serializer_class(self):
        if self.action == 'list':
            return JobPostingListSerializer
        return JobPostingSerializer

    def perform_create(self, serializer):
        if not is_tpo_or_chairman(self.request.user):
            raise PermissionError("Not authorized")
        serializer.save(posted_by=self.request.user)

    @action(detail=True, methods=['get'])
    def check_eligibility(self, request, pk=None):
        """Student checks eligibility for a posting."""
        posting = self.get_object()
        profile = get_object_or_404(ExtraInfo, user=request.user)
        try:
            student = Student.objects.get(id=profile)
        except Student.DoesNotExist:
            return Response({'error': 'Student profile not found'}, status=404)

        is_eligible, reasons = check_eligibility(student, posting)
        can_apply, policy_reason = check_placement_policy(student, posting)
        has_applied = check_duplicate_application(student, posting)

        return Response({
            'eligible': is_eligible,
            'reasons': reasons,
            'policy_check': can_apply,
            'policy_reason': policy_reason,
            'already_applied': has_applied,
        })

    @action(detail=True, methods=['post'])
    def apply(self, request, pk=None):
        """Student applies for a job."""
        posting = self.get_object()
        profile = get_object_or_404(ExtraInfo, user=request.user)
        try:
            student = Student.objects.get(id=profile)
        except Student.DoesNotExist:
            return Response({'error': 'Student profile not found'}, status=404)

        if check_duplicate_application(student, posting):
            return Response({'error': 'Already applied'}, status=400)

        is_eligible, reasons = check_eligibility(student, posting)
        if not is_eligible:
            return Response({'error': 'Not eligible', 'reasons': reasons}, status=400)

        can_apply, policy_reason = check_placement_policy(student, posting)
        if not can_apply:
            return Response({'error': policy_reason}, status=400)

        application = create_job_application(student, posting)
        return Response(
            JobApplicationSerializer(application).data,
            status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=['get'])
    def applications(self, request, pk=None):
        """TPO gets all applications for a posting."""
        if not is_tpo_or_chairman(request.user):
            return Response({'error': 'Not authorized'}, status=403)
        posting = self.get_object()
        apps = posting.applications.select_related('student', 'student__id__user')
        return Response(JobApplicationSerializer(apps, many=True).data)


class JobApplicationViewSet(viewsets.ModelViewSet):
    """API endpoint for managing applications."""
    permission_classes = [IsAuthenticated]
    serializer_class = JobApplicationSerializer
    queryset = JobApplication.objects.all()

    def get_queryset(self):
        user = self.request.user
        if is_tpo_or_chairman(user):
            return JobApplication.objects.all()
        profile = get_object_or_404(ExtraInfo, user=user)
        try:
            student = Student.objects.get(id=profile)
            return JobApplication.objects.filter(student=student)
        except Student.DoesNotExist:
            return JobApplication.objects.none()

    @action(detail=True, methods=['post'])
    def update_status(self, request, pk=None):
        """TPO updates application status."""
        if not is_tpo_or_chairman(request.user):
            return Response({'error': 'Not authorized'}, status=403)
        application = self.get_object()
        new_status = request.data.get('status')
        remarks = request.data.get('remarks', '')
        updated_app = update_job_application_status(application, new_status, remarks)
        return Response(JobApplicationSerializer(updated_app).data)


class JobOfferViewSet(viewsets.ModelViewSet):
    """API endpoint for managing offers."""
    permission_classes = [IsAuthenticated]
    serializer_class = JobOfferSerializer
    queryset = JobOffer.objects.all()

    def get_queryset(self):
        user = self.request.user
        if is_tpo_or_chairman(user):
            return JobOffer.objects.all()
        profile = get_object_or_404(ExtraInfo, user=user)
        try:
            student = Student.objects.get(id=profile)
            return JobOffer.objects.filter(application__student=student)
        except Student.DoesNotExist:
            return JobOffer.objects.none()

    def perform_create(self, serializer):
        from datetime import timedelta
        # Auto-set response deadline to 48 hours if not provided
        deadline = self.request.data.get('response_deadline')
        if not deadline:
            deadline = timezone.now() + timedelta(hours=48)
            serializer.save(response_deadline=deadline)
        else:
            serializer.save()

    @action(detail=True, methods=['post'])
    def respond(self, request, pk=None):
        """Student accepts or rejects an offer."""
        offer = self.get_object()
        action_type = request.data.get('action')
        success, message = process_offer_response(offer, action_type)
        if success:
            return Response({'status': message})
        return Response({'error': message}, status=400)


class AppealViewSet(viewsets.ModelViewSet):
    """API endpoint for managing appeals."""
    permission_classes = [IsAuthenticated]
    serializer_class = AppealSerializer
    queryset = Appeal.objects.all()

    def get_queryset(self):
        user = self.request.user
        if is_tpo_or_chairman(user):
            return Appeal.objects.all()
        profile = get_object_or_404(ExtraInfo, user=user)
        try:
            student = Student.objects.get(id=profile)
            return Appeal.objects.filter(application__student=student)
        except Student.DoesNotExist:
            return Appeal.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        profile = get_object_or_404(ExtraInfo, user=user)
        student = get_object_or_404(Student, id=profile)
        # Verify application belongs to student
        application = get_object_or_404(JobApplication, id=self.request.data.get('application'), student=student)
        serializer.save(application=application)

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        if not is_tpo_or_chairman(request.user):
            return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)
        appeal = self.get_object()
        appeal.status = request.data.get('status', 'RESOLVED')
        appeal.remarks = request.data.get('remarks', '')
        appeal.resolved_at = timezone.now()
        appeal.save()

        # Optionally update application status
        new_app_status = request.data.get('application_status')
        if new_app_status:
            appeal.application.status = new_app_status
            appeal.application.save()

        return Response(AppealSerializer(appeal).data)


class AnnouncementViewSet(viewsets.ModelViewSet):
    """API endpoint for announcements."""
    permission_classes = [IsAuthenticated]
    serializer_class = AnnouncementSerializer
    queryset = Announcement.objects.filter(is_active=True)

    def perform_create(self, serializer):
        if not _is_tpo_or_chairman(self.request.user):
            raise PermissionError("Not authorized")
        serializer.save(created_by=self.request.user)


# =============================================
# PCMS FUNCTION-BASED VIEWS
# =============================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([TokenAuthentication])
def placement_stats_pcms_api(request):
    """Get PCMS placement statistics."""
    year = request.query_params.get('year')
    stats = get_placement_statistics(year=year)
    return Response(stats)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([TokenAuthentication])
def my_application_summary_api(request):
    """Get current student's application summary."""
    profile = get_object_or_404(ExtraInfo, user=request.user)
    try:
        student = Student.objects.get(id=profile)
    except Student.DoesNotExist:
        return Response({'error': 'Student not found'}, status=404)

    summary = get_student_application_summary(student)
    # Remove queryset from summary for JSON serialization
    apps = JobApplicationSerializer(summary.pop('applications'), many=True).data
    summary['applications'] = apps
    return Response(summary)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([TokenAuthentication])
def dashboard_api(request):
    """PCMS dashboard summary data."""
    user = request.user
    roles = get_user_roles(user)
    is_chairman_val = roles['is_chairman']
    is_officer_val = roles['is_officer']
    is_student_val = roles['is_student']

    data = {
        'is_chairman': is_chairman_val,
        'is_officer': is_officer_val,
        'is_student': is_student_val,
    }

    if is_student_val:
        student = get_student(user)
        if student:
            active_postings = JobPosting.objects.filter(is_active=True).count()
            my_apps = JobApplication.objects.filter(student=student).count()
            my_offers_count = JobOffer.objects.filter(
                application__student=student, status='PENDING'
            ).count()
            announcements = get_active_announcements(limit=5)

            data.update({
                'active_postings': active_postings,
                'my_apps': my_apps,
                'my_offers_count': my_offers_count,
                'recent_announcements': AnnouncementSerializer(announcements, many=True).data,
            })
    elif is_officer_val or is_chairman_val:
        data.update({
            'total_companies': Company.objects.filter(approval_status='APPROVED').count(),
            'pending_companies': Company.objects.filter(approval_status='PENDING').count(),
            'active_postings': JobPosting.objects.filter(is_active=True).count(),
            'total_applications': JobApplication.objects.count(),
            'pending_offers': JobOffer.objects.filter(status='PENDING').count(),
            'accepted_offers': JobOffer.objects.filter(status='ACCEPTED').count(),
            'recent_applications': JobApplicationSerializer(
                JobApplication.objects.select_related(
                    'student__id__user', 'job_posting__company'
                ).order_by('-applied_at')[:10],
                many=True
            ).data,
        })

    return Response(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([TokenAuthentication])
def reports_api(request):
    """Generate placement reports and analytics."""
    year_filter = request.query_params.get('year')
    dept_filter = request.query_params.get('department')
    prog_filter = request.query_params.get('programme')
    job_type_filter = request.query_params.get('job_type')

    report_data = get_placement_report_data(year_filter, dept_filter, prog_filter, job_type_filter)

    return Response({
        'stats': report_data['stats'],
        'offers': JobOfferSerializer(report_data['offers'], many=True).data,
        'companies_participated': report_data['companies_participated'],
        'total_students': report_data['total_students'],
        'placed_students': report_data['placed_students'],
        'placement_rate': report_data['placement_rate'],
    })


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([TokenAuthentication])
def policies_api(request):
    """Manage placement policies."""
    if request.method == 'GET':
        policies = PlacementPolicy.objects.all()
        return Response(PlacementPolicySerializer(policies, many=True).data)

    elif request.method == 'POST':
        if not _is_tpo_or_chairman(request.user):
            return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)

        action_type = request.data.get('action', 'create')

        if action_type == 'create':
            serializer = PlacementPolicySerializer(data=request.data)
            if serializer.is_valid():
                PlacementPolicy.objects.update(is_active=False)
                serializer.save(is_active=True)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        elif action_type == 'toggle':
            policy_id = request.data.get('policy_id')
            try:
                policy = PlacementPolicy.objects.get(id=policy_id)
                if not policy.is_active:
                    PlacementPolicy.objects.update(is_active=False)
                    policy.is_active = True
                else:
                    policy.is_active = False
                policy.save()
                return Response(PlacementPolicySerializer(policy).data)
            except PlacementPolicy.DoesNotExist:
                return Response({'error': 'Policy not found'}, status=status.HTTP_404_NOT_FOUND)

        return Response({'error': 'Invalid action'}, status=status.HTTP_400_BAD_REQUEST)


# =============================================
# INTERVIEW MANAGEMENT
# =============================================

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([TokenAuthentication])
def interviews_api(request):
    """List or create interview schedules."""
    if request.method == 'GET':
        # Students only see interviews they're assigned to
        if _is_student(request.user):
            student = _get_student(request.user)
            if student:
                panel_interviews = InterviewPanel.objects.filter(
                    application__student=student
                ).values_list('interview_id', flat=True)
                interviews = InterviewSchedule.objects.filter(
                    id__in=panel_interviews
                ).select_related('job_posting', 'job_posting__company').order_by('-date')
            else:
                interviews = InterviewSchedule.objects.none()
        else:
            interviews = InterviewSchedule.objects.select_related(
                'job_posting', 'job_posting__company'
            ).all().order_by('-date')
        return Response(InterviewScheduleSerializer(interviews, many=True).data)

    elif request.method == 'POST':
        if not _is_tpo_or_chairman(request.user):
            return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)

        serializer = InterviewScheduleSerializer(data=request.data)
        if serializer.is_valid():
            # Compute end_time for conflict check
            import datetime as dt
            time_slot = serializer.validated_data.get('time_slot')
            duration = serializer.validated_data.get('duration_minutes', 60)
            venue = serializer.validated_data.get('venue_or_link', '')
            interview_date = serializer.validated_data.get('date')

            if time_slot and duration:
                start_dt = dt.datetime.combine(dt.date.today(), time_slot)
                end_time = (start_dt + dt.timedelta(minutes=duration)).time()
            else:
                end_time = None

            # Check for conflicts
            conflicts = check_interview_conflicts(
                interview_date, time_slot, end_time, venue
            )
            if conflicts.exists():
                conflict_data = InterviewScheduleSerializer(conflicts, many=True).data
                return Response({
                    'error': 'Scheduling conflict detected',
                    'conflicts': conflict_data,
                }, status=status.HTTP_409_CONFLICT)

            serializer.save(created_by=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
@authentication_classes([TokenAuthentication])
def interview_detail_api(request, interview_id):
    """Get, update (reschedule), or delete an interview schedule."""
    interview = get_object_or_404(InterviewSchedule, id=interview_id)

    if request.method == 'GET':
        panelists = InterviewPanel.objects.filter(
            interview=interview
        ).select_related('application', 'application__student', 'application__student__id__user')

        return Response({
            'interview': InterviewScheduleSerializer(interview).data,
            'panelists': InterviewPanelSerializer(panelists, many=True).data,
        })

    elif request.method == 'PUT':
        if not _is_tpo_or_chairman(request.user):
            return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)

        # Detect if this is a reschedule (date or time changed)
        new_date = request.data.get('date')
        new_time = request.data.get('time_slot')
        is_reschedule = False
        if new_date and str(new_date) != str(interview.date):
            is_reschedule = True
        if new_time and str(new_time) != str(interview.time_slot):
            is_reschedule = True

        if is_reschedule:
            can_reschedule, msg = validate_reschedule(interview)
            if not can_reschedule:
                return Response({'error': msg}, status=status.HTTP_400_BAD_REQUEST)

        serializer = InterviewScheduleSerializer(interview, data=request.data, partial=True)
        if serializer.is_valid():
            # Conflict check for the new slot
            import datetime as dt
            check_date = serializer.validated_data.get('date', interview.date)
            check_time = serializer.validated_data.get('time_slot', interview.time_slot)
            check_duration = serializer.validated_data.get('duration_minutes', interview.duration_minutes)
            check_venue = serializer.validated_data.get('venue_or_link', interview.venue_or_link)

            if check_time and check_duration:
                start_dt = dt.datetime.combine(dt.date.today(), check_time)
                check_end = (start_dt + dt.timedelta(minutes=check_duration)).time()
            else:
                check_end = interview.end_time

            conflicts = check_interview_conflicts(
                check_date, check_time, check_end, check_venue,
                exclude_id=interview.id
            )
            if conflicts.exists():
                conflict_data = InterviewScheduleSerializer(conflicts, many=True).data
                return Response({
                    'error': 'Scheduling conflict detected',
                    'conflicts': conflict_data,
                }, status=status.HTTP_409_CONFLICT)

            # Increment reschedule counter if date/time changed
            if is_reschedule:
                serializer.validated_data['reschedule_count'] = interview.reschedule_count + 1

            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    elif request.method == 'DELETE':
        if not _is_tpo_or_chairman(request.user):
            return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)
        interview.delete()
        return Response({'detail': 'Interview deleted.'}, status=status.HTTP_204_NO_CONTENT)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([TokenAuthentication])
def check_conflicts_api(request):
    """
    Preview conflicts for a proposed date/time/venue slot without creating.
    Query params: date, time_slot, duration_minutes, venue_or_link, exclude_id (optional)
    """
    import datetime as dt
    interview_date = request.query_params.get('date')
    time_slot_str = request.query_params.get('time_slot')
    duration = int(request.query_params.get('duration_minutes', 60))
    venue = request.query_params.get('venue_or_link', '')
    exclude_id = request.query_params.get('exclude_id')

    if not interview_date or not time_slot_str:
        return Response({'conflicts': [], 'has_conflicts': False})

    try:
        parsed_date = dt.datetime.strptime(interview_date, '%Y-%m-%d').date()
        parsed_time = dt.datetime.strptime(time_slot_str, '%H:%M').time()
    except ValueError:
        return Response({'error': 'Invalid date or time format. Use YYYY-MM-DD and HH:MM.'},
                        status=status.HTTP_400_BAD_REQUEST)

    start_dt = dt.datetime.combine(dt.date.today(), parsed_time)
    end_time = (start_dt + dt.timedelta(minutes=duration)).time()

    conflicts = check_interview_conflicts(parsed_date, parsed_time, end_time, venue, exclude_id)
    return Response({
        'has_conflicts': conflicts.exists(),
        'conflicts': InterviewScheduleSerializer(conflicts, many=True).data,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([TokenAuthentication])
def assign_panel_api(request, interview_id):
    """
    Assign shortlisted students to an interview panel.
    Body: { "application_ids": [1, 2, 3] }
    """
    if not _is_tpo_or_chairman(request.user):
        return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)

    interview = get_object_or_404(InterviewSchedule, id=interview_id)
    application_ids = request.data.get('application_ids', [])

    if not application_ids:
        return Response({'error': 'No application IDs provided.'}, status=status.HTTP_400_BAD_REQUEST)

    created = []
    skipped = []
    for app_id in application_ids:
        try:
            application = JobApplication.objects.get(id=app_id, job_posting=interview.job_posting)
            _, was_created = InterviewPanel.objects.get_or_create(
                interview=interview, application=application
            )
            if was_created:
                created.append(app_id)
            else:
                skipped.append(app_id)
        except JobApplication.DoesNotExist:
            skipped.append(app_id)

    panelists = InterviewPanel.objects.filter(interview=interview).select_related(
        'application', 'application__student', 'application__student__id__user'
    )
    return Response({
        'detail': f'{len(created)} assigned, {len(skipped)} skipped.',
        'panelists': InterviewPanelSerializer(panelists, many=True).data,
    })


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
@authentication_classes([TokenAuthentication])
def record_outcome_api(request, interview_id):
    """
    Batch-update outcomes for an interview's panelists.
    Body: { "outcomes": [ {"panel_id": 1, "result": "SELECTED", "remarks": "..."}, ... ] }
    """
    if not _is_tpo_or_chairman(request.user):
        return Response({'error': 'Not authorized'}, status=status.HTTP_403_FORBIDDEN)

    interview = get_object_or_404(InterviewSchedule, id=interview_id)
    outcomes = request.data.get('outcomes', [])

    if not outcomes:
        return Response({'error': 'No outcomes provided.'}, status=status.HTTP_400_BAD_REQUEST)

    updated = 0
    for outcome in outcomes:
        panel_id = outcome.get('panel_id')
        result = outcome.get('result', '')
        remarks = outcome.get('remarks', '')
        try:
            panel = InterviewPanel.objects.get(id=panel_id, interview=interview)
            if result:
                panel.result = result
            if remarks:
                panel.remarks = remarks
            panel.save()
            updated += 1
        except InterviewPanel.DoesNotExist:
            pass

    panelists = InterviewPanel.objects.filter(interview=interview).select_related(
        'application', 'application__student', 'application__student__id__user'
    )
    return Response({
        'detail': f'{updated} outcomes recorded.',
        'panelists': InterviewPanelSerializer(panelists, many=True).data,
    })




def check_eligibility(student, job_posting):
    """
    Validates whether a student is eligible to apply for a given job posting.
    Returns (is_eligible: bool, reasons: list[str])
    """
    reasons = []

    # 1. Check if student is debarred
    try:
        sp = StudentPlacement.objects.get(unique_id=student)
        if sp.debar == 'DEBAR':
            reasons.append("You are currently debarred from placement activities.")
            return False, reasons
    except StudentPlacement.DoesNotExist:
        pass

    # 2. Check CPI
    if job_posting.min_cpi and student.cpi < job_posting.min_cpi:
        reasons.append(
            "Minimum CPI required: {}. Your CPI: {}.".format(job_posting.min_cpi, student.cpi)
        )

    # 3. Check programme eligibility
    if job_posting.eligible_programmes:
        eligible_progs = [p.strip().upper() for p in job_posting.eligible_programmes.split(',')]
        student_prog = student.programme.upper() if student.programme else ''
        if student_prog and student_prog not in eligible_progs:
            reasons.append(
                "Your programme ({}) is not eligible. Eligible: {}.".format(
                    student.programme, job_posting.eligible_programmes
                )
            )

    # 4. Check branch/department eligibility
    if job_posting.eligible_branches:
        eligible_branches = [b.strip().upper() for b in job_posting.eligible_branches.split(',')]
        try:
            student_dept = student.id.department.name.upper() if student.id.department else ''
        except Exception:
            student_dept = ''

        # Also check specialization for M.Tech
        student_spec = student.specialization.upper() if student.specialization else ''

        if student_dept and student_dept not in eligible_branches:
            if not (student_spec and student_spec in eligible_branches):
                reasons.append(
                    "Your branch/department is not eligible. Eligible: {}.".format(
                        job_posting.eligible_branches
                    )
                )

    # 5. Check batch eligibility
    if job_posting.eligible_batch_from and student.batch < job_posting.eligible_batch_from:
        reasons.append(
            "Minimum batch year: {}. Your batch: {}.".format(
                job_posting.eligible_batch_from, student.batch
            )
        )
    if job_posting.eligible_batch_to and student.batch > job_posting.eligible_batch_to:
        reasons.append(
            "Maximum batch year: {}. Your batch: {}.".format(
                job_posting.eligible_batch_to, student.batch
            )
        )

    # 6. Check required skills
    if job_posting.required_skills.exists():
        student_skills = Has.objects.filter(unique_id=student).values_list('skill_id', flat=True)
        required_skill_ids = job_posting.required_skills.values_list('id', flat=True)
        missing_skills = set(required_skill_ids) - set(student_skills)
        if missing_skills:
            missing_names = Skill.objects.filter(id__in=missing_skills).values_list('skill', flat=True)
            reasons.append(
                "Missing required skills: {}.".format(', '.join(missing_names))
            )

    # 7. Check application deadline
    if job_posting.is_deadline_passed:
        reasons.append("Application deadline has passed.")

    # 8. Check if job is active
    if not job_posting.is_active:
        reasons.append("This job posting is no longer active.")

    is_eligible = len(reasons) == 0
    return is_eligible, reasons


def check_duplicate_application(student, job_posting):
    """
    Check if a student has already applied for this job posting.
    Returns True if duplicate exists.
    """
    return JobApplication.objects.filter(
        student=student, job_posting=job_posting
    ).exists()


def check_placement_policy(student, job_posting):
    """
    Enforce placement policies (e.g., max offers, dream company rules).
    Returns (can_apply: bool, reason: str)
    """
    active_policy = PlacementPolicy.objects.filter(is_active=True).first()
    if not active_policy:
        return True, ""

    # Check if student already has max offers accepted
    accepted_offers_count = JobOffer.objects.filter(
        application__student=student,
        status='ACCEPTED'
    ).count()

    if accepted_offers_count >= active_policy.max_offers_allowed:
        # Check dream company exception
        if active_policy.allow_dream_company and job_posting.ctc >= active_policy.dream_ctc_threshold:
            return True, ""
        return False, "You have already accepted {} offer(s). Maximum allowed: {}.".format(
            accepted_offers_count, active_policy.max_offers_allowed
        )

    return True, ""


def expire_pending_offers():
    """
    Utility to mark pending offers as expired if the deadline has passed.
    Should be called periodically (e.g., via celery task or management command).
    """
    expired = JobOffer.objects.filter(
        status='PENDING',
        response_deadline__lt=timezone.now()
    ).update(status='EXPIRED')
    return expired


def get_placement_statistics(year=None):
    """
    Generate aggregated placement statistics.
    Returns a dict with placement data.
    """
    from django.db.models import Avg, Count, Max, Min, Sum

    filters = {}
    if year:
        filters['application__job_posting__created_at__year'] = year

    offers = JobOffer.objects.filter(status='ACCEPTED', **filters)

    stats = {
        'total_offers': offers.count(),
        'avg_ctc': offers.aggregate(avg=Avg('ctc_offered'))['avg'] or 0,
        'max_ctc': offers.aggregate(max=Max('ctc_offered'))['max'] or 0,
        'min_ctc': offers.aggregate(min=Min('ctc_offered'))['min'] or 0,
        'total_ctc': offers.aggregate(total=Sum('ctc_offered'))['total'] or 0,
    }

    # Company-wise stats
    stats['company_wise'] = offers.values(
        'application__job_posting__company__name'
    ).annotate(
        count=Count('id'),
        avg_package=Avg('ctc_offered')
    ).order_by('-count')

    # Branch-wise stats
    stats['branch_wise'] = offers.values(
        'application__student__id__department__name'
    ).annotate(
        count=Count('id'),
        avg_package=Avg('ctc_offered')
    ).order_by('-count')

    # Programme-wise stats
    stats['programme_wise'] = offers.values(
        'application__student__programme'
    ).annotate(
        count=Count('id'),
        avg_package=Avg('ctc_offered')
    ).order_by('-count')

    return stats


def get_student_application_summary(student):
    """
    Get a summary of a student's placement applications.
    """
    applications = JobApplication.objects.filter(student=student).select_related(
        'job_posting', 'job_posting__company'
    )

    summary = {
        'total': applications.count(),
        'applied': applications.filter(status='APPLIED').count(),
        'shortlisted': applications.filter(status='SHORTLISTED').count(),
        'interview_scheduled': applications.filter(status='INTERVIEW_SCHEDULED').count(),
        'offer_extended': applications.filter(status='OFFER_EXTENDED').count(),
        'offer_accepted': applications.filter(status='OFFER_ACCEPTED').count(),
        'offer_rejected': applications.filter(status='OFFER_REJECTED').count(),
        'rejected': applications.filter(status='REJECTED').count(),
        'applications': applications,
    }
    return summary


class PlacementProfileViewSet(viewsets.ModelViewSet):
    serializer_class = PlacementProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Admin can see all, student can see only theirs
        user = self.request.user
        if is_student(user):
            student = get_object_or_404(Student, id__user=user)
            return PlacementProfile.objects.filter(student=student)
        return PlacementProfile.objects.all()

    def list(self, request, *args, **kwargs):
        if is_student(request.user):
            # Create if doesn't exist
            student = get_object_or_404(Student, id__user=request.user)
            profile, created = PlacementProfile.objects.get_or_create(student=student)
            serializer = self.get_serializer(profile)
            return Response(serializer.data)

        # otherwise return normal list
        return super().list(request, *args, **kwargs)

    def perform_update(self, serializer):
        # Save old state for audit
        instance = self.get_object()
        old_data = self.get_serializer(instance).data

        # Save the new state
        new_instance = serializer.save()
        new_data = self.get_serializer(new_instance).data

        # Calculate differences and create audit log
        changes = {}
        # Only log fields that we care about
        fields_to_track = ['resume', 'about_me', 'linkedin_url', 'portfolio_url',
                           'github_url', 'achievements', 'certifications']

        for field in fields_to_track:
            old_value = old_data.get(field)
            new_value = new_data.get(field)
            if old_value != new_value:
                changes[field] = {
                    'old': old_value,
                    'new': new_value
                }

        if changes:
            PlacementProfileAuditLog.objects.create(
                profile=new_instance,
                changed_by=self.request.user,
                changes=changes
            )


# =============================================
# ALUMNI NETWORK VIEWSETS
# =============================================

class AlumniProfileViewSet(viewsets.ModelViewSet):
    """
    Alumni registration and profile management.
    - Any authenticated user can POST to register as alumni.
    - TPO/Chairman can list all alumni (filterable by status) and approve/reject.
    - Students see only APPROVED alumni.
    - Alumni can PATCH their own profile.
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [TokenAuthentication]

    def get_serializer_class(self):
        if self.action == 'list' and not is_tpo_or_chairman(self.request.user):
            return AlumniProfileListSerializer
        return AlumniProfileSerializer

    def get_queryset(self):
        user = self.request.user
        if is_tpo_or_chairman(user):
            qs = AlumniProfile.objects.all()
            status_filter = self.request.query_params.get('status')
            if status_filter:
                qs = qs.filter(approval_status=status_filter.upper())
            return qs
        elif is_alumni(user):
            return AlumniProfile.objects.filter(user=user)
        else:
            # Students & others see only approved alumni
            return AlumniProfile.objects.filter(approval_status='APPROVED')

    def perform_create(self, serializer):
        # Check if the user already has an alumni profile
        if AlumniProfile.objects.filter(user=self.request.user).exists():
            raise serializers.ValidationError(
                {'detail': 'You have already registered as an alumni.'}
            )
        serializer.save(user=self.request.user)

    def perform_update(self, serializer):
        instance = self.get_object()
        if instance.user != self.request.user and not is_tpo_or_chairman(self.request.user):
            raise serializers.ValidationError(
                {'detail': 'You can only update your own profile.'}
            )
        serializer.save()

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        """TPO/Chairman approves an alumni registration."""
        if not is_tpo_or_chairman(request.user):
            return Response({'detail': 'Not authorized.'}, status=status.HTTP_403_FORBIDDEN)
        profile = self.get_object()
        if profile.approval_status == 'APPROVED':
            return Response({'detail': 'Already approved.'}, status=status.HTTP_400_BAD_REQUEST)
        approve_alumni(profile, request.user)
        return Response(AlumniProfileSerializer(profile).data)

    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None):
        """TPO/Chairman rejects an alumni registration."""
        if not is_tpo_or_chairman(request.user):
            return Response({'detail': 'Not authorized.'}, status=status.HTTP_403_FORBIDDEN)
        profile = self.get_object()
        remarks = request.data.get('remarks', '')
        reject_alumni(profile, remarks)
        return Response(AlumniProfileSerializer(profile).data)

    @action(detail=False, methods=['get'], url_path='me')
    def me(self, request):
        """Get the current user's alumni profile (or 404)."""
        profile = get_alumni_profile(request.user)
        if not profile:
            return Response({'detail': 'No alumni profile found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(AlumniProfileSerializer(profile).data)


class MentorshipProfileViewSet(viewsets.ModelViewSet):
    """
    Mentorship profile management.
    - Alumni create/update their mentorship profile.
    - Students & TPO can list available mentors.
    """
    serializer_class = MentorshipProfileSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [TokenAuthentication]

    def get_queryset(self):
        user = self.request.user
        if is_alumni(user):
            alumni = get_alumni_profile(user)
            if alumni:
                return MentorshipProfile.objects.filter(alumni=alumni)
            return MentorshipProfile.objects.none()
        # Students & TPO see available mentors only
        qs = MentorshipProfile.objects.filter(
            is_available=True,
            alumni__approval_status='APPROVED'
        )
        return qs

    def perform_create(self, serializer):
        alumni = get_alumni_profile(self.request.user)
        if not alumni or not alumni.is_approved:
            raise serializers.ValidationError(
                {'detail': 'Only approved alumni can create a mentorship profile.'}
            )
        if MentorshipProfile.objects.filter(alumni=alumni).exists():
            raise serializers.ValidationError(
                {'detail': 'You already have a mentorship profile. Use PATCH to update.'}
            )
        serializer.save(alumni=alumni)

    def perform_update(self, serializer):
        instance = self.get_object()
        if instance.alumni.user != self.request.user:
            raise serializers.ValidationError(
                {'detail': 'You can only update your own mentorship profile.'}
            )
        serializer.save()


class MentorshipSessionViewSet(viewsets.ModelViewSet):
    """
    Mentorship session booking.
    - Students create (request) sessions.
    - Mentors confirm/cancel and add meeting link.
    - Both parties list their sessions.
    """
    serializer_class = MentorshipSessionSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [TokenAuthentication]

    def get_queryset(self):
        user = self.request.user
        if is_alumni(user):
            alumni = get_alumni_profile(user)
            if alumni:
                try:
                    mp = alumni.mentorship_profile
                    return MentorshipSession.objects.filter(mentor=mp)
                except MentorshipProfile.DoesNotExist:
                    pass
            return MentorshipSession.objects.none()
        elif is_student(user):
            student = get_student(user)
            if student:
                return MentorshipSession.objects.filter(student=student)
            return MentorshipSession.objects.none()
        elif is_tpo_or_chairman(user):
            return MentorshipSession.objects.all()
        return MentorshipSession.objects.none()

    def perform_create(self, serializer):
        student = get_student(self.request.user)
        if not student:
            raise serializers.ValidationError(
                {'detail': 'Only students can request mentorship sessions.'}
            )
        serializer.save(student=student)

    def perform_update(self, serializer):
        instance = self.get_object()
        user = self.request.user
        # Mentor can update status, meeting_link, mentor_notes
        if is_alumni(user) and instance.mentor.alumni.user == user:
            serializer.save()
        elif is_student(user) and instance.student.id.user == user:
            # Student can only cancel
            if serializer.validated_data.get('status') not in (None, 'CANCELLED'):
                raise serializers.ValidationError(
                    {'detail': 'Students can only cancel sessions.'}
                )
            serializer.save()
        elif is_tpo_or_chairman(user):
            serializer.save()
        else:
            raise serializers.ValidationError(
                {'detail': 'Not authorized to update this session.'}
            )


class JobReferralViewSet(viewsets.ModelViewSet):
    """
    Job referral postings by alumni.
    - Alumni CRUD their own referrals.
    - Students list active referrals.
    - TPO can moderate (delete).
    """
    serializer_class = JobReferralSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [TokenAuthentication]

    def get_queryset(self):
        user = self.request.user
        if is_alumni(user):
            alumni = get_alumni_profile(user)
            if alumni:
                return JobReferral.objects.filter(posted_by=alumni)
            return JobReferral.objects.none()
        elif is_tpo_or_chairman(user):
            return JobReferral.objects.all()
        else:
            # Students see only active, non-expired referrals
            from datetime import date as _date
            return JobReferral.objects.filter(
                is_active=True
            ).filter(
                Q(deadline__isnull=True) | Q(deadline__gte=_date.today())
            )

    def perform_create(self, serializer):
        alumni = get_alumni_profile(self.request.user)
        if not alumni or not alumni.is_approved:
            raise serializers.ValidationError(
                {'detail': 'Only approved alumni can post job referrals.'}
            )
        serializer.save(posted_by=alumni)

    def perform_update(self, serializer):
        instance = self.get_object()
        if instance.posted_by.user != self.request.user and not is_tpo_or_chairman(self.request.user):
            raise serializers.ValidationError(
                {'detail': 'You can only update your own referrals.'}
            )
        serializer.save()

    def perform_destroy(self, instance):
        if instance.posted_by.user != self.request.user and not is_tpo_or_chairman(self.request.user):
            raise serializers.ValidationError(
                {'detail': 'You can only delete your own referrals.'}
            )
        instance.delete()

