# apps/demo_data/demo_data/loan_demo.py
import frappe
import json
import os
from frappe.utils import nowdate
from .demo import DEMO_DIR, _get_identity_value, _fill_required_fields, _resolve_links_for_doc

# Ensure DEMO_DIR is pointing to the correct path
DEMO_DIR = os.path.join(os.path.dirname(__file__), "sample_data", "data")

# Define dependency map for loan application
LOAN_APP_DEPENDENCIES = {
    "Loan Application": [
        {"doctype": "Company", "field": "company"},
        {"doctype": "Loan Product", "field": "loan_product"},
        {"doctype": "Customer", "field": "applicant", "condition": "applicant_type == 'Customer'"},
        {"doctype": "Employee", "field": "applicant", "condition": "applicant_type == 'Employee'"}
    ]
}

# Define mandatory fields for loan application (from doctype definition)
LOAN_APP_MANDATORY_FIELDS = [
    "applicant_type", "applicant", "company", "loan_product", "posting_date"
]

# Define conditional mandatory fields (based on applicant_type)
LOAN_APP_CONDITIONAL_MANDATORY_FIELDS = {
    "Customer": ["applicant_email_address", "applicant_phone_number"]
}

# Define all required JSON files for dependencies
REQUIRED_JSON_FILES = [
    "company.json",
    "customer.json", 
    "employee.json",
    "loan_product.json",
    "loan_application.json"
]

def check_dependencies(doctype, record):
    """Check if all dependencies for a record exist, return missing dependencies"""
    missing = []
    
    if doctype not in LOAN_APP_DEPENDENCIES:
        return missing
    
    for dep in LOAN_APP_DEPENDENCIES[doctype]:
        dep_doctype = dep["doctype"]
        field = dep["field"]
        condition = dep.get("condition")
        
        # Skip if condition is not met
        if condition:
            # Simple condition evaluation (only supports == operator)
            if "==" in condition:
                parts = condition.split("==")
                field_name = parts[0].strip()
                expected_value = parts[1].strip().strip("'\"")
                
                if record.get(field_name) != expected_value:
                    continue
        
        # Check if the dependency exists
        value = record.get(field)
        if not value:
            continue
        
        # Special handling for loan products - check by product_name instead of loan_product_name
        if dep_doctype == "Loan Product":
            # Check if loan product exists by product_name
            loan_product = frappe.get_all("Loan Product", 
                                        filters={"product_name": value},
                                        fields=["name"],
                                        limit=1)
            if loan_product:
                # It exists, so we don't need to add it to missing dependencies
                continue
        
        # Special handling for Employee lookup by employee_number or name
        if dep_doctype == "Employee":
            # Check if employee exists by employee_number and company
            company = record.get("company", "SCF")
            employee = frappe.get_all("Employee", 
                                    filters={"employee_number": value, "company": company},
                                    fields=["name"],
                                    limit=1)
            if employee:
                continue  # Employee exists, no need to add to missing
            
            # Also check if employee exists by name and company
            employee = frappe.get_all("Employee", 
                                    filters={"name": value, "company": company},
                                    fields=["name"],
                                    limit=1)
            if employee:
                continue  # Employee exists, no need to add to missing
        else:
            # For other doctypes, check if they exist
            exists = frappe.db.exists(dep_doctype, value)
            if exists:
                continue  # Exists, no need to add to missing
        
        # If we reach here, the dependency doesn't exist
        # Check if the dependency exists in the sample data
        dep_file = os.path.join(DEMO_DIR, f"{dep_doctype.lower().replace(' ', '_')}.json")
        if os.path.exists(dep_file):
            missing.append({
                "doctype": dep_doctype,
                "value": value,
                "file": dep_file
            })
        else:
            missing.append({
                "doctype": dep_doctype,
                "value": value,
                "file": None
            })
    
    return missing

def check_required_json_files():
    """Check if all required JSON files exist in the sample data directory"""
    missing_files = []
    
    for filename in REQUIRED_JSON_FILES:
        file_path = os.path.join(DEMO_DIR, filename)
        if not os.path.exists(file_path):
            missing_files.append(filename)
    
    return missing_files

def check_mandatory_fields(doctype, record):
    """Check if all mandatory fields are present in the record"""
    missing = []
    
    if doctype == "Loan Application":
        # Check basic mandatory fields
        for field in LOAN_APP_MANDATORY_FIELDS:
            if field not in record or not record[field]:
                missing.append(field)
        
        # Check conditional mandatory fields based on applicant_type
        applicant_type = record.get("applicant_type")
        if applicant_type in LOAN_APP_CONDITIONAL_MANDATORY_FIELDS:
            for field in LOAN_APP_CONDITIONAL_MANDATORY_FIELDS[applicant_type]:
                if field not in record or not record[field]:
                    missing.append(f"{field} (required for {applicant_type})")
    
    return missing

