"""
Notification helpers for the Placement Cell module.

These wrappers send notifications using the existing
``notification.views.placement_cell_notif`` helper, which in turn dispatches
the ``notify.send`` signal from ``django-notifications-hq``.

Each wrapper is defensive: any failure during notification dispatch is logged
but never bubbled up, so a notification problem can never break the underlying
business action (e.g. creating a posting / updating an application).
"""
import logging

from django.contrib.auth.models import User
from django.db.models import Q

from applications.globals.models import HoldsDesignation
from applications.academic_information.models import Student

logger = logging.getLogger('django.server')


def _safe_notify(sender, recipient, notif_type):
    """Best-effort wrapper around placement_cell_notif."""
    if recipient is None or sender is None:
        return
    try:
        # Local import to avoid circular imports at module load time.
        from notification.views import placement_cell_notif
        placement_cell_notif(sender, recipient, notif_type)
    except Exception as exc:  # pragma: no cover - notifications are best-effort
        logger.warning(
            "placement notification failed (type=%s, recipient=%s): %s",
            notif_type, getattr(recipient, 'username', recipient), exc,
        )


def _student_user(student):
    """Resolve the ``User`` object for a Student instance, or None."""
    try:
        return student.id.user
    except Exception:
        return None


def get_placement_officer_users():
    """Return the set of User objects holding the placement officer/chairman role."""
    return User.objects.filter(
        Q(current_designation__designation__name="placement officer") |
        Q(current_designation__designation__name="placement chairman")
    ).distinct()


def _is_student_eligible_for_posting(student, job_posting):
    """
    Lightweight eligibility check matching ``services.check_eligibility``
    semantics for the fields that gate notifications and visibility:
    placement policy (already-placed gate), minimum CPI, programme,
    branch / specialization, and batch. Returns True/False.
    """
    if job_posting is None:
        return True

    # Already-placed gate (respects TPO apply_override).
    try:
        from applications.placement_cell.services import check_placement_policy
        can_apply, _ = check_placement_policy(student, job_posting)
        if not can_apply:
            return False
    except Exception:
        # Never fail visibility/notification on a service error.
        pass

    # Minimum CPI
    if job_posting.min_cpi and (student.cpi or 0) < job_posting.min_cpi:
        return False

    # Programme
    progs = job_posting.eligible_programmes
    if progs:
        eligible = [p.strip().upper() for p in progs.split(',') if p.strip()]
        if eligible:
            student_prog = (student.programme or '').upper()
            if student_prog and student_prog not in eligible:
                return False

    # Branch / specialization (compares against globals.DepartmentInfo.name).
    branches = job_posting.eligible_branches
    if branches:
        eligible_branches = [
            b.strip().upper() for b in branches.split(',') if b.strip()
        ]
        if eligible_branches:
            try:
                dept = (
                    student.id.department.name.upper()
                    if student.id.department else ''
                )
            except Exception:
                dept = ''
            spec = (student.specialization or '').upper()
            if dept not in eligible_branches and spec not in eligible_branches:
                return False

    # Batch
    eligible_batches = getattr(job_posting, 'eligible_batches', None) or []
    try:
        years = [int(b) for b in eligible_batches if str(b).strip()]
    except (TypeError, ValueError):
        years = []
    if years and student.batch not in years:
        return False

    return True


def get_eligible_student_users(job_posting):
    """
    Return User objects of students that should be notified about a new job
    posting. When a posting is provided, students are filtered by programme,
    branch/specialization, and batch; without a posting all active students
    are returned (used by generic broadcasts like announcements).
    """
    students = Student.objects.select_related(
        'id', 'id__user', 'id__department'
    ).all()
    user_ids = []
    for student in students:
        user = _student_user(student)
        if user is None:
            continue
        if job_posting is not None and not _is_student_eligible_for_posting(
            student, job_posting
        ):
            continue
        user_ids.append(user.id)
    return User.objects.filter(id__in=user_ids, is_active=True)


# ---------------------------------------------------------------------------
# Public notification helpers (called from views/services)
# ---------------------------------------------------------------------------

def notify_new_job_posting(sender, job_posting):
    """Notify all students that a new job opportunity has been posted."""
    if job_posting is None or not job_posting.is_active:
        return
    for user in get_eligible_student_users(job_posting):
        _safe_notify(sender, user, 'new_job_posting')


def notify_new_application(sender, application):
    """Notify placement officers that a new application has been submitted."""
    if application is None:
        return
    for officer in get_placement_officer_users():
        _safe_notify(sender, officer, 'new_application')


def notify_application_status_change(sender, application, new_status):
    """
    Notify the student when their application status changes.

    Maps known statuses to specific notification types so that the verb shown
    to the student matches the action.
    """
    if application is None:
        return
    user = _student_user(application.student)
    if user is None:
        return

    status_to_type = {
        'SHORTLISTED': 'shortlisted',
        'INTERVIEW_SCHEDULED': 'interview_scheduled',
        'OFFER_EXTENDED': 'offer_extended',
    }
    notif_type = status_to_type.get(new_status, 'application_status_update')
    _safe_notify(sender, user, notif_type)


def notify_offer_extended(sender, offer):
    """Notify the student that an offer has been extended to them."""
    if offer is None:
        return
    user = _student_user(offer.application.student)
    if user is None:
        return
    _safe_notify(sender, user, 'offer_extended')


def notify_offer_accepted(sender, offer):
    """Notify placement officers that a student has accepted an offer."""
    if offer is None:
        return
    for officer in get_placement_officer_users():
        _safe_notify(sender, officer, 'offer_accepted')


def notify_announcement(sender, announcement):
    """Notify students about a new placement announcement."""
    if announcement is None or not getattr(announcement, 'is_active', True):
        return
    for user in get_eligible_student_users(None):
        _safe_notify(sender, user, 'announcement')
