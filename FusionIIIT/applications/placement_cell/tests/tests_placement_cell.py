"""
Tests for the placement_cell module.

These tests cover the service layer in `applications/placement_cell/services.py`
and key model invariants in `applications/placement_cell/models.py`. The
suite is structured into focused TestCase classes per area so failures point
clearly to the affected feature:

    - PlacementCellEligibilityTests
    - PlacementCellPolicyAndClaimTests
    - PlacementCellApplicationFlowTests
    - PlacementCellOfferFlowTests
    - PlacementCellInterviewTests
    - PlacementCellStatisticsTests
    - PlacementCellRoleHelperTests
    - PlacementCellAnnouncementTests
    - PlacementCellAlumniTests
    - PlacementCellDebarTests
    - PlacementCellModelPropertyTests
"""

from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from applications.academic_information.models import Student
from applications.globals.models import (
	Designation,
	DepartmentInfo,
	ExtraInfo,
	HoldsDesignation,
)
from applications.placement_cell.models import (
	AlumniProfile,
	Announcement,
	Company,
	CompanyDetails,
	Has,
	InterviewSchedule,
	JobApplication,
	JobOffer,
	JobPosting,
	PlacementClaim,
	PlacementPolicy,
	PlacementProfile,
	Skill,
	StudentPlacement,
)
from applications.placement_cell.services import (
	MAX_RESCHEDULES,
	approve_alumni,
	check_duplicate_application,
	check_eligibility,
	check_interview_conflicts,
	check_placement_policy,
	create_job_application,
	debar_student,
	expire_pending_offers,
	get_active_announcements,
	get_placement_statistics,
	get_student_application_summary,
	get_student_debar_status,
	get_user_roles,
	has_verified_placement,
	is_alumni,
	is_chairman,
	is_officer,
	is_student,
	is_tpo_or_chairman,
	process_offer_response,
	register_company,
	reject_alumni,
	undebar_student,
	update_job_application_status,
	validate_reschedule,
)


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------


def _make_student(roll, username, department, *, cpi=8.5, batch=2022,
                  programme='B.Tech', specialization=''):
	"""Create a User + ExtraInfo + Student triplet and return the Student."""
	user = User.objects.create_user(username=username, password='pwd')
	extra = ExtraInfo.objects.create(
		id=roll,
		user=user,
		user_type='student',
		department=department,
	)
	student = Student.objects.create(
		id=extra,
		programme=programme,
		batch=batch,
		cpi=cpi,
		category='GEN',
		specialization=specialization,
	)
	return student


def _make_active_job(company, **overrides):
	defaults = dict(
		company=company,
		title='SDE',
		description='Software role',
		job_type='PLACEMENT',
		ctc=12.0,
		min_cpi=7.0,
		eligible_programmes='B.Tech',
		eligible_branches='CSE,ECE',
		application_deadline=timezone.now() + timedelta(days=7),
	)
	defaults.update(overrides)
	return JobPosting.objects.create(**defaults)


class PlacementCellBaseTestCase(TestCase):
	"""Base TestCase that provisions students, a company and two job postings."""

	def setUp(self):
		self.cse_department = DepartmentInfo.objects.create(name='CSE')
		self.me_department = DepartmentInfo.objects.create(name='ME')

		self.eligible_student = _make_student(
			'TEST2022CS01', 'eligible_student', self.cse_department, cpi=8.5,
		)
		self.ineligible_student = _make_student(
			'TEST2022ME01', 'ineligible_student', self.me_department,
			cpi=5.5,
		)

		self.company = Company.objects.create(
			name='TechCorp',
			contact_email='hr@techcorp.com',
		)

		self.active_job = _make_active_job(self.company)
		self.expired_job = _make_active_job(
			self.company,
			title='Old SDE',
			description='Expired role',
			ctc=10.0,
			min_cpi=6.0,
			eligible_branches='CSE',
			application_deadline=timezone.now() - timedelta(days=1),
		)

		self.policy = PlacementPolicy.objects.create(
			name='Default Policy',
			is_active=True,
			max_offers_allowed=1,
			allow_dream_company=False,
			dream_ctc_threshold=15,
		)


# ---------------------------------------------------------------------------
# Eligibility checks
# ---------------------------------------------------------------------------


