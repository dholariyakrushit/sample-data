# apps/lending/lending/demo.py
import frappe
import json
import os
import re
from frappe.utils import nowdate

DEMO_DIR = os.path.join(os.path.dirname(__file__), "sample_data","data")

IGNORED_FIELD_TYPES = {
    "Section Break", "Column Break", "HTML", "Tab Break", "Button", "Image"
}

# Known identity fields to check before inserting / to delete on reset
IDENTITY_MAP = {
    "Company": ["company_name", "name", "company"],
    "Customer": ["customer_name", "name"],
    "Employee": ["employee_number", "employee_name", "name"],
    "Loan Product": ["product_code", "product_name", "name"],
    "Loan Application": ["name"],  # Loan Application usually auto-named; don't try to delete by this
}


def _default_for_field(field):
    ft = field.fieldtype
    fname = getattr(field, "fieldname", "") or ""
    # small heuristics
    if fname.lower() == "gender":
        return "Male"
    if fname.lower() in ("date_of_birth", "dob"):
        return "1990-01-01"
    if ft in ("Data", "Small Text", "Text", "Link", "Dynamic Link"):
        if ft == "Select" and getattr(field, "options", None):
            return field.options.splitlines()[0]
        return f"Demo {fname}"
    if ft in ("Int", "Float", "Currency", "Percent"):
        return 1
    if ft == "Date":
        return nowdate()
    if ft == "Check":
        return 0
    return None


def _generate_code_from_name(name, dt, candidate_field=None):
    """Make a short unique code based on name and ensure it does not collide."""
    base = "".join([w[0] for w in re.findall(r"[A-Za-z0-9]+", name)][:4]).upper() or "PRD"
    i = 1
    while True:
        code = f"{base}-{i:03d}"
        # Two checks:
        # 1) Does a doc exist with name == code?
        if frappe.db.exists(dt, code):
            i += 1
            continue
        # 2) If candidate_field provided (e.g., 'product_code'), check if any doc has that field == code
        if candidate_field:
            exists = frappe.db.get_value(dt, {candidate_field: code}, "name")
            if exists:
                i += 1
                continue
        return code


def _get_identity_value(dt, rec):
    """Try to find a value we can use to detect an existing doc for dt using IDENTITY_MAP."""
    candidates = IDENTITY_MAP.get(dt, [])
    for key in candidates:
        if key in rec and rec.get(key):
            # Attempt to find existing name using this key (e.g. WHERE employee_number = val -> name)
            try:
                existing = frappe.db.get_value(dt, {key: rec.get(key)}, "name")
            except Exception:
                existing = None
            if existing:
                return existing
            # If the value itself could be the name
            if frappe.db.exists(dt, rec.get(key)):
                return rec.get(key)
    # fallback check: if rec has "name" and exists
    if rec.get("name") and frappe.db.exists(dt, rec.get("name")):
        return rec.get("name")
    return None


def _fill_required_fields(rec, meta):
    """Populate missing required fields for *rec* using metadata heuristics."""
    for f in meta.fields:
        fname = f.fieldname
        if getattr(f, "reqd", False) and fname not in rec:
            # skip layout fields
            if f.fieldtype in IGNORED_FIELD_TYPES:
                continue
            # helpful heuristics
            if fname == "first_name" and rec.get("employee_name"):
                rec["first_name"] = str(rec["employee_name"]).split()[0]
                continue
            if fname == "last_name" and rec.get("employee_name"):
                parts = str(rec["employee_name"]).split()
                rec["last_name"] = parts[-1] if len(parts) > 1 else ""
                continue
            if "code" in fname.lower():
                # try to generate based on any 'name-like' field in rec
                name_like = rec.get("loan_product_name") or rec.get("product_name") or rec.get("employee_number") or rec.get("company_name") or rec.get("customer_name") or rec.get("name") or rec.get("employee_name") or "X"
                rec[fname] = _generate_code_from_name(name_like, meta.name, candidate_field=fname)
                continue
            default = _default_for_field(f)
            if default is not None:
                rec[fname] = default
    return rec


