"""
Business logic services for the Placement Cell Management System (PCMS).
This module contains all non-HTTP-related business logic extracted from views.py
"""
import datetime
import logging

from datetime import date
from django.contrib.auth.models import User
from django.db.models import Avg, Count, Max, Min, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone

from applications.globals.models import ExtraInfo, HoldsDesignation, Designation
from applications.academic_information.models import Student

from applications.placement_cell.models import (
    Achievement, ChairmanVisit, Course, Education, Experience, Conference,
    Has, NotifyStudent, Patent, PlacementRecord, Extracurricular, Reference,
    PlacementSchedule, PlacementStatus, Project, Publication, Interest,
    Skill, StudentPlacement, StudentRecord, Role, CompanyDetails,
    Company, JobPosting, JobApplication, InterviewSchedule,
    InterviewPanel, JobOffer, Announcement, PlacementPolicy,
    Coauthor, Coinventor, AlumniProfile,
)


logger = logging.getLogger('django.server')


# =============================================
# USER ROLE & AUTHENTICATION SERVICES
# =============================================

def is_tpo_or_chairman(user):
    """Check if user is TPO or Placement Chairman."""
    return HoldsDesignation.objects.filter(
        Q(working=user, designation__name="placement officer") |
        Q(working=user, designation__name="placement chairman")
    ).exists()


def is_chairman(user):
    """Check if user is Placement Chairman."""
    return HoldsDesignation.objects.filter(
        Q(working=user, designation__name="placement chairman")
    ).exists()


def is_officer(user):
    """Check if user is Placement Officer (TPO)."""
    return HoldsDesignation.objects.filter(
        Q(working=user, designation__name="placement officer")
    ).exists()


def is_student(user):
    """Check if user is a student."""
    return HoldsDesignation.objects.filter(
        Q(working=user, designation__name="student")
    ).exists()


def is_alumni(user):
    """Check if user is a verified alumni."""
    return HoldsDesignation.objects.filter(
        Q(working=user, designation__name="alumni")
    ).exists()


def get_student(user):
    """Get the Student object for a user. Returns None if not a student."""
    try:
        profile = ExtraInfo.objects.get(user=user)
        return Student.objects.get(id=profile)
    except (ExtraInfo.DoesNotExist, Student.DoesNotExist):
        return None


def get_alumni_profile(user):
    """Get the AlumniProfile for a user. Returns None if not registered."""
    try:
        return AlumniProfile.objects.get(user=user)
    except AlumniProfile.DoesNotExist:
        return None


def get_user_roles(user):
    """
    Get the placement roles for a user.
    Returns a dict with role and boolean flags.
    """
    is_chairman_val = is_chairman(user)
    is_officer_val = is_officer(user)
    is_student_val = is_student(user)
    is_alumni_val = is_alumni(user)

    role = 'other'
    if is_chairman_val:
        role = 'placement chairman'
    elif is_officer_val:
        role = 'placement officer'
    elif is_alumni_val:
        role = 'alumni'
    elif is_student_val:
        role = 'student'

    return {
        'role': role,
        'is_chairman': is_chairman_val,
        'is_officer': is_officer_val,
        'is_student': is_student_val,
        'is_alumni': is_alumni_val,
    }


# =============================================
# PLACEMENT SCHEDULE SERVICES
# =============================================

def check_invitation_date(placementstatus_qs):
    """Expire pending invitations past their deadline."""
    try:
        for ps in placementstatus_qs:
            if ps.invitation == 'PENDING':
                dt = ps.timestamp + datetime.timedelta(days=ps.no_of_days)
                if dt < datetime.datetime.now():
                    ps.invitation = 'IGNORE'
                    ps.save()
    except Exception as e:
        logger.error('Error checking invitation date: {}'.format(e))