class PlacementCellEligibilityTests(PlacementCellBaseTestCase):
	def test_register_company_creates_then_reuses_record(self):
		first, created = register_company('NewCorp')
		self.assertTrue(created)
		self.assertEqual(first.company_name, 'NewCorp')

		second, created_again = register_company('NewCorp')
		self.assertFalse(created_again)
		self.assertEqual(first.id, second.id)

	def test_register_company_returns_company_details_instance(self):
		obj, _created = register_company('AnotherCorp')
		self.assertIsInstance(obj, CompanyDetails)

	def test_check_eligibility_accepts_valid_student(self):
		eligible, reasons = check_eligibility(self.eligible_student, self.active_job)
		self.assertTrue(eligible)
		self.assertEqual(reasons, [])

	def test_check_eligibility_rejects_low_cpi(self):
		eligible, reasons = check_eligibility(self.ineligible_student, self.active_job)
		self.assertFalse(eligible)
		self.assertTrue(any('Minimum CPI required' in r for r in reasons))

	def test_check_eligibility_rejects_programme_mismatch(self):
		self.active_job.eligible_programmes = 'M.Tech'
		self.active_job.save()
		eligible, reasons = check_eligibility(self.eligible_student, self.active_job)
		self.assertFalse(eligible)
		self.assertTrue(any('programme' in r.lower() for r in reasons))

	def test_check_eligibility_rejects_branch_mismatch(self):
		self.active_job.eligible_branches = 'ECE,EE'
		self.active_job.save()
		eligible, reasons = check_eligibility(self.eligible_student, self.active_job)
		self.assertFalse(eligible)
		self.assertTrue(any('branch/department' in r.lower() for r in reasons))

	def test_check_eligibility_rejects_expired_job(self):
		eligible, reasons = check_eligibility(self.eligible_student, self.expired_job)
		self.assertFalse(eligible)
		self.assertTrue(any('deadline' in r.lower() for r in reasons))

	def test_check_eligibility_rejects_inactive_job(self):
		self.active_job.is_active = False
		self.active_job.save()
		eligible, reasons = check_eligibility(self.eligible_student, self.active_job)
		self.assertFalse(eligible)
		self.assertTrue(any('no longer active' in r.lower() for r in reasons))

	def test_check_eligibility_rejects_debarred_student(self):
		StudentPlacement.objects.create(unique_id=self.eligible_student, debar='DEBAR')
		eligible, reasons = check_eligibility(self.eligible_student, self.active_job)
		self.assertFalse(eligible)
		self.assertTrue(any('debarred' in r.lower() for r in reasons))

	def test_check_eligibility_rejects_when_required_skills_missing(self):
		required = Skill.objects.create(skill='Python')
		self.active_job.required_skills.add(required)
		eligible, reasons = check_eligibility(self.eligible_student, self.active_job)
		self.assertFalse(eligible)
		self.assertTrue(any('missing required skills' in r.lower() for r in reasons))

	def test_check_eligibility_accepts_when_required_skills_present(self):
		required = Skill.objects.create(skill='Django')
		self.active_job.required_skills.add(required)
		Has.objects.create(skill_id=required, unique_id=self.eligible_student)
		eligible, reasons = check_eligibility(self.eligible_student, self.active_job)
		self.assertTrue(eligible)
		self.assertEqual(reasons, [])

	def test_check_eligibility_legacy_batch_range_rejects_out_of_range(self):
		self.active_job.eligible_batch_from = 2023
		self.active_job.eligible_batch_to = 2025
		self.active_job.save()
		eligible, reasons = check_eligibility(self.eligible_student, self.active_job)
		self.assertFalse(eligible)
		self.assertTrue(any('batch' in r.lower() for r in reasons))

	def test_check_eligibility_legacy_batch_range_accepts_boundary(self):
		self.active_job.eligible_batch_from = 2022
		self.active_job.eligible_batch_to = 2022
		self.active_job.save()
		eligible, reasons = check_eligibility(self.eligible_student, self.active_job)
		self.assertTrue(eligible)
		self.assertEqual(reasons, [])

	def test_check_eligibility_eligible_batches_jsonfield_accepts_match(self):
		self.active_job.eligible_batches = [2021, 2022, 2023]
		self.active_job.save()
		eligible, reasons = check_eligibility(self.eligible_student, self.active_job)
		self.assertTrue(eligible)
		self.assertEqual(reasons, [])

	def test_check_eligibility_eligible_batches_jsonfield_rejects_no_match(self):
		self.active_job.eligible_batches = [2024, 2025]
		self.active_job.save()
		eligible, reasons = check_eligibility(self.eligible_student, self.active_job)
		self.assertFalse(eligible)
		self.assertTrue(any('batch' in r.lower() for r in reasons))

	def test_check_eligibility_eligible_batches_takes_precedence_over_legacy_range(self):
		# Legacy range would reject (only 2024) but JSON list explicitly allows.
		self.active_job.eligible_batch_from = 2024
		self.active_job.eligible_batch_to = 2024
		self.active_job.eligible_batches = [2022]
		self.active_job.save()
		eligible, reasons = check_eligibility(self.eligible_student, self.active_job)
		self.assertTrue(eligible)
		self.assertEqual(reasons, [])

	def test_check_eligibility_branch_case_insensitive(self):
		self.active_job.eligible_branches = 'cse,me'
		self.active_job.save()
		eligible, reasons = check_eligibility(self.eligible_student, self.active_job)
		self.assertTrue(eligible)

	def test_check_eligibility_programme_case_insensitive(self):
		self.active_job.eligible_programmes = 'b.tech'
		self.active_job.save()
		eligible, reasons = check_eligibility(self.eligible_student, self.active_job)
		self.assertTrue(eligible)

	def test_check_eligibility_no_branch_restriction(self):
		self.active_job.eligible_branches = ''
		self.active_job.save()
		eligible, _ = check_eligibility(self.eligible_student, self.active_job)
		self.assertTrue(eligible)

	def test_check_eligibility_no_programme_restriction(self):
		self.active_job.eligible_programmes = None
		self.active_job.save()
		eligible, _ = check_eligibility(self.eligible_student, self.active_job)
		self.assertTrue(eligible)

	def test_check_eligibility_exact_min_cpi_is_eligible(self):
		self.eligible_student.cpi = self.active_job.min_cpi
		self.eligible_student.save()
		eligible, reasons = check_eligibility(self.eligible_student, self.active_job)
		self.assertTrue(eligible)
		self.assertEqual(reasons, [])

	def test_check_eligibility_specialization_overrides_branch(self):
		"""M.Tech students whose specialization matches eligible_branches should pass."""
		mtech_dept = DepartmentInfo.objects.create(name='Other')
		mtech_student = _make_student(
			'TEST2021MT01', 'mtech_student', mtech_dept,
			cpi=8.0, programme='M.Tech', specialization='CSE',
		)
		self.active_job.eligible_programmes = 'M.Tech'
		self.active_job.eligible_branches = 'CSE'
		self.active_job.save()
		eligible, reasons = check_eligibility(mtech_student, self.active_job)
		self.assertTrue(eligible, msg=reasons)