def create_link_doc(doctype, desired_value):
    """
    Create a minimal doc for link target `doctype` with sensible defaults.
    Returns the created or existing doc name.
    """
    # if exists as name
    if frappe.db.exists(doctype, desired_value):
        return frappe.db.get_value(doctype, {"name": desired_value}, "name") or desired_value

    # if exists by a known identity field => return that name
    # try to find a doc where first identity field equals desired_value
    for idf in IDENTITY_MAP.get(doctype, []):
        try:
            exists = frappe.db.get_value(doctype, {idf: desired_value}, "name")
        except Exception:
            exists = None
        if exists:
            return exists

    # Build minimal payload
    try:
        meta = frappe.get_meta(doctype)
    except Exception as e:
        frappe.log_error(f"create_link_doc: cannot get meta for {doctype}: {e}", "lending.demo")
        raise

    docdata = {"doctype": doctype}
    # Try to set a likely name field
    # If a field 'name' not allowed, we will set required fields instead
    # Populate required fields from heuristics
    rf = _first_required_field(meta=meta)
    if rf:
        docdata[rf] = desired_value

    # fill all required fields
    for f in meta.fields:
        if getattr(f, "reqd", False) and f.fieldname not in docdata:
            default = _default_for_field(f)
            if default is not None:
                docdata[f.fieldname] = default

    # If there is any obvious "_name" field, set it
    for f in meta.fields:
        if f.fieldname.endswith("_name") and f.fieldname not in docdata:
            # fallback to desired_value
            docdata[f.fieldname] = desired_value

    # attempt insert
    try:
        new = frappe.get_doc(docdata)
        new.insert(ignore_permissions=True)
        frappe.db.commit()
        return new.name
    except Exception as e:
        frappe.log_error(f"Failed creating {doctype} with data {docdata}: {e}", "lending.demo")
        raise


def _first_required_field(meta):
    for f in meta.fields:
        if getattr(f, "reqd", False) and f.fieldtype not in IGNORED_FIELD_TYPES:
            return f.fieldname
    return None


def _resolve_links_for_doc(record, docmeta):
    for f in docmeta.fields:
        fname = f.fieldname
        if f.fieldtype == "Dynamic Link":
            dt_field = f.options
            actual_doctype = record.get(dt_field)
            val = record.get(fname)
            if val and actual_doctype:
                if not frappe.db.exists(actual_doctype, val):
                    try:
                        record[fname] = create_link_doc(actual_doctype, val)
                    except Exception:
                        frappe.log_error(f"Could not create Dynamic Link {actual_doctype} {val}", "lending.demo")
        elif f.fieldtype == "Link":
            val = record.get(fname)
            target = f.options
            if val and target:
                if not frappe.db.get_value(target, {target_meta_field_name(target): val}, "name") and not frappe.db.exists(target, val):
                    try:
                        record[fname] = create_link_doc(target, val)
                    except Exception:
                        frappe.log_error(f"Could not create Link {target} {val}", "lending.demo")
        elif f.fieldtype == "Table":
            child_doctype = f.options
            rows = record.get(fname) or []
            if rows:
                try:
                    child_meta = frappe.get_meta(child_doctype)
                except Exception:
                    child_meta = None
                new_rows = []
                for row in rows:
                    if "doctype" not in row:
                        row["doctype"] = child_doctype
                    if child_meta:
                        # fill required fields for child row
                        row = _fill_required_fields(row, child_meta)
                        # resolve links in child rows
                        for cf in child_meta.fields:
                            if cf.fieldtype == "Dynamic Link":
                                dt_field = cf.options
                                actual_doctype = row.get(dt_field)
                                val = row.get(cf.fieldname)
                                if val and actual_doctype and not frappe.db.exists(actual_doctype, val):
                                    try:
                                        row[cf.fieldname] = create_link_doc(actual_doctype, val)
                                    except Exception:
                                        frappe.log_error(f"child create fail {actual_doctype} {val}", "lending.demo")
                            elif cf.fieldtype == "Link":
                                val = row.get(cf.fieldname)
                                target = cf.options
                                if val and not frappe.db.exists(target, val):
                                    try:
                                        row[cf.fieldname] = create_link_doc(target, val)
                                    except Exception:
                                        frappe.log_error(f"child create fail {target} {val}", "lending.demo")
                    new_rows.append(row)
                record[fname] = new_rows
    return record


