import re
from datetime import datetime
from pathlib import Path
import streamlit as st

st.set_page_config(page_title="OpsPilot | Log Intelligence", page_icon="🔎", layout="wide")

st.markdown("""
<style>
.block-container{max-width:1450px;padding-top:1.2rem;padding-bottom:2rem}
.hero{padding:1.6rem 1.8rem;border-radius:20px;background:linear-gradient(120deg,#0b1220,#153a5b 60%,#11717a);color:white;margin-bottom:1rem}
.hero h1{font-size:2.25rem;margin:0 0 .35rem}.hero p{margin:0;color:#dbeafe}
.panel{border:1px solid rgba(130,145,165,.3);padding:1rem;border-radius:15px}
.eyebrow{text-transform:uppercase;letter-spacing:.09em;font-size:.72rem;opacity:.72}
</style>
""", unsafe_allow_html=True)

RULES = [
 {"category":"Missing input file","priority":"High","owner":"Upstream / File Transfer Team","patterns":[r"file not found",r"no such file or directory",r"cannot find the file",r"input file.{0,30}missing"],
  "cause":"The job appears unable to locate an expected input file. The file may not have arrived, its name/path may differ, or access to it may be unavailable.",
  "checks":["Confirm whether the upstream job delivered the expected file.","Verify the expected filename, directory and arrival time.","Check access using the approved support procedure."],
  "guardrail":"Do not restart until the expected file is present and the approved runbook permits a retry."},
 {"category":"Database / connection error","priority":"High","owner":"Database / DBA Team","patterns":[r"ora-\d{5}",r"connection refused",r"could not connect",r"connection timed out",r"connect timeout",r"database.{0,30}unavailable"],
  "cause":"The job appears to have encountered a database or service connectivity issue. The log alone does not establish whether the cause is network, database availability, or configuration.",
  "checks":["Capture the exact error code and timestamp.","Check approved database/service health information.","Check whether other jobs using the same connection are affected."],
  "guardrail":"Confirm connectivity is restored and follow the runbook before requesting a restart."},
 {"category":"Permission / access denied","priority":"Medium","owner":"Infrastructure / Access Team","patterns":[r"permission denied",r"access is denied",r"unauthorized",r"not authorized"],
  "cause":"The process appears to lack permission to read, write, or access a resource.",
  "checks":["Confirm the service account and required access with the authorized team.","Check whether permissions or access changed recently.","Do not paste or share credentials in the assistant."],
  "guardrail":"Resolve and verify access before retrying."},
 {"category":"Timeout / long-running process","priority":"Medium","owner":"Application / Batch Support","patterns":[r"timed out",r"\btimeout\b",r"execution time exceeded",r"maximum runtime",r"no progress detected"],
  "cause":"The process appears to have exceeded a time limit or stopped making progress.",
  "checks":["Compare runtime with the normal baseline.","Check upstream delays, input size, and resource constraints.","Record the start time and last log activity."],
  "guardrail":"Check for duplicate or partially completed work before any rerun."},
 {"category":"Disk / storage capacity","priority":"High","owner":"Infrastructure / Storage Team","patterns":[r"no space left on device",r"disk full",r"insufficient disk space",r"quota exceeded"],
  "cause":"The process appears unable to write because storage capacity or quota may be exhausted.",
  "checks":["Ask the authorized server team to verify filesystem capacity.","Check whether temporary or output files are accumulating.","Do not delete files or change storage without approval."],
  "guardrail":"Wait for authorized storage remediation and verify capacity before retrying."},
 {"category":"Data / format issue","priority":"Medium","owner":"Application / Data Team","patterns":[r"invalid format",r"parse error",r"invalid number",r"conversion failed",r"unexpected end of file",r"record length"],
  "cause":"The job appears to have encountered unexpected or invalid input data or a format mismatch.",
  "checks":["Inspect the first failing record using approved procedures.","Compare input format with the expected specification.","Contact the source-data owner if the file structure or values changed."],
  "guardrail":"Validate or correct the input before retrying."},
 {"category":"Memory / resource issue","priority":"High","owner":"Application / Infrastructure Team","patterns":[r"out of memory",r"memory exhausted",r"cannot allocate memory",r"oom-killer",r"resource temporarily unavailable"],
  "cause":"The process may have exhausted memory or another required system resource.",
  "checks":["Capture the error and timestamp.","Ask the authorized team to review resource metrics.","Compare with previous successful runs and input volume."],
  "guardrail":"Do not repeatedly rerun until resource conditions and partial processing are understood."},
 {"category":"Generic application / batch error","priority":"Medium","owner":"L2 / Application Support","patterns":[r"\berror\b",r"\bfailed\b",r"\bexception\b",r"\babend\b",r"\bterminated\b"],
  "cause":"The log contains a generic failure signal, but the available text does not identify a specific cause.",
  "checks":["Review lines immediately before and after the failure.","Check the last successful processing step and error code.","Compare with known incidents and the approved runbook."],
  "guardrail":"Do not repeatedly retry without understanding the failure."}
]