# ---------------------------------------------------------------------------
# Policy + PlacementClaim gating
# ---------------------------------------------------------------------------


class PlacementCellPolicyAndClaimTests(PlacementCellBaseTestCase):
	def test_check_placement_policy_allows_when_no_active_policy(self):
		self.policy.is_active = False
		self.policy.save()
		can_apply, reason = check_placement_policy(self.eligible_student, self.active_job)
		self.assertTrue(can_apply)
		self.assertEqual(reason, '')

	def test_check_placement_policy_blocks_after_max_accepted_offers(self):
		application = JobApplication.objects.create(
			job_posting=self.active_job, student=self.eligible_student,
		)
		JobOffer.objects.create(
			application=application,
			ctc_offered=11,
			response_deadline=timezone.now() + timedelta(days=1),
			status='ACCEPTED',
		)
		can_apply, reason = check_placement_policy(self.eligible_student, self.active_job)
		self.assertFalse(can_apply)
		self.assertIn('Maximum allowed', reason)

	def test_check_placement_policy_allows_dream_company_above_threshold(self):
		self.policy.allow_dream_company = True
		self.policy.dream_ctc_threshold = 10
		self.policy.save()
		application = JobApplication.objects.create(
			job_posting=self.active_job, student=self.eligible_student,
		)
		JobOffer.objects.create(
			application=application,
			ctc_offered=11,
			response_deadline=timezone.now() + timedelta(days=1),
			status='ACCEPTED',
		)
		dream_job = _make_active_job(
			self.company,
			title='Dream Role', ctc=20.0,
		)
		can_apply, reason = check_placement_policy(self.eligible_student, dream_job)
		self.assertTrue(can_apply)
		self.assertEqual(reason, '')

	def test_check_placement_policy_dream_ctc_exact_threshold(self):
		self.policy.allow_dream_company = True
		self.policy.dream_ctc_threshold = 15.0
		self.policy.save()
		application = JobApplication.objects.create(
			job_posting=self.active_job, student=self.eligible_student,
		)
		JobOffer.objects.create(
			application=application,
			ctc_offered=11,
			response_deadline=timezone.now() + timedelta(days=1),
			status='ACCEPTED',
		)
		dream_job = _make_active_job(self.company, title='Dream Role', ctc=15.0)
		can_apply, reason = check_placement_policy(self.eligible_student, dream_job)
		self.assertTrue(can_apply)
		self.assertEqual(reason, '')

	def test_check_placement_policy_max_offers_two_allows_one_more(self):
		self.policy.max_offers_allowed = 2
		self.policy.save()
		app = JobApplication.objects.create(
			job_posting=self.active_job, student=self.eligible_student,
		)
		JobOffer.objects.create(
			application=app,
			ctc_offered=11,
			response_deadline=timezone.now() + timedelta(days=1),
			status='ACCEPTED',
		)
		can_apply, _ = check_placement_policy(self.eligible_student, self.expired_job)
		self.assertTrue(can_apply)

	def test_verified_placement_claim_blocks_new_application_of_same_kind(self):
		PlacementClaim.objects.create(
			student=self.eligible_student,
			kind=PlacementClaim.KIND_PLACEMENT,
			company_name='OffCampusCorp',
			status=PlacementClaim.STATUS_VERIFIED,
			source=PlacementClaim.SOURCE_OFFCAMPUS,
		)
		can_apply, reason = check_placement_policy(self.eligible_student, self.active_job)
		self.assertFalse(can_apply)
		self.assertIn('verified placement', reason.lower())

	def test_verified_internship_claim_does_not_block_placement_application(self):
		PlacementClaim.objects.create(
			student=self.eligible_student,
			kind=PlacementClaim.KIND_INTERNSHIP,
			company_name='InternCorp',
			status=PlacementClaim.STATUS_VERIFIED,
		)
		can_apply, _ = check_placement_policy(self.eligible_student, self.active_job)
		self.assertTrue(can_apply)

	def test_apply_override_bypasses_verified_claim_block(self):
		PlacementClaim.objects.create(
			student=self.eligible_student,
			kind=PlacementClaim.KIND_PLACEMENT,
			company_name='OffCampusCorp',
			status=PlacementClaim.STATUS_VERIFIED,
		)
		PlacementProfile.objects.create(
			student=self.eligible_student, apply_override=True,
		)
		can_apply, reason = check_placement_policy(self.eligible_student, self.active_job)
		self.assertTrue(can_apply)
		self.assertEqual(reason, '')

	def test_pending_placement_claim_does_not_block(self):
		PlacementClaim.objects.create(
			student=self.eligible_student,
			kind=PlacementClaim.KIND_PLACEMENT,
			company_name='OffCampusCorp',
			status=PlacementClaim.STATUS_PENDING,
		)
		can_apply, _ = check_placement_policy(self.eligible_student, self.active_job)
		self.assertTrue(can_apply)

	def test_has_verified_placement_helper(self):
		self.assertFalse(
			has_verified_placement(self.eligible_student, PlacementClaim.KIND_PLACEMENT)
		)
		PlacementClaim.objects.create(
			student=self.eligible_student,
			kind=PlacementClaim.KIND_PLACEMENT,
			company_name='C',
			status=PlacementClaim.STATUS_VERIFIED,
		)
		self.assertTrue(
			has_verified_placement(self.eligible_student, PlacementClaim.KIND_PLACEMENT)
		)
		self.assertFalse(
			has_verified_placement(self.eligible_student, PlacementClaim.KIND_INTERNSHIP)
		)


