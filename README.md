# Expense Manager - iOS App

A comprehensive expense tracking application built with Python and Toga (BeeWare), designed specifically for iOS devices and ready for App Store distribution.

## Features

### Core Functionality
- ✅ **Add Expenses**: Record your daily expenses with detailed information
- ✅ **Expense Management**: View, search, and filter your expense history
- ✅ **Category System**: Organize expenses with customizable categories
- ✅ **Analytics & Reports**: Visualize your spending patterns with interactive charts
- ✅ **Search & Filter**: Find specific expenses quickly with search and filtering options

### Data Management
- SQLite database for local storage
- Automatic database initialization with default categories
- Data export capabilities (CSV, PDF) - *Coming Soon*
- Backup and restore functionality - *Coming Soon*

### User Interface
- Native iOS interface built with Toga (BeeWare)
- Optimized for iPhone and iPad
- Touch-friendly interface with smooth animations
- Native iOS design patterns and user experience

## iOS App Development & Distribution

### Professional Development Environment

#### IDE and Tools
- **Xcode** (Primary IDE) - Apple's official iOS development environment
- **Visual Studio Code** (Secondary) - For Python code editing and Git integration
- **Android Studio** (Optional) - For cross-platform testing if expanding to Android

#### Development Setup
```bash
# Install Xcode from Mac App Store (free)
# Xcode includes iOS Simulator and all iOS SDKs

# Install VS Code
# https://code.visualstudio.com/

# Python environment (already set up)
python3 -m venv expense_manager_env
source expense_manager_env/bin/activate
pip install toga-ios briefcase
```

#### Prerequisites for Development
- macOS with Apple Silicon (M1/M2/M3 chip) or Intel Mac
- Xcode (latest version from Mac App Store)
- Apple Developer account (for App Store distribution)
- Python 3.8 or higher

#### Prerequisites for App Store Distribution
- Paid Apple Developer Program membership ($99/year)
- iOS devices for testing (iPhone/iPad)
- App Store Connect account (free)

### Development Setup

1. **Clone the project**:
   ```bash
   git clone <repository-url>
   cd expense-manager
   ```

2. **Set up the virtual environment**:
   ```bash
   python3 -m venv expense_manager_env
   source expense_manager_env/bin/activate
   ```

3. **Install BeeWare tools**:
   ```bash
   pip install toga-ios briefcase
   ```

4. **Install additional dependencies**:
   ```bash
   pip install sqlalchemy pandas matplotlib python-dateutil
   ```

5. **Test the app on iOS Simulator**:
   ```bash
   briefcase run iOS
   ```

### App Store Distribution Process

1. **Create an Apple Developer account** at developer.apple.com

2. **Configure app signing**:
   - Create an App ID in your Apple Developer account
   - Generate development and distribution certificates
   - Create a provisioning profile

3. **Build for distribution**:
   ```bash
   briefcase build iOS --adhoc
   ```

4. **Test on real devices**:
   - Install the app on your iOS devices
   - Test all functionality thoroughly

5. **Submit to App Store**:
   - Create an app record in App Store Connect
   - Upload screenshots and app metadata
   - Submit for review

### Version Management with Git and GitHub

#### Git Workflow (Industry Standard)
```bash
# Initialize Git repository (if not already done)
git init

# Create .gitignore for Python and iOS projects
curl https://raw.githubusercontent.com/github/gitignore/main/Python.gitignore > .gitignore
# Add iOS-specific ignores to .gitignore:
echo "
# iOS
*.ipa
*.dSYM.zip
*.dSYM
*.swp
*.lock
*.tmp
*.temp
# Xcode
*.pbxuser
!default.pbxuser
*.mode1v3
!default.mode1v3
*.mode2v3
!default.mode2v3
*.perspectivev3
!default.perspectivev3
xcuserdata/
*.moved-aside
*.xccheckout
*.xcscmblueprint
# Briefcase
build/
dist/
*.app
" >> .gitignore

# Initial commit
git add .
git commit -m "Initial commit: iOS Expense Manager app with Toga/BeeWare"

# Create feature branches
git checkout -b feature/add-receipt-scanning
# Work on feature...
git add .
git commit -m "Add receipt scanning with OCR"
git checkout main
git merge feature/add-receipt-scanning
```

#### GitHub Repository Setup
1. **Create repository** on GitHub.com
2. **Add remote origin**:
   ```bash
   git remote add origin https://github.com/yourusername/expense-manager.git
   git push -u origin main
   ```

