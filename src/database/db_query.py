import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "sections.db"


def get_connection():
    return sqlite3.connect(DB_PATH)


def get_all_sections(shape=None):
    conn = get_connection()
    cursor = conn.cursor()

    if shape is None:
        cursor.execute("""
            SELECT name, shape, area, weight, I, W, section_class
            FROM sections
        """)
    else:
        cursor.execute("""
            SELECT name, shape, area, weight, I, W, section_class
            FROM sections
            WHERE shape = ?
        """, (shape,))

    rows = cursor.fetchall()
    conn.close()
    return rows


def get_section(name):
    conn = get_connection()
    cursor = conn.cursor()

    normalized_name = str(name).replace("\xa0", " ").strip()

    cursor.execute("""
        SELECT name, shape, area, weight, I, W, section_class
        FROM sections
    """)
    rows = cursor.fetchall()
    conn.close()

    for row in rows:
        db_name = str(row[0]).replace("\xa0", " ").strip()
        if db_name == normalized_name:
            return row

    return None

def get_all_materials():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT grade, fy, cost
        FROM materials
    """)

    rows = cursor.fetchall()
    conn.close()
    return rows


def get_material(grade):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT grade, fy, cost
        FROM materials
        WHERE grade = ?
    """, (grade,))

    row = cursor.fetchone()
    conn.close()
    return row


def get_all_design_standards():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT code, alpha, beta
        FROM design_standards
    """)

    rows = cursor.fetchall()
    conn.close()
    return rows


def get_design_standard(code):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT code, alpha, beta
        FROM design_standards
        WHERE code = ?
    """, (code,))

    row = cursor.fetchone()
    conn.close()
    return row


def get_all_section_names():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT name
        FROM sections
        ORDER BY name
    """)

    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_all_material_grades():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT grade
        FROM materials
        ORDER BY fy
    """)

    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_all_design_standard_codes():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT code
        FROM design_standards
    """)

    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]

def get_sections_by_shape(shape):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT name, shape, area, weight, I, W, section_class
        FROM sections
        WHERE shape = ?
    """, (shape,))

    rows = cursor.fetchall()
    conn.close()
    return rows


def get_unique_sections_by_shape(shape):
    rows = get_sections_by_shape(shape)
    seen = set()
    unique_rows = []

    for row in rows:
        key = row[0]  # section name
        if key not in seen:
            seen.add(key)
            unique_rows.append(row)

    return unique_rows

def get_unique_sections_by_shape_sorted(shape, sort_by="weight"):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT name, shape, area, weight, I, W, section_class
        FROM sections
        WHERE shape = ?
    """, (shape,))

    rows = cursor.fetchall()
    conn.close()

    # Deduplicate by section name, keep first occurrence
    seen = set()
    unique_rows = []
    for row in rows:
        name = row[0]
        if name not in seen:
            seen.add(name)
            unique_rows.append(row)

    # Sort by chosen field
    field_index = {
        "name": 0,
        "area": 2,
        "weight": 3,
        "I": 4,
        "W": 5,
        "section_class": 6,
    }

    idx = field_index.get(sort_by, 3)

    # Put None safely at the end
    unique_rows = sorted(
        unique_rows,
        key=lambda r: (r[idx] is None, r[idx])
    )

    return unique_rows

def grade_to_value(grade):
    """
    'S235' -> 235
    """
    return int(str(grade).replace("S", "").strip())


def get_materials_in_grade_range(min_grade, max_grade):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT grade, fy, cost
        FROM materials
    """)

    rows = cursor.fetchall()
    conn.close()

    min_val = grade_to_value(min_grade)
    max_val = grade_to_value(max_grade)

    filtered = []
    for row in rows:
        grade = row[0]
        val = grade_to_value(grade)
        if min_val <= val <= max_val:
            filtered.append(row)

    filtered.sort(key=lambda r: grade_to_value(r[0]))
    return filtered

if __name__ == "__main__":
    mats = get_materials_in_grade_range("S235", "S355")
    for m in mats:
        print(m)