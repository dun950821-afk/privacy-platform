"""数据库初始化: 建表 + 种子数据"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import engine, Base
from app.models import *  # noqa
from app.seed import seed_database


def init_db():
    """创建所有表"""
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Tables created.")

    print("Seeding initial data...")
    seed_database()
    print("Done. Database initialized.")


if __name__ == "__main__":
    init_db()