3. **Branch Strategy**:
   - `main` - Production-ready code
   - `develop` - Integration branch for features
   - `feature/*` - Individual feature branches
   - `hotfix/*` - Urgent bug fixes
   - `release/*` - Release preparation

#### Pull Request Workflow
```bash
# Create pull request on GitHub
# Code review process
# Automated checks run (CI/CD)
# Merge after approval
```

### Testing Strategy

#### Local Testing
```bash
# Test on iOS Simulator
briefcase run iOS

# Test on multiple iOS versions
briefcase run iOS --device "iPhone 14 Pro"
briefcase run iOS --device "iPad Pro"

# Test on connected devices
briefcase run iOS --udid DEVICE_UDID
```

#### Unit Testing Setup
```python
# Create tests/test_expense_manager.py
import unittest
from models import ExpenseModel, CategoryModel

class TestExpenseModel(unittest.TestCase):
    def test_add_expense(self):
        # Test expense creation
        pass

    def test_get_expenses(self):
        # Test expense retrieval
        pass

# Run tests
python -m unittest tests.test_expense_manager
```

#### Integration Testing
- Test database operations
- Test API integrations (if any)
- Test app startup and navigation

### CI/CD Pipeline

#### GitHub Actions Setup
Create `.github/workflows/ios-build.yml`:
```yaml
name: iOS Build and Test

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: macos-latest
    steps:
    - uses: actions/checkout@v3
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.9'
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install toga-ios briefcase
    - name: Run tests
      run: python test_app.py
    - name: Build iOS app
      run: briefcase build iOS

  deploy:
    needs: test
    runs-on: macos-latest
    if: github.ref == 'refs/heads/main'
    steps:
    - name: Package for distribution
      run: briefcase package iOS --adhoc
```

#### Automated Deployment
- **TestFlight**: Automatic beta distribution
- **App Store**: Automated submission after approval
- **Crash Reporting**: Integration with services like Crashlytics

### Industry Best Practices

#### Code Quality
- **Linting**: Use flake8, black for Python code
- **Type Hints**: Add type annotations for better IDE support
- **Documentation**: Docstrings for all functions and classes
- **Code Reviews**: Mandatory for all changes

#### Security
- **Code Signing**: Proper certificate management
- **Data Encryption**: Encrypt sensitive user data
- **API Security**: Secure communication with external services
- **Privacy Compliance**: GDPR, CCPA compliance

#### Performance
- **Memory Management**: Monitor and optimize memory usage
- **Battery Optimization**: Efficient background processing
- **Network Efficiency**: Optimize API calls and data usage
- **UI Responsiveness**: Smooth 60fps animations

#### User Experience
- **Accessibility**: Support for VoiceOver, larger text
- **Internationalization**: Multi-language support
- **Dark Mode**: Native dark theme support
- **Haptic Feedback**: Tactile user feedback

### Development Workflow

#### Daily Development
1. **Pull latest changes**: `git pull origin main`
2. **Create feature branch**: `git checkout -b feature/new-feature`
3. **Develop and test locally**
4. **Commit changes**: `git add . && git commit -m "Add new feature"`
5. **Push and create PR**: `git push origin feature/new-feature`
6. **Code review and merge**

#### Release Process
1. **Version bump**: Update version in `pyproject.toml`
2. **Create release branch**: `git checkout -b release/v1.1.0`
3. **Final testing**: Comprehensive testing suite
4. **Tag release**: `git tag -a v1.1.0 -m "Release version 1.1.0"`
5. **Build for distribution**: `briefcase build iOS --release`
6. **Submit to App Store**

### Monitoring and Analytics

#### Crash Reporting
```python
# Integrate with Crashlytics or similar service
try:
    # App code
    pass
except Exception as e:
    # Report crash
    crash_reporter.report(e)
```

#### User Analytics
- Track feature usage
- Monitor performance metrics
- User journey analysis
- A/B testing capabilities

### App Store Optimization (ASO)

#### Metadata Optimization
- **Keywords**: Research and optimize app store keywords
- **Screenshots**: High-quality screenshots for all devices
- **App Preview**: Video demonstrations
- **Description**: Clear, benefit-focused description
- **Reviews**: Encourage and respond to user reviews

#### Marketing Strategy
- **Beta Testing**: TestFlight for early feedback
- **Social Proof**: User testimonials and ratings
- **Content Marketing**: Blog posts about expense management
- **App Store Features**: Aim for "App of the Day" features