def create_placement_schedule(company_name, placement_date, location, ctc, time_val,
                             placement_type, role_offered, description, schedule_at, attached_file):
    """
    Create a new placement schedule with associated notification and role.
    Returns the created PlacementSchedule instance.
    """
    # Ensure CompanyDetails exists
    CompanyDetails.objects.get_or_create(company_name=company_name)

    # Ensure Role exists
    role_obj, _ = Role.objects.get_or_create(role=role_offered)

    # Create notification
    notify = NotifyStudent.objects.create(
        placement_type=placement_type,
        company_name=company_name,
        description=description,
        ctc=ctc,
        timestamp=timezone.now(),
    )

    # Create schedule
    schedule = PlacementSchedule.objects.create(
        notify_id=notify,
        title=company_name,
        description=description,
        placement_date=placement_date,
        attached_file=attached_file,
        role=role_obj,
        location=location,
        time=time_val,
        schedule_at=schedule_at or timezone.now(),
    )

    return schedule


def update_student_invitation(student, schedule, invitation_action):
    """
    Update a student's invitation status for a placement schedule.
    Returns the updated PlacementStatus instance.
    """
    try:
        ps = PlacementStatus.objects.get(
            unique_id=student, notify_id=schedule.notify_id
        )
    except PlacementStatus.DoesNotExist:
        ps = PlacementStatus.objects.create(
            unique_id=student,
            notify_id=schedule.notify_id,
            invitation='PENDING',
        )

    if invitation_action in ('ACCEPTED', 'REJECTED'):
        ps.invitation = invitation_action
        ps.timestamp = timezone.now()
        ps.save()
        return ps

    return None


def delete_placement_schedule(schedule):
    """Delete a placement schedule and its cascaded notifications."""
    try:
        schedule.notify_id.delete()  # Cascades to PlacementStatus
        schedule.delete()
        return True
    except Exception as e:
        logger.error('Error deleting placement schedule: {}'.format(e))
        return False


# =============================================
# STUDENT RECORDS & CV SERVICES
# =============================================

def get_all_students_with_placement_info():
    """
    Get all students with their profile and placement information.
    Returns a list of dicts with student data.
    """
    students = Student.objects.select_related('id', 'id__user', 'id__department').all()

    data = []
    for student in students:
        try:
            sp = StudentPlacement.objects.get(unique_id=student)
            debar = sp.debar
            placed = sp.placed_type
        except StudentPlacement.DoesNotExist:
            debar = 'NOT DEBAR'
            placed = 'NOT PLACED'

        data.append({
            'id': student.id.id,
            'name': '{} {}'.format(student.id.user.first_name, student.id.user.last_name),
            'roll_no': student.id.id,
            'department': student.id.department.name if student.id.department else '',
            'programme': student.programme or '',
            'batch': student.batch,
            'cpi': student.cpi,
            'debar': debar,
            'placed': placed,
        })

    return data


def get_student_cv_data(target_user):
    """
    Get complete CV data for a student.
    Returns a dict with all student information and qualifications.
    """
    profile = get_object_or_404(ExtraInfo, user=target_user)
    student = get_object_or_404(Student, id=profile)

    skills = Has.objects.select_related('skill_id').filter(unique_id=student)
    education = Education.objects.filter(unique_id=student)
    references = Reference.objects.filter(unique_id=student)
    courses = Course.objects.filter(unique_id=student)
    experiences = Experience.objects.filter(unique_id=student)
    projects = Project.objects.filter(unique_id=student)
    achievements = Achievement.objects.filter(unique_id=student)
    extracurriculars = Extracurricular.objects.filter(unique_id=student)
    conferences = Conference.objects.filter(unique_id=student)
    publications = Publication.objects.filter(unique_id=student)
    patents = Patent.objects.filter(unique_id=student)

    return {
        'user': {
            'username': target_user.username,
            'first_name': target_user.first_name,
            'last_name': target_user.last_name,
            'email': target_user.email,
        },
        'profile': {
            'about_me': profile.about_me or '',
            'age': profile.age if hasattr(profile, 'age') else None,
            'address': profile.address or '',
            'phone_no': profile.phone_no or '',
            'department': profile.department.name if profile.department else '',
            'profile_picture': profile.profile_picture.url if profile.profile_picture else None,
        },
        'student': {
            'programme': student.programme or '',
            'batch': student.batch,
            'cpi': student.cpi,
            'specialization': student.specialization or '',
        },
        'skills': skills,
        'education': education,
        'references': references,
        'courses': courses,
        'experiences': experiences,
        'projects': projects,
        'achievements': achievements,
        'extracurriculars': extracurriculars,
        'conferences': conferences,
        'publications': publications,
        'patents': patents,
    }