def target_meta_field_name(dt):
    """Return a sensible field to lookup by when we want to find if a doc exists using a friendly field value."""
    # heuristic: product_code, item_code, name, company_name, customer_name, employee_number
    candidates = ["product_code", "loan_product_code", "item_code", "employee_number",
                  "company_name", "customer_name", "name"]
    for c in candidates:
        try:
            if frappe.db.has_column(f"`tab{dt}`", c):
                return c
        except Exception:
            continue
    return "name"


def load_demo_data(demo_dir=None, submit=False, verbose=True):
    demo_dir = demo_dir or DEMO_DIR
    if not os.path.exists(demo_dir):
        raise FileNotFoundError(f"Demo data folder not found: {demo_dir}")

    summary = {"inserted": [], "errors": []}

    for fname in sorted(os.listdir(demo_dir)):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(demo_dir, fname)
        with open(path, "r", encoding="utf-8") as f:
            try:
                records = json.load(f)
            except Exception as e:
                frappe.log_error(f"Invalid JSON in {path}: {e}", "lending.demo")
                summary["errors"].append({"file": path, "error": str(e)})
                continue

        for rec in records:
            dt = rec.get("doctype") or None
            if not dt:
                dt = os.path.splitext(fname)[0].replace("_", " ").title()
                rec["doctype"] = dt

            try:
                meta = frappe.get_meta(dt)
            except Exception as e:
                frappe.log_error(f"Meta load failed for {dt}: {e}", "lending.demo")
                summary["errors"].append({"record": rec, "error": f"meta error: {e}"})
                continue

            # if there is already a doc for this identity, skip (idempotent)
            existing_name = _get_identity_value(dt, rec)
            if existing_name:
                if verbose:
                    print(f"Exists {dt} {existing_name} -> skipping")
                summary["inserted"].append({"doctype": dt, "name": existing_name, "skipped": True})
                continue

            # fill required fields for parent doc
            rec = _fill_required_fields(rec, meta)
            # resolve links and table children (creates minimal linked docs if missing)
            try:
                rec = _resolve_links_for_doc(rec, meta)
            except Exception as e:
                frappe.log_error(f"Error resolving links for {dt}: {e}", "lending.demo")

            # insert
            try:
                doc = frappe.get_doc(rec)
                doc.insert(ignore_permissions=True)
                if submit and getattr(meta, "is_submittable", False):
                    doc.submit()
                summary["inserted"].append({"doctype": doc.doctype, "name": doc.name})
                if verbose:
                    print(f"Inserted {doc.doctype} {doc.name}")
            except Exception as e:
                frappe.log_error(f"Failed to insert {dt}: {e}\nRecord: {rec}", "lending.demo")
                summary["errors"].append({"record": rec, "error": str(e)})
    frappe.db.commit()
    return summary


def reset_demo_data(demo_dir=None, verbose=True):
    demo_dir = demo_dir or DEMO_DIR
    if not os.path.exists(demo_dir):
        raise FileNotFoundError(f"Demo data folder not found: {demo_dir}")

    deleted = []
    errors = []
    for fname in sorted(os.listdir(demo_dir)):
        if not fname.endswith(".json"):
            continue
        path = os.path.join(demo_dir, fname)
        with open(path, "r", encoding="utf-8") as f:
            try:
                records = json.load(f)
            except Exception as e:
                errors.append({"file": path, "error": str(e)})
                continue

        for rec in records:
            dt = rec.get("doctype") or os.path.splitext(fname)[0].replace("_", " ").title()
            identity = _get_identity_value(dt, rec)
            # if identity was not found by value, attempt to find by mapping keys
            if not identity:
                # try each candidate key
                for key in IDENTITY_MAP.get(dt, []):
                    val = rec.get(key)
                    if val:
                        name = frappe.db.get_value(dt, {key: val}, "name")
                        if name:
                            identity = name
                            break
            if identity and frappe.db.exists(dt, identity):
                try:
                    frappe.delete_doc(dt, identity, force=True)
                    deleted.append({"doctype": dt, "name": identity})
                    if verbose:
                        print(f"Deleted {dt} {identity}")
                except Exception as e:
                    errors.append({"doctype": dt, "name": identity, "error": str(e)})
    frappe.db.commit()
    return {"deleted": deleted, "errors": errors}
