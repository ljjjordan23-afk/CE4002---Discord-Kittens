import pandas as pd
import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "sections.db"


# -------------------------------
# Create Tables
# -------------------------------
def create_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Drop tables
    cursor.execute("DROP TABLE IF EXISTS sections")
    cursor.execute("DROP TABLE IF EXISTS materials")
    cursor.execute("DROP TABLE IF EXISTS design_standards")

    # Sections table
    cursor.execute("""
    CREATE TABLE sections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        shape TEXT,
        area REAL,
        weight REAL,
        I REAL,
        W REAL,
        section_class INTEGER
    )
    """)

    # Materials table
    cursor.execute("""
    CREATE TABLE materials (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        grade TEXT,
        fy REAL,
        cost REAL
    )
    """)

    # Design standards table
    cursor.execute("""
    CREATE TABLE design_standards (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT,
        alpha REAL,
        beta REAL
    )
    """)

    conn.commit()
    conn.close()


# -------------------------------
# Load Sections
# -------------------------------
def load_sections():
    conn = sqlite3.connect(DB_PATH)

    sheets = pd.read_excel(DATA_DIR / "member_section.xlsx", sheet_name=None, header=1)

    all_data = []

    for sheet_name, df in sheets.items():
        # Clean column names thoroughly
        df.columns = [
            str(col).replace("\xa0", " ").strip() for col in df.columns
        ]

        # Drop rows without first column
        df = df[df.iloc[:, 0].notna()].copy()

        # Remove unit row like [mm], [kg/m], etc.
        df = df[~df.iloc[:, 0].astype(str).str.contains(r"\[", na=False)].copy()

        if "I Section" in sheet_name:
            shape = "I"
            df = df.rename(columns={
                "Section Name": "name",
                "Area": "area",
                "Weight": "weight",
                "Second moment of area": "I",
                "Elastic section modulus": "W",
                "Unnamed: 15": "section_class"
            })

        elif "Circular" in sheet_name:
            shape = "CHS"
            df = df.rename(columns={
                "Profile": "name",
                "Area": "area",
                "Weight": "weight",
                "Second moment of area": "I",
                "Elastic section modulus": "W",
                "Unnamed: 11": "section_class"
            })

        elif "Square" in sheet_name:
            shape = "SHS"
            df = df.rename(columns={
                "Profile": "name",
                "Area": "area",
                "Weight": "weight",
                "Second moment of area": "I",
                "Elastic section modulus": "W",
                "Unnamed: 13": "section_class"
            })

        else:
            continue

        needed_cols = ["name", "area", "weight", "I", "W", "section_class"]
        df = df[needed_cols].copy()

        # Clean section names
        df["name"] = (
            df["name"]
            .astype(str)
            .str.replace("\xa0", " ", regex=False)
            .str.strip()
        )

        # Convert numeric columns safely
        for col in ["area", "weight", "I", "W", "section_class"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df["shape"] = shape
        all_data.append(df)

    final_df = pd.concat(all_data, ignore_index=True)

    final_df = final_df.dropna(subset=["name"])
    final_df = final_df.fillna(0)
    final_df = final_df.drop_duplicates(
        subset=["name", "shape", "area", "weight", "I", "W", "section_class"]
    ).reset_index(drop=True)

    final_df.to_sql("sections", conn, if_exists="append", index=False)

    conn.close()


# -------------------------------
# Load Materials
# -------------------------------
def load_materials():
    conn = sqlite3.connect(DB_PATH)

    df = pd.read_excel(DATA_DIR / "material_cost.xlsx")
    df.columns = df.columns.str.strip()

    df = df.rename(columns={
        "Steel Grade": "grade",
        "Yield strength (MPa)": "fy",
        "Cost (SGD per kg)": "cost"
    })

    df = df[["grade", "fy", "cost"]]

    df.to_sql("materials", conn, if_exists="append", index=False)

    conn.close()


# -------------------------------
# Load Design Standards
# -------------------------------
def load_design_standards():
    conn = sqlite3.connect(DB_PATH)

    df = pd.read_excel(DATA_DIR / "design_standard.xlsx")
    df.columns = df.columns.str.strip()

    df = df.rename(columns={
        "Design code": "code",
        "alpha": "alpha",
        "beta": "beta"
    })

    df = df[["code", "alpha", "beta"]]

    df.to_sql("design_standards", conn, if_exists="append", index=False)

    conn.close()


# -------------------------------
# Run All
# -------------------------------
def run_all():
    print("Creating database...")
    create_database()

    print("Loading sections...")
    load_sections()

    print("Loading materials...")
    load_materials()

    print("Loading design standards...")
    load_design_standards()

    print("✅ DONE! Database ready.")


if __name__ == "__main__":
    run_all()