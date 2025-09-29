#!/usr/bin/env python3
"""
Test script to verify the Expense Manager app functionality.
"""

import sys
import os
from database import db
from models import ExpenseModel, CategoryModel, AnalyticsModel
from datetime import datetime, date

def test_database():
    """Test database initialization and basic operations."""
    print("Testing database initialization...")

    # Create tables
    db.create_tables()
    db.init_default_categories()

    # Test categories
    categories = CategoryModel.get_all_categories()
    print(f"✓ Created {len(categories)} default categories")

    # Test adding an expense
    expense = ExpenseModel.add_expense(
        amount=25.50,
        description="Test lunch expense",
        category_id=categories[0].id,  # Use first category
        expense_date=date.today(),
        payment_method="Credit Card",
        location="Test Restaurant"
    )
    print(f"✓ Added test expense: {expense.description} - ${expense.amount}")

    # Test retrieving expenses
    expenses = ExpenseModel.get_expenses()
    print(f"✓ Retrieved {len(expenses)} expenses")

    # Test analytics
    monthly_data = AnalyticsModel.get_monthly_expenses(datetime.now().year, datetime.now().month)
    print(f"✓ Generated monthly analytics with {len(monthly_data)} categories")

    print("✅ All database tests passed!")
    return True

def test_imports():
    """Test that all required modules can be imported."""
    print("Testing imports...")

    try:
        import toga
        from toga.style import Pack
        from toga.style.pack import ROW, COLUMN
        print("✓ Toga UI framework imported successfully")
    except ImportError as e:
        print(f"❌ Toga import failed: {e}")
        return False

    try:
        import sqlalchemy
        from sqlalchemy import create_engine
        print("✓ SQLAlchemy database framework imported successfully")
    except ImportError as e:
        print(f"❌ SQLAlchemy import failed: {e}")
        return False

    try:
        import pandas as pd
        import matplotlib
        print("✓ Data analysis libraries (pandas, matplotlib) imported successfully")
    except ImportError as e:
        print(f"❌ Data analysis libraries import failed: {e}")
        return False

    return True

def main():
    """Run all tests."""
    print("🚀 Testing Expense Manager App Setup")
    print("=" * 50)

    # Test imports
    if not test_imports():
        print("❌ Import tests failed. Please check your installation.")
        sys.exit(1)

    # Test database functionality
    if not test_database():
        print("❌ Database tests failed.")
        sys.exit(1)

    print("=" * 50)
    print("🎉 All tests passed! Your Expense Manager app is ready for iOS development.")
    print()
    print("Next steps:")
    print("1. Run 'briefcase run iOS' to test in iOS Simulator")
    print("2. Set up your Apple Developer account for App Store distribution")
    print("3. Configure iOS certificates and provisioning profiles")
    print("4. Build with 'briefcase build iOS' for device testing")

if __name__ == "__main__":
    main()