SAMPLE_LOG = """2026-10-21 02:00:00 INFO OpCon agent received schedule NIGHTLY_DATA_PIPELINE
2026-10-21 02:00:01 INFO Initializing job DAILY_FILE_LOAD
2026-10-21 02:00:02 INFO Runtime environment: DEMO
2026-10-21 02:00:03 INFO Service account validation completed
2026-10-21 02:00:04 INFO Checking source directory /demo/input
2026-10-21 02:00:05 INFO Checking expected file daily.csv
2026-10-21 02:00:06 INFO Upstream dependency status: COMPLETED
2026-10-21 02:00:07 INFO Starting input validation
2026-10-21 02:00:08 INFO File scan started
2026-10-21 02:00:09 WARN No file metadata found for daily.csv
2026-10-21 02:00:10 INFO Retrying directory listing once
2026-10-21 02:00:11 INFO Directory listing completed
2026-10-21 02:00:12 ERROR Input file not found: /demo/input/daily.csv
2026-10-21 02:00:12 ERROR File validation failed
2026-10-21 02:00:13 INFO Cleanup started
2026-10-21 02:00:14 INFO Cleanup completed
2026-10-21 02:00:15 ERROR Job failed with return code 2
2026-10-21 02:00:16 INFO Job ended with status FAILED
2026-10-21 02:00:17 INFO OpCon notification generated for support team"""

SAMPLE_LOG_2 = """2026-10-21 03:15:00 INFO OpCon agent received schedule CUSTOMER_DAILY_EXPORT
2026-10-21 03:15:01 INFO Job name: CUSTOMER_DAILY_EXPORT
2026-10-21 03:15:02 INFO Environment: TEST
2026-10-21 03:15:03 INFO Checking database connection profile ORA_REPORTING
2026-10-21 03:15:04 INFO Connection request submitted
2026-10-21 03:15:09 INFO Waiting for database response
2026-10-21 03:15:19 WARN Database response slower than baseline
2026-10-21 03:15:29 INFO Connection retry 1 of 2
2026-10-21 03:15:39 INFO Waiting for database response
2026-10-21 03:15:49 ERROR ORA-12170: TNS:Connect timeout occurred
2026-10-21 03:15:49 ERROR Connection timed out while opening ORA_REPORTING session
2026-10-21 03:15:50 INFO No export query was started
2026-10-21 03:15:51 INFO Job state changed to WAITING_FOR_REVIEW
2026-10-21 03:20:51 WARN No progress detected for 5 minutes
2026-10-21 03:20:52 INFO Job remains active in scheduler view
2026-10-21 03:25:52 WARN No progress detected for 10 minutes
2026-10-21 03:25:53 INFO Last heartbeat received at 03:15:39
2026-10-21 03:30:53 ERROR Maximum wait threshold reached
2026-10-21 03:30:54 ERROR Job appears stuck; operator review required
2026-10-21 03:30:55 INFO No automatic kill or restart action was taken
2026-10-21 03:30:56 INFO Awaiting operator decision"""

SAMPLE_EMAIL = """Subject: OpCon Job Failure - DAILY_FILE_LOAD
Job Name: DAILY_FILE_LOAD
Schedule: NIGHTLY_DATA_PIPELINE
Status: Failed
Failure Time: 2026-10-21 02:15:00
Incident: INC0012345
Environment: DEMO"""

def extract(pattern, text):
    m = re.search(pattern, text, re.I | re.M)
    return m.group(1).strip() if m else ""

