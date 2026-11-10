"""DEV ONLY: rebuild text-faithful stand-in PDFs from the text of the Drive originals.

The real documents live in the BiztelAI Drive folder. These stand-ins exist so the app can be
developed/tested where the originals can't be downloaded. Replace docs/*.pdf with the originals
(same filenames) before demoing or submitting.
"""
import sys
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "docs")
OUT.mkdir(exist_ok=True)
body = ParagraphStyle("b", fontName="Helvetica", fontSize=9.5, leading=13, spaceAfter=3)
head = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=11, leading=14, spaceBefore=8, spaceAfter=4)
title = ParagraphStyle("t", fontName="Helvetica-Bold", fontSize=13, leading=17, spaceAfter=6)
cell = ParagraphStyle("c", fontName="Helvetica", fontSize=8.5, leading=11)
cellb = ParagraphStyle("cb", fontName="Helvetica-Bold", fontSize=8.5, leading=11)


def P(t, s=body): return Paragraph(t, s)
def H(t): return Paragraph(t, head)
def B(t): return Paragraph("&bull; " + t, body)


def table(rows, widths):
    data = [[Paragraph(str(c), cellb if i == 0 else cell) for c in r] for i, r in enumerate(rows)]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.6, colors.grey),
                           ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8e8e8")),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return t


def header(co_title, no, rev, eff, prep, appr):
    return [P("Kaveri Precision Components Pvt. Ltd. - Hosur Plant", body), P(co_title, title),
            P(f"Document No. {no} &nbsp;&nbsp; Revision {rev}"), P(f"Effective Date {eff} &nbsp;&nbsp; Page See footer"),
            P(f"Prepared By {prep} &nbsp;&nbsp; Approved By {appr}")]


def build(fname, docno, rev, story):
    def footer(c, d):
        c.setFont("Helvetica", 7.5)
        c.drawString(20 * mm, 12 * mm, f"{docno} | Rev {rev} | Uncontrolled copy when printed. Refer to QMS for the latest version. Page {d.page}")
    SimpleDocTemplate(str(OUT / fname), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                      topMargin=18 * mm, bottomMargin=22 * mm, title=docno,
                      author="Kaveri Precision Components").build(story, onFirstPage=footer, onLaterPages=footer)


# ---------------- SAF-SOP-003 Rev 05
s = header("Lockout / Tagout (LOTO) - Safety Procedure", "SAF-SOP-003", "05", "12-Feb-2026", "J. Fathima, Safety Officer", "A. Krishnan, Plant Head")
s += [H("1. Purpose"), P("To protect people from the unexpected start-up of machines or release of stored energy (electrical, hydraulic, pneumatic, mechanical) during maintenance, cleaning, setting or repair."),
      H("2. Scope"), P("Applies to all employees and contract workers at the Hosur plant who maintain, clean or repair machines, including CNC turning centres, presses and compressors."),
      H("3. Definitions"),
      B("Authorised person: a trained employee who applies their own personal lock and tag to isolate energy."),
      B("Affected person: an operator or employee who works in the area but does not perform the isolation."),
      B("Zero energy state: the condition where all energy sources are isolated and stored energy is released, so that the machine cannot move or release energy."),
      H("4. Lockout Procedure"),
      P("1. Inform all affected persons that the machine is being shut down for maintenance."),
      P("2. Stop the machine using the normal stop sequence."),
      P("3. Isolate all energy sources: main electrical isolator, compressed air valve, and hydraulic power unit."),
      P("4. Apply your personal red lock and danger tag to each isolation point. Each authorised person working on the machine applies their own lock. Use a multi-lock hasp when more than one person is involved."),
      P("5. Release stored energy: bleed hydraulic pressure and accumulators until the gauge reads zero, vent compressed air to 0 bar, and block any parts that can fall under gravity."),
      P("6. Verify zero energy: try to start the machine from the control panel and confirm it does not start. Confirm all pressure gauges read zero. Return controls to OFF."),
      H("5. Removing Locks"),
      P("1. Check that tools and materials are removed and guards are refitted."),
      P("2. Confirm all persons are clear of the machine."),
      P("3. Each authorised person removes only their own lock. Nobody may remove another person's lock."),
      P("4. Inform affected persons that the machine is being restarted."),
      H("6. Removal of a Lock When the Owner Is Absent"),
      P("If an authorised person has left the plant without removing their lock, the lock may be removed only through this procedure:"),
      P("1. The Shift Supervisor makes every reasonable effort to contact the lock owner by phone."),
      P("2. If the owner cannot be reached, the Production Manager and the Safety Officer must both authorise removal."),
      P("3. The machine is physically inspected to confirm it is safe to re-energise."),
      PageBreak(),
      P("4. The removal is recorded on form SF-12 Lock Removal Record."),
      P("5. The lock owner must be informed before they resume work on their next shift."),
      H("7. Training and Audits"),
      B("All authorised persons must complete LOTO training before applying locks, with refresher training every 12 months."),
      B("The Safety Officer audits LOTO practice on each shift at least once a month."),
      B("Violation of this procedure is treated as a serious safety breach.")]