# ---------------------------------------------------------------------------
# Application creation, dedup, status update
# ---------------------------------------------------------------------------


class PlacementCellApplicationFlowTests(PlacementCellBaseTestCase):
	def test_create_job_application_creates_applied_record(self):
		application = create_job_application(self.eligible_student, self.active_job)
		self.assertIsNotNone(application.id)
		self.assertEqual(application.student, self.eligible_student)
		self.assertEqual(application.job_posting, self.active_job)
		self.assertEqual(application.status, 'APPLIED')

	def test_check_duplicate_application_false_before_apply(self):
		self.assertFalse(
			check_duplicate_application(self.eligible_student, self.active_job)
		)

	def test_check_duplicate_application_true_after_apply(self):
		create_job_application(self.eligible_student, self.active_job)
		self.assertTrue(
			check_duplicate_application(self.eligible_student, self.active_job)
		)

	def test_check_duplicate_application_scoped_per_job(self):
		create_job_application(self.eligible_student, self.active_job)
		self.assertFalse(
			check_duplicate_application(self.eligible_student, self.expired_job)
		)

	def test_update_job_application_status_with_remarks(self):
		app = create_job_application(self.eligible_student, self.active_job)
		updated = update_job_application_status(app, 'SHORTLISTED', remarks='Looks good')
		self.assertEqual(updated.status, 'SHORTLISTED')
		self.assertEqual(updated.remarks, 'Looks good')

	def test_update_job_application_status_without_remarks(self):
		app = create_job_application(self.eligible_student, self.active_job)
		updated = update_job_application_status(app, 'INTERVIEW_SCHEDULED')
		self.assertEqual(updated.status, 'INTERVIEW_SCHEDULED')

	def test_update_job_application_does_not_overwrite_remarks_when_empty(self):
		app = create_job_application(self.eligible_student, self.active_job)
		update_job_application_status(app, 'SHORTLISTED', remarks='Initial note')
		update_job_application_status(app, 'INTERVIEW_SCHEDULED')
		app.refresh_from_db()
		self.assertEqual(app.remarks, 'Initial note')

	def test_get_student_application_summary_counts(self):
		app1 = create_job_application(self.eligible_student, self.active_job)
		update_job_application_status(app1, 'SELECTED' if False else 'OFFER_EXTENDED')
		app2 = JobApplication.objects.create(
			job_posting=self.expired_job,
			student=self.eligible_student,
			status='INTERVIEW_SCHEDULED',
		)
		update_job_application_status(app2, 'INTERVIEW_SCHEDULED')

		summary = get_student_application_summary(self.eligible_student)
		self.assertEqual(summary['total'], 2)
		self.assertEqual(summary['offer_extended'], 1)
		self.assertEqual(summary['interview_scheduled'], 1)

	def test_get_student_application_summary_empty(self):
		summary = get_student_application_summary(self.eligible_student)
		self.assertEqual(summary['total'], 0)
		self.assertEqual(summary['applied'], 0)
		self.assertEqual(summary['offer_extended'], 0)


# ---------------------------------------------------------------------------
# Job offer accept / reject / expire flow
# ---------------------------------------------------------------------------