def parse_notification(text):
    subject = extract(r"^\s*Subject\s*:\s*(.+)$", text)
    job = extract(r"^\s*(?:Job Name|Job|Task)\s*:\s*(.+)$", text)
    if not job and subject:
        job = re.sub(r"(?i)^.*?(?:job failure|job failed|failure)\s*[-:]\s*", "", subject).strip()
    return {
      "subject":subject, "job":job,
      "schedule":extract(r"^\s*(?:Schedule|Workflow)\s*:\s*(.+)$", text),
      "status":extract(r"^\s*Status\s*:\s*(.+)$", text),
      "time":extract(r"^\s*(?:Failure Time|Failed At|Timestamp)\s*:\s*(.+)$", text),
      "incident":extract(r"\b(INC\d{5,})\b", text),
      "environment":extract(r"^\s*Environment\s*:\s*(.+)$", text)
    }

def analyze(log_text):
    lines = [x.rstrip() for x in log_text.splitlines() if x.strip()]
    matches = []
    for idx,line in enumerate(lines):
        for rule in RULES:
            hits = [p for p in rule["patterns"] if re.search(p,line,re.I)]
            if hits:
                matches.append({"line_no":idx+1,"line":line,"rule":rule})
                break
    # Prefer a specific match over generic "error/failed"; preserve every matched line.
    specific = [m for m in matches if m["rule"]["category"] != "Generic application / batch error"]
    selected = specific[0] if specific else (matches[0] if matches else None)
    context = []
    if selected:
        i=selected["line_no"]-1
        context = [{"line_no":j+1,"line":lines[j]} for j in range(max(0,i-2),min(len(lines),i+3))]
    elif lines:
        context = [{"line_no":i+1,"line":line} for i,line in list(enumerate(lines))[-10:]]
    return {"lines":lines,"matches":matches,"selected":selected,"context":context}

def infer_job_details(log_text, meta):
    """Fill gaps in notification metadata using safe, simple log patterns."""
    if not meta.get("job"):
        for pattern in [r"Job name\s*:\s*(.+)$", r"Initializing job\s+([A-Za-z0-9_.-]+)", r"Starting\s+([A-Za-z0-9_.-]+)"]:
            found = extract(pattern, log_text)
            if found:
                meta["job"] = found
                break
    if not meta.get("schedule"):
        meta["schedule"] = extract(r"schedule\s+([A-Za-z0-9_.-]+)", log_text)
    if not meta.get("environment"):
        meta["environment"] = extract(r"Environment\s*:\s*(.+)$", log_text) or extract(r"Runtime environment\s*:\s*(.+)$", log_text)
    if not meta.get("time"):
        # Use the first timestamp on a matched failure line when available.
        for line in log_text.splitlines():
            if re.search(r"error|failed|stuck|timeout|timed out|not found|no progress", line, re.I):
                stamp = re.search(r"^\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})", line)
                if stamp:
                    meta["time"] = stamp.group(1)
                    break
    if not meta.get("status"):
        if re.search(r"\b(stuck|no progress detected|maximum wait threshold reached)\b", log_text, re.I):
            meta["status"] = "Stuck / no progress detected"
        elif re.search(r"\b(failed|job failed|status FAILED|abend|terminated)\b", log_text, re.I):
            meta["status"] = "Failed"
        else:
            meta["status"] = "Requires review"
    return meta

def build_operator_email(meta, result, log_filename, report_filename):
    sel = result.get("selected")
    category = sel["rule"]["category"] if sel else "No configured pattern matched"
    matched = [f"- Line {m['line_no']}: [{m['rule']['category']}] {m['line']}" for m in result.get("matches", [])[:8]]
    evidence = "\n".join(matched) if matched else "- No configured error signature matched; please review the attached log."
    return (
        "Hi Operator Team,\n\n"
        f"The OpCon job below has reported a failure or appears to be stuck. Please review the attached log ({log_filename}) and analysis report ({report_filename}).\n\n"
        f"Job Name: {meta.get('job') or 'Not detected'}\n"
        f"Schedule: {meta.get('schedule') or 'Not detected'}\n"
        f"Status: {meta.get('status') or 'Failed / stuck'}\n"
        f"Failure Time: {meta.get('time') or 'Not detected'}\n"
        f"Incident Number: {meta.get('incident') or 'Not provided'}\n"
        f"Environment: {meta.get('environment') or 'Not detected'}\n"
        f"Likely Error Category: {category}\n\n"
        f"Relevant log evidence:\n{evidence}\n\n"
        "Could you please review the logs and confirm whether we should kill the job and restart it, or whether another action is required? We will wait for your explicit green flag before taking any kill/restart action.\n\n"
        "Thanks & Regards,\nOperations Team"
    )

