# apps/demo_data/demo_data/commands.py
import click
import frappe
from frappe.commands import pass_context
from . import demo
from . import loan_demo

@click.command("lending_load_demo")
@click.option("--reset", "-r", is_flag=True, help="Delete demo records first (idempotent).")
@pass_context
def lending_load_demo(context, reset=False):
    """Load Lending demo data (company, loan product, customer, employee, loan application)."""
    site = frappe.local.site
    click.secho(f"Running on site: {site}", fg="yellow")
    if reset:
        click.secho("Resetting demo data (deleting demo records)...", fg="yellow")
        result = demo.reset_demo_data()
        if result.get("errors"):
            click.secho("Errors while deleting demo records:", fg="red")
            for e in result["errors"]:
                click.echo(str(e))
        else:
            click.secho("Reset completed.", fg="green")

    click.secho("Loading demo data...", fg="yellow")
    result = demo.load_demo_data(submit=True, verbose=True)
    click.secho("Demo data load finished.", fg="green")
    if result.get("errors"):
        click.secho("Some errors occurred:", fg="red")
        for e in result["errors"]:
            click.echo(str(e))
    else:
        click.secho("All demo records inserted successfully.", fg="green")


@click.command("load_loan_applications")
@click.option("--reset", "-r", is_flag=True, help="Delete loan application records first (idempotent).")
@click.option("--count", "-c", default=5, help="Number of loan applications to create (default: 5)")
@click.option("--submit", "-s", is_flag=True, help="Submit the loan applications after creation")
@click.option("--validate-only", "-v", is_flag=True, help="Only validate setup without creating data")
@click.option("--no-auto-create", is_flag=True, help="Disable automatic creation of missing dependencies")
@pass_context
def load_loan_applications(context, reset=False, count=5, submit=False, validate_only=False, no_auto_create=False):
    """Load loan application sample data with automatic dependency creation and comprehensive validation."""
    import frappe
    
    # Initialize Frappe
    frappe.init(site=context.sites[0])
    frappe.connect()
    
    click.secho(f"Running on site: {context.sites[0]}", fg="yellow")
    
    if not no_auto_create:
        click.secho("🔧 Auto-creation of missing dependencies is ENABLED", fg="green")
    else:
        click.secho("⚠️  Auto-creation of missing dependencies is DISABLED", fg="yellow")
    
    # First validate the setup
    click.secho("🔍 Validating loan application setup...", fg="yellow")
    validation_result = loan_demo.validate_loan_application_setup()
    
    if not validation_result["valid"]:
        if not no_auto_create:
            click.secho("\n🔧 Auto-creating missing dependencies...", fg="yellow", bold=True)
            if loan_demo.create_missing_dependencies():
                click.secho("✅ Dependencies created successfully! Re-validating...", fg="green")
                # Re-validate after creating dependencies
                validation_result = loan_demo.validate_loan_application_setup()
                if not validation_result["valid"]:
                    click.secho("\n❌ VALIDATION STILL FAILED AFTER AUTO-CREATION", fg="red", bold=True)
                    click.secho("=" * 60, fg="red")
                    for error in validation_result["errors"]:
                        click.echo(f"❌ {error}")
                    click.secho("=" * 60, fg="red")
                    click.secho("🚫 Please fix the remaining errors manually.", fg="red", bold=True)
                    return
            else:
                click.secho("❌ Failed to create dependencies automatically.", fg="red", bold=True)
                return
        else:
            click.secho("\n❌ VALIDATION FAILED - STOPPING EXECUTION", fg="red", bold=True)
            click.secho("=" * 60, fg="red")
            for error in validation_result["errors"]:
                click.echo(f"❌ {error}")
            click.secho("=" * 60, fg="red")
            click.secho("🚫 Please fix the above errors before proceeding.", fg="red", bold=True)
            click.secho("💡 Tip: Remove --no-auto-create flag to automatically create missing dependencies", fg="yellow")
            click.secho("💡 Or run: bench --site loan.localhost lending_load_demo", fg="yellow")
            return
    
    if validation_result["warnings"]:
        click.secho("\n⚠️  Validation warnings:", fg="yellow")
        for warning in validation_result["warnings"]:
            click.echo(f"  - {warning}")
    
    click.secho("\n✅ All validations passed! Proceeding with data creation...", fg="green", bold=True)
    
    if validate_only:
        click.secho("Validation completed. No data was created.", fg="green")
        return
    
    if reset:
        click.secho("Resetting loan application data...", fg="yellow")
        result = loan_demo.reset_loan_application_data(verbose=True)
        if result.get("errors"):
            click.secho("Errors while deleting loan application records:", fg="red")
            for e in result["errors"]:
                click.echo(str(e))
        else:
            click.secho("Reset completed.", fg="green")
    
    click.secho(f"Loading {count} loan application records...", fg="yellow")
    result = loan_demo.load_loan_application_data(count=count, submit=submit, verbose=True)
    
    click.secho("Loan application data load finished.", fg="green")
    
    if result.get("dependencies_loaded"):
        click.secho("Dependencies loaded:", fg="blue")
        for dep in result["dependencies_loaded"]:
            click.echo(f"- {dep['doctype']}: {dep['value']}")
    
    if result.get("inserted"):
        click.secho("Inserted records:", fg="green")
        for rec in result["inserted"]:
            status = "(skipped, already exists)" if rec.get("skipped") else ""
            click.echo(f"- {rec['doctype']}: {rec['name']} {status}")
    
    if result.get("errors"):
        click.secho("Some errors occurred:", fg="red")
        for e in result["errors"]:
            if "record" in e and "error" in e:
                click.echo(f"- {e['error']}")
            elif "dependency" in e:
                dep = e["dependency"]
                click.echo(f"- Dependency error: {dep['doctype']} {dep['value']}: {e['error']}")
            else:
                click.echo(f"- {e['error']}")
    else:
        click.secho("All loan application records inserted successfully.", fg="green")


commands=[
    lending_load_demo,
    load_loan_applications
]