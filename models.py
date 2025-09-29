"""
Data models and business logic for the Expense Manager application.
"""

from database import Expense, Category, db
from datetime import datetime, date
from typing import List, Optional
from sqlalchemy.orm import joinedload
import pandas as pd

class ExpenseModel:
    """Model class for expense operations."""

    @staticmethod
    def add_expense(amount: float, description: str, category_id: int,
                   expense_date: datetime = None, payment_method: str = None,
                   location: str = None, notes: str = None) -> Expense:
        """Add a new expense to the database."""
        session = db.get_session()

        if expense_date is None:
            expense_date = datetime.now()

        expense = Expense(
            amount=amount,
            description=description,
            category_id=category_id,
            date=expense_date,
            payment_method=payment_method,
            location=location,
            notes=notes
        )

        session.add(expense)
        session.commit()
        session.refresh(expense)
        session.close()

        return expense

    @staticmethod
    def get_expenses(start_date: datetime = None, end_date: datetime = None,
                    category_id: int = None) -> List[Expense]:
        """Get expenses with optional filtering."""
        session = db.get_session()

        query = session.query(Expense)

        if start_date:
            query = query.filter(Expense.date >= start_date)
        if end_date:
            query = query.filter(Expense.date <= end_date)
        if category_id:
            query = query.filter(Expense.category_id == category_id)

        expenses = query.all()
        session.close()

        return expenses

    @staticmethod
    def update_expense(expense_id: int, **kwargs) -> bool:
        """Update an existing expense."""
        session = db.get_session()

        expense = session.query(Expense).filter_by(id=expense_id).first()
        if not expense:
            session.close()
            return False

        for key, value in kwargs.items():
            if hasattr(expense, key):
                setattr(expense, key, value)

        expense.updated_at = datetime.now()
        session.commit()
        session.close()

        return True

    @staticmethod
    def delete_expense(expense_id: int) -> bool:
        """Delete an expense."""
        session = db.get_session()

        expense = session.query(Expense).filter_by(id=expense_id).first()
        if not expense:
            session.close()
            return False

        session.delete(expense)
        session.commit()
        session.close()

        return True

    @staticmethod
    def get_expenses_dataframe(start_date: datetime = None, end_date: datetime = None,
                              category_id: int = None) -> pd.DataFrame:
        """Get expenses as a pandas DataFrame for analysis."""
        session = db.get_session()

        query = session.query(Expense).options(joinedload(Expense.category))

        if start_date:
            query = query.filter(Expense.date >= start_date)
        if end_date:
            query = query.filter(Expense.date <= end_date)
        if category_id:
            query = query.filter(Expense.category_id == category_id)

        expenses = query.all()
        session.close()

        if not expenses:
            return pd.DataFrame()

        data = []
        for expense in expenses:
            data.append({
                'id': expense.id,
                'amount': expense.amount,
                'description': expense.description,
                'date': expense.date,
                'category': expense.category.name if expense.category else 'Unknown',
                'payment_method': expense.payment_method or '',
                'location': expense.location or '',
                'notes': expense.notes or ''
            })

        return pd.DataFrame(data)

class CategoryModel:
    """Model class for category operations."""

    @staticmethod
    def get_all_categories() -> List[Category]:
        """Get all categories."""
        session = db.get_session()
        categories = session.query(Category).all()
        session.close()
        return categories

    @staticmethod
    def add_category(name: str, description: str = None, color: str = None) -> Category:
        """Add a new category."""
        session = db.get_session()

        category = Category(
            name=name,
            description=description,
            color=color
        )

        session.add(category)
        session.commit()
        session.refresh(category)
        session.close()

        return category

    @staticmethod
    def get_category_by_id(category_id: int) -> Optional[Category]:
        """Get a category by ID."""
        session = db.get_session()
        category = session.query(Category).filter_by(id=category_id).first()
        session.close()
        return category

    @staticmethod
    def get_expenses_by_category(category_id: int) -> List[Expense]:
        """Get all expenses for a specific category."""
        session = db.get_session()
        category = session.query(Category).filter_by(id=category_id).first()

        if not category:
            session.close()
            return []

        expenses = category.expenses
        session.close()
        return expenses

class AnalyticsModel:
    """Model class for analytics and reporting."""

    @staticmethod
    def get_monthly_expenses(year: int, month: int) -> pd.DataFrame:
        """Get expenses grouped by category for a specific month."""
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1)
        else:
            end_date = datetime(year, month + 1, 1)

        expenses_df = ExpenseModel.get_expenses_dataframe(start_date, end_date)

        if expenses_df.empty:
            return pd.DataFrame()

        # Group by category and calculate totals
        monthly_summary = expenses_df.groupby('category').agg({
            'amount': 'sum',
            'date': 'count'
        }).rename(columns={'date': 'count', 'amount': 'total'}).reset_index()

        return monthly_summary

    @staticmethod
    def get_category_totals(start_date: datetime = None, end_date: datetime = None) -> pd.DataFrame:
        """Get total expenses by category."""
        expenses_df = ExpenseModel.get_expenses_dataframe(start_date, end_date)

        if expenses_df.empty:
            return pd.DataFrame()

        category_totals = expenses_df.groupby('category')['amount'].sum().reset_index()
        category_totals = category_totals.sort_values('amount', ascending=False)

        return category_totals

    @staticmethod
    def get_daily_expenses(days: int = 30) -> pd.DataFrame:
        """Get daily expense totals for the last N days."""
        end_date = datetime.now()
        start_date = end_date.replace(day=end_date.day - days)

        expenses_df = ExpenseModel.get_expenses_dataframe(start_date, end_date)

        if expenses_df.empty:
            return pd.DataFrame()

        # Group by date and sum amounts
        daily_totals = expenses_df.groupby(expenses_df['date'].dt.date)['amount'].sum().reset_index()
        daily_totals['date'] = pd.to_datetime(daily_totals['date'])

        return daily_totals