def validate_database_dependencies():
    """Validate that all required doctypes have data in the database"""
    errors = []
    
    # Check if companies exist
    companies = frappe.get_all("Company", fields=["name"], limit=1)
    if not companies:
        errors.append("No companies found in database. Please create at least one company.")
    
    # Check if customers exist
    customers = frappe.get_all("Customer", fields=["name"], limit=1)
    if not customers:
        errors.append("No customers found in database. Please create at least one customer.")
    
    # Check if loan products exist
    loan_products = frappe.get_all("Loan Product", fields=["name"], limit=1)
    if not loan_products:
        errors.append("No loan products found in database. Please create at least one loan product.")
    
    return {"valid": len(errors) == 0, "errors": errors}

def validate_account_dependencies():
    """Validate that all required accounts exist for loan products"""
    errors = []
    
    # Get companies used in loan applications
    loan_app_file = os.path.join(DEMO_DIR, "loan_application.json")
    used_companies = set()
    
    if os.path.exists(loan_app_file):
        try:
            with open(loan_app_file, "r", encoding="utf-8") as f:
                loan_apps = json.load(f)
                for app in loan_apps:
                    if app.get("company"):
                        used_companies.add(app["company"])
        except Exception as e:
            print(f"  ⚠️  Could not read loan application file: {e}")
    
    # If no companies found in loan apps, check all companies
    if not used_companies:
        companies = frappe.get_all("Company", fields=["name"])
        used_companies = {company.name for company in companies}
    
    if not used_companies:
        errors.append("No companies found to validate accounts")
        return {"valid": False, "errors": errors}
    
    for company_name in used_companies:
        print(f"  Checking accounts for company: {company_name}")
        
        # Check for required account types (only essential ones for loan products)
        required_account_types = [
            "Receivable", "Income Account", "Cash"
        ]
        
        missing_accounts = []
        for account_type in required_account_types:
            accounts = frappe.get_all("Account", 
                                    filters={
                                        "account_type": account_type,
                                        "company": company_name,
                                        "is_group": 0
                                    },
                                    fields=["name"],
                                    limit=1)
            if not accounts:
                missing_accounts.append(account_type)
        
        if missing_accounts:
            errors.append(f"Company '{company_name}' missing account types: {', '.join(missing_accounts)}")
    
    return {"valid": len(errors) == 0, "errors": errors}

