import os
import django
import random
import datetime
from django.utils import timezone
from django.db import transaction

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Fusion.settings')
django.setup()

from django.contrib.auth.models import User
from applications.globals.models import (
    ExtraInfo, DepartmentInfo, Designation, HoldsDesignation, ModuleAccess
)
from applications.academic_information.models import Student
from applications.programme_curriculum.models import Programme, Batch
from applications.placement_cell.models import (
    Constants as PlacementConstants,
    Skill, Has, Project, Education, Experience, Course, Conference, Publication,
    Reference, Patent, Interest, Achievement, Extracurricular,
    NotifyStudent, PlacementStatus,
    Company, JobPosting, JobApplication, InterviewSchedule, InterviewPanel, JobOffer,
    Announcement, PlacementPolicy
)


def ensure_module_access(designation, **flags):
    """Ensure exactly one ModuleAccess row is effectively used for a designation.

    If duplicates exist, keep the oldest row, merge required flags into it,
    and remove the rest to prevent MultipleObjectsReturned in future runs.
    """
    matches = ModuleAccess.objects.filter(designation=designation).order_by('id')
    primary = matches.first()

    if primary is None:
        return ModuleAccess.objects.create(designation=designation, **flags)

    changed_fields = []
    for field, value in flags.items():
        if getattr(primary, field) != value:
            setattr(primary, field, value)
            changed_fields.append(field)

    if changed_fields:
        primary.save(update_fields=changed_fields)

    duplicate_qs = matches.exclude(id=primary.id)
    if duplicate_qs.exists():
        print(f"  Found duplicate ModuleAccess rows for '{designation}', cleaning up: {duplicate_qs.count()} removed")
        duplicate_qs.delete()

    return primary


def create_department_info():
    print("Creating Departments...")
    depts = ['CSE', 'ECE', 'ME', 'Design', 'Natural Science']
    dept_objs = {}
    for name in depts:
        dept, created = DepartmentInfo.objects.get_or_create(name=name)
        dept_objs[name] = dept
        if created:
            print(f"  Created Department: {name}")
    return dept_objs

def create_designations():
    print("Creating Designations...")
    student_desig, _ = Designation.objects.get_or_create(name='student', defaults={'full_name': 'Student', 'type': 'academic'})
    placement_officer_desig, _ = Designation.objects.get_or_create(name='placement officer', defaults={'full_name': 'Placement Officer', 'type': 'administrative'})

    # Module Access (designation is not unique in model, so avoid get_or_create here)
    ensure_module_access('student', placement_cell=True)
    ensure_module_access('placement officer', placement_cell=True)

    return student_desig, placement_officer_desig

def create_programmes_and_batches():
    print("Creating Programmes and Batches...")

    # Create Programmes
    btech, _ = Programme.objects.get_or_create(name='B.Tech', category='UG', defaults={'programme_begin_year': 2005})
    mtech, _ = Programme.objects.get_or_create(name='M.Tech', category='PG', defaults={'programme_begin_year': 2005})

    batches = []
    years = [2021, 2022, 2023, 2024]
    disciplines = ['CSE', 'ECE', 'ME']

    for year in years:
        for disc in disciplines:
            # Note: Adjust fields based on actual Batch model structure if it differs
            try:
                # Based on previous error logs, we know Batch exists.
                # We try to get or create specific batches.
                # Since I don't have the full Batch model definition with all fields, I'll try a safe approach
                # accessing via filter first.

                # Assuming a naming convention or ensuring unique batches for sample data
                batch_name = f"B.Tech {disc} {year}"

                # Try creating with defaults if not exists
                defaults = {
                        'year': year,
                        'discipline': disc,
                        'programme': btech
                }

                # Check if filter returns anything first to avoid MultipleObjectsReturned
                existing = Batch.objects.filter(name=batch_name).first()
                if not existing:
                    existing = Batch.objects.filter(year=year, discipline=disc, programme=btech).first()

                if existing:
                    batch = existing
                    # print(f"  Found existing batch: {batch}")
                else:
                    batch = Batch.objects.create(name=batch_name, **defaults)
                    print(f"  Created Batch: {batch_name}")

                batches.append(batch)

            except Exception as e:
                # If fields don't match, we might need to fallback or query existing
                # Let's try to just fetch any batch for the year to avoid the MultipleObjectsReturned error
                existing_batches = Batch.objects.filter(year=year)
                if existing_batches.exists():
                    batches.append(existing_batches.first())
                else:
                    print(f"  Could not create/find batch for {year} {disc}: {e}")

    return batches