### Default Categories
The application comes with pre-configured categories:
- Food & Dining 🍽️
- Transportation 🚗
- Shopping 🛍️
- Entertainment 🎬
- Bills & Utilities 💡
- Healthcare ⚕️
- Education 📚
- Travel ✈️
- Other 📦

## Usage Guide

### Adding Expenses
1. Tap the "Add Expense" button at the bottom
2. Fill in the expense details:
   - **Amount**: Enter the expense amount (supports decimals)
   - **Description**: Describe what the expense was for
   - **Category**: Select from available categories
   - **Date**: Choose the date of the expense (defaults to today)
   - **Payment Method**: How you paid (Cash, Credit Card, etc.)
   - **Location**: Where the expense occurred (optional)
   - **Notes**: Additional notes (optional)
3. Tap "Save Expense" to save

### Viewing and Managing Expenses
1. Tap the "Expenses" button at the bottom
2. Browse through your expense history
3. **Search**: Use the search field to find specific expenses
4. **Pull to refresh**: Swipe down to reload the expenses list

### Analytics and Reports
1. Tap the "Analytics" button at the bottom
2. Select a month to view spending patterns
3. View the breakdown showing expense distribution by category
4. See total spending for the selected month

## Project Structure

```
expense-manager/
├── app.py              # Main iOS application using Toga
├── database.py         # Database models and connection
├── models.py          # Business logic and data models
├── pyproject.toml     # Briefcase configuration for iOS builds
├── expense_manager.db # SQLite database (auto-created)
└── README.md          # This file
```

## Technical Details

### Technologies Used
- **iOS Framework**: Toga (BeeWare) with native iOS APIs
- **Database**: SQLite with SQLAlchemy ORM
- **Data Analysis**: Pandas (for analytics calculations)
- **Date Handling**: python-dateutil
- **Build System**: Briefcase for iOS packaging and distribution

### Architecture
- **Native iOS App**: Built with Python but runs as native iOS app
- **MVC Pattern**: Separated concerns with Models, Views, and Controllers
- **Database Layer**: SQLAlchemy for database operations
- **Business Logic**: Separate model classes for different operations
- **Cross-platform Ready**: Same codebase can run on macOS, Linux, and Windows

## Development

### Adding New Features
1. Database changes: Modify `database.py`
2. Business logic: Add methods to appropriate model classes in `models.py`
3. UI changes: Modify `app.py` for iOS interface updates

### Customization
- **Categories**: Add new categories in `database.py` or through the application
- **UI Styling**: Modify colors and styling in `app.py`
- **Analytics**: Extend analytics features in `models.py`

### iOS-Specific Development

**Running on iOS Simulator:**
```bash
briefcase run iOS
```

**Building for Distribution:**
```bash
briefcase build iOS
briefcase run iOS --adhoc
```

**Debugging:**
- Use Python's logging module for debugging
- Check Briefcase logs in the build directory
- Use Xcode's console when running on devices

## Troubleshooting

### Common iOS Development Issues

**Briefcase build fails:**
- Ensure Xcode is installed and updated
- Check that you have accepted Xcode license: `sudo xcodebuild -license accept`
- Verify your Apple Developer account is properly configured

**iOS Simulator won't start:**
- Restart your Mac
- Reset iOS Simulator: Delete `~/Library/Developer/CoreSimulator/Caches`
- Ensure iOS Simulator is compatible with your macOS version

**App crashes on device:**
- Check device logs using Xcode's Devices and Simulators window
- Ensure your device is running iOS 12.0 or later
- Verify provisioning profile is correctly installed

**Database errors:**
- Delete `expense_manager.db` and restart the app (will recreate with defaults)
- Check file permissions in the app's documents directory

**Import errors:**
- Make sure you're running from the virtual environment
- Try reinstalling dependencies: `pip install -r requirements.txt`

### Getting Help
- Check the console output for error messages
- Ensure all dependencies are up to date
- Verify your Python installation

## Future Enhancements

- [ ] Data export to CSV and PDF
- [ ] iCloud synchronization and backup
- [ ] Recurring expenses and reminders
- [ ] Budget tracking and alerts
- [ ] Multiple currencies with auto-conversion
- [ ] Receipt scanning with OCR
- [ ] Apple Watch companion app
- [ ] Dark mode theme
- [ ] Siri integration for voice expense entry
- [ ] Advanced analytics with charts and trends
- [ ] Expense categories with custom icons
- [ ] Location-based expense suggestions

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Contributing

Contributions are welcome! Please feel free to submit issues and enhancement requests.