def create_missing_dependencies():
    """Create missing dependencies automatically"""
    print("🔧 Creating missing dependencies...")
    
    # Create company if it doesn't exist
    companies = frappe.get_all("Company", fields=["name"], limit=1)
    if not companies:
        print("  Creating default company...")
        try:
            doc = frappe.get_doc({
                "doctype": "Company",
                "company_name": "SCF",
                "abbr": "SCF",
                "default_currency": "INR",
                "country": "India"
            })
            doc.insert(ignore_permissions=True)
            print("  ✅ Created company: SCF")
        except Exception as e:
            print(f"  ❌ Failed to create company: {e}")
            return False
    
    # Create customer if it doesn't exist
    customers = frappe.get_all("Customer", fields=["name"], limit=1)
    if not customers:
        print("  Creating default customer...")
        try:
            doc = frappe.get_doc({
                "doctype": "Customer",
                "customer_name": "Demo Customer",
                "customer_group": "Individual",
                "territory": "All Territories",
                "customer_type": "Individual"
            })
            doc.insert(ignore_permissions=True)
            print("  ✅ Created customer: Demo Customer")
        except Exception as e:
            print(f"  ❌ Failed to create customer: {e}")
            return False
    
    # Create basic accounts if they don't exist
    company = "SCF"
    print(f"  Creating basic accounts for {company}...")
    
    # Get company abbreviation
    company_abbr = frappe.get_cached_value("Company", company, "abbr") or "SCF"
    
    # Create basic accounts with proper parent accounts
    basic_accounts = [
        {"account_name": f"Debtors - {company_abbr}", "account_type": "Receivable", "parent_account": f"Accounts Receivable - {company_abbr}"},
        {"account_name": f"Sales - {company_abbr}", "account_type": "Income Account", "parent_account": f"Direct Income - {company_abbr}"},
        {"account_name": f"Cash - {company_abbr}", "account_type": "Cash", "parent_account": f"Cash In Hand - {company_abbr}"},
        {"account_name": f"Bank - {company_abbr}", "account_type": "Bank", "parent_account": f"Bank Accounts - {company_abbr}"},
        {"account_name": f"Expenses - {company_abbr}", "account_type": "Expense Account", "parent_account": f"Direct Expenses - {company_abbr}"},
    ]
    
    for account_data in basic_accounts:
        account_name = account_data["account_name"]
        if not frappe.db.exists("Account", account_name):
            try:
                # Try to find the parent account
                parent_account = account_data["parent_account"]
                if not frappe.db.exists("Account", parent_account):
                    # Create parent account as group
                    try:
                        parent_doc = frappe.get_doc({
                            "doctype": "Account",
                            "account_name": parent_account,
                            "account_type": account_data["account_type"],
                            "company": company,
                            "is_group": 1
                        })
                        parent_doc.insert(ignore_permissions=True)
                        print(f"  ✅ Created parent account: {parent_account}")
                    except Exception as e:
                        print(f"  ⚠️  Could not create parent account {parent_account}: {e}")
                        # Continue without parent
                        parent_account = None
                
                # Create the account
                doc = frappe.get_doc({
                    "doctype": "Account",
                    "account_name": account_name,
                    "account_type": account_data["account_type"],
                    "company": company,
                    "is_group": 0,
                    "parent_account": parent_account if parent_account else None
                })
                doc.insert(ignore_permissions=True)
                print(f"  ✅ Created account: {account_name}")
            except Exception as e:
                print(f"  ⚠️  Could not create account {account_name}: {e}")
    
    # Create loan product if it doesn't exist
    loan_products = frappe.get_all("Loan Product", fields=["name"], limit=1)
    if not loan_products:
        print("  Creating default loan product...")
        try:
            # Get account names - try to find existing accounts first
            receivable_account = None
            income_account = None
            cash_account = None
            
            # Try to find existing accounts
            accounts = frappe.get_all("Account", 
                                    filters={"company": company, "is_group": 0},
                                    fields=["name", "account_type"])
            
            for account in accounts:
                if account.account_type == "Receivable" and not receivable_account:
                    receivable_account = account.name
                elif account.account_type == "Income Account" and not income_account:
                    income_account = account.name
                elif account.account_type == "Cash" and not cash_account:
                    cash_account = account.name
            
            # If no income account found, use receivable account as fallback
            if not income_account:
                income_account = receivable_account
            
            # Fallback to default names if not found
            if not receivable_account:
                receivable_account = f"Debtors - {company_abbr}"
            if not income_account:
                income_account = receivable_account  # Use receivable as fallback
            if not cash_account:
                cash_account = f"Cash - {company_abbr}"
            
            doc = frappe.get_doc({
                "doctype": "Loan Product",
                "product_name": "Personal Loan",
                "product_code": "PERSONAL_LOAN",
                "is_term_loan": 1,
                "rate_of_interest": 12.0,
                "maximum_loan_amount": 500000,
                "company": company,
                "min_days_bw_disbursement_first_repayment": 30,
                "loan_account": receivable_account,
                "payment_account": cash_account,
                "interest_income_account": income_account,
                "penalty_income_account": income_account,
                "disbursement_account": cash_account,
                "security_deposit_account": receivable_account,
                "customer_refund_account": cash_account,
                "interest_accrued_account": receivable_account,
                "interest_waiver_account": income_account,
                "interest_receivable_account": receivable_account,
                "broken_period_interest_recovery_account": income_account,
                "penalty_accrued_account": receivable_account,
                "penalty_waiver_account": income_account,
                "penalty_receivable_account": receivable_account,
                "write_off_account": income_account,
                "write_off_recovery_account": income_account
            })
            doc.insert(ignore_permissions=True)
            print("  ✅ Created loan product: Personal Loan")
        except Exception as e:
            print(f"  ❌ Failed to create loan product: {e}")
            return False
    
    frappe.db.commit()
    print("✅ All missing dependencies created successfully!")
    return True