def build_cv_context(target_user, achievementcheck, educationcheck, publicationcheck,
                     patentcheck, internshipcheck, projectcheck, coursecheck,
                     skillcheck, extracurricularcheck, conferencecheck, reference_list):
    """
    Build the context dict for CV generation.
    """
    profile = get_object_or_404(ExtraInfo, user=target_user)
    student = get_object_or_404(Student, id=profile)

    skills = Has.objects.select_related('skill_id').filter(unique_id=student)
    education = Education.objects.filter(unique_id=student)
    references = Reference.objects.filter(id__in=reference_list) if reference_list else Reference.objects.none()
    courses = Course.objects.filter(unique_id=student)
    experiences = Experience.objects.filter(unique_id=student)
    projects = Project.objects.filter(unique_id=student)
    achievements = Achievement.objects.filter(unique_id=student)
    extracurriculars = Extracurricular.objects.filter(unique_id=student)
    conferences = Conference.objects.filter(unique_id=student)
    publications = Publication.objects.filter(unique_id=student)
    patents = Patent.objects.filter(unique_id=student)

    student_info = get_object_or_404(Student, id=target_user.username)
    batch = student_info.batch
    now = datetime.datetime.now()
    roll = min(now.year - batch, 4) if now.year - batch <= 4 else 4

    referencecheck = '1' if references.exists() else '0'

    context = {
        'pagesize': 'A4',
        'user': target_user,
        'profile': profile,
        'projects': projects,
        'skills': skills,
        'educations': education,
        'references': references,
        'courses': courses,
        'experiences': experiences,
        'achievements': achievements,
        'extracurriculars': extracurriculars,
        'publications': publications,
        'patents': patents,
        'conferences': conferences,
        'roll': roll,
        'referencecheck': referencecheck,
        'achievementcheck': achievementcheck,
        'educationcheck': educationcheck,
        'publicationcheck': publicationcheck,
        'patentcheck': patentcheck,
        'internshipcheck': internshipcheck,
        'projectcheck': projectcheck,
        'coursecheck': coursecheck,
        'skillcheck': skillcheck,
        'extracurricularcheck': extracurricularcheck,
        'conferencecheck': conferencecheck,
        'today': datetime.date.today(),
    }

    return context


# =============================================
# INVITATION & APPLICATION STATUS SERVICES
# =============================================

def get_placement_status_list(notify_id=None, placement_type=None, company=None,
                              student_name=None, roll=None):
    """
    Get placement statuses with optional filters.
    Returns a queryset of PlacementStatus objects.
    """
    qs = PlacementStatus.objects.select_related(
        'unique_id', 'unique_id__id', 'unique_id__id__user', 'notify_id'
    )

    if notify_id:
        qs = qs.filter(notify_id=notify_id)
    if placement_type:
        qs = qs.filter(notify_id__placement_type=placement_type)
    if company:
        qs = qs.filter(notify_id__company_name__icontains=company)
    if student_name:
        qs = qs.filter(unique_id__id__user__first_name__icontains=student_name)
    if roll:
        qs = qs.filter(unique_id__id__id__icontains=roll)

    return qs.order_by('-timestamp')


def update_student_placement_status(ps, new_invitation=None, new_placed=None):
    """
    Update a PlacementStatus record.
    """
    if new_invitation:
        ps.invitation = new_invitation
    if new_placed:
        ps.placed = new_placed
    ps.timestamp = timezone.now()
    ps.save()
    return ps