def make_report(meta, result):
    sel = result["selected"]
    rule = sel["rule"] if sel else None
    out = ["OPS PILOT — JOB FAILURE ANALYSIS REPORT", f"Generated: {datetime.now():%Y-%m-%d %H:%M:%S}", ""]
    for key,label in [("job","Job"),("schedule","Schedule"),("incident","ServiceNow incident"),("time","Failure time"),("status","Reported status"),("environment","Environment")]:
        out.append(f"{label}: {meta.get(key) or 'Not detected'}")
    out += ["",f"Likely category: {rule['category'] if rule else 'No known pattern matched'}",
            f"Suggested owner: {rule['owner'] if rule else 'Manual review'}",
            f"Initial assessment: {rule['cause'] if rule else 'Insufficient evidence for a rule-based category.'}","",
            "Matched log lines:"]
    out += [f"Line {m['line_no']}: [{m['rule']['category']}] {m['line']}" for m in result["matches"]] or ["No configured patterns matched."]
    out += ["","Relevant context:"] + [f"Line {x['line_no']}: {x['line']}" for x in result["context"]]
    out += ["","Important: rule-based suggestion only. Validate against the approved runbook. No live system actions were performed."]
    return "\n".join(out)

with st.sidebar:
    st.markdown("## 🔎 OpsPilot")
    st.caption("Log Intelligence • Incident Support")
    st.markdown("### Quick demo")
    if st.button("Load sample email + log", use_container_width=True):
        st.session_state["notification"] = SAMPLE_EMAIL
        st.session_state["log_editor"] = SAMPLE_LOG
        st.session_state.pop("analysis", None)
    st.markdown("### Test log files")
    st.download_button("Download sample log 1 — Missing file", SAMPLE_LOG, file_name="sample_missing_input_file.log", mime="text/plain", use_container_width=True)
    st.download_button("Download sample log 2 — DB timeout / stuck", SAMPLE_LOG_2, file_name="sample_database_timeout_stuck.log", mime="text/plain", use_container_width=True)
    st.markdown("---")
    st.caption("Offline prototype • No live client connections")

st.markdown("""<div class="hero"><div class="eyebrow">Batch operations · incident intelligence</div><h1>Job Failure Analysis Assistant</h1><p>Analyze failed-job logs, review evidence, and track the operator team’s recovery decision.</p></div>""", unsafe_allow_html=True)
st.warning("Use fictional or client-approved sanitized data only. This tool gives rule-based clues, not a confirmed root cause. It does not connect to PuTTY/SSH, OpCon, email, or ServiceNow.")

tab1, tab2, tab3, tab4 = st.tabs(["🔍 Analyze log", "🟡 Operator approval", "✉️ Draft operator email", "📘 How it works"])

