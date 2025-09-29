"""
Unit tests for the Expense Manager application.
"""

import unittest
import os
import tempfile
from datetime import datetime, date
from database import db
from models import ExpenseModel, CategoryModel, AnalyticsModel


class TestExpenseManager(unittest.TestCase):
    """Test cases for the Expense Manager models."""

    def setUp(self):
        """Set up test database."""
        # Use in-memory database for testing
        self.test_db_path = ":memory:"
        self.original_db_path = db.db_path
        db.db_path = self.test_db_path
        db.engine = db.create_engine(f'sqlite:///{self.test_db_path}', echo=False)
        db.Session = db.sessionmaker(bind=db.engine)

        # Create tables
        db.create_tables()
        db.init_default_categories()

    def tearDown(self):
        """Clean up after tests."""
        # Restore original database path
        db.db_path = self.original_db_path

    def test_database_initialization(self):
        """Test that database initializes correctly."""
        categories = CategoryModel.get_all_categories()
        self.assertGreater(len(categories), 0, "Should have default categories")

        # Check for expected categories
        category_names = [cat.name for cat in categories]
        self.assertIn("Food & Dining", category_names)

    def test_add_expense(self):
        """Test adding a new expense."""
        categories = CategoryModel.get_all_categories()
        category_id = categories[0].id

        expense = ExpenseModel.add_expense(
            amount=25.50,
            description="Test lunch",
            category_id=category_id,
            expense_date=date.today(),
            payment_method="Credit Card",
            location="Test Restaurant"
        )

        self.assertIsNotNone(expense.id)
        self.assertEqual(expense.amount, 25.50)
        self.assertEqual(expense.description, "Test lunch")
        self.assertEqual(expense.category_id, category_id)

    def test_get_expenses(self):
        """Test retrieving expenses."""
        # Add test expense
        categories = CategoryModel.get_all_categories()
        category_id = categories[0].id

        ExpenseModel.add_expense(
            amount=10.00,
            description="Test expense 1",
            category_id=category_id,
            expense_date=date.today()
        )

        ExpenseModel.add_expense(
            amount=20.00,
            description="Test expense 2",
            category_id=category_id,
            expense_date=date.today()
        )

        # Test retrieving all expenses
        expenses = ExpenseModel.get_expenses()
        self.assertEqual(len(expenses), 2)

        # Test filtering by category
        category_expenses = ExpenseModel.get_expenses(category_id=category_id)
        self.assertEqual(len(category_expenses), 2)

    def test_update_expense(self):
        """Test updating an expense."""
        categories = CategoryModel.get_all_categories()
        category_id = categories[0].id

        # Add expense
        expense = ExpenseModel.add_expense(
            amount=15.00,
            description="Original description",
            category_id=category_id,
            expense_date=date.today()
        )

        # Update expense
        success = ExpenseModel.update_expense(
            expense.id,
            description="Updated description",
            amount=25.00
        )

        self.assertTrue(success)

        # Verify update
        updated_expenses = ExpenseModel.get_expenses()
        self.assertEqual(len(updated_expenses), 1)
        self.assertEqual(updated_expenses[0].description, "Updated description")
        self.assertEqual(updated_expenses[0].amount, 25.00)

    def test_delete_expense(self):
        """Test deleting an expense."""
        categories = CategoryModel.get_all_categories()
        category_id = categories[0].id

        # Add expense
        expense = ExpenseModel.add_expense(
            amount=30.00,
            description="To be deleted",
            category_id=category_id,
            expense_date=date.today()
        )

        # Delete expense
        success = ExpenseModel.delete_expense(expense.id)
        self.assertTrue(success)

        # Verify deletion
        expenses = ExpenseModel.get_expenses()
        self.assertEqual(len(expenses), 0)

    def test_analytics_monthly_expenses(self):
        """Test monthly analytics generation."""
        categories = CategoryModel.get_all_categories()

        # Add expenses in current month
        for i, category in enumerate(categories[:3]):  # Use first 3 categories
            ExpenseModel.add_expense(
                amount=10.00 + i,
                description=f"Test expense {i+1}",
                category_id=category.id,
                expense_date=date.today()
            )

        # Get analytics for current month
        current_year = datetime.now().year
        current_month = datetime.now().month

        monthly_data = AnalyticsModel.get_monthly_expenses(current_year, current_month)

        # Should have data for 3 categories
        self.assertEqual(len(monthly_data), 3)

        # Check total amount
        total_amount = monthly_data['total'].sum()
        expected_total = 10.00 + 11.00 + 12.00  # 33.00
        self.assertEqual(total_amount, expected_total)

    def test_category_operations(self):
        """Test category-related operations."""
        # Test getting all categories
        categories = CategoryModel.get_all_categories()
        initial_count = len(categories)

        # Test adding a new category
        new_category = CategoryModel.add_category(
            name="Test Category",
            description="A test category",
            color="#FF0000"
        )

        self.assertIsNotNone(new_category.id)
        self.assertEqual(new_category.name, "Test Category")

        # Verify category was added
        categories = CategoryModel.get_all_categories()
        self.assertEqual(len(categories), initial_count + 1)

        # Test getting category by ID
        retrieved_category = CategoryModel.get_category_by_id(new_category.id)
        self.assertIsNotNone(retrieved_category)
        self.assertEqual(retrieved_category.name, "Test Category")

        # Test getting expenses by category
        ExpenseModel.add_expense(
            amount=5.00,
            description="Category test expense",
            category_id=new_category.id,
            expense_date=date.today()
        )

        category_expenses = CategoryModel.get_expenses_by_category(new_category.id)
        self.assertEqual(len(category_expenses), 1)
        self.assertEqual(category_expenses[0].amount, 5.00)


if __name__ == '__main__':
    unittest.main()