build("SAF-SOP-003_Lockout_Tagout_Procedure.pdf", "SAF-SOP-003", "05", s)

# ---------------- QC-SOP-014 Rev 03
s = header("Incoming Material Inspection - Standard Operating Procedure", "QC-SOP-014", "03", "15-Mar-2023", "R. Selvam, QC Engineer", "M. Prakash, QC Manager")
s += [H("1. Purpose"), P("This procedure describes how incoming raw materials and bought-out components are inspected at the receiving area before they are released to stores and production."),
      H("2. Scope"), P("Applies to all steel bar stock, castings, forgings and bought-out components received at the Hosur plant."),
      H("3. Responsibilities"),
      B("Stores Executive: receives material, checks quantity against the delivery challan and informs QC."),
      B("QC Inspector: carries out sampling, visual and dimensional inspection, and records results."),
      B("QC Supervisor: approves acceptance or rejection of the lot."),
      H("4. Procedure"),
      P("1. Stores Executive places the received lot in the Incoming Inspection Area and raises an inspection request."),
      P("2. QC Inspector collects the purchase order, drawing and supplier test certificate (if available)."),
      P("3. Draw 5 samples at random from every lot, irrespective of lot size."),
      P("4. Perform visual inspection for rust, dents, cracks and burrs."),
      P("5. Perform dimensional inspection on all critical dimensions using a vernier caliper."),
      P("6. If all 5 samples are within specification, the lot is accepted. If any sample fails, the complete lot is rejected."),
      P("7. Record results on paper form QF-07 Incoming Inspection Report and file it in the QC office."),
      P("8. Accepted material is tagged with a GREEN tag and moved to stores."),
      P("9. Rejected material is tagged with a RED tag and kept in the Red Bin area near Gate 2 until it is returned to the supplier."),
      P("10. QC Supervisor informs Purchase by email about rejected lots by end of the shift."),
      H("5. Records"), B("QF-07 Incoming Inspection Report (paper) - retained for 2 years."),
      H("6. Revision History"),
      table([["Rev", "Date", "Change"], ["01", "10-Jan-2019", "First issue"], ["02", "05-Aug-2021", "Added visual inspection criteria"],
             ["03", "15-Mar-2023", "Changed sample size to 5 for all lots"]], [20, 35, 110])]
build("QC-SOP-014_Rev03_Incoming_Material_Inspection.pdf", "QC-SOP-014", "03", s)