# =============================================
# PLACEMENT STATISTICS & RECORDS SERVICES
# =============================================

def get_placement_records(placement_type=None, year=None, name=None):
    """
    Get placement records with optional filters.
    """
    qs = PlacementRecord.objects.all()
    if placement_type:
        qs = qs.filter(placement_type=placement_type)
    if year:
        qs = qs.filter(year=year)
    if name:
        qs = qs.filter(name__icontains=name)

    return qs.order_by('-year')


def get_placement_year_statistics():
    """
    Get department-wise placement counts by year.
    """
    years = PlacementRecord.objects.filter(
        ~Q(placement_type="HIGHER STUDIES")
    ).values('year').annotate(Count('year')).order_by('-year')

    year_stats = []
    for y in years:
        student_records = StudentRecord.objects.select_related(
            'unique_id__id__department', 'record_id'
        ).filter(record_id__year=y['year'])

        cse = student_records.filter(unique_id__id__department__name='CSE').count()
        ece = student_records.filter(unique_id__id__department__name='ECE').count()
        me = student_records.filter(unique_id__id__department__name='ME').count()
        total = cse + ece + me

        year_stats.append({
            'year': y['year'],
            'total': total,
            'cse': cse,
            'ece': ece,
            'me': me,
        })

    return year_stats


def get_student_records(placement_type=None, year=None, company=None):
    """
    Get student records with optional filters.
    """
    qs = StudentRecord.objects.select_related(
        'unique_id', 'unique_id__id', 'unique_id__id__user',
        'unique_id__id__department', 'record_id'
    ).all()

    if placement_type:
        qs = qs.filter(record_id__placement_type=placement_type)
    if year:
        qs = qs.filter(record_id__year=year)
    if company:
        qs = qs.filter(record_id__name__icontains=company)

    return qs


# =============================================
# DEBARRED STUDENTS SERVICES
# =============================================

def get_debarred_students():
    """Get all debarred students."""
    return StudentPlacement.objects.filter(debar='DEBAR').select_related(
        'unique_id', 'unique_id__id', 'unique_id__id__user'
    )


def debar_student(roll_no):
    """Mark a student as debarred."""
    try:
        extra_info = ExtraInfo.objects.get(id=roll_no)
        student = Student.objects.get(id=extra_info)
    except (ExtraInfo.DoesNotExist, Student.DoesNotExist):
        return None

    sp, created = StudentPlacement.objects.get_or_create(unique_id=student)
    sp.debar = 'DEBAR'
    sp.save()

    return sp


def undebar_student(roll_no):
    """Mark a student as not debarred."""
    try:
        extra_info = ExtraInfo.objects.get(id=roll_no)
        student = Student.objects.get(id=extra_info)
        sp = StudentPlacement.objects.get(unique_id=student)
        sp.debar = 'NOT DEBAR'
        sp.save()
        return sp
    except (ExtraInfo.DoesNotExist, Student.DoesNotExist, StudentPlacement.DoesNotExist):
        return None


def get_student_debar_status(roll_no):
    """Get debar status for a specific student."""
    try:
        extra_info = ExtraInfo.objects.get(id=roll_no)
        student = Student.objects.get(id=extra_info)
        sp = StudentPlacement.objects.get(unique_id=student)
        return {
            'roll_no': roll_no,
            'name': '{} {}'.format(extra_info.user.first_name, extra_info.user.last_name),
            'debar': sp.debar,
            'placed': sp.placed_type,
        }
    except StudentPlacement.DoesNotExist:
        extra_info = ExtraInfo.objects.get(id=roll_no)
        return {
            'roll_no': roll_no,
            'name': '{} {}'.format(extra_info.user.first_name, extra_info.user.last_name),
            'debar': 'NOT DEBAR',
            'placed': 'NOT PLACED',
        }
    except (ExtraInfo.DoesNotExist, Student.DoesNotExist):
        return None