def validate_loan_application_setup():
    """Validate that all required files and dependencies are in place"""
    errors = []
    warnings = []
    
    print("🔍 Starting comprehensive validation...")
    
    # Check for missing JSON files
    print("📁 Checking for required JSON files...")
    missing_files = check_required_json_files()
    if missing_files:
        errors.append(f"❌ Missing required JSON files: {', '.join(missing_files)}")
        print(f"❌ Missing files: {', '.join(missing_files)}")
        return {"valid": False, "errors": errors, "warnings": warnings}
    print("✅ All required JSON files found")
    
    # Check if JSON files have valid data
    print("📄 Validating JSON file contents...")
    for filename in REQUIRED_JSON_FILES:
        file_path = os.path.join(DEMO_DIR, filename)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not data or not isinstance(data, list):
                    errors.append(f"❌ {filename} is empty or invalid format")
                    print(f"❌ {filename} is empty or invalid format")
                elif filename == "loan_application.json":
                    # Validate loan application records
                    for i, record in enumerate(data):
                        missing_fields = check_mandatory_fields("Loan Application", record)
                        if missing_fields:
                            errors.append(f"❌ {filename}[{i}]: Missing mandatory fields: {', '.join(missing_fields)}")
                            print(f"❌ {filename}[{i}]: Missing mandatory fields: {', '.join(missing_fields)}")
                else:
                    print(f"✅ {filename} has valid data ({len(data)} records)")
        except Exception as e:
            errors.append(f"❌ Error reading {filename}: {str(e)}")
            print(f"❌ Error reading {filename}: {str(e)}")
    
    # Check database dependencies
    print("🗄️ Checking database dependencies...")
    db_validation = validate_database_dependencies()
    if not db_validation["valid"]:
        errors.extend(db_validation["errors"])
        for error in db_validation["errors"]:
            print(f"❌ {error}")
    else:
        print("✅ All database dependencies satisfied")
    
    # Check account dependencies for loan products
    print("💰 Checking account dependencies...")
    account_validation = validate_account_dependencies()
    if not account_validation["valid"]:
        errors.extend(account_validation["errors"])
        for error in account_validation["errors"]:
            print(f"❌ {error}")
    else:
        print("✅ All account dependencies satisfied")
    
    if errors:
        print(f"\n❌ Validation failed with {len(errors)} errors")
        return {"valid": False, "errors": errors, "warnings": warnings}
    
    print("✅ All validations passed!")
    return {"valid": True, "errors": errors, "warnings": warnings}

def load_dependency_file(file_path, verbose=False):
    """Load a dependency file and insert records"""
    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            records = json.load(f)
        
        result = {"inserted": [], "errors": []}
        
        for rec in records:
            dt = rec.get("doctype")
            if not dt:
                continue
                
            # If there is already a doc for this identity, skip (idempotent)
            existing_name = _get_identity_value(dt, rec)
            if existing_name:
                if verbose:
                    print(f"Exists {dt} {existing_name} -> skipping")
                result["inserted"].append({"doctype": dt, "name": existing_name, "skipped": True})
                continue
            
            try:
                meta = frappe.get_meta(dt)
                # fill required fields for parent doc
                rec = _fill_required_fields(rec, meta)
                # resolve links and table children
                rec = _resolve_links_for_doc(rec, meta)
                
                # Special handling for loan product lookup
                if dt == "Loan Application" and rec.get("loan_product"):
                    # Check if loan product exists by loan_product_name
                    loan_product = frappe.get_all("Loan Product", 
                                                filters={"loan_product_name": rec["loan_product"]},
                                                fields=["name"],
                                                limit=1)
                    if loan_product:
                        # Replace loan_product field with the actual document name
                        rec["loan_product"] = loan_product[0].name
                    else:
                        # Try to create the loan product if it doesn't exist
                        result = create_loan_product(rec["loan_product"], verbose)
                        if "error" not in result and "name" in result:
                            rec["loan_product"] = result["name"]
                
                # insert
                doc = frappe.get_doc(rec)
                doc.insert(ignore_permissions=True)
                result["inserted"].append({"doctype": doc.doctype, "name": doc.name})
                if verbose:
                    print(f"Inserted {doc.doctype} {doc.name}")
            except Exception as e:
                error_msg = f"Failed to insert {dt}: {e}"
                if verbose:
                    print(error_msg)
                result["errors"].append({"record": rec, "error": error_msg})
        
        frappe.db.commit()
        return result
    except Exception as e:
        return {"error": str(e)}