with tab1:
    col1,col2 = st.columns([1,1.2], gap="large")
    with col1:
        st.subheader("1 · Failure notification")
        notification = st.text_area("Paste the failure email (optional)", value=st.session_state.get("notification",""), height=190, placeholder="Subject, job name, schedule, incident ID…", key="notification_editor")
        st.subheader("2 · Provide log")
        upload = st.file_uploader("Upload a .log or .txt file", type=["log","txt"])
        pasted_log = st.text_area("Or paste log text", value=st.session_state.get("log_editor",""), height=260, placeholder="Paste relevant sanitized log lines…", key="pasted_log")
        if upload is not None:
            try:
                uploaded_text = upload.getvalue().decode("utf-8", errors="replace")
                st.caption(f"Loaded file: {upload.name} · {len(uploaded_text.splitlines())} lines")
                log_text = uploaded_text
            except Exception:
                log_text = pasted_log
        else:
            log_text = pasted_log
        st.caption("Tip: include a few lines before and after the error, not just the final 'FAILED' line.")
        if st.button("Analyze failure", type="primary", use_container_width=True):
            if not log_text.strip():
                st.error("Upload a log or paste log text first.")
            else:
                parsed_meta = infer_job_details(log_text, parse_notification(notification))
                st.session_state["analysis"] = {
                    "meta":parsed_meta,
                    "result":analyze(log_text),
                    "raw_log":log_text,
                    "log_filename": upload.name if upload is not None else "pasted_log.txt",
                    "notification":notification,
                    "created":datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
    with col2:
        st.subheader("3 · Analysis results")
        if "analysis" not in st.session_state:
            st.markdown('<div class="panel"><div class="eyebrow">Ready for analysis</div><h3>Waiting for a log</h3><p>Provide a log file or paste log content, then click <b>Analyze failure</b>.</p><p>OpsPilot will identify known error signatures, show matching lines, explain likely causes, and suggest checks.</p></div>', unsafe_allow_html=True)
        else:
            a = st.session_state["analysis"]
            meta, res = a["meta"], a["result"]
            sel = res["selected"]
            rule = sel["rule"] if sel else None
            k1,k2,k3 = st.columns(3)
            k1.metric("Lines scanned",len(res["lines"]))
            k2.metric("Error signals",len(res["matches"]))
            k3.metric("Likely category", "Matched" if rule else "Review")
            st.markdown("#### Job / incident details")
            d1,d2 = st.columns(2)
            d1.write(f"**Job:** {meta.get('job') or 'Not detected'}")
            d1.write(f"**Schedule:** {meta.get('schedule') or 'Not detected'}")
            d2.write(f"**Incident:** {meta.get('incident') or 'Not detected'}")
            d2.write(f"**Failure time:** {meta.get('time') or 'Not detected'}")
            if rule:
                st.success(f"Likely category: {rule['category']} · Suggested team: {rule['owner']} · Priority suggestion: {rule['priority']}")
                st.write("**What may have failed**")
                st.write(rule["cause"])
                st.write("**Recommended checks**")
                for check in rule["checks"]:
                    st.markdown(f"- {check}")
                st.warning("Recovery guardrail: " + rule["guardrail"])
            else:
                st.info("No configured pattern matched. Review the evidence manually and add approved signatures to the rules.")
            st.write("**Matched log evidence**")
            if res["matches"]:
                st.dataframe([{"Line":m["line_no"],"Category":m["rule"]["category"],"Log line":m["line"]} for m in res["matches"]], use_container_width=True, hide_index=True)
            else:
                st.caption("No configured error signature was found.")
            with st.expander("Relevant context around the primary match", expanded=True):
                st.code("\n".join(f"{x['line_no']:>5} | {x['line']}" for x in res["context"]) or "No context available.")
            st.download_button("Download analysis report (.txt)", make_report(meta,res), file_name="opspilot_analysis_report.txt", mime="text/plain", use_container_width=True)

with tab2:
    st.subheader("Operator decision and recovery tracking")
    st.info("OpsPilot does not decide whether a job should be killed or restarted. The operator team must assess dependencies and provide the green flag.")
    if "analysis" not in st.session_state:
        st.info("Analyze a log first. The operator decision tracker will then show the job and incident details.")
    else:
        a = st.session_state["analysis"]
        meta, res = a["meta"], a["result"]
        st.write(f"**Job:** {meta.get('job') or 'Not detected'}")
        st.write(f"**Schedule:** {meta.get('schedule') or 'Not detected'}")
        st.write(f"**ServiceNow incident:** {meta.get('incident') or 'Not detected'}")

        statuses = [
            "Pending operator decision",
            "Operator approved restart (green flag received)",
            "Operator advised no restart",
            "Restart performed — monitoring",
            "Job completed successfully",
            "Escalated for further investigation",
        ]
        if "operator_status" not in st.session_state:
            st.session_state["operator_status"] = statuses[0]
        status = st.selectbox("Current workflow status", statuses, key="operator_status")
        operator_notes = st.text_area(
            "Operator team's instruction / notes (optional)",
            key="operator_notes",
            placeholder="Record the operator team's decision or reference. Do not include passwords or secrets.",
            height=100,
        )

        if status == "Pending operator decision":
            st.warning("Waiting for the operator team. Do not kill or restart the job until they confirm the approved action.")
        elif status == "Operator approved restart (green flag received)":
            st.success("Green flag recorded. Perform the restart manually according to the approved runbook and dependency checks.")
        elif status == "Operator advised no restart":
            st.info("No restart is indicated by the operator team. Follow their instructions and the approved runbook.")
        elif status == "Restart performed — monitoring":
            st.info("Restart status is recorded for tracking only. Check the job's actual status in OpCon / approved monitoring tools.")
        elif status == "Job completed successfully":
            st.success("Successful completion recorded. Follow your team's ServiceNow incident closure process.")
        else:
            st.warning("Further investigation is required. Keep the incident in the appropriate state according to your team's process.")

        report_text = (
            "OPSPILOT — OPERATOR WORKFLOW RECORD\n"
            f"Generated: {datetime.now():%Y-%m-%d %H:%M:%S}\n"
            f"Job: {meta.get('job') or 'Not detected'}\n"
            f"Schedule: {meta.get('schedule') or 'Not detected'}\n"
            f"ServiceNow incident: {meta.get('incident') or 'Not detected'}\n"
            f"Current workflow status: {status}\n"
            f"Operator notes: {operator_notes.strip() or 'None recorded'}\n\n"
            "CONTROL NOTE: This record does not execute or authorize a job action. A restart must be performed manually only after the operator team's explicit approval and required dependency checks.\n"
        )
        st.download_button(
            "Download operator workflow record (.txt)",
            report_text,
            file_name="opspilot_operator_workflow.txt",
            mime="text/plain",
            use_container_width=True,
        )
        st.caption("This tracker does not send messages, kill/restart jobs, or update ServiceNow automatically.")

with tab3:
    st.subheader("Draft email to operator team")
    st.caption("This creates a copyable email draft only. It does not send email or automatically attach files to an email client.")
    if "analysis" not in st.session_state:
        st.info("Analyze a log first. The email draft will be populated from the notification and uploaded log.")
    else:
        a = st.session_state["analysis"]
        meta, res = a["meta"], a["result"]
        st.markdown("#### Confirm or edit job details")
        e1, e2 = st.columns(2)
        with e1:
            email_job = st.text_input("Job name", value=meta.get("job", ""), key="email_job")
            email_schedule = st.text_input("Schedule / workflow", value=meta.get("schedule", ""), key="email_schedule")
            email_status = st.selectbox("Job status", ["Failed", "Stuck / no progress detected", "Failed / stuck — needs review"], index=1 if "stuck" in (meta.get("status", "").lower()) else 0, key="email_status")
        with e2:
            email_incident = st.text_input("ServiceNow incident number", value=meta.get("incident", ""), key="email_incident")
            email_time = st.text_input("Failure time", value=meta.get("time", ""), key="email_time")
            email_environment = st.text_input("Environment", value=meta.get("environment", ""), key="email_environment")
        email_meta = {**meta, "job":email_job.strip(), "schedule":email_schedule.strip(), "status":email_status, "incident":email_incident.strip(), "time":email_time.strip(), "environment":email_environment.strip()}
        report_filename = "opspilot_analysis_report.txt"
        email_text = build_operator_email(email_meta, res, a.get("log_filename", "uploaded_log.log"), report_filename)
        st.text_input("Subject", value=f"Operator Guidance Required — {email_job or 'Job'} — {email_status}", key="email_subject")
        st.text_area("Email draft", value=email_text, height=360, key="email_body")
        c1, c2 = st.columns(2)
        with c1:
            st.download_button("Download email draft (.txt)", st.session_state.get("email_body", email_text), file_name="operator_guidance_email.txt", mime="text/plain", use_container_width=True)
        with c2:
            st.download_button("Download original log for attachment", a["raw_log"], file_name=a.get("log_filename", "uploaded_log.log"), mime="text/plain", use_container_width=True)
        st.download_button("Download analysis report to attach", make_report(email_meta, res), file_name=report_filename, mime="text/plain", use_container_width=True)
        st.warning("Before sending, attach the downloaded log and analysis report to your email manually. Wait for the operator team's explicit green flag before any kill/restart action.")

with tab4:
    st.subheader("How the prototype works")
    st.markdown("""
**1. Read input:** upload a `.log`/`.txt` file or paste log lines.

**2. Detect patterns:** the rules scan for recognizable messages such as missing files, Oracle/connection errors, permissions, timeouts, storage, data-format, and resource errors.

**3. Select evidence:** the app shows every matched line and surrounding context for the first specific match.

**4. Recommend checks:** the matching rule supplies cautious troubleshooting steps and a restart guardrail.

**5. Operator approval:** the tracker records the operator team's decision and current recovery status. The email tab creates a dynamic draft asking whether the job should be killed/restarted, and provides downloads for the original log and analysis report. You attach the files manually in your email client.

**Current limitations:** this is deterministic rule-based analysis, not an LLM-based root-cause engine. Pattern matches can be wrong or incomplete. Validate every suggestion against client-approved runbooks.

**Future scaling:** after security approval, add read-only log retrieval through an approved SSH/SFTP adapter or centralized logging API. PuTTY itself is a terminal client; avoid automating its GUI. Use least-privilege access, host-key verification, a secret manager, redaction, audit logging, and human review. Any future integration must preserve operator approval before a restart and require explicit client approval.
""")

st.divider()
st.caption("OpsPilot · Prototype only · No live system connections or production actions")