class PlacementCellOfferFlowTests(PlacementCellBaseTestCase):
	def _make_offer(self, student=None, job=None, *, ctc=13, status='PENDING',
	                deadline_delta=timedelta(days=1)):
		student = student or self.eligible_student
		job = job or self.active_job
		application = create_job_application(student, job)
		return JobOffer.objects.create(
			application=application,
			ctc_offered=ctc,
			response_deadline=timezone.now() + deadline_delta,
			status=status,
		)

	def test_accept_offer_sets_offer_application_and_student_state(self):
		offer = self._make_offer()
		ok, msg = process_offer_response(offer, 'accept')
		offer.refresh_from_db()
		offer.application.refresh_from_db()

		self.assertTrue(ok)
		self.assertEqual(msg, 'accepted')
		self.assertEqual(offer.status, 'ACCEPTED')
		self.assertIsNotNone(offer.responded_at)
		self.assertEqual(offer.application.status, 'OFFER_ACCEPTED')
		self.assertTrue(StudentPlacement.objects.filter(
			unique_id=self.eligible_student, placed_type='PLACED'
		).exists())

	def test_accept_offer_creates_verified_placement_claim(self):
		offer = self._make_offer()
		process_offer_response(offer, 'accept')
		claim = PlacementClaim.objects.get(related_offer=offer)
		self.assertEqual(claim.status, PlacementClaim.STATUS_VERIFIED)
		self.assertEqual(claim.kind, PlacementClaim.KIND_PLACEMENT)
		self.assertEqual(claim.source, PlacementClaim.SOURCE_ONCAMPUS)
		self.assertEqual(claim.student, self.eligible_student)

	def test_accept_internship_offer_creates_internship_claim(self):
		internship_job = _make_active_job(
			self.company, title='SDE Intern', job_type='INTERNSHIP',
		)
		offer = self._make_offer(job=internship_job)
		process_offer_response(offer, 'accept')
		claim = PlacementClaim.objects.get(related_offer=offer)
		self.assertEqual(claim.kind, PlacementClaim.KIND_INTERNSHIP)

	def test_reject_offer_updates_status(self):
		offer = self._make_offer()
		ok, msg = process_offer_response(offer, 'reject')
		offer.refresh_from_db()
		offer.application.refresh_from_db()

		self.assertTrue(ok)
		self.assertEqual(msg, 'rejected')
		self.assertEqual(offer.status, 'REJECTED')
		self.assertEqual(offer.application.status, 'OFFER_REJECTED')

	def test_cannot_process_already_processed_offer(self):
		offer = self._make_offer(status='ACCEPTED')
		ok, msg = process_offer_response(offer, 'reject')
		self.assertFalse(ok)
		self.assertIn('already', msg)

	def test_invalid_action_returns_error(self):
		offer = self._make_offer()
		ok, msg = process_offer_response(offer, 'maybe')
		self.assertFalse(ok)
		self.assertIn('Invalid', msg)

	def test_accept_after_deadline_marks_expired(self):
		offer = self._make_offer(deadline_delta=timedelta(days=-1))
		ok, msg = process_offer_response(offer, 'accept')
		offer.refresh_from_db()
		self.assertFalse(ok)
		self.assertEqual(offer.status, 'EXPIRED')
		self.assertIn('deadline', msg.lower())

	def test_cannot_accept_second_offer_when_one_already_accepted(self):
		first = self._make_offer()
		process_offer_response(first, 'accept')

		# Second offer for a different posting
		second_job = _make_active_job(self.company, title='Other Role')
		application2 = JobApplication.objects.create(
			job_posting=second_job, student=self.eligible_student,
		)
		second = JobOffer.objects.create(
			application=application2,
			ctc_offered=14,
			response_deadline=timezone.now() + timedelta(days=1),
		)
		ok, msg = process_offer_response(second, 'accept')
		self.assertFalse(ok)
		self.assertIn('only one', msg.lower())

	def test_expire_pending_offers_only_overdue(self):
		expired = self._make_offer(deadline_delta=timedelta(hours=-1))
		future_job = _make_active_job(self.company, title='Future')
		future_app = JobApplication.objects.create(
			job_posting=future_job, student=self.ineligible_student,
		)
		active = JobOffer.objects.create(
			application=future_app,
			ctc_offered=9,
			response_deadline=timezone.now() + timedelta(hours=2),
		)
		count = expire_pending_offers()
		expired.refresh_from_db()
		active.refresh_from_db()
		self.assertEqual(count, 1)
		self.assertEqual(expired.status, 'EXPIRED')
		self.assertEqual(active.status, 'PENDING')

	def test_expire_pending_offers_returns_zero_when_none(self):
		self.assertEqual(expire_pending_offers(), 0)

	def test_expire_pending_offers_does_not_affect_already_accepted(self):
		offer = self._make_offer(deadline_delta=timedelta(hours=-1), status='ACCEPTED')
		expire_pending_offers()
		offer.refresh_from_db()
		self.assertEqual(offer.status, 'ACCEPTED')


# ---------------------------------------------------------------------------
# Interview schedule / conflicts / reschedule
# ---------------------------------------------------------------------------


