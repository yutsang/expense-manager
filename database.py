"""
Database models and schema for the Expense Manager application.
"""

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from datetime import datetime
import os

Base = declarative_base()

class Category(Base):
    """Category model for organizing expenses."""
    __tablename__ = 'categories'

    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    color = Column(String(7), nullable=True)  # Hex color code
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationship with expenses
    expenses = relationship("Expense", back_populates="category")

    def __repr__(self):
        return f"<Category(id={self.id}, name='{self.name}')>"

class Expense(Base):
    """Expense model for storing individual expense records."""
    __tablename__ = 'expenses'

    id = Column(Integer, primary_key=True)
    amount = Column(Float, nullable=False)
    description = Column(Text, nullable=False)
    date = Column(DateTime, nullable=False)
    category_id = Column(Integer, ForeignKey('categories.id'), nullable=False)
    payment_method = Column(String(50), nullable=True)  # cash, card, bank transfer, etc.
    location = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship with category
    category = relationship("Category", back_populates="expenses")

    def __repr__(self):
        return f"<Expense(id={self.id}, amount={self.amount}, description='{self.description[:30]}...')>"

class Database:
    """Database connection and session management."""

    def __init__(self, db_path=None):
        if db_path is None:
            db_path = os.path.join(os.path.dirname(__file__), 'expense_manager.db')
        self.db_path = db_path
        self.engine = create_engine(f'sqlite:///{db_path}', echo=False)
        self.Session = sessionmaker(bind=self.engine)

    def create_tables(self):
        """Create all database tables."""
        Base.metadata.create_all(self.engine)

    def get_session(self):
        """Get a new database session."""
        return self.Session()

    def init_default_categories(self):
        """Initialize default expense categories."""
        session = self.get_session()

        default_categories = [
            {"name": "Food & Dining", "description": "Restaurants, groceries, etc.", "color": "#FF6B6B"},
            {"name": "Transportation", "description": "Gas, public transport, etc.", "color": "#4ECDC4"},
            {"name": "Shopping", "description": "Clothes, electronics, etc.", "color": "#45B7D1"},
            {"name": "Entertainment", "description": "Movies, games, etc.", "color": "#96CEB4"},
            {"name": "Bills & Utilities", "description": "Rent, electricity, phone, etc.", "color": "#FFEAA7"},
            {"name": "Healthcare", "description": "Medical expenses, insurance", "color": "#DDA0DD"},
            {"name": "Education", "description": "Books, courses, etc.", "color": "#98D8C8"},
            {"name": "Travel", "description": "Vacations, trips", "color": "#F7DC6F"},
            {"name": "Other", "description": "Miscellaneous expenses", "color": "#BB8FCE"}
        ]

        for cat_data in default_categories:
            # Check if category already exists
            existing = session.query(Category).filter_by(name=cat_data["name"]).first()
            if not existing:
                category = Category(**cat_data)
                session.add(category)

        session.commit()
        session.close()

# Global database instance
db = Database()

if __name__ == "__main__":
    # Create tables and initialize default data when run directly
    db.create_tables()
    db.init_default_categories()
    print("Database initialized successfully!")