def create_students(dept_objs, student_desig, batches):
    print("Creating Students...")
    students = []

    # 20 Students
    for i in range(1, 21):
        username = f'student{i}'
        email = f'student{i}@fusion.ac.in'
        password = 'password123'

        user, created = User.objects.get_or_create(username=username, defaults={'email': email})
        if created:
            user.set_password(password)
            user.save()
            print(f"  Created User: {username}")

        # Extra Info
        dept_name = random.choice(list(dept_objs.keys()))
        dept = dept_objs[dept_name]

        # Unique ID for ExtraInfo
        extra_info_id = f'2021{i:03d}' # e.g., 2021001

        extra_info, created = ExtraInfo.objects.get_or_create(
            id=extra_info_id,
            defaults={
                'user': user,
                'user_type': 'student',
                'department': dept,
                'sex': random.choice(['M', 'F']),
                'date_of_birth': datetime.date(2000, 1, 1),
                'address': 'Fusion Campus',
                'phone_no': 9876543210 + i
            }
        )

        # Holds Designation
        HoldsDesignation.objects.get_or_create(
            user=user,
            working=user,
            designation=student_desig
        )

        # Student Model
        batch = random.choice(batches) if batches else None

        if batch:
            student, created = Student.objects.get_or_create(
                id=extra_info,
                defaults={
                    'programme': 'B.Tech',
                    'batch': batch.year,
                    'batch_id': batch,
                    'cpi': round(random.uniform(6.0, 10.0), 2),
                    'category': 'GEN',
                    'father_name': f'Father of {username}',
                    'mother_name': f'Mother of {username}',
                    'hall_no': 1,
                    'room_no': f'A-{i}',
                    'specialization': dept_name
                }
            )
            students.append(student)
            if created:
                # print(f"  Created Student profile for: {username}")
                pass

    return students

def create_skills_and_associations(students):
    print("Creating Skills and Associations...")
    skill_names = ['Python', 'Java', 'C++', 'Django', 'React', 'Machine Learning', 'Data Science', 'SQL', 'AWS', 'Docker']
    skills = []
    for name in skill_names:
        skill, _ = Skill.objects.get_or_create(skill=name)
        skills.append(skill)

    for student in students:
        # Assign 3-5 random skills
        student_skills = random.sample(skills, k=random.randint(3, 5))
        for skill in student_skills:
            Has.objects.get_or_create(
                skill_id=skill,
                unique_id=student,
                defaults={'skill_rating': random.randint(3, 5)} # Assuming 1-5 or 0-100 rating
            )

def create_student_portfolio(students):
    print("Creating Student Portfolios (Projects, Edu, Exp, etc)...")
    for student in students:
        # Projects
        Project.objects.get_or_create(
            unique_id=student,
            project_name='Library Management System',
            defaults={
                'project_status': 'COMPLETED',
                'summary': 'A Django based library management system.',
                'project_link': 'http://github.com/example/lms',
                'sdate': datetime.date(2023, 1, 1),
                'edate': datetime.date(2023, 5, 1)
            }
        )

        # Education (10th, 12th)
        Education.objects.get_or_create(
            unique_id=student,
            degree='Class X',
            defaults={
                'grade': '95%',
                'institute': 'ABC School',
                'stream': 'General',
                'sdate': datetime.date(2018, 4, 1),
                'edate': datetime.date(2019, 3, 31)
            }
        )

        # Experience (Internship)
        if random.choice([True, False]):
            Experience.objects.get_or_create(
                unique_id=student,
                company='Tech Corp',
                defaults={
                    'title': 'SDE Intern',
                    'status': 'COMPLETED',
                    'description': 'Worked on backend APIs.',
                    'location': 'Bangalore',
                    'sdate': datetime.date(2024, 5, 1),
                    'edate': datetime.date(2024, 7, 31)
                }
            )

        # Achievements
        Achievement.objects.get_or_create(
            unique_id=student,
            achievement='Hackathon Winner',
            defaults={
                'achievement_type': 'EDUCATIONAL',
                'description': 'Won 1st prize in national hackathon.',
                'issuer': 'Tech University',
                'date_earned': datetime.date(2023, 10, 15)
            }
        )

def create_tpo_user(dept_objs, placement_officer_desig):
    print("Creating TPO User...")
    tpo_user, created = User.objects.get_or_create(username='tpo_admin', defaults={'email': 'tpo@iiitdmj.ac.in'})
    if created:
        tpo_user.set_password('password')
        tpo_user.save()

    tpo_extra, _ = ExtraInfo.objects.get_or_create(
        id='TPO001',
        defaults={
            'user': tpo_user,
            'user_type': 'staff',
            'department': dept_objs.get('CSE'),
            'sex': 'M',
            'phone_no': 9999999999
        }
    )
    HoldsDesignation.objects.get_or_create(user=tpo_user, working=tpo_user, designation=placement_officer_desig)

    return tpo_user

