from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from applications.academic_information.models import Student
from applications.globals.models import DepartmentInfo, ExtraInfo
from applications.placement_cell.models import (
	Company,
	Has,
	JobApplication,
	JobOffer,
	JobPosting,
	PlacementPolicy,
	Skill,
	StudentPlacement,
)
from applications.placement_cell.services import (
	check_duplicate_application,
	check_eligibility,
	check_placement_policy,
	create_job_application,
	expire_pending_offers,
	get_placement_statistics,
	get_student_application_summary,
	process_offer_response,
	register_company,
	update_job_application_status,
)


class PlacementCellServiceTests(TestCase):
	def setUp(self):
		self.cse_department = DepartmentInfo.objects.create(name='CSE')
		self.me_department = DepartmentInfo.objects.create(name='ME')

		self.student_user_eligible = User.objects.create_user(
			username='eligible_student',
			password='pwd',
		)
		self.student_user_ineligible = User.objects.create_user(
			username='ineligible_student',
			password='pwd',
		)

		eligible_extra = ExtraInfo.objects.create(
			id='TEST2022CS01',
			user=self.student_user_eligible,
			user_type='student',
			department=self.cse_department,
		)
		ineligible_extra = ExtraInfo.objects.create(
			id='TEST2022ME01',
			user=self.student_user_ineligible,
			user_type='student',
			department=self.me_department,
		)

		self.eligible_student = Student.objects.create(
			id=eligible_extra,
			programme='B.Tech',
			batch=2022,
			cpi=8.5,
			category='GEN',
		)
		self.ineligible_student = Student.objects.create(
			id=ineligible_extra,
			programme='B.Tech',
			batch=2022,
			cpi=5.5,
			category='GEN',
		)

		self.company = Company.objects.create(
			name='TechCorp',
			contact_email='hr@techcorp.com',
		)

		self.active_job = JobPosting.objects.create(
			company=self.company,
			title='SDE',
			description='Software role',
			job_type='PLACEMENT',
			ctc=12.0,
			min_cpi=7.0,
			eligible_programmes='B.Tech',
			eligible_branches='CSE,ECE',
			application_deadline=timezone.now() + timedelta(days=7),
		)

		self.expired_job = JobPosting.objects.create(
			company=self.company,
			title='Old SDE',
			description='Expired role',
			job_type='PLACEMENT',
			ctc=10.0,
			min_cpi=6.0,
			eligible_programmes='B.Tech',
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

	def test_register_company_creates_then_reuses_record(self):
		company_details, created = register_company('NewCorp')
		self.assertTrue(created)
		self.assertEqual(company_details.company_name, 'NewCorp')

		same_company_details, created_again = register_company('NewCorp')
		self.assertFalse(created_again)
		self.assertEqual(company_details.id, same_company_details.id)

	def test_check_eligibility_accepts_valid_student(self):
		is_eligible, reasons = check_eligibility(self.eligible_student, self.active_job)
		self.assertTrue(is_eligible)
		self.assertEqual(reasons, [])

	def test_check_eligibility_rejects_low_cpi(self):
		is_eligible, reasons = check_eligibility(self.ineligible_student, self.active_job)
		self.assertFalse(is_eligible)
		self.assertTrue(any('Minimum CPI required' in reason for reason in reasons))

	def test_check_eligibility_rejects_programme_mismatch(self):
		self.active_job.eligible_programmes = 'M.Tech'
		self.active_job.save()

		is_eligible, reasons = check_eligibility(self.eligible_student, self.active_job)
		self.assertFalse(is_eligible)
		self.assertTrue(any('programme' in reason.lower() for reason in reasons))

	def test_check_eligibility_rejects_branch_mismatch(self):
		self.active_job.eligible_branches = 'ECE,EE'
		self.active_job.save()

		is_eligible, reasons = check_eligibility(self.eligible_student, self.active_job)
		self.assertFalse(is_eligible)
		self.assertTrue(any('branch/department' in reason.lower() for reason in reasons))

	def test_check_eligibility_rejects_expired_job(self):
		is_eligible, reasons = check_eligibility(self.eligible_student, self.expired_job)
		self.assertFalse(is_eligible)
		self.assertTrue(any('deadline' in reason.lower() for reason in reasons))

	def test_check_placement_policy_blocks_after_accepted_offer(self):
		application = JobApplication.objects.create(
			job_posting=self.active_job,
			student=self.eligible_student,
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

	def test_check_placement_policy_allows_dream_company_exception(self):
		self.policy.allow_dream_company = True
		self.policy.dream_ctc_threshold = 10
		self.policy.save()

		application = JobApplication.objects.create(
			job_posting=self.active_job,
			student=self.eligible_student,
		)
		JobOffer.objects.create(
			application=application,
			ctc_offered=11,
			response_deadline=timezone.now() + timedelta(days=1),
			status='ACCEPTED',
		)

		high_ctc_job = JobPosting.objects.create(
			company=self.company,
			title='Dream Role',
			description='High paying role',
			job_type='PLACEMENT',
			ctc=20.0,
			min_cpi=7.0,
			eligible_programmes='B.Tech',
			eligible_branches='CSE',
			application_deadline=timezone.now() + timedelta(days=5),
		)

		can_apply, reason = check_placement_policy(self.eligible_student, high_ctc_job)
		self.assertTrue(can_apply)
		self.assertEqual(reason, '')

	def test_create_job_application_creates_applied_record(self):
		application = create_job_application(self.eligible_student, self.active_job)

		self.assertIsNotNone(application.id)
		self.assertEqual(application.student, self.eligible_student)
		self.assertEqual(application.job_posting, self.active_job)
		self.assertEqual(application.status, 'APPLIED')

	def test_update_job_application_status_updates_status_and_remarks(self):
		application = create_job_application(self.eligible_student, self.active_job)

		updated = update_job_application_status(
			application,
			'SHORTLISTED',
			remarks='Meets all criteria',
		)

		self.assertEqual(updated.status, 'SHORTLISTED')
		self.assertEqual(updated.remarks, 'Meets all criteria')

	def test_check_duplicate_application_false_before_apply(self):
		is_duplicate = check_duplicate_application(self.eligible_student, self.active_job)
		self.assertFalse(is_duplicate)

	def test_check_duplicate_application_true_after_apply(self):
		create_job_application(self.eligible_student, self.active_job)
		is_duplicate = check_duplicate_application(self.eligible_student, self.active_job)
		self.assertTrue(is_duplicate)

	def test_check_eligibility_rejects_inactive_job(self):
		self.active_job.is_active = False
		self.active_job.save()

		is_eligible, reasons = check_eligibility(self.eligible_student, self.active_job)
		self.assertFalse(is_eligible)
		self.assertTrue(any('no longer active' in reason.lower() for reason in reasons))

	def test_check_eligibility_rejects_debarred_student(self):
		StudentPlacement.objects.create(unique_id=self.eligible_student, debar='DEBAR')

		is_eligible, reasons = check_eligibility(self.eligible_student, self.active_job)
		self.assertFalse(is_eligible)
		self.assertTrue(any('debarred' in reason.lower() for reason in reasons))

	def test_check_eligibility_rejects_when_required_skills_missing(self):
		required_skill = Skill.objects.create(skill='Python')
		self.active_job.required_skills.add(required_skill)

		is_eligible, reasons = check_eligibility(self.eligible_student, self.active_job)
		self.assertFalse(is_eligible)
		self.assertTrue(any('missing required skills' in reason.lower() for reason in reasons))

	def test_check_eligibility_accepts_when_required_skills_present(self):
		required_skill = Skill.objects.create(skill='Django')
		self.active_job.required_skills.add(required_skill)
		Has.objects.create(skill_id=required_skill, unique_id=self.eligible_student)

		is_eligible, reasons = check_eligibility(self.eligible_student, self.active_job)
		self.assertTrue(is_eligible)
		self.assertEqual(reasons, [])

	def test_check_eligibility_rejects_batch_out_of_range(self):
		self.active_job.eligible_batch_from = 2023
		self.active_job.eligible_batch_to = 2025
		self.active_job.save()

		is_eligible, reasons = check_eligibility(self.eligible_student, self.active_job)
		self.assertFalse(is_eligible)
		self.assertTrue(any('batch year' in reason.lower() for reason in reasons))

	def test_check_placement_policy_allows_when_no_active_policy(self):
		self.policy.is_active = False
		self.policy.save()

		can_apply, reason = check_placement_policy(self.eligible_student, self.active_job)
		self.assertTrue(can_apply)
		self.assertEqual(reason, '')

	def test_process_offer_response_accept_updates_offer_application_and_student(self):
		application = create_job_application(self.eligible_student, self.active_job)
		offer = JobOffer.objects.create(
			application=application,
			ctc_offered=13,
			response_deadline=timezone.now() + timedelta(days=1),
		)

		success, message = process_offer_response(offer, 'accept')
		offer.refresh_from_db()
		application.refresh_from_db()

		self.assertTrue(success)
		self.assertEqual(message, 'accepted')
		self.assertEqual(offer.status, 'ACCEPTED')
		self.assertEqual(application.status, 'OFFER_ACCEPTED')
		self.assertTrue(StudentPlacement.objects.filter(unique_id=self.eligible_student, placed_type='PLACED').exists())

	def test_process_offer_response_reject_updates_offer_and_application(self):
		application = create_job_application(self.eligible_student, self.active_job)
		offer = JobOffer.objects.create(
			application=application,
			ctc_offered=13,
			response_deadline=timezone.now() + timedelta(days=1),
		)

		success, message = process_offer_response(offer, 'reject')
		offer.refresh_from_db()
		application.refresh_from_db()

		self.assertTrue(success)
		self.assertEqual(message, 'rejected')
		self.assertEqual(offer.status, 'REJECTED')
		self.assertEqual(application.status, 'OFFER_REJECTED')

	def test_process_offer_response_rejects_when_offer_already_processed(self):
		application = create_job_application(self.eligible_student, self.active_job)
		offer = JobOffer.objects.create(
			application=application,
			ctc_offered=13,
			response_deadline=timezone.now() + timedelta(days=1),
			status='ACCEPTED',
		)

		success, message = process_offer_response(offer, 'reject')
		self.assertFalse(success)
		self.assertIn('already', message)

	def test_expire_pending_offers_marks_only_overdue_pending_offers(self):
		application1 = create_job_application(self.eligible_student, self.active_job)
		application2 = create_job_application(self.ineligible_student, self.expired_job)

		expired_offer = JobOffer.objects.create(
			application=application1,
			ctc_offered=10,
			response_deadline=timezone.now() - timedelta(hours=1),
			status='PENDING',
		)
		active_offer = JobOffer.objects.create(
			application=application2,
			ctc_offered=9,
			response_deadline=timezone.now() + timedelta(hours=2),
			status='PENDING',
		)

		expired_count = expire_pending_offers()
		expired_offer.refresh_from_db()
		active_offer.refresh_from_db()

		self.assertEqual(expired_count, 1)
		self.assertEqual(expired_offer.status, 'EXPIRED')
		self.assertEqual(active_offer.status, 'PENDING')

	def test_get_placement_statistics_returns_expected_aggregates(self):
		application1 = create_job_application(self.eligible_student, self.active_job)
		application2 = create_job_application(self.ineligible_student, self.expired_job)

		JobOffer.objects.create(
			application=application1,
			ctc_offered=12,
			response_deadline=timezone.now() + timedelta(days=1),
			status='ACCEPTED',
		)
		JobOffer.objects.create(
			application=application2,
			ctc_offered=8,
			response_deadline=timezone.now() + timedelta(days=1),
			status='ACCEPTED',
		)

		stats = get_placement_statistics()

		self.assertEqual(stats['total_offers'], 2)
		self.assertEqual(float(stats['max_ctc']), 12.0)
		self.assertEqual(float(stats['min_ctc']), 8.0)
		self.assertEqual(float(stats['total_ctc']), 20.0)

	def test_get_student_application_summary_counts_statuses(self):
		app1 = create_job_application(self.eligible_student, self.active_job)
		app2 = JobApplication.objects.create(
			job_posting=self.expired_job,
			student=self.eligible_student,
			status='SHORTLISTED',
		)
		app3 = JobApplication.objects.create(
			job_posting=self.expired_job,
			student=self.ineligible_student,
			status='REJECTED',
		)

		# Keep only eligible student's records for summary assertions
		app3.delete()
		update_job_application_status(app1, 'OFFER_EXTENDED')
		update_job_application_status(app2, 'INTERVIEW_SCHEDULED')

		summary = get_student_application_summary(self.eligible_student)

		self.assertEqual(summary['total'], 2)
		self.assertEqual(summary['offer_extended'], 1)
		self.assertEqual(summary['interview_scheduled'], 1)