def create_loan_product(name, verbose=False, company=None):
    """Create a loan product if it doesn't exist"""
    try:
        # Get company if not provided
        if not company:
            company = "SCF"  # Always default to SCF Company
            if verbose:
                print(f"Using default company: {company}")
                    
        # Ensure company exists
        if not frappe.db.exists("Company", company):
            if verbose:
                print(f"Company {company} does not exist, creating it")
            try:
                # Create a simple company
                doc = frappe.get_doc({
                    "doctype": "Company",
                    "company_name": company,
                    "abbr": ''.join([c[0] for c in company.split()]) or company[:3],
                    "default_currency": "INR",
                    "country": "India"
                })
                doc.insert(ignore_permissions=True)
                if verbose:
                    print(f"Created Company: {company}")
            except Exception as e:
                if verbose:
                    print(f"Failed to create Company {company}: {e}")
                # Continue anyway, as the company might exist with a different name
                
        # Check if loan product exists by product_name and company
        existing_products = frappe.get_all("Loan Product", 
                                        filters={
                                            "product_name": name,
                                            "company": company
                                        },
                                        fields=["name"])
        if existing_products:
            if verbose:
                print(f"Loan Product {name} already exists with name {existing_products[0].name}")
            return {"doctype": "Loan Product", "name": existing_products[0].name, "skipped": True}
        
        # If we're creating for SCF Company, use specific accounts
        if company == "SCF":
            # Find accounts by type
            receivable_account = None
            income_account = None
            cash_account = None
            expense_account = None
            
            # Try to find accounts by type
            accounts = frappe.get_all('Account', 
                                    filters={'company': company},
                                    fields=['name', 'account_type'])
            
            for account in accounts:
                if account.get('account_type') == 'Receivable':
                    receivable_account = account.get('name')
                elif account.get('account_type') == 'Bank':
                    cash_account = account.get('name')
                elif not income_account and account.get('name').endswith('- DC') and 'Income' in account.get('name'):
                    income_account = account.get('name')
            
            # If we couldn't find specific accounts, use some defaults
            if not receivable_account:
                receivable_account = "Debtors - SCF"
            if not income_account:
                income_account = "Sales - SCF"
            if not cash_account:
                cash_account = "Cash - SCF"
        else:
            # For other companies, try to find suitable accounts
            receivable_account = None
            income_account = None
            expense_account = None
            cash_account = None
            
            try:
                # Find a receivable account
                receivable_accounts = frappe.get_all("Account", 
                                                filters={
                                                    "account_type": "Receivable",
                                                    "company": company,
                                                    "is_group": 0
                                                },
                                                fields=["name"],
                                                limit=1)
                if receivable_accounts:
                    receivable_account = receivable_accounts[0].name
                    if verbose:
                        print(f"Using receivable account: {receivable_account}")
                
                # Find an income account
                income_accounts = frappe.get_all("Account", 
                                            filters={
                                                "account_type": "Income Account",
                                                "company": company,
                                                "is_group": 0
                                            },
                                            fields=["name"],
                                            limit=1)
                if income_accounts:
                    income_account = income_accounts[0].name
                    if verbose:
                        print(f"Using income account: {income_account}")
                
                # Find an expense account
                expense_accounts = frappe.get_all("Account", 
                                                filters={
                                                    "account_type": "Expense Account",
                                                    "company": company,
                                                    "is_group": 0
                                                },
                                                fields=["name"],
                                                limit=1)
                if expense_accounts:
                    expense_account = expense_accounts[0].name
                    if verbose:
                        print(f"Using expense account: {expense_account}")
                
                # Find a cash account
                cash_accounts = frappe.get_all("Account", 
                                            filters={
                                                "account_type": ["in", ["Cash", "Bank"]],
                                                "company": company,
                                                "is_group": 0
                                            },
                                            fields=["name"],
                                            limit=1)
                if cash_accounts:
                    cash_account = cash_accounts[0].name
                    if verbose:
                        print(f"Using cash account: {cash_account}")
            except Exception as e:
                if verbose:
                    print(f"Error finding accounts for {company}: {e}")
                # Use default accounts as fallback
                company_abbr = "_TC"
                try:
                    company_abbr = frappe.get_cached_value("Company", company, "abbr")
                except:
                    # Create a simple abbreviation if not found
                    company_abbr = ''.join([c[0] for c in company.split()]) or company[:3]
                    if verbose:
                        print(f"Using generated company abbreviation: {company_abbr}")
                
                receivable_account = f"Debtors - {company_abbr}"
                income_account = f"Sales - {company_abbr}"
                cash_account = f"Cash - {company_abbr}"
        
        # Generate a product code from the name
        base_product_code = name.upper().replace(" ", "_")[:10]
        
        # Check if product code exists and generate a unique one if needed
        i = 1
        product_code = base_product_code
        while frappe.db.exists("Loan Product", product_code):
            product_code = f"{base_product_code}_{i}"
            i += 1
            if i > 10:  # Prevent infinite loop
                if verbose:
                    print(f"Could not generate unique product code for {name}")
                return {"error": f"Could not generate unique product code for {name}"}
        
        if verbose and product_code != base_product_code:
            print(f"Generated unique product code: {product_code} for {name}")
        
        # Find or create required accounts
        account_fields = [
            "loan_account", "payment_account", "interest_income_account", "penalty_income_account",
            "disbursement_account", "security_deposit_account", "customer_refund_account", 
            "interest_accrued_account", "interest_waiver_account", "interest_receivable_account",
            "broken_period_interest_recovery_account", "penalty_accrued_account", "penalty_waiver_account", 
            "penalty_receivable_account", "write_off_account", "write_off_recovery_account"
        ]
        
        # Get actual existing accounts
        actual_receivable_account = None
        actual_income_account = None
        actual_cash_account = None
        
        # Try to find existing accounts
        accounts_list = frappe.get_all("Account", 
                                    filters={"company": company, "is_group": 0},
                                    fields=["name", "account_type"])
        
        for account in accounts_list:
            if account.account_type == "Receivable" and not actual_receivable_account:
                actual_receivable_account = account.name
            elif account.account_type == "Income Account" and not actual_income_account:
                actual_income_account = account.name
            elif account.account_type == "Cash" and not actual_cash_account:
                actual_cash_account = account.name
        
        # Use actual accounts or fallback to provided ones
        final_receivable = actual_receivable_account or receivable_account
        final_income = actual_income_account or income_account or actual_receivable_account
        final_cash = actual_cash_account or cash_account
        
        # Check if we have the minimum required accounts
        if not final_receivable or not final_income or not final_cash:
            if verbose:
                print("Missing required accounts for loan product creation")
            return {"error": "Missing required accounts for loan product creation"}
        
        # Set up all accounts
        accounts = {}
        for field in account_fields:
            if "receivable" in field or "loan" in field or "security" in field:
                accounts[field] = final_receivable
            elif "income" in field or "recovery" in field:
                accounts[field] = final_income
            elif "waiver" in field or "write_off" in field:
                accounts[field] = final_income  # Use income account for waivers
            elif "payment" in field or "disbursement" in field or "refund" in field:
                accounts[field] = final_cash
            else:
                # Default to receivable for any other account
                accounts[field] = final_receivable
        
        # Check if product_name already exists for another product
        i = 1
        product_name = name
        while frappe.db.exists("Loan Product", {"product_name": product_name, "company": company}):
            product_name = f"{name} {i}"
            i += 1
            if i > 10:  # Prevent infinite loop
                if verbose:
                    print(f"Could not generate unique product name for {name}")
                return {"error": f"Could not generate unique product name for {name}"}
        
        if verbose and product_name != name:
            print(f"Generated unique product name: {product_name} for {name}")
        
        # Create a complete loan product with all required accounts
        doc = frappe.get_doc({
            "doctype": "Loan Product",
            "product_code": product_code,
            "is_term_loan": 1,
            "rate_of_interest": 10.0,
            "maximum_loan_amount": 500000,
            "product_name": product_name,  # Required field
            "company": company,  # Required field
            "min_days_bw_disbursement_first_repayment": 30,  # Required field
            
            # Set all required accounts
            "loan_account": accounts["loan_account"],
            "payment_account": accounts["payment_account"],
            "interest_income_account": accounts["interest_income_account"],
            "penalty_income_account": accounts["penalty_income_account"],
            "disbursement_account": accounts["disbursement_account"],
            "security_deposit_account": accounts["security_deposit_account"],
            "customer_refund_account": accounts["customer_refund_account"],
            "interest_accrued_account": accounts["interest_accrued_account"],
            "interest_waiver_account": accounts["interest_waiver_account"],
            "interest_receivable_account": accounts["interest_receivable_account"],
            "broken_period_interest_recovery_account": accounts["broken_period_interest_recovery_account"],
            "penalty_accrued_account": accounts["penalty_accrued_account"],
            "penalty_waiver_account": accounts["penalty_waiver_account"],
            "penalty_receivable_account": accounts["penalty_receivable_account"],
            "write_off_account": accounts["write_off_account"],
            "write_off_recovery_account": accounts["write_off_recovery_account"]
        })
        
        # Ensure company is set correctly
        doc.company = company
        doc.insert(ignore_permissions=True)
        if verbose:
            print(f"Created Loan Product: {name} with code {product_code}")
        return {"doctype": "Loan Product", "name": doc.name}
    except Exception as e:
        if verbose:
            print(f"Failed to create Loan Product {name}: {e}")
        return {"error": str(e)}