def create_companies_and_jobs(tpo_user):
    print("Creating Companies and Job Postings...")
    companies = []

    # 5 Companies
    company_data = [
        ('Google', 'Technology'),
        ('Microsoft', 'Technology'),
        ('Goldman Sachs', 'Finance'),
        ('Amazon', 'Technology'),
        ('Tata Motors', 'Manufacturing')
    ]

    for name, domain in company_data:
        company, created = Company.objects.get_or_create(
            name=name,
            defaults={
                'domain': domain,
                'contact_email': f'hr@{name.lower().replace(" ", "")}.com',
                'approval_status': 'APPROVED',
                'registered_by': tpo_user,
                'approved_by': tpo_user
            }
        )
        companies.append(company)
        if created:
            print(f"  Created Company: {name}")

    # Job Postings
    jobs = []
    for company in companies:
        for i in range(2): # 2 jobs per company
            job, created = JobPosting.objects.get_or_create(
                company=company,
                title=f'Software Engineer - Position {i+1}',
                defaults={
                    'description': 'We are looking for talented developers.',
                    'job_type': 'PLACEMENT',
                    'ctc': random.randint(10, 50), # LPA
                    'min_cpi': 7.0,
                    'application_deadline': timezone.now() + datetime.timedelta(days=10),
                    'is_active': True,
                    'posted_by': tpo_user
                }
            )
            jobs.append(job)
            if created:
                print(f"    Created Job: {job.title} at {company.name}")

    return jobs

def create_applications_interviews_offers(students, jobs, tpo_user):
    print("Creating Applications, Interviews, and Offers...")

    for job in jobs:
        # Randomly select students to apply
        applicants = random.sample(students, k=random.randint(5, len(students)//2))

        for student in applicants:
            app, created = JobApplication.objects.get_or_create(
                job_posting=job,
                student=student,
                defaults={'status': 'APPLIED'}
            )

            # Shortlist some
            if created and random.choice([True, False]):
                app.status = 'SHORTLISTED'
                app.save()

                # Schedule Interview (Logic simplified, usually one schedule per job)
                interview, _ = InterviewSchedule.objects.get_or_create(
                    job_posting=job,
                    defaults={
                        'date': datetime.date.today() + datetime.timedelta(days=5),
                        'time_slot': datetime.time(10, 0),
                        'mode': 'ONLINE',
                        'created_by': tpo_user
                    }
                )

                # Add to panel
                InterviewPanel.objects.get_or_create(
                    interview=interview,
                    application=app,
                    defaults={'result': 'SELECTED' if random.random() > 0.7 else 'REJECTED'}
                )

                # Offer
                if random.random() > 0.8:
                    app.status = 'OFFER_EXTENDED'
                    app.save()
                    JobOffer.objects.get_or_create(
                        application=app,
                        defaults={
                            'ctc_offered': job.ctc,
                            'status': 'PENDING',
                            'response_deadline': timezone.now() + datetime.timedelta(days=7)
                        }
                    )
                    # print(f"      Offer Extended to {student.id.user.username} for {job.title}")

def create_legacy_data(students):
    print("Creating Legacy Placement Data (NotifyStudent, PlacementStatus)...")
    # This ensures backward compatibility testing if needed
    for i in range(3):
        notify = NotifyStudent.objects.create(
            company_name=f"Legacy Company {random.randint(1,100)}",
            ctc=12.0,
            description="Legacy placement drive",
            placement_type='PLACEMENT'
        )

        for student in random.sample(students, 3):
            PlacementStatus.objects.create(
                notify_id=notify,
                unique_id=student,
                invitation='ACCEPTED',
                placed='NOT PLACED'
            )

def create_announcements(tpo_user):
    print("Creating Announcements...")
    Announcement.objects.get_or_create(
        title='Placement Orientation 2024',
        defaults={
            'content': 'All students are requested to attend the orientation session.',
            'announcement_type': 'GENERAL',
            'target_audience': 'ALL',
            'created_by': tpo_user
        }
    )

def create_policies():
    print("Creating Policies...")
    PlacementPolicy.objects.get_or_create(
        name='One Student One Offer',
        defaults={
            'description': 'Once a student accepts an offer, they are out of the placement process.',
            'max_offers_allowed': 1
        }
    )

@transaction.atomic
def run():
    print("Starting Data Population...")
    dept_objs = create_department_info()
    student_desig, po_desig = create_designations()
    batches = create_programmes_and_batches()
    tpo_user = create_tpo_user(dept_objs, po_desig)
    students = create_students(dept_objs, student_desig, batches)

    if not students:
        print("No students created. Exiting.")
        return

    create_skills_and_associations(students)
    create_student_portfolio(students)

    jobs = create_companies_and_jobs(tpo_user)
    create_applications_interviews_offers(students, jobs, tpo_user)

    create_legacy_data(students)
    create_announcements(tpo_user)
    create_policies()

    print("Data Population Completed Successfully!")

if __name__ == '__main__':
    run()