class PlacementCellInterviewTests(PlacementCellBaseTestCase):
	def _make_interview(self, **overrides):
		defaults = dict(
			job_posting=self.active_job,
			date=timezone.now().date() + timedelta(days=1),
			time_slot=timezone.datetime.strptime('10:00', '%H:%M').time(),
			duration_minutes=60,
			mode='OFFLINE',
			venue_or_link='LHC 101',
		)
		defaults.update(overrides)
		return InterviewSchedule.objects.create(**defaults)

	def test_interview_schedule_auto_computes_end_time(self):
		interview = self._make_interview()
		self.assertIsNotNone(interview.end_time)
		# 10:00 + 60 minutes = 11:00
		self.assertEqual(interview.end_time.hour, 11)
		self.assertEqual(interview.end_time.minute, 0)

	def test_check_interview_conflicts_returns_empty_when_no_overlap(self):
		interview = self._make_interview()
		conflicts = check_interview_conflicts(
			interview_date=interview.date,
			time_slot=timezone.datetime.strptime('12:00', '%H:%M').time(),
			end_time=timezone.datetime.strptime('13:00', '%H:%M').time(),
			venue_or_link='LHC 101',
		)
		self.assertEqual(conflicts.count(), 0)

	def test_check_interview_conflicts_detects_same_venue_overlap(self):
		interview = self._make_interview()
		conflicts = check_interview_conflicts(
			interview_date=interview.date,
			time_slot=timezone.datetime.strptime('10:30', '%H:%M').time(),
			end_time=timezone.datetime.strptime('11:30', '%H:%M').time(),
			venue_or_link='LHC 101',
		)
		self.assertEqual(conflicts.count(), 1)
		self.assertEqual(conflicts.first().pk, interview.pk)

	def test_check_interview_conflicts_ignores_different_venue(self):
		interview = self._make_interview()
		conflicts = check_interview_conflicts(
			interview_date=interview.date,
			time_slot=timezone.datetime.strptime('10:30', '%H:%M').time(),
			end_time=timezone.datetime.strptime('11:30', '%H:%M').time(),
			venue_or_link='LHC 102',
		)
		self.assertEqual(conflicts.count(), 0)

	def test_check_interview_conflicts_venue_match_is_case_insensitive(self):
		self._make_interview(venue_or_link='LHC 101')
		conflicts = check_interview_conflicts(
			interview_date=timezone.now().date() + timedelta(days=1),
			time_slot=timezone.datetime.strptime('10:30', '%H:%M').time(),
			end_time=timezone.datetime.strptime('11:30', '%H:%M').time(),
			venue_or_link='lhc 101',
		)
		self.assertEqual(conflicts.count(), 1)

	def test_check_interview_conflicts_excludes_self_when_exclude_id_passed(self):
		interview = self._make_interview()
		conflicts = check_interview_conflicts(
			interview_date=interview.date,
			time_slot=interview.time_slot,
			end_time=interview.end_time,
			venue_or_link=interview.venue_or_link,
			exclude_id=interview.id,
		)
		self.assertEqual(conflicts.count(), 0)

	def test_check_interview_conflicts_returns_empty_when_no_venue(self):
		conflicts = check_interview_conflicts(
			interview_date=timezone.now().date(),
			time_slot=timezone.datetime.strptime('10:00', '%H:%M').time(),
			end_time=timezone.datetime.strptime('11:00', '%H:%M').time(),
			venue_or_link='',
		)
		self.assertEqual(conflicts.count(), 0)

	def test_validate_reschedule_allows_when_under_limit(self):
		interview = self._make_interview()
		ok, msg = validate_reschedule(interview)
		self.assertTrue(ok)
		self.assertIn('0/{}'.format(MAX_RESCHEDULES), msg)

	def test_validate_reschedule_blocks_when_limit_reached(self):
		interview = self._make_interview()
		interview.reschedule_count = MAX_RESCHEDULES
		interview.save()
		ok, msg = validate_reschedule(interview)
		self.assertFalse(ok)
		self.assertIn('Maximum', msg)


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


class PlacementCellStatisticsTests(PlacementCellBaseTestCase):
	def _accept_offer(self, student, job, ctc):
		application = create_job_application(student, job)
		return JobOffer.objects.create(
			application=application,
			ctc_offered=ctc,
			response_deadline=timezone.now() + timedelta(days=1),
			status='ACCEPTED',
		)

	def test_get_placement_statistics_returns_aggregates(self):
		self._accept_offer(self.eligible_student, self.active_job, 12)
		self._accept_offer(self.ineligible_student, self.expired_job, 8)

		stats = get_placement_statistics()
		self.assertEqual(stats['total_offers'], 2)
		self.assertEqual(float(stats['max_ctc']), 12.0)
		self.assertEqual(float(stats['min_ctc']), 8.0)
		self.assertEqual(float(stats['total_ctc']), 20.0)
		self.assertEqual(float(stats['avg_ctc']), 10.0)

	def test_get_placement_statistics_empty(self):
		stats = get_placement_statistics()
		self.assertEqual(stats['total_offers'], 0)
		self.assertEqual(stats['total_ctc'], 0)
		self.assertEqual(stats['avg_ctc'], 0)

	def test_get_placement_statistics_only_counts_accepted_offers(self):
		# Pending offer should NOT be counted
		application = create_job_application(self.eligible_student, self.active_job)
		JobOffer.objects.create(
			application=application,
			ctc_offered=20,
			response_deadline=timezone.now() + timedelta(days=1),
			status='PENDING',
		)
		stats = get_placement_statistics()
		self.assertEqual(stats['total_offers'], 0)


# ---------------------------------------------------------------------------
# Role helpers
# ---------------------------------------------------------------------------


