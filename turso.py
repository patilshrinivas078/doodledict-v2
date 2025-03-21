from sqlalchemy import create_engine, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))

    def __repr__(self):
        return f"User(id={self.id!r}, name={self.name!r}"
    
TURSO_DATABASE_URL = "libsql://doodledict-patilshrinivas078.turso.io"
TURSO_AUTH_TOKEN = "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.eyJhIjoicnciLCJpYXQiOjE3NDI1MzgyNDIsImlkIjoiYWQ2YTRlOGItOWQwMi00ODQxLWFmMTItNTg1NGY5MjRiZGFlIiwicmlkIjoiM2JmZWE1ZTEtMThlZC00Yzg0LThlODUtOWJhZDMyMzFmMmU2In0.d2qSyOKrcWC-6pfVzCmuHAJPuhgtF-GGM12h9b9nJvpeYaXzRtey0OSqhF1NG_ebh23swTSuFzJv-nTt_aSUCg"

db_url = f"sqlite+{TURSO_DATABASE_URL}/?authToken={TURSO_AUTH_TOKEN}&secure=true"

engine = create_engine(db_url, connect_args={'check_same_thread': False}, echo=True)

def print_users():
    with Session(engine) as db:
        users = db.query(User).all()
        for user in users:
            print(user)
if __name__ == "__main__":
    print_users()