# =============================================
# COMPANY & JOB POSTING SERVICES
# =============================================

def register_company(company_name):
    """Register or retrieve a company."""
    obj, created = CompanyDetails.objects.get_or_create(company_name=company_name)
    return obj, created


def get_all_companies():
    """Get all registered companies."""
    return CompanyDetails.objects.all()


# =============================================
# ELIGIBILITY & POLICY CHECKING SERVICES
# =============================================

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


# =============================================
# APPLICATION & OFFER SERVICES
# =============================================

def create_job_application(student, job_posting):
    """Create a new job application for a student."""
    application = JobApplication.objects.create(
        job_posting=job_posting,
        student=student,
        status='APPLIED',
    )
    return application


def update_job_application_status(application, new_status, remarks=''):
    """Update the status of a job application."""
    application.status = new_status
    if remarks:
        application.remarks = remarks
    application.save()
    return application


def process_offer_response(offer, action_type):
    """
    Process student's response to an offer (accept/reject).
    Returns success status and message.
    """
    if offer.status != 'PENDING':
        return False, 'Offer already {}'.format(offer.status)

    if action_type == 'accept':
        offer.status = 'ACCEPTED'
        offer.responded_at = timezone.now()
        offer.save()
        offer.application.status = 'OFFER_ACCEPTED'
        offer.application.save()

        # Update StudentPlacement
        student = offer.application.student
        sp, created = StudentPlacement.objects.get_or_create(unique_id=student)
        sp.placed_type = 'PLACED'
        sp.placement_date = datetime.date.today()
        sp.package = offer.ctc_offered
        sp.save()

        return True, 'accepted'

    elif action_type == 'reject':
        offer.status = 'REJECTED'
        offer.responded_at = timezone.now()
        offer.save()
        offer.application.status = 'OFFER_REJECTED'
        offer.application.save()
        return True, 'rejected'

    return False, 'Invalid action'


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


# =============================================
# PLACEMENT STATISTICS & REPORTING SERVICES
# =============================================

def get_placement_statistics(year=None):
    """
    Generate aggregated placement statistics.
    Returns a dict with placement data.
    """
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
    stats['company_wise'] = list(offers.values(
        'application__job_posting__company__name'
    ).annotate(
        count=Count('id'),
        avg_package=Avg('ctc_offered')
    ).order_by('-count'))

    # Branch-wise stats
    stats['branch_wise'] = list(offers.values(
        'application__student__id__department__name'
    ).annotate(
        count=Count('id'),
        avg_package=Avg('ctc_offered')
    ).order_by('-count'))

    # Programme-wise stats
    stats['programme_wise'] = list(offers.values(
        'application__student__programme'
    ).annotate(
        count=Count('id'),
        avg_package=Avg('ctc_offered')
    ).order_by('-count'))

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


def get_placement_report_data(year_filter=None, dept_filter=None, prog_filter=None, job_type_filter=None):
    """
    Generate comprehensive placement report data.
    """
    stats = get_placement_statistics(year=year_filter)

    offers_qs = JobOffer.objects.filter(status='ACCEPTED').select_related(
        'application__student__id__department',
        'application__student',
        'application__job_posting__company'
    )

    if year_filter:
        offers_qs = offers_qs.filter(application__job_posting__created_at__year=year_filter)
    if dept_filter:
        offers_qs = offers_qs.filter(application__student__id__department__name=dept_filter)
    if prog_filter:
        offers_qs = offers_qs.filter(application__student__programme=prog_filter)
    if job_type_filter:
        offers_qs = offers_qs.filter(application__job_posting__job_type=job_type_filter)

    companies_participated = Company.objects.filter(
        approval_status='APPROVED',
        job_postings__is_active=True
    ).distinct().count()

    total_students = Student.objects.count()
    placed_students = JobOffer.objects.filter(status='ACCEPTED').values(
        'application__student'
    ).distinct().count()

    placement_rate = (placed_students / total_students * 100) if total_students > 0 else 0

    return {
        'stats': stats,
        'offers': offers_qs,
        'companies_participated': companies_participated,
        'total_students': total_students,
        'placed_students': placed_students,
        'placement_rate': round(placement_rate, 2),
    }