def create_employee(employee_id, verbose=False, company="SCF"):
    """Create an employee if it doesn't exist"""
    # Check if employee exists by employee_number and company
    existing_employee = frappe.get_all("Employee", 
                                     filters={"employee_number": employee_id, "company": company},
                                     fields=["name"],
                                     limit=1)
    if existing_employee:
        if verbose:
            print(f"Employee {employee_id} already exists in {company}")
        return {"doctype": "Employee", "name": existing_employee[0].name, "skipped": True}
    
    # Also check if employee exists by name and company
    existing_employee = frappe.get_all("Employee", 
                                     filters={"name": employee_id, "company": company},
                                     fields=["name"],
                                     limit=1)
    if existing_employee:
        if verbose:
            print(f"Employee {employee_id} already exists in {company}")
        return {"doctype": "Employee", "name": existing_employee[0].name, "skipped": True}
    
    try:
        # Create a minimal employee
        doc = frappe.get_doc({
            "doctype": "Employee",
            "employee_name": f"Employee {employee_id}",
            "employee_number": employee_id,
            "first_name": "Demo",
            "last_name": "Employee",
            "company": company,
            "status": "Active",
            "gender": "Other",
            "date_of_birth": "1990-01-01",
            "date_of_joining": nowdate()
        })
        doc.insert(ignore_permissions=True)
        if verbose:
            print(f"Created Employee: {doc.name} in {company}")
        return {"doctype": "Employee", "name": doc.name}
    except Exception as e:
        if verbose:
            print(f"Failed to create Employee {employee_id}: {e}")
        return {"error": str(e)}

