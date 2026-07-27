"""Stable employee-import limits shared by schemas and spreadsheet adapters."""

EMPLOYEE_IMPORT_MAX_ROWS = 10_000
EMPLOYEE_IMPORT_FIELDS = (
    "employee_number",
    "first_name",
    "last_name",
    "work_email",
    "status",
    "employment_start_date",
    "employment_end_date",
    "legal_entity_code",
    "branch_code",
    "department_code",
    "position_code",
)

__all__ = ["EMPLOYEE_IMPORT_FIELDS", "EMPLOYEE_IMPORT_MAX_ROWS"]