# ---------------- QC-SOP-014 Rev 04
s = header("Incoming Material Inspection - Standard Operating Procedure", "QC-SOP-014", "04", "01-Jul-2026", "K. Divya, Supplier Quality Engineer", "M. Prakash, QC Manager")
s += [H("1. Purpose"), P("This procedure describes how incoming raw materials and bought-out components are inspected at the receiving area before they are released to stores and production."),
      H("2. Scope"), P("Applies to all steel bar stock, castings, forgings and bought-out components received at the Hosur plant, including machined BH-220 bearing housings received from sub-contractors."),
      H("3. Responsibilities"),
      B("Stores Executive: receives material, checks quantity against the delivery challan and raises the inspection request in the QMS app."),
      B("QC Inspector: carries out sampling, visual and dimensional inspection, and records results in the QMS app."),
      B("Shift QC Supervisor: approves acceptance, rejection or hold of the lot."),
      B("Supplier Quality Engineer (SQE): handles supplier communication for rejected or held lots."),
      H("4. Sampling Plan"), P("Defects are classified as follows:"),
      B("Critical: a defect that can cause a safety risk or failure of the part, e.g. crack, wrong material grade, or a dimension out of tolerance on a characteristic marked Critical."),
      B("Major: a defect that affects fit or function but is not critical, e.g. deep dent, damaged thread, or a dimension out of tolerance on a characteristic marked Major."),
      B("Minor: a cosmetic defect that does not affect fit or function, e.g. light surface marks or light surface rust that can be removed by cleaning."),
      P("The number of samples depends on the lot size. Minor defects are allowed only as shown below."),
      table([["Lot size (pieces)", "Samples to inspect", "Accept if minor defects are", "Reject if minor defects are"],
             ["2 - 5", "All pieces", "0", "1 or more"], ["6 - 90", "5", "0", "1 or more"], ["91 - 500", "13", "0", "1 or more"],
             ["501 - 3,200", "32", "1 or fewer", "2 or more"], ["Above 3,200", "50", "2 or fewer", "3 or more"]], [40, 40, 45, 45]),
      Spacer(1, 4),
      P("Any critical defect in any sample: the complete lot is rejected and returned to the supplier. Sorting is not allowed."),
      P("Any major defect in any sample: the complete lot is rejected. The SQE may decide to have the lot 100% sorted at the supplier's cost instead of returning it."),
      H("5. Procedure"),
      PageBreak(),
      P("1. Stores Executive places the received lot in the Incoming Inspection Area and raises an inspection request in the QMS app."),
      P("2. QC Inspector checks that the supplier's Material Test Certificate (MTC) is attached. The MTC is mandatory. If it is missing, the lot is put on HOLD and must not be inspected or accepted until the MTC is received."),
      P("3. Draw samples at random as per the sampling plan in Section 4."),
      P("4. Perform visual inspection for rust, dents, cracks and burrs."),
      P("5. Perform dimensional inspection using a calibrated digital caliper. Dimensions of BH-220 housings marked CMM in Section 6 must be checked on the CMM."),
      P("6. Record results in the QMS app using digital form QF-07A. Paper form QF-07 is no longer used."),
      P("7. Accepted material is tagged with a GREEN tag and moved to stores."),
      P("8. Rejected material is tagged with a RED tag and moved to Quarantine Cage Q1, Stores Bay 3. The cage is locked; the key is held by the Shift QC Supervisor."),
      P("9. The Shift QC Supervisor must inform the SQE within 4 hours of rejection. The SQE raises a Supplier Corrective Action Request (SCAR)."),
      H("6. Inspection Dimensions - BH-220 Bearing Housing (Machined, from sub-contractor)"),
      P("All values in millimetres. Dimensions marked CMM must be checked on the coordinate measuring machine."),
      table([["Characteristic", "Nominal", "Tolerance", "Method", "Class"],
             ["Bore diameter", "52.000", "+0.030 / -0.000", "CMM", "Critical"], ["Outer diameter", "90.000", "+/- 0.050", "Digital caliper", "Major"],
             ["Overall height", "38.00", "+/- 0.10", "Digital caliper", "Major"], ["Mounting hole PCD", "72.00", "+/- 0.05", "CMM", "Critical"],
             ["Mounting hole diameter (4x)", "9.00", "+0.20 / -0.00", "Pin gauge", "Major"], ["Bore concentricity to OD", "-", "0.02 max.", "CMM", "Critical"]], [55, 25, 35, 30, 25]),
      H("7. Records"), B("QF-07A Incoming Inspection Report (digital, in QMS app) - retained for 5 years."),
      B("Supplier MTCs - scanned and attached to the QF-07A record."),
      H("8. Revision History"),
      table([["Rev", "Date", "Change"], ["01", "10-Jan-2019", "First issue"], ["02", "05-Aug-2021", "Added visual inspection criteria"],
             ["03", "15-Mar-2023", "Changed sample size to 5 for all lots"],
             ["04", "01-Jul-2026", "Supersedes Rev 03. Lot-size based sampling plan; MTC made mandatory; quarantine moved to Cage Q1; digital form QF-07A; 4-hour SQE escalation; BH-220 critical dimensions added."]], [20, 35, 110])]
build("QC-SOP-014_Rev04_Incoming_Material_Inspection.pdf", "QC-SOP-014", "04", s)

