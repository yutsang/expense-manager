"""
Expense Manager iOS App using Toga (BeeWare)
"""

import toga
from toga.style import Pack
from toga.style.pack import ROW, COLUMN, CENTER, LEFT, RIGHT
from toga.colors import WHITE, BLACK, GRAY

from models import ExpenseModel, CategoryModel, AnalyticsModel
from database import db
import datetime


class ExpenseManagerApp(toga.App):
    """Main iOS application class."""

    def startup(self):
        """Initialize the app."""
        # Initialize database
        db.create_tables()
        db.init_default_categories()

        # Create main container
        self.main_box = toga.Box(style=Pack(direction=COLUMN))

        # Create tab container
        self.tab_container = toga.Box(style=Pack(direction=COLUMN, flex=1))

        # Create navigation buttons
        nav_box = toga.Box(style=Pack(direction=ROW, padding=10))
        self.add_expense_btn = toga.Button(
            "Add Expense",
            on_press=self.show_add_expense,
            style=Pack(flex=1, padding=10, background_color="#007AFF")
        )
        self.expenses_btn = toga.Button(
            "Expenses",
            on_press=self.show_expenses,
            style=Pack(flex=1, padding=10, background_color=GRAY)
        )
        self.analytics_btn = toga.Button(
            "Analytics",
            on_press=self.show_analytics,
            style=Pack(flex=1, padding=10, background_color=GRAY)
        )

        nav_box.add(self.add_expense_btn)
        nav_box.add(self.expenses_btn)
        nav_box.add(self.analytics_btn)

        self.main_box.add(nav_box)
        self.main_box.add(self.tab_container)

        # Start with add expense view
        self.show_add_expense()

        # Create and show main window
        self.main_window = toga.MainWindow(title="Expense Manager")
        self.main_window.content = self.main_box
        self.main_window.show()

    def show_add_expense(self, widget=None):
        """Show the add expense form."""
        # Clear current content
        self.tab_container.clear()

        # Update button colors
        self.add_expense_btn.style.background_color = "#007AFF"
        self.expenses_btn.style.background_color = GRAY
        self.analytics_btn.style.background_color = GRAY

        # Create form
        form_box = toga.Box(style=Pack(direction=COLUMN, padding=20))

        # Amount input
        amount_label = toga.Label("Amount ($):", style=Pack(padding=(5, 0)))
        self.amount_input = toga.TextInput(
            placeholder="0.00",
            style=Pack(padding=5, width=200)
        )

        # Description input
        desc_label = toga.Label("Description:", style=Pack(padding=(10, 0)))
        self.desc_input = toga.TextInput(
            placeholder="What did you spend on?",
            style=Pack(padding=5, width=300)
        )

        # Category selection
        category_label = toga.Label("Category:", style=Pack(padding=(10, 0)))
        self.category_box = toga.Box(style=Pack(direction=ROW, padding=5))
        self.category_input = toga.Selection()
        self.load_categories()
        self.category_box.add(self.category_input)

        # Date input
        date_label = toga.Label("Date:", style=Pack(padding=(10, 0)))
        self.date_input = toga.DatePicker()
        self.date_input.value = datetime.date.today()

        # Payment method
        payment_label = toga.Label("Payment Method:", style=Pack(padding=(10, 0)))
        self.payment_input = toga.Selection(items=["Cash", "Credit Card", "Debit Card", "Bank Transfer", "Other"])

        # Location input
        location_label = toga.Label("Location (optional):", style=Pack(padding=(10, 0)))
        self.location_input = toga.TextInput(placeholder="Where?", style=Pack(padding=5, width=300))

        # Notes input
        notes_label = toga.Label("Notes (optional):", style=Pack(padding=(10, 0)))
        self.notes_input = toga.TextInput(
            placeholder="Additional notes...",
            style=Pack(padding=5, width=300, height=80)
        )

        # Add form elements
        form_box.add(amount_label)
        form_box.add(self.amount_input)
        form_box.add(desc_label)
        form_box.add(self.desc_input)
        form_box.add(category_label)
        form_box.add(self.category_box)
        form_box.add(date_label)
        form_box.add(self.date_input)
        form_box.add(payment_label)
        form_box.add(self.payment_input)
        form_box.add(location_label)
        form_box.add(self.location_input)
        form_box.add(notes_label)
        form_box.add(self.notes_input)

        # Buttons
        button_box = toga.Box(style=Pack(direction=ROW, padding=20))
        save_btn = toga.Button(
            "Save Expense",
            on_press=self.save_expense,
            style=Pack(flex=1, padding=10, background_color="#34C759")
        )
        clear_btn = toga.Button(
            "Clear",
            on_press=self.clear_form,
            style=Pack(flex=1, padding=10, background_color=GRAY)
        )

        button_box.add(save_btn)
        button_box.add(clear_btn)
        form_box.add(button_box)

        self.tab_container.add(form_box)

    def show_expenses(self, widget=None):
        """Show the expenses list."""
        # Clear current content
        self.tab_container.clear()

        # Update button colors
        self.add_expense_btn.style.background_color = GRAY
        self.expenses_btn.style.background_color = "#007AFF"
        self.analytics_btn.style.background_color = GRAY

        # Get expenses
        try:
            expenses = ExpenseModel.get_expenses()
        except Exception as e:
            self.show_error(f"Failed to load expenses: {str(e)}")
            return

        # Create expenses list
        expenses_box = toga.Box(style=Pack(direction=COLUMN, padding=20))

        # Search and filter
        search_box = toga.Box(style=Pack(direction=ROW, padding=(0, 0, 10, 0)))
        self.search_input = toga.TextInput(
            placeholder="Search expenses...",
            on_change=self.filter_expenses,
            style=Pack(flex=1)
        )
        search_box.add(self.search_input)

        expenses_box.add(search_box)

        # Expenses list
        self.expenses_list = toga.Box(style=Pack(direction=COLUMN))
        self.display_expenses(expenses)
        expenses_box.add(self.expenses_list)

        # Action buttons
        action_box = toga.Box(style=Pack(direction=ROW, padding=10))
        refresh_btn = toga.Button(
            "Refresh",
            on_press=self.refresh_expenses,
            style=Pack(flex=1, padding=5)
        )
        action_box.add(refresh_btn)

        expenses_box.add(action_box)
        self.tab_container.add(expenses_box)

    def show_analytics(self, widget=None):
        """Show analytics and reports."""
        # Clear current content
        self.tab_container.clear()

        # Update button colors
        self.add_expense_btn.style.background_color = GRAY
        self.expenses_btn.style.background_color = GRAY
        self.analytics_btn.style.background_color = "#007AFF"

        analytics_box = toga.Box(style=Pack(direction=COLUMN, padding=20))

        # Month selection
        month_box = toga.Box(style=Pack(direction=ROW, padding=(0, 0, 10, 0)))
        month_label = toga.Label("Select Month:", style=Pack(padding=(0, 10)))
        month_box.add(month_label)

        self.month_input = toga.Selection()
        current_date = datetime.datetime.now()
        for i in range(12):
            date = current_date.replace(month=current_date.month - i)
            month_name = date.strftime("%B %Y")
            self.month_input.items.append(month_name)

        self.month_input.items = self.month_input.items[::-1]  # Reverse to show oldest first
        month_box.add(self.month_input)
        analytics_box.add(month_box)

        # Analytics content
        self.analytics_content = toga.Box(style=Pack(direction=COLUMN, padding=10))
        analytics_box.add(self.analytics_content)

        # Refresh button
        refresh_btn = toga.Button(
            "Show Analytics",
            on_press=self.refresh_analytics,
            style=Pack(padding=10, background_color="#007AFF")
        )
        analytics_box.add(refresh_btn)

        self.tab_container.add(analytics_box)

    def load_categories(self):
        """Load categories into the selection widget."""
        try:
            categories = CategoryModel.get_all_categories()
            self.category_input.items.clear()

            for category in categories:
                self.category_input.items.append(f"{category.name} - {category.description}")
        except Exception as e:
            self.show_error(f"Failed to load categories: {str(e)}")

    def save_expense(self, widget):
        """Save a new expense."""
        try:
            # Get form data
            amount_text = self.amount_input.value.strip()
            if not amount_text:
                self.show_error("Please enter an amount")
                return

            amount = float(amount_text)
            description = self.desc_input.value.strip()
            if not description:
                self.show_error("Please enter a description")
                return

            category_index = self.category_input.selected_index
            if category_index < 0:
                self.show_error("Please select a category")
                return

            # Get category ID (this is a simplified approach)
            categories = CategoryModel.get_all_categories()
            if category_index < len(categories):
                category_id = categories[category_index].id
            else:
                self.show_error("Invalid category selection")
                return

            expense_date = self.date_input.value
            payment_method = self.payment_input.value
            location = self.location_input.value.strip()
            notes = self.notes_input.value.strip()

            # Save expense
            expense = ExpenseModel.add_expense(
                amount=amount,
                description=description,
                category_id=category_id,
                expense_date=expense_date,
                payment_method=payment_method,
                location=location,
                notes=notes
            )

            # Show success message
            self.show_message("Success", "Expense saved successfully!")

            # Clear form and switch to expenses view
            self.clear_form()
            self.show_expenses()

        except ValueError:
            self.show_error("Please enter a valid amount")
        except Exception as e:
            self.show_error(f"Failed to save expense: {str(e)}")

    def clear_form(self, widget=None):
        """Clear the add expense form."""
        self.amount_input.value = ""
        self.desc_input.value = ""
        self.category_input.selected_index = -1
        self.date_input.value = datetime.date.today()
        self.payment_input.selected_index = 0
        self.location_input.value = ""
        self.notes_input.value = ""

    def display_expenses(self, expenses):
        """Display expenses in the list."""
        self.expenses_list.clear()

        if not expenses:
            no_data_label = toga.Label(
                "No expenses found",
                style=Pack(padding=20, text_align=CENTER)
            )
            self.expenses_list.add(no_data_label)
            return

        for expense in expenses:
            expense_box = toga.Box(
                style=Pack(direction=ROW, padding=10, background_color="#F0F0F0")
            )

            # Expense info
            info_box = toga.Box(style=Pack(direction=COLUMN))

            date_str = expense.date.strftime("%Y-%m-%d")
            category_name = expense.category.name if expense.category else "Unknown"
            amount_str = f"${expense.amount".2f"}"

            title_label = toga.Label(
                f"{date_str} - {category_name}",
                style=Pack(font_weight="bold")
            )
            desc_label = toga.Label(expense.description)
            amount_label = toga.Label(
                amount_str,
                style=Pack(text_align=RIGHT, color="#34C759", font_weight="bold")
            )

            info_box.add(title_label)
            info_box.add(desc_label)

            expense_box.add(info_box)
            expense_box.add(amount_label)

            self.expenses_list.add(expense_box)

    def filter_expenses(self, widget):
        """Filter expenses based on search text."""
        search_text = self.search_input.value.lower()

        try:
            expenses = ExpenseModel.get_expenses()

            if search_text:
                filtered_expenses = []
                for expense in expenses:
                    if (search_text in expense.description.lower() or
                        search_text in expense.category.name.lower() if expense.category else False):
                        filtered_expenses.append(expense)
                expenses = filtered_expenses

            self.display_expenses(expenses)

        except Exception as e:
            self.show_error(f"Failed to filter expenses: {str(e)}")

    def refresh_expenses(self, widget):
        """Refresh the expenses list."""
        self.show_expenses()

    def refresh_analytics(self, widget):
        """Refresh analytics display."""
        self.analytics_content.clear()

        try:
            # Get selected month
            selected_month = self.month_input.value
            if not selected_month:
                self.show_error("Please select a month")
                return

            # Parse month name to get year and month
            # This is a simplified approach - in a real app you'd want better date handling
            current_year = datetime.datetime.now().year
            month_names = [
                "January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December"
            ]

            month_index = month_names.index(selected_month.split()[0])
            year = current_year if month_index <= datetime.datetime.now().month else current_year - 1

            # Get analytics data
            monthly_data = AnalyticsModel.get_monthly_expenses(year, month_index + 1)

            if monthly_data.empty:
                no_data_label = toga.Label(
                    f"No expense data for {selected_month}",
                    style=Pack(padding=20, text_align=CENTER)
                )
                self.analytics_content.add(no_data_label)
                return

            # Display summary
            total_amount = monthly_data['total'].sum()
            summary_label = toga.Label(
                f"Total spent in {selected_month}: ${total_amount".2f"}",
                style=Pack(font_weight="bold", padding=(0, 0, 20, 0))
            )
            self.analytics_content.add(summary_label)

            # Display category breakdown
            for _, row in monthly_data.iterrows():
                category_box = toga.Box(style=Pack(direction=ROW, padding=5))
                category_label = toga.Label(
                    f"{row['category']}: ${row['total']".2f"} ({row['count']} expenses)",
                    style=Pack(flex=1)
                )
                category_box.add(category_label)
                self.analytics_content.add(category_box)

        except Exception as e:
            self.show_error(f"Failed to load analytics: {str(e)}")

    def show_message(self, title, message):
        """Show an information message."""
        # In a real iOS app, you'd use toga's dialog system
        print(f"{title}: {message}")

    def show_error(self, message):
        """Show an error message."""
        print(f"Error: {message}")

        # In a real iOS app, you'd show a proper dialog
        error_label = toga.Label(
            message,
            style=Pack(padding=10, color="red")
        )
        self.tab_container.add(error_label)


def main():
    """Main application entry point."""
    return ExpenseManagerApp("Expense Manager", "com.expensemanager.app")


if __name__ == "__main__":
    app = main()
    app.main_loop()