def _grant_designation(user, name):
	designation, _ = Designation.objects.get_or_create(
		name=name, defaults={'full_name': name.title(), 'type': 'administrative'}
	)
	HoldsDesignation.objects.get_or_create(
		user=user, designation=designation, defaults={'working': user},
	)


class PlacementCellRoleHelperTests(TestCase):
	def setUp(self):
		self.officer = User.objects.create_user('tpo_user', password='pwd')
		self.chairman = User.objects.create_user('chair_user', password='pwd')
		self.student = User.objects.create_user('stud_user', password='pwd')
		self.alumnus = User.objects.create_user('alum_user', password='pwd')
		self.other = User.objects.create_user('other_user', password='pwd')

		_grant_designation(self.officer, 'placement officer')
		_grant_designation(self.chairman, 'placement chairman')
		_grant_designation(self.student, 'student')
		_grant_designation(self.alumnus, 'alumni')

	def test_is_officer(self):
		self.assertTrue(is_officer(self.officer))
		self.assertFalse(is_officer(self.chairman))
		self.assertFalse(is_officer(self.student))

	def test_is_chairman(self):
		self.assertTrue(is_chairman(self.chairman))
		self.assertFalse(is_chairman(self.officer))

	def test_is_tpo_or_chairman_matches_both_roles(self):
		self.assertTrue(is_tpo_or_chairman(self.officer))
		self.assertTrue(is_tpo_or_chairman(self.chairman))
		self.assertFalse(is_tpo_or_chairman(self.student))

	def test_is_student(self):
		self.assertTrue(is_student(self.student))
		self.assertFalse(is_student(self.officer))

	def test_is_alumni(self):
		self.assertTrue(is_alumni(self.alumnus))
		self.assertFalse(is_alumni(self.student))

	def test_get_user_roles_chairman_takes_priority(self):
		# Chairman should win over officer/student even if both held.
		_grant_designation(self.chairman, 'placement officer')
		_grant_designation(self.chairman, 'student')
		roles = get_user_roles(self.chairman)
		self.assertEqual(roles['role'], 'placement chairman')
		self.assertTrue(roles['is_chairman'])
		self.assertTrue(roles['is_officer'])
		self.assertTrue(roles['is_student'])

	def test_get_user_roles_other_for_user_without_role(self):
		roles = get_user_roles(self.other)
		self.assertEqual(roles['role'], 'other')
		self.assertFalse(roles['is_chairman'])
		self.assertFalse(roles['is_officer'])
		self.assertFalse(roles['is_student'])
		self.assertFalse(roles['is_alumni'])

	def test_get_user_roles_alumni_priority_over_student(self):
		_grant_designation(self.alumnus, 'student')
		roles = get_user_roles(self.alumnus)
		self.assertEqual(roles['role'], 'alumni')


# ---------------------------------------------------------------------------
# Announcement lifecycle
# ---------------------------------------------------------------------------


class PlacementCellAnnouncementTests(TestCase):
	def setUp(self):
		self.author = User.objects.create_user('tpo', password='pwd')

	def _make_announcement(self, **overrides):
		defaults = dict(
			title='Notice',
			content='Body',
			notice_type='GENERAL',
			priority='NORMAL',
			visibility_scope='ALL',
			created_by=self.author,
			is_active=True,
			publish_at=timezone.now() - timedelta(hours=1),
		)
		defaults.update(overrides)
		return Announcement.objects.create(**defaults)

	def test_returns_only_published_active_non_expired(self):
		published = self._make_announcement(title='visible')
		# Inactive
		self._make_announcement(title='inactive', is_active=False)
		# Future publish_at
		self._make_announcement(
			title='future', publish_at=timezone.now() + timedelta(hours=1),
		)
		# Already expired
		self._make_announcement(
			title='expired', expires_at=timezone.now() - timedelta(minutes=1),
		)

		titles = list(get_active_announcements().values_list('title', flat=True))
		self.assertEqual(titles, [published.title])

	def test_high_priority_orders_before_normal(self):
		normal = self._make_announcement(title='Normal')
		high = self._make_announcement(title='High', priority='HIGH')
		ordered = list(get_active_announcements().values_list('title', flat=True))
		self.assertEqual(ordered[0], high.title)
		self.assertIn(normal.title, ordered)

	def test_filter_by_notice_type(self):
		self._make_announcement(title='General Notice', notice_type='GENERAL')
		self._make_announcement(title='Policy Notice', notice_type='POLICY')
		titles = list(
			get_active_announcements(notice_type='POLICY').values_list('title', flat=True)
		)
		self.assertEqual(titles, ['Policy Notice'])

	def test_filter_by_visibility_scope(self):
		self._make_announcement(title='ALL audience', visibility_scope='ALL')
		self._make_announcement(
			title='Batch only', visibility_scope='SPECIFIC_BATCH',
		)
		titles = list(
			get_active_announcements(visibility_scope='SPECIFIC_BATCH')
			.values_list('title', flat=True)
		)
		self.assertEqual(titles, ['Batch only'])

	def test_limit_truncates_results(self):
		for i in range(5):
			self._make_announcement(title='N{}'.format(i))
		self.assertEqual(get_active_announcements(limit=2).count(), 2)


# ---------------------------------------------------------------------------
# Alumni approval / rejection
# ---------------------------------------------------------------------------