def load_loan_application_data(count=5, submit=False, verbose=False):
    """Load loan application sample data with dependency checking"""
    # First validate the setup
    validation_result = validate_loan_application_setup()
    if not validation_result["valid"]:
        return {"error": "Validation failed", "validation_errors": validation_result["errors"]}
    
    if validation_result["warnings"] and verbose:
        print("Validation warnings:")
        for warning in validation_result["warnings"]:
            print(f"  - {warning}")
    
    loan_app_file = os.path.join(DEMO_DIR, "loan_application.json")
    
    if not os.path.exists(loan_app_file):
        return {"error": f"Loan application sample data not found: {loan_app_file}"}
    
    summary = {"inserted": [], "errors": [], "dependencies_loaded": [], "validation_warnings": validation_result["warnings"]}
    
    try:
        with open(loan_app_file, "r", encoding="utf-8") as f:
            records = json.load(f)
        
        # Limit to specified count
        records = records[:count] if count > 0 else records
        
        # Now process loan applications
        for rec in records:
            dt = rec.get("doctype") or "Loan Application"
            rec["doctype"] = dt
            
            # Check mandatory fields
            missing_fields = check_mandatory_fields(dt, rec)
            if missing_fields:
                error_msg = f"Missing mandatory fields in {dt}: {', '.join(missing_fields)}"
                if verbose:
                    print(error_msg)
                summary["errors"].append({"record": rec, "error": error_msg})
                continue
            
            # Check dependencies
            missing_deps = check_dependencies(dt, rec)
            
            # Handle remaining dependencies
            for dep in missing_deps:
                if dep["doctype"] == "Employee":
                    # Create employee directly with the correct company
                    company = rec.get("company", "SCF")
                    result = create_employee(dep["value"], verbose, company)
                    if "error" not in result:
                        # Update the record to use the actual employee name
                        if rec.get("applicant_type") == "Employee":
                            rec["applicant"] = result["name"]
                        summary["dependencies_loaded"].append({
                            "doctype": "Employee",
                            "value": dep["value"]
                        })
                elif dep["doctype"] == "Loan Product":
                    # Handle loan product creation
                    product_name = dep["value"]
                    company = rec.get("company", "SCF")
                    result = create_loan_product(product_name, verbose, company)
                    if "error" not in result:
                        summary["dependencies_loaded"].append({
                            "doctype": "Loan Product",
                            "value": product_name
                        })
                elif dep["file"]:
                    if verbose:
                        print(f"Loading dependency {dep['doctype']} from {dep['file']}")
                    dep_result = load_dependency_file(dep["file"], verbose)
                    if dep_result.get("error"):
                        summary["errors"].append({"dependency": dep, "error": dep_result["error"]})
                    else:
                        summary["dependencies_loaded"].append(dep)
                else:
                    error_msg = f"Missing dependency {dep['doctype']} with value {dep['value']} and no sample data file found"
                    if verbose:
                        print(error_msg)
                    summary["errors"].append({"dependency": dep, "error": error_msg})
            
            # Check if dependencies are now satisfied
            missing_deps = check_dependencies(dt, rec)
            if missing_deps:
                error_msg = f"Still missing dependencies after loading: {missing_deps}"
                if verbose:
                    print(error_msg)
                summary["errors"].append({"record": rec, "error": error_msg})
                continue
            
            # If there is already a doc for this identity, skip (idempotent)
            existing_name = _get_identity_value(dt, rec)
            if existing_name:
                if verbose:
                    print(f"Exists {dt} {existing_name} -> skipping")
                summary["inserted"].append({"doctype": dt, "name": existing_name, "skipped": True})
                continue
            
            try:
                meta = frappe.get_meta(dt)
                # fill required fields for parent doc
                rec = _fill_required_fields(rec, meta)
                # resolve links and table children
                rec = _resolve_links_for_doc(rec, meta)
                
                # Special handling for loan applications
                if dt == "Loan Application" and rec.get("loan_product"):
                    company = rec.get("company") or "SCF"
                    product_name = rec["loan_product"]
                    
                    # First, try exact match by product name and company
                    loan_product = frappe.get_all("Loan Product", 
                                                filters={
                                                    "product_name": product_name,
                                                    "company": company
                                                },
                                                fields=["name"],
                                                limit=1)
                    
                    if loan_product:
                        # Replace loan_product field with the actual document name
                        rec["loan_product"] = loan_product[0].name
                        if verbose:
                            print(f"Found loan product {loan_product[0].name} for {product_name}")
                    else:
                        # Try to create the loan product if it doesn't exist
                        result = create_loan_product(product_name, verbose, company)
                        if "error" not in result and "name" in result:
                            rec["loan_product"] = result["name"]
                            if verbose:
                                print(f"Created and using loan product {result['name']} for {product_name}")
                        else:
                            # If we couldn't create the loan product, try to find any loan product for this company
                            any_loan_product = frappe.get_all("Loan Product", 
                                                           filters={"company": company},
                                                           fields=["name"],
                                                           limit=1)
                            if any_loan_product:
                                rec["loan_product"] = any_loan_product[0].name
                                if verbose:
                                    print(f"Using fallback loan product {any_loan_product[0].name} for {product_name}")
                            else:
                                # Last resort: find any loan product
                                any_loan_product = frappe.get_all("Loan Product", 
                                                               fields=["name"],
                                                               limit=1)
                                if any_loan_product:
                                    rec["loan_product"] = any_loan_product[0].name
                                    if verbose:
                                        print(f"Using any available loan product {any_loan_product[0].name} for {product_name}")
                                
                    # Debug: Print the loan_product value after resolution
                    if verbose:
                        print(f"Final loan_product value: {rec.get('loan_product')}")
                        
                    # Ensure the loan_product is properly set in the doc
                    if not rec.get('loan_product'):
                        error_msg = f"Failed to resolve loan_product for {product_name}"
                        if verbose:
                            print(error_msg)
                        summary["errors"].append({"record": rec, "error": error_msg})
                        continue
                
                # insert
                try:
                    if verbose:
                        print(f"Attempting to insert {dt} with loan_product={rec.get('loan_product')}")
                        if dt == "Loan Application":
                            # Debug: Check if the loan_product exists in the database
                            if rec.get('loan_product'):
                                loan_product_exists = frappe.db.exists("Loan Product", rec.get('loan_product'))
                                print(f"Loan Product {rec.get('loan_product')} exists in DB: {loan_product_exists}")
                    doc = frappe.get_doc(rec)
                    doc.insert(ignore_permissions=True)
                    if submit and getattr(meta, "is_submittable", False):
                        doc.submit()
                    summary["inserted"].append({"doctype": doc.doctype, "name": doc.name})
                    if verbose:
                        print(f"Inserted {doc.doctype} {doc.name}")
                except Exception as e:
                    error_msg = f"Failed to insert {dt}: {e}"
                    if verbose:
                        print(error_msg)
                        print(f"Record details: {rec}")
                    summary["errors"].append({"record": rec, "error": error_msg})
            except Exception as e:
                error_msg = f"Failed to insert {dt}: {e}"
                if verbose:
                    print(error_msg)
                summary["errors"].append({"record": rec, "error": error_msg})
        
        frappe.db.commit()
    except Exception as e:
        summary["errors"].append({"error": str(e)})
    
    return summary

def reset_loan_application_data(verbose=False):
    """Delete loan application sample data"""
    loan_app_file = os.path.join(DEMO_DIR, "loan_application.json")
    
    if not os.path.exists(loan_app_file):
        return {"error": f"Loan application sample data not found: {loan_app_file}"}
    
    deleted = []
    errors = []
    
    try:
        with open(loan_app_file, "r", encoding="utf-8") as f:
            records = json.load(f)
        
        for rec in records:
            dt = rec.get("doctype") or "Loan Application"
            identity = _get_identity_value(dt, rec)
            
            if identity and frappe.db.exists(dt, identity):
                try:
                    frappe.delete_doc(dt, identity, force=True)
                    deleted.append({"doctype": dt, "name": identity})
                    if verbose:
                        print(f"Deleted {dt} {identity}")
                except Exception as e:
                    errors.append({"doctype": dt, "name": identity, "error": str(e)})
        
        frappe.db.commit()
    except Exception as e:
        errors.append({"error": str(e)})
    
    return {"deleted": deleted, "errors": errors}