# ---------------- MNT-MAN-CNC-02 Rev 02
s = header("Preventive Maintenance Manual - TX-200 CNC Turning Centre", "MNT-MAN-CNC-02", "02", "20-Jan-2026", "S. Arun, Maintenance Engineer", "V. Ramesh, Maintenance Manager")
s += [H("1. Purpose"), P("This manual defines the preventive maintenance (PM) activities, operating parameters and common alarms for the TX-200 CNC turning centres (machines CNC-04 to CNC-09) used on the shaft machining line."),
      H("2. Safety First"), P("Before starting any maintenance activity other than daily operator checks, the machine must be isolated as per SAF-SOP-003 Lockout/Tagout. Never open the electrical cabinet or hydraulic circuit on a running or energised machine."),
      H("3. Normal Operating Parameters"),
      table([["Parameter", "Normal range", "Check method"], ["Hydraulic system pressure", "3.5 - 4.0 MPa (35 - 40 bar)", "Panel pressure gauge"],
             ["Chuck clamping pressure", "2.0 - 2.5 MPa", "Chuck pressure gauge"], ["Coolant concentration", "6 - 8 %", "Refractometer reading x 1.0 factor"],
             ["Coolant tank level", "Between MIN and MAX marks", "Sight glass"], ["Way lube oil", "ISO VG 68", "Visual, top-up as needed"],
             ["Spindle runout (at chuck face)", "0.005 mm max.", "Dial indicator"], ["Compressed air supply", "5.5 - 6.5 bar", "FRL unit gauge"]], [60, 60, 50]),
      H("4. Preventive Maintenance Schedule"),
      table([["Frequency", "Activity", "Done by"],
             ["Daily (start of shift)", "Check hydraulic pressure, coolant level, way lube level, air pressure; clean chips from slideways", "Operator"],
             ["Weekly", "Check coolant concentration; clean coolant tank filter; check chuck jaw wear", "Operator"],
             ["Monthly", "Check spindle runout; inspect hydraulic hoses for leaks or cracks; clean electrical cabinet fan filter", "Maintenance technician"],
             ["Quarterly", "Replace hydraulic return filter; check turret alignment; check backlash on X and Z axes", "Maintenance technician"],
             ["Yearly", "Replace hydraulic oil (ISO VG 46); full geometric accuracy check; replace coolant completely", "Maintenance engineer"]], [35, 95, 40]),
      H("5. Chuck Mounting Bolt Torque"), P("When re-mounting the chuck after maintenance, tighten the mounting bolts in a criss-cross sequence to 110 Nm using a calibrated torque wrench."),
      H("6. Common Alarms"),
      table([["Alarm", "Meaning", "Operator action"], ["AL-101", "Hydraulic pressure low", "Stop cycle. Check oil level and pressure gauge. Call maintenance if pressure stays below 3.5 MPa."]], [25, 50, 95]),
      PageBreak(),
      table([["Alarm", "Meaning", "Operator action"],
             ["AL-104", "Way lube oil level low", "Top up with ISO VG 68 oil to the MAX mark, then press RESET. Machine can continue after reset."],
             ["AL-210", "Chuck clamp not confirmed", "Do not start cycle. Check chuck pressure and part seating. Call maintenance if repeated."],
             ["AL-305", "Spindle overload", "Stop cycle. Check tool wear and cutting parameters. Inform shift supervisor."],
             ["AL-412", "Coolant level low", "Top up coolant mixed to 6 - 8 % concentration."]], [25, 50, 95]),
      H("7. Replacing a Hydraulic Hose"),
      P("1. Isolate the machine as per SAF-SOP-003, including releasing stored hydraulic pressure."),
      P("2. Confirm the panel pressure gauge reads zero before loosening any fitting."),
      P("3. Place a drip tray under the hose and loosen the fittings slowly."),
      P("4. Fit a new hose of the same rating and tighten fittings."),
      P("5. Remove locks as per SAF-SOP-003, start the hydraulic unit and confirm pressure returns to 3.5 - 4.0 MPa with no leaks.")]
build("MNT-MAN-CNC-02_TX-200_Preventive_Maintenance.pdf", "MNT-MAN-CNC-02", "02", s)
print("built", sorted(p.name for p in OUT.glob("*.pdf")))