class PlacementCellAlumniTests(TestCase):
	def setUp(self):
		self.tpo = User.objects.create_user('tpo', password='pwd')
		self.alum_user = User.objects.create_user('alum', password='pwd')
		self.alum = AlumniProfile.objects.create(
			user=self.alum_user,
			graduation_year=2020,
			programme='B.Tech',
			department='CSE',
		)

	def test_approve_alumni_marks_approved_and_grants_designation(self):
		approve_alumni(self.alum, self.tpo)
		self.alum.refresh_from_db()
		self.assertEqual(self.alum.approval_status, 'APPROVED')
		self.assertEqual(self.alum.approved_by, self.tpo)
		# Helper should now report alumni
		self.assertTrue(is_alumni(self.alum_user))

	def test_approve_alumni_clears_previous_rejection_remarks(self):
		self.alum.approval_status = 'REJECTED'
		self.alum.rejection_remarks = 'Document unclear'
		self.alum.save()
		approve_alumni(self.alum, self.tpo)
		self.alum.refresh_from_db()
		self.assertIsNone(self.alum.rejection_remarks)

	def test_approve_alumni_idempotent_does_not_create_duplicate_designation(self):
		approve_alumni(self.alum, self.tpo)
		approve_alumni(self.alum, self.tpo)
		count = HoldsDesignation.objects.filter(
			user=self.alum_user, designation__name='alumni',
		).count()
		self.assertEqual(count, 1)

	def test_reject_alumni_sets_status_and_remarks(self):
		reject_alumni(self.alum, remarks='Verification failed')
		self.alum.refresh_from_db()
		self.assertEqual(self.alum.approval_status, 'REJECTED')
		self.assertEqual(self.alum.rejection_remarks, 'Verification failed')


# ---------------------------------------------------------------------------
# Debar workflow
# ---------------------------------------------------------------------------


class PlacementCellDebarTests(PlacementCellBaseTestCase):
	def test_debar_student_creates_record_when_missing(self):
		sp = debar_student(self.eligible_student.id.id)
		self.assertIsNotNone(sp)
		self.assertEqual(sp.debar, 'DEBAR')

	def test_debar_student_returns_none_for_unknown_roll(self):
		self.assertIsNone(debar_student('NO_SUCH_ROLL'))

	def test_undebar_student_clears_status(self):
		debar_student(self.eligible_student.id.id)
		sp = undebar_student(self.eligible_student.id.id)
		self.assertIsNotNone(sp)
		self.assertEqual(sp.debar, 'NOT DEBAR')

	def test_undebar_student_returns_none_when_no_existing_record(self):
		self.assertIsNone(undebar_student(self.eligible_student.id.id))

	def test_get_student_debar_status_with_record(self):
		debar_student(self.eligible_student.id.id)
		info = get_student_debar_status(self.eligible_student.id.id)
		self.assertEqual(info['debar'], 'DEBAR')
		self.assertEqual(info['placed'], 'NOT PLACED')
		self.assertEqual(info['roll_no'], self.eligible_student.id.id)

	def test_get_student_debar_status_without_record_returns_defaults(self):
		info = get_student_debar_status(self.eligible_student.id.id)
		self.assertEqual(info['debar'], 'NOT DEBAR')
		self.assertEqual(info['placed'], 'NOT PLACED')

	def test_get_student_debar_status_unknown_roll_returns_none(self):
		self.assertIsNone(get_student_debar_status('NO_SUCH_ROLL'))


# ---------------------------------------------------------------------------
# Model property smoke tests
# ---------------------------------------------------------------------------


class PlacementCellModelPropertyTests(PlacementCellBaseTestCase):
	def test_jobposting_is_deadline_passed_property(self):
		self.assertFalse(self.active_job.is_deadline_passed)
		self.assertTrue(self.expired_job.is_deadline_passed)

	def test_jobposting_total_applications_property(self):
		self.assertEqual(self.active_job.total_applications, 0)
		create_job_application(self.eligible_student, self.active_job)
		self.assertEqual(self.active_job.total_applications, 1)

	def test_joboffer_is_deadline_passed_property_only_for_pending(self):
		application = create_job_application(self.eligible_student, self.active_job)
		past_pending = JobOffer.objects.create(
			application=application,
			ctc_offered=10,
			response_deadline=timezone.now() - timedelta(hours=1),
			status='PENDING',
		)
		self.assertTrue(past_pending.is_deadline_passed)
		past_pending.status = 'ACCEPTED'
		past_pending.save()
		self.assertFalse(past_pending.is_deadline_passed)

	def test_placement_profile_is_complete_and_missing_fields(self):
		profile = PlacementProfile.objects.create(student=self.eligible_student)
		self.assertFalse(profile.is_complete)
		self.assertEqual(
			set(profile.missing_required_fields()),
			{'professional_email', 'linkedin_url', 'github_url'},
		)
		profile.professional_email = 'a@b.com'
		profile.linkedin_url = 'https://linkedin.com/in/a'
		profile.github_url = 'https://github.com/a'
		profile.save()
		self.assertTrue(profile.is_complete)
		self.assertEqual(profile.missing_required_fields(), [])
