import pathlib

rev_path = pathlib.Path("revenue_report.py")
rcode = rev_path.read_text()

# Find the print block for top risks and make it extract the string cleanly
old_print = """            if result["top_5_risks"]:
                print(f"\\n  Top Revenue Risks:")
                for d in result["top_5_risks"][:3]:
                    print(f"    • {d['defect'][:50]}")
                    print(f"      Risk: ${d['revenue_at_risk_nzd']:,.0f}/mo | Fix: ${d['fix_cost_nzd']:,.0f} | Payback: {d['payback_months']} months")"""

new_print = """            if result["top_5_risks"]:
                print(f"\\n  Top Revenue Risks:")
                for d in result["top_5_risks"][:3]:
                    # Cleanly extract defect name whether it's a string or nested dict
                    defect_name = d['defect']
                    if isinstance(defect_name, dict):
                        defect_name = defect_name.get('issue') or defect_name.get('title') or defect_name.get('defect') or str(defect_name)
                    elif isinstance(defect_name, str) and defect_name.startswith("{"):
                        try:
                            import ast
                            parsed = ast.literal_eval(defect_name)
                            defect_name = parsed.get('issue') or parsed.get('title') or parsed.get('defect') or defect_name
                        except: pass
                    
                    # Truncate for clean terminal display
                    defect_short = str(defect_name).replace('\\n', ' ')[:55]
                    
                    payback = f"{d['payback_months']}mo" if d['payback_months'] != "N/A" else "N/A"
                    print(f"    • {defect_short}")
                    print(f"      Risk: ${d['revenue_at_risk_nzd']:,.0f}/mo | Fix: ${d['fix_cost_nzd']:,.0f} | Payback: {payback}")"""

if old_print in rcode:
    rcode = rcode.replace(old_print, new_print)
    rev_path.write_text(rcode)
    print("✅ Terminal print formatting fixed!")
else:
    print("ℹ️ Print block already patched or not found.")