# =============================================
# INTERVIEW MANAGEMENT SERVICES
# =============================================

def get_interview_schedules():
    """Get all interview schedules ordered by date."""
    return InterviewSchedule.objects.select_related(
        'job_posting', 'job_posting__company'
    ).all().order_by('-date')


def create_interview_schedule(job_posting, date, time, location, interview_type='TECHNICAL', created_by=None):
    """Create a new interview schedule."""
    schedule = InterviewSchedule.objects.create(
        job_posting=job_posting,
        date=date,
        time=time,
        location=location,
        interview_type=interview_type,
        created_by=created_by,
    )
    return schedule


def get_interview_details(interview_id):
    """Get interview schedule and associated panelists."""
    interview = get_object_or_404(InterviewSchedule, id=interview_id)
    panelists = InterviewPanel.objects.filter(
        interview=interview
    ).select_related('application', 'application__student', 'application__student__id__user')

    return {
        'interview': interview,
        'panelists': panelists,
    }


# =============================================
# POLICY MANAGEMENT SERVICES
# =============================================

def get_placement_policies():
    """Get all placement policies."""
    return PlacementPolicy.objects.all()


def create_or_update_policy(policy_data):
    """Create or update a placement policy."""
    # Deactivate existing policies first
    PlacementPolicy.objects.update(is_active=False)
    # Create new policy
    policy = PlacementPolicy.objects.create(is_active=True, **policy_data)
    return policy


def toggle_policy_active(policy_id):
    """Toggle active status of a policy."""
    try:
        policy = PlacementPolicy.objects.get(id=policy_id)
        if not policy.is_active:
            PlacementPolicy.objects.update(is_active=False)
            policy.is_active = True
        else:
            policy.is_active = False
        policy.save()
        return policy
    except PlacementPolicy.DoesNotExist:
        return None


# =============================================
# ROLE & FIELD MANAGEMENT SERVICES
# =============================================

def get_all_roles():
    """Get all job roles."""
    return Role.objects.all()


def create_or_get_role(role_name):
    """Create or retrieve a role by name."""
    role_obj, created = Role.objects.get_or_create(role=role_name)
    return role_obj, created


def get_form_field_config():
    """Get form field configuration (roles, companies, skills)."""
    return {
        'roles': Role.objects.all(),
        'companies': CompanyDetails.objects.all(),
        'skills': Skill.objects.all(),
    }


# =============================================
# ANNOUNCEMENT SERVICES
# =============================================

def get_active_announcements(limit=None):
    """Get active announcements, optionally limited."""
    qs = Announcement.objects.filter(is_active=True)
    if limit:
        qs = qs[:limit]
    return qs


# =============================================
# ALUMNI SERVICES
# =============================================

def approve_alumni(alumni_profile, approver):
    """
    Approve an alumni profile and grant the 'alumni' designation.
    Creates a HoldsDesignation entry so is_alumni() returns True.
    """
    alumni_profile.approval_status = 'APPROVED'
    alumni_profile.approved_by = approver
    alumni_profile.rejection_remarks = None
    alumni_profile.save()

    # Ensure 'alumni' designation exists
    designation, _ = Designation.objects.get_or_create(
        name='alumni',
        defaults={'full_name': 'Alumni', 'type': 'administrative'}
    )

    # Grant the designation to the alumni user
    HoldsDesignation.objects.get_or_create(
        user=alumni_profile.user,
        designation=designation,
        defaults={'working': alumni_profile.user}
    )

    return alumni_profile


def reject_alumni(alumni_profile, remarks=''):
    """Reject an alumni registration."""
    alumni_profile.approval_status = 'REJECTED'
    alumni_profile.rejection_remarks = remarks
    alumni_profile.save()
    return alumni_profile

