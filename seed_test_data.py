from app import SessionLocal, Company, Record


def seed():
    db = SessionLocal()
    try:
        db.query(Record).delete()
        db.query(Company).delete()
        db.commit()

        company = Company(name="Test Company")
        db.add(company)
        db.commit()

        records = [
            Record(name="First Record", company_id=company.id),
            Record(name="Second Record", company_id=company.id),
        ]
        db.add_all(records)
        db.commit()
        print("Seeded demo data.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
