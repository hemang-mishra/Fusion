import datetime

from django.contrib.auth.models import User
from django.db import transaction

from applications.academic_information.models import Student
from applications.globals.models import (
    DepartmentInfo,
    Designation,
    ExtraInfo,
    HoldsDesignation,
)
from applications.programme_curriculum.models import Batch

# NOTE:
# Run with:
#   python manage.py shell < populate_placement_data_2.py
# This script is idempotent and safe to re-run.


def _default_batch():
    # Batch.discipline is a FK to Discipline, so filter via related fields.
    preferred = (
        Batch.objects.filter(year=2021, name="B.Tech", discipline__acronym="CSE").first()
        or Batch.objects.filter(year=2021, discipline__acronym="CSE").first()
        or Batch.objects.filter(year=2021, name="B.Tech").first()
        or Batch.objects.filter(year=2021).first()
        or Batch.objects.first()
    )
    return preferred


def _extra_info_id_for_user(user):
    # For usernames like student1 -> 2021001, student20 -> 2021020.
    digits = "".join(ch for ch in user.username if ch.isdigit())
    if digits:
        return f"2021{int(digits):03d}"
    return f"STU{user.id:05d}"


def _safe_create_extrainfo(user, department):
    target_id = _extra_info_id_for_user(user)

    existing = ExtraInfo.objects.filter(id=target_id).first()
    if existing and existing.user_id != user.id:
        # Avoid PK collision if the generated ID is already used by someone else.
        target_id = f"STU{user.id:05d}"

    extra, created = ExtraInfo.objects.get_or_create(
        user=user,
        defaults={
            "id": target_id,
            "title": "Mr.",
            "sex": "M",
            "date_of_birth": datetime.date(2000, 1, 1),
            "user_status": "PRESENT",
            "address": "Fusion Campus",
            "phone_no": 9000000000 + user.id,
            "user_type": "student",
            "department": department,
            "about_me": "Generated test profile",
        },
    )

    # If ExtraInfo exists but has stale values, normalize key student fields.
    changed = []
    if extra.user_type != "student":
        extra.user_type = "student"
        changed.append("user_type")
    if extra.department_id is None:
        extra.department = department
        changed.append("department")
    if extra.phone_no is None:
        extra.phone_no = 9000000000 + user.id
        changed.append("phone_no")
    if changed:
        extra.save(update_fields=changed)

    return extra, created


def _ensure_student_designation(user):
    designation, _ = Designation.objects.get_or_create(
        name="student",
        defaults={"full_name": "Student", "type": "academic"},
    )
    _, created = HoldsDesignation.objects.get_or_create(
        user=user,
        working=user,
        designation=designation,
    )
    return created


def _ensure_student_model(extra, batch_obj):
    student, created = Student.objects.get_or_create(
        id=extra,
        defaults={
            "programme": "B.Tech",
            "batch": 2021,
            "batch_id": batch_obj,
            "cpi": 7.0,
            "category": "GEN",
            "father_name": "NA",
            "mother_name": "NA",
            "hall_no": 1,
            "room_no": "A-101",
            "specialization": "CSE",
            "curr_semester_no": 1,
        },
    )

    changed = []
    if student.batch_id is None and batch_obj is not None:
        student.batch_id = batch_obj
        changed.append("batch_id")
    if not student.programme:
        student.programme = "B.Tech"
        changed.append("programme")
    if not student.category:
        student.category = "GEN"
        changed.append("category")
    if changed:
        student.save(update_fields=changed)

    return created


@transaction.atomic
def run():
    print("Starting populate_placement_data_2 backfill...")

    department, _ = DepartmentInfo.objects.get_or_create(name="CSE")
    batch_obj = _default_batch()

    # Target generated student accounts from earlier scripts.
    users = User.objects.filter(username__startswith="student").order_by("id")

    total = users.count()
    extra_created = 0
    student_created = 0
    holds_created = 0

    for user in users:
        extra, created_extra = _safe_create_extrainfo(user, department)
        if created_extra:
            extra_created += 1

        created_student = _ensure_student_model(extra, batch_obj)
        if created_student:
            student_created += 1

        created_hold = _ensure_student_designation(user)
        if created_hold:
            holds_created += 1

    print("Backfill completed.")
    print(f"Users scanned: {total}")
    print(f"ExtraInfo created: {extra_created}")
    print(f"Student created: {student_created}")
    print(f"HoldsDesignation created: {holds_created}")


run()

