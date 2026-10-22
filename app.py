import re
from datetime import datetime
from collections import Counter, defaultdict
import streamlit as st

st.set_page_config(page_title="OpsPilot | Log Intelligence", page_icon="🔎", layout="wide")

# ═══════════════════════════════════════════════════════════════════════════════
#  STYLING
# ═══════════════════════════════════════════════════════════════════════════════

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
*{font-family:'Inter',sans-serif}
.block-container{max-width:1500px;padding-top:1rem;padding-bottom:2rem}
.hero{padding:1.6rem 1.8rem;border-radius:20px;
      background:linear-gradient(135deg,#0b1220 0%,#153a5b 40%,#11717a 70%,#0d9488 100%);
      color:white;margin-bottom:1rem;box-shadow:0 4px 24px rgba(0,0,0,.25)}
.hero h1{font-size:2.2rem;margin:0 0 .35rem;font-weight:700}
.hero p{margin:0;color:#dbeafe;font-size:.95rem}
.eyebrow{text-transform:uppercase;letter-spacing:.09em;font-size:.72rem;opacity:.72;font-weight:600}
.panel{border:1px solid rgba(130,145,165,.3);padding:1.2rem;border-radius:15px;
       background:rgba(130,145,165,.04)}
.rc-box{border-left:4px solid #e74c3c;background:rgba(231,76,60,.07);
        padding:1rem 1.2rem;border-radius:8px;margin:.5rem 0}
.sym-box{border-left:3px solid #f39c12;background:rgba(243,156,18,.05);
         padding:.6rem 1rem;border-radius:6px;margin:.35rem 0;font-size:.92rem}
.chain-box{border-left:4px solid #3498db;background:rgba(52,152,219,.05);
           padding:1rem 1.2rem;border-radius:8px;margin:.5rem 0}
.phase-box{border-left:3px solid #8e44ad;background:rgba(142,68,173,.05);
           padding:.6rem 1rem;border-radius:6px;margin:.35rem 0}
.dup-badge{display:inline-block;background:#e74c3c;color:white;border-radius:10px;
           padding:1px 8px;font-size:.75rem;font-weight:600;margin-left:6px}
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
#  PRODUCTION RULE ENGINE — comprehensive pattern library
# ═══════════════════════════════════════════════════════════════════════════════

RULES = [
    # ── File / path errors ───────────────────────────────────────────────
    {"category": "Missing input file / path error",
     "priority": "High", "owner": "Upstream / File Transfer Team",
     "patterns": [
         r"file not found", r"no such file or directory", r"cannot find the file",
         r"input file.{0,30}missing", r"path.{0,20}not found", r"does not exist",
         r"cannot open", r"failed to open", r"file.{0,15}unavailable",
         r"cannot read file", r"unable to read", r"source file.{0,20}missing",
         r"FileNotFoundException", r"FileNotFoundError", r"ENOENT",
         r"cannot access.{0,30}no such file", r"file.{0,10}absent",
     ],
     "cause": "A required file or path could not be found or opened.",
     "checks": [
         "Confirm whether the upstream job delivered the expected file.",
         "Verify filename, directory, case-sensitivity and arrival time.",
         "Check filesystem mount status and NFS/CIFS availability.",
         "Verify service account has read permission on the path.",
     ],
     "guardrail": "Do not restart until the expected file is present and the approved runbook permits a retry."},

    # ── Database / connection errors ─────────────────────────────────────
    {"category": "Database / connection error",
     "priority": "High", "owner": "Database / DBA Team",
     "patterns": [
         r"ora-\d{4,5}", r"connection refused", r"could not connect",
         r"connection timed out", r"connect timeout", r"database.{0,30}unavailable",
         r"cannot connect to", r"connection reset", r"broken pipe",
         r"connection closed", r"lost connection", r"connection pool exhausted",
         r"too many connections", r"deadlock", r"lock wait timeout",
         r"communications link failure", r"sql\s*exception",
         r"SQLRecoverableException", r"SQLTransientException",
         r"jdbc.{0,30}error", r"SQLSTATE", r"mysql.{0,20}error",
         r"pg_connect", r"psycopg.{0,10}error", r"MongoServerError",
         r"redis.{0,15}connection", r"cannot reach database",
         r"TNS:.{0,40}(?:timeout|refused|unavailable|listener)",
         r"connection.{0,15}(?:abort|fail|drop|terminat|lost)",
         r"database is locked", r"unable to acquire lock",
     ],
     "cause": "The process encountered a database or service connectivity issue.",
     "checks": [
         "Capture the exact error code, database name and timestamp.",
         "Check database/service health dashboards and connection pool status.",
         "Verify whether other jobs using the same connection are affected.",
         "Check network connectivity, firewall rules and DNS resolution to the database host.",
     ],
     "guardrail": "Confirm connectivity is restored and follow the runbook before requesting a restart."},

    # ── Network / connectivity errors ────────────────────────────────────
    {"category": "Network / connectivity error",
     "priority": "High", "owner": "Network / Infrastructure Team",
     "patterns": [
         r"network.{0,15}unreachable", r"host.{0,15}unreachable",
         r"no route to host", r"connection reset by peer",
         r"socket.{0,15}(?:error|timeout|closed|exception)",
         r"ECONNREFUSED", r"ECONNRESET", r"ETIMEDOUT", r"EHOSTUNREACH",
         r"ENETUNREACH", r"network is down", r"socket hang up",
         r"connect ECONNREFUSED", r"getaddrinfo.{0,15}failed",
         r"name or service not known", r"temporary failure in name resolution",
         r"dns.{0,15}(?:resolution|lookup).{0,15}(?:fail|error|timeout)",
         r"could not resolve host", r"UnknownHostException",
         r"SocketTimeoutException", r"ConnectException",
         r"java\.net\.(?:Socket|Connect|Unknown)",
         r"requests\.exceptions\.ConnectionError",
         r"urllib3\.exceptions",
     ],
     "cause": "A network connectivity, DNS resolution or socket-level failure occurred.",
     "checks": [
         "Check network connectivity (ping/traceroute) to the target host.",
         "Verify DNS resolution for the target hostname.",
         "Check firewall rules, security groups and proxy configuration.",
         "Verify the target service is running and listening on the expected port.",
     ],
     "guardrail": "Confirm network path is restored before retrying."},

    # ── Authentication / authorization errors ────────────────────────────
    {"category": "Authentication / authorization error",
     "priority": "High", "owner": "Security / Access Management Team",
     "patterns": [
         r"permission denied", r"access.{0,10}denied", r"unauthorized",
         r"not authorized", r"forbidden", r"authentication fail",
         r"login fail", r"invalid credentials", r"bad password",
         r"access control", r"insufficient privilege",
         r"EACCES", r"EPERM", r"403 Forbidden",
         r"401 Unauthorized", r"AccessDeniedException",
         r"AuthenticationException", r"PermissionError",
         r"credential.{0,15}(?:expired|invalid|rejected)",
         r"token.{0,15}(?:expired|invalid|rejected|revoked)",
         r"certificate.{0,15}(?:expired|invalid|rejected|revoked|untrusted)",
         r"ssl.{0,15}(?:handshake|verify|certificate).{0,15}(?:fail|error)",
         r"CERTIFICATE_VERIFY_FAILED", r"SSLHandshakeException",
         r"trust.{0,15}anchor.{0,15}not found",
         r"kerberos.{0,15}(?:fail|error|expired)",
         r"GSSAPI", r"ldap.{0,15}(?:bind|auth).{0,15}fail",
     ],
     "cause": "The process lacks permission, has invalid credentials, or an SSL/certificate issue prevents access.",
     "checks": [
         "Verify service account credentials and expiration dates.",
         "Check whether permissions, roles or group memberships changed recently.",
         "Verify SSL certificates are valid and trusted.",
         "Check Kerberos ticket / token / API key validity.",
     ],
     "guardrail": "Resolve and verify access through the proper access-management workflow before retrying."},

    # ── Timeout / long-running / hung process ────────────────────────────
    {"category": "Timeout / hung process",
     "priority": "Medium", "owner": "Application / Batch Support",
     "patterns": [
         r"timed?\s*out", r"\btimeout\b", r"execution time exceeded",
         r"maximum runtime", r"no progress detected",
         r"deadline exceeded", r"request timeout", r"read timed out",
         r"write timed out", r"operation timed out", r"gateway timeout",
         r"504 Gateway", r"408 Request Timeout",
         r"TimeoutException", r"TimeoutError",
         r"watchdog.{0,15}timeout", r"heartbeat.{0,15}(?:miss|lost|timeout)",
         r"appears?\s*stuck", r"not responding",
         r"hung", r"stall(?:ed)?", r"freeze", r"frozen",
         r"maximum wait.{0,15}(?:reached|exceeded)",
     ],
     "cause": "The process exceeded a time limit, stopped making progress, or appears hung.",
     "checks": [
         "Compare runtime with the normal baseline.",
         "Check upstream delays, input volume and resource constraints.",
         "Record the start time, last log activity and last heartbeat.",
         "Check for locks, deadlocks or blocking queries.",
     ],
     "guardrail": "Check for duplicate or partially completed work before any rerun."},

    # ── Disk / storage / quota ───────────────────────────────────────────
    {"category": "Disk / storage capacity",
     "priority": "High", "owner": "Infrastructure / Storage Team",
     "patterns": [
         r"no space left on device", r"disk full", r"insufficient disk",
         r"quota exceeded", r"ENOSPC", r"filesystem full",
         r"cannot write", r"write fail.{0,15}space",
         r"disk quota", r"storage.{0,15}(?:full|exhausted|limit)",
         r"IOError.{0,20}space", r"not enough space",
         r"volume.{0,15}(?:full|capacity)", r"inode.{0,15}(?:full|limit)",
     ],
     "cause": "The process cannot write because storage capacity or quota may be exhausted.",
     "checks": [
         "Check filesystem capacity (`df -h`) and inode usage (`df -i`).",
         "Check whether temp, log or output files are accumulating.",
         "Identify the largest recent files and growth rate.",
         "Do not delete files or change storage without approval.",
     ],
     "guardrail": "Wait for authorized storage remediation and verify capacity before retrying."},

    # ── Memory / resource exhaustion ─────────────────────────────────────
    {"category": "Memory / resource exhaustion",
     "priority": "High", "owner": "Application / Infrastructure Team",
     "patterns": [
         r"out of memory", r"OutOfMemoryError", r"MemoryError",
         r"memory.{0,15}exhaust", r"cannot allocate memory",
         r"oom-killer", r"OOM", r"killed by signal\s*9",
         r"ENOMEM", r"heap space", r"GC overhead limit",
         r"memory limit", r"container.{0,15}killed",
         r"resource temporarily unavailable", r"EAGAIN",
         r"too many open files", r"EMFILE", r"ulimit",
         r"thread.{0,15}limit", r"cannot create.{0,15}thread",
         r"fork.{0,10}fail", r"process.{0,15}limit",
         r"resource.{0,15}(?:limit|exhaust|exceed)",
         r"StackOverflowError", r"stack overflow",
     ],
     "cause": "The process exhausted memory, file descriptors, threads, or another system resource.",
     "checks": [
         "Capture the error, PID and timestamp.",
         "Review resource metrics (memory, CPU, open FDs, thread count).",
         "Compare with previous successful runs and input volume.",
         "Check container memory limits and JVM heap settings.",
     ],
     "guardrail": "Do not repeatedly rerun until resource conditions and partial processing are understood."},

    # ── Data / format / parsing errors ───────────────────────────────────
    {"category": "Data / format / parsing error",
     "priority": "Medium", "owner": "Application / Data Team",
     "patterns": [
         r"invalid format", r"parse error", r"invalid number",
         r"conversion failed", r"unexpected end of file",
         r"record length", r"malformed", r"corrupt",
         r"invalid.{0,15}(?:data|input|record|value|character|encoding)",
         r"parsing.{0,10}fail", r"syntax error",
         r"JsonParseException", r"JSONDecodeError", r"json.{0,10}parse.{0,10}error",
         r"XMLParseException", r"SAXParseException",
         r"csv.{0,10}error", r"encoding.{0,10}error",
         r"UnicodeDecodeError", r"CharacterCodingException",
         r"NumberFormatException", r"DateTimeParseException",
         r"data truncat", r"value too (?:long|large)",
         r"constraint violation", r"integrity constraint",
         r"duplicate (?:key|entry)", r"unique constraint",
         r"check constraint", r"foreign key",
         r"invalid.{0,15}xml", r"invalid.{0,15}json",
         r"unexpected token", r"unexpected character",
         r"premature end", r"unterminated string",
     ],
     "cause": "The job encountered unexpected, malformed or invalid input data.",
     "checks": [
         "Inspect the first failing record using approved procedures.",
         "Compare input format/schema with the expected specification.",
         "Check encoding (UTF-8 vs Latin-1 vs others).",
         "Contact the source-data owner if file structure or values changed.",
     ],
     "guardrail": "Validate or correct the input data before retrying."},

    # ── Configuration / environment errors ───────────────────────────────
    {"category": "Configuration / environment error",
     "priority": "Medium", "owner": "DevOps / Configuration Team",
     "patterns": [
         r"config.{0,15}(?:error|missing|invalid|not found)",
         r"property.{0,15}not (?:found|set|defined)",
         r"environment variable.{0,15}(?:not set|missing|undefined)",
         r"missing.{0,15}(?:config|property|setting|parameter|argument)",
         r"invalid.{0,15}(?:config|property|setting|parameter|option)",
         r"ClassNotFoundException", r"NoClassDefFoundError",
         r"ModuleNotFoundError", r"ImportError",
         r"cannot find module", r"module.{0,15}not found",
         r"library.{0,15}not found", r"cannot load",
         r"dependency.{0,15}(?:missing|not found|fail)",
         r"version.{0,15}(?:mismatch|conflict|incompatible)",
         r"unsupported.{0,15}version",
     ],
     "cause": "A missing or invalid configuration, environment variable, dependency or library prevented the process from running.",
     "checks": [
         "Verify all required configuration files and environment variables are set.",
         "Compare config with the last known working version (diff).",
         "Check library/dependency versions and classpath/module path.",
         "Verify recent deployments or config changes.",
     ],
     "guardrail": "Correct the configuration and verify in a non-production environment if possible before retrying."},

    # ── Service / dependency / API errors ────────────────────────────────
    {"category": "Upstream service / API error",
     "priority": "High", "owner": "Service / Integration Team",
     "patterns": [
         r"service.{0,15}unavailable", r"503 Service Unavailable",
         r"502 Bad Gateway", r"500 Internal Server Error",
         r"upstream.{0,15}(?:fail|error|timeout|unavailable)",
         r"downstream.{0,15}(?:fail|error|timeout|unavailable)",
         r"api.{0,15}(?:fail|error|timeout|unavailable)",
         r"endpoint.{0,15}(?:fail|error|timeout|unavailable)",
         r"microservice.{0,15}(?:fail|error|unavailable)",
         r"circuit.{0,10}breaker", r"rate.{0,10}limit",
         r"429 Too Many Requests", r"throttl",
         r"health.{0,10}check.{0,10}fail",
         r"dependency.{0,10}check.{0,10}fail",
     ],
     "cause": "An upstream or downstream service, API or dependency is unavailable or returned an error.",
     "checks": [
         "Check the health/status of the dependent service.",
         "Verify API keys, endpoints and rate limits.",
         "Check whether the service is in maintenance or experiencing an outage.",
         "Review circuit breaker state and retry configuration.",
     ],
     "guardrail": "Confirm all dependent services are healthy before retrying."},

    # ── Container / orchestration errors ─────────────────────────────────
    {"category": "Container / orchestration error",
     "priority": "High", "owner": "Platform / DevOps Team",
     "patterns": [
         r"CrashLoopBackOff", r"ImagePullBackOff", r"ErrImagePull",
         r"OOMKilled", r"pod.{0,15}(?:fail|evict|terminat|restart)",
         r"container.{0,15}(?:fail|crash|exit|terminat|restart)",
         r"docker.{0,15}(?:error|fail)", r"cannot pull image",
         r"liveness.{0,10}probe.{0,10}fail",
         r"readiness.{0,10}probe.{0,10}fail",
         r"scheduling.{0,10}fail", r"insufficient.{0,10}(?:cpu|memory|resources)",
         r"evict", r"preempt",
     ],
     "cause": "A container, pod or orchestration issue prevented the workload from running.",
     "checks": [
         "Check pod/container status, events and describe output.",
         "Review resource requests/limits and node capacity.",
         "Verify image name, tag, registry access and pull secrets.",
         "Check liveness/readiness probe configuration.",
     ],
     "guardrail": "Investigate the orchestration issue before redeploying or restarting."},

    # ── Scheduler / batch / job control errors ───────────────────────────
    {"category": "Scheduler / batch control error",
     "priority": "Medium", "owner": "Operations / Batch Support",
     "patterns": [
         r"job.{0,15}(?:abort|cancel|kill|terminat)",
         r"schedule.{0,15}(?:fail|error|miss)",
         r"dependency.{0,15}not (?:met|satisfied)",
         r"predecessor.{0,15}(?:fail|not complete)",
         r"return code.{0,10}(?!0\b)\d+",
         r"exit (?:code|status).{0,10}(?!0\b)\d+",
         r"non-zero exit", r"abnormal.{0,15}(?:end|terminat)",
         r"\babend\b", r"abended",
         r"job.{0,15}(?:fail|error).{0,15}(?:code|status|rc)",
     ],
     "cause": "The job was aborted, cancelled or terminated by the scheduler, or a predecessor dependency was not met.",
     "checks": [
         "Check the job's return/exit code and its meaning in the runbook.",
         "Verify predecessor job completion status.",
         "Check whether the job was manually killed or auto-cancelled.",
         "Review scheduler logs for dependency chain status.",
     ],
     "guardrail": "Understand the termination reason and verify dependencies before restarting."},

    # ── Application exception / stack trace ──────────────────────────────
    {"category": "Application exception / crash",
     "priority": "Medium", "owner": "L2 / Application Development Team",
     "patterns": [
         r"NullPointerException", r"NullReferenceException",
         r"ArrayIndexOutOfBoundsException", r"IndexError",
         r"ClassCastException", r"TypeError", r"ValueError",
         r"IllegalArgumentException", r"IllegalStateException",
         r"ArithmeticException", r"ZeroDivisionError",
         r"RuntimeException", r"RuntimeError",
         r"AssertionError", r"assertion fail",
         r"segmentation fault", r"segfault", r"SIGSEGV",
         r"SIGABRT", r"SIGBUS", r"SIGKILL",
         r"core dump", r"Traceback \(most recent",
         r"panic:", r"fatal error:", r"unhandled exception",
         r"uncaught exception",
         r"at [a-zA-Z0-9_.]+\([a-zA-Z0-9_]+\.java:\d+\)",
     ],
     "cause": "The application encountered an unhandled exception, crash or fatal error in its code.",
     "checks": [
         "Capture the full stack trace and the triggering input/state.",
         "Identify the exception class, message and source file/line.",
         "Check whether this is a known/recurring bug.",
         "Reproduce in a non-production environment if possible.",
     ],
     "guardrail": "A code fix may be required. Do not retry if the same input will cause the same crash."},

    # ── Generic error (catch-all — must be LAST) ─────────────────────────
    {"category": "Generic error signal",
     "priority": "Low", "owner": "L2 / Application Support",
     "patterns": [
         r"\berror\b", r"\bfailed\b", r"\bfailure\b",
         r"\bexception\b", r"\bterminated\b",
         r"\bcritical\b", r"\bfatal\b",
         r"\bsevere\b", r"\bemergency\b",
     ],
     "cause": "The log contains a generic failure signal but the text does not match a more specific category.",
     "checks": [
         "Review lines immediately before and after the failure.",
         "Check the last successful processing step and error code.",
         "Compare with known incidents and the approved runbook.",
         "Search the log for additional context clues.",
     ],
     "guardrail": "Do not repeatedly retry without understanding the failure."},
]

# ── Severity hierarchy (higher = more severe) ────────────────────────────────

_SEV_ORDER = {"TRACE": 0, "DEBUG": 1, "INFO": 2, "NOTICE": 3, "WARN": 4, "WARNING": 4,
              "ERROR": 5, "SEVERE": 5, "CRITICAL": 6, "FATAL": 6, "EMERGENCY": 7, "EMERG": 7, "ALERT": 7}

# ── Sample data ──────────────────────────────────────────────────────────────

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

# ═══════════════════════════════════════════════════════════════════════════════
#  LOG PARSING ENGINE — auto-detects format, handles any log
# ═══════════════════════════════════════════════════════════════════════════════

# Timestamp regexes ordered by specificity
_TS_PATTERNS = [
    # ISO-style: 2026-10-21 02:00:00.123  or  2026-10-21T02:00:00Z
    (re.compile(r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)"), ["%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"]),
    # DD/Mon/YYYY:HH:MM:SS (Apache CLF)
    (re.compile(r"(\d{2}/\w{3}/\d{4}:\d{2}:\d{2}:\d{2})"), ["%d/%b/%Y:%H:%M:%S"]),
    # Mon DD HH:MM:SS (syslog)
    (re.compile(r"(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})"), ["%b %d %H:%M:%S"]),
    # DD-Mon-YYYY HH:MM:SS (Oracle)
    (re.compile(r"(\d{2}-\w{3}-\d{4}\s+\d{2}:\d{2}:\d{2})"), ["%d-%b-%Y %H:%M:%S"]),
    # Epoch millis (13 digits) or seconds (10 digits)
    (re.compile(r"\b(1\d{12})\b"), ["epoch_ms"]),
    (re.compile(r"\b(1\d{9})\b"), ["epoch_s"]),
]

_SEVERITY_RE = re.compile(
    r"\b(EMERGENCY|EMERG|ALERT|CRITICAL|CRIT|FATAL|SEVERE|ERROR|ERR|WARNING|WARN|NOTICE|INFO|DEBUG|TRACE)\b", re.I
)

# Stack trace continuation patterns
_STACKTRACE_CONTINUATIONS = re.compile(
    r"^\s+(?:at |Caused by:|\.{3} \d+ more|File \"|Traceback|During handling|The above exception)"
    r"|^\s+[\w.$]+(?:Exception|Error|Fault):"
    r"|^\s+\^"                # Python caret indicator
    r"|^\s+\|"                # pipe-style continuation
    r"|^\t+\w",              # tab-indented lines (common in Java stack traces)
    re.M
)


def _parse_timestamp(ts_str):
    """Try multiple formats to parse a timestamp string."""
    ts_str = ts_str.strip().rstrip("Z")
    # Remove timezone offset for simple parsing
    clean = re.sub(r"[+-]\d{2}:?\d{2}$", "", ts_str)
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S.%f",
                "%Y-%m-%d %H:%M:%S", "%d/%b/%Y:%H:%M:%S", "%b %d %H:%M:%S",
                "%d-%b-%Y %H:%M:%S", "%m/%d/%Y %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(clean, fmt)
        except ValueError:
            continue
    return None


def _detect_severity(line):
    """Extract severity level from a log line."""
    m = _SEVERITY_RE.search(line)
    if m:
        sev = m.group(1).upper()
        # Normalize aliases
        if sev in ("ERR",):
            sev = "ERROR"
        elif sev in ("CRIT",):
            sev = "CRITICAL"
        elif sev == "WARNING":
            sev = "WARN"
        elif sev == "EMERG":
            sev = "EMERGENCY"
        return sev
    return _infer_severity_from_context(line)


def _infer_severity_from_context(line):
    """Infer severity from keywords when no explicit severity marker is found."""
    ll = line.lower()
    if re.search(r"\b(fatal|critical|emergency|panic|crash|abort|segfault|oom-killer|oomkilled)\b", ll):
        return "FATAL"
    if re.search(r"\b(error|failed|failure|exception|traceback|stderr|ora-\d|econnrefused|enoent)\b", ll):
        return "ERROR"
    if re.search(r"\b(warn(?:ing)?|deprecated|slow|degraded|retry|retrying|timed?\s*out|no progress)\b", ll):
        return "WARN"
    if re.search(r"\b(debug|trace|verbose)\b", ll):
        return "DEBUG"
    return ""


def _extract_timestamp(line):
    """Try each timestamp pattern on a line; return the first match as datetime."""
    for regex, fmts in _TS_PATTERNS:
        m = regex.search(line)
        if m:
            raw = m.group(1)
            if fmts == ["epoch_ms"]:
                try:
                    return datetime.fromtimestamp(int(raw) / 1000)
                except (ValueError, OSError):
                    continue
            elif fmts == ["epoch_s"]:
                try:
                    return datetime.fromtimestamp(int(raw))
                except (ValueError, OSError):
                    continue
            else:
                ts = _parse_timestamp(raw)
                if ts:
                    return ts
    return None


def _is_stack_continuation(line):
    """True if `line` looks like a continuation of a stack trace / traceback."""
    return bool(_STACKTRACE_CONTINUATIONS.match(line))

# ═══════════════════════════════════════════════════════════════════════════════
#  ANALYSIS ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

def analyze(log_text):
    """Production-grade full-depth analysis of ANY log.

    1. Parses every line (timestamp, severity, content).
    2. Groups multi-line stack traces with their parent error.
    3. Matches every line against the full rule library.
    4. Deduplicates repeated errors.
    5. Identifies root cause (earliest specific error with highest severity).
    6. Labels everything else as symptoms.
    7. Detects execution phases (startup → processing → failure → cleanup).
    8. Returns rich data for the UI.
    """
    raw_lines = log_text.splitlines()
    lines = [x.rstrip() for x in raw_lines if x.strip()]

    if not lines:
        return _empty_result()

    # ── Step 1: Parse every line ─────────────────────────────────────────
    parsed = []
    for idx, line in enumerate(lines):
        entry = {
            "line_no": idx + 1,
            "line": line,
            "timestamp": _extract_timestamp(line),
            "severity": _detect_severity(line),
            "is_stack_continuation": _is_stack_continuation(line),
            "matches": [],            # rule matches for this line
            "is_root_cause": False,
            "is_symptom": False,
            "stack_group": None,       # line_no of parent error
            "phase": "",
        }
        parsed.append(entry)

    # ── Step 2: Group stack trace continuations ──────────────────────────
    current_error_line = None
    for entry in parsed:
        if entry["severity"] in ("ERROR", "FATAL", "CRITICAL", "SEVERE", "EMERGENCY"):
            current_error_line = entry["line_no"]
            entry["stack_group"] = entry["line_no"]
        elif entry["is_stack_continuation"] and current_error_line is not None:
            entry["stack_group"] = current_error_line
        else:
            if entry["severity"] and entry["severity"] not in ("", "TRACE", "DEBUG"):
                current_error_line = None  # reset on a new non-continuation log line

    # ── Step 3: Match every line against all rules ───────────────────────
    all_matches = []
    for entry in parsed:
        line = entry["line"]
        for rule in RULES:
            hits = [p for p in rule["patterns"] if re.search(p, line, re.I)]
            if hits:
                match_info = {
                    "line_no": entry["line_no"],
                    "line": line,
                    "rule": rule,
                    "patterns_hit": hits,
                    "severity": entry["severity"],
                    "timestamp": entry["timestamp"],
                    "stack_group": entry["stack_group"],
                }
                entry["matches"].append(match_info)
                all_matches.append(match_info)
                break  # first matching rule wins per line

    # ── Step 4: Deduplicate repeated errors ──────────────────────────────
    dedup_map = defaultdict(list)  # (category, normalized_msg) → [match_info, ...]
    for m in all_matches:
        # Normalize: strip timestamps, numbers and whitespace for grouping
        norm = re.sub(r"\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2}[.\d]*", "", m["line"])
        norm = re.sub(r"\b\d+\b", "N", norm).strip().lower()
        key = (m["rule"]["category"], norm)
        dedup_map[key].append(m)

    unique_errors = []
    for key, group in dedup_map.items():
        representative = group[0]  # earliest occurrence
        unique_errors.append({
            **representative,
            "occurrences": len(group),
            "all_line_nos": [m["line_no"] for m in group],
        })
    unique_errors.sort(key=lambda x: x["line_no"])

    # ── Step 5: Identify root cause ──────────────────────────────────────
    # Strategy: The root cause is the earliest error with the highest
    # specificity (non-generic category).  Among ties, prefer higher severity.
    specific = [m for m in all_matches if m["rule"]["category"] != "Generic error signal"]
    generic  = [m for m in all_matches if m["rule"]["category"] == "Generic error signal"]

    def _score(m):
        """Lower score = more likely root cause.  Prioritize specificity, then
        severity, then earliness."""
        sev_rank = _SEV_ORDER.get(m.get("severity", ""), 2)
        # Invert severity so higher severity gets lower score
        return (m["line_no"], -sev_rank)

    root_cause = None
    if specific:
        # Among specific matches, pick the earliest high-severity one
        high_sev = [m for m in specific if _SEV_ORDER.get(m.get("severity", ""), 0) >= 5]
        candidates = high_sev if high_sev else specific
        root_cause = min(candidates, key=lambda m: m["line_no"])
    elif generic:
        high_sev_gen = [m for m in generic if _SEV_ORDER.get(m.get("severity", ""), 0) >= 5]
        candidates = high_sev_gen if high_sev_gen else generic
        root_cause = min(candidates, key=lambda m: m["line_no"])

    symptoms = [m for m in all_matches if root_cause and m["line_no"] != root_cause["line_no"]]

    # Mark entries
    for entry in parsed:
        if root_cause and entry["line_no"] == root_cause["line_no"]:
            entry["is_root_cause"] = True
        elif entry["line_no"] in {m["line_no"] for m in symptoms}:
            entry["is_symptom"] = True

    # ── Step 6: Phase detection ──────────────────────────────────────────
    _detect_phases(parsed, root_cause)

    # ── Step 7: Focused context around root cause ────────────────────────
    focused = []
    if root_cause:
        rc_idx = root_cause["line_no"] - 1
        # Include the whole stack trace group if any
        group_lines = [e for e in parsed if e.get("stack_group") == root_cause["line_no"]]
        if group_lines:
            first_gl = group_lines[0]["line_no"] - 1
            last_gl = group_lines[-1]["line_no"] - 1
            start = max(0, first_gl - 10)
            end = min(len(parsed), last_gl + 11)
        else:
            start = max(0, rc_idx - 10)
            end = min(len(parsed), rc_idx + 11)
        focused = parsed[start:end]
    elif parsed:
        focused = parsed[-20:]

    # ── Step 8: Category breakdown ───────────────────────────────────────
    category_counts = Counter(m["rule"]["category"] for m in all_matches)

    # ── Step 9: Analysis depth metrics ──────────────────────────────────
    lines_with_ts  = sum(1 for e in parsed if e.get("timestamp"))
    lines_with_sev = sum(1 for e in parsed if e.get("severity"))
    total_lines    = len(lines) if lines else 1
    coverage_pct   = round(len(all_matches) / total_lines * 100, 1)
    analysis_depth = {
        "lines_with_timestamps": lines_with_ts,
        "lines_with_severity":   lines_with_sev,
        "lines_matched":         len(all_matches),
        "coverage_pct":          coverage_pct,
    }

    return {
        "lines": lines,
        "parsed": parsed,
        "matches": all_matches,
        "specific": specific,
        "generic": generic,
        "unique_errors": unique_errors,
        "root_cause": root_cause,
        "symptoms": symptoms,
        "focused_context": focused,
        "category_counts": dict(category_counts),
        "analysis_depth": analysis_depth,
        # backward compat
        "selected": root_cause,
        "context": focused,
        "full_context": parsed,
    }


def _empty_result():
    return {"lines": [], "parsed": [], "matches": [], "specific": [], "generic": [],
            "unique_errors": [], "root_cause": None, "symptoms": [], "focused_context": [],
            "category_counts": {}, "analysis_depth": {"lines_with_timestamps": 0, "lines_with_severity": 0, "lines_matched": 0, "coverage_pct": 0.0},
            "selected": None, "context": [], "full_context": []}


def _detect_phases(parsed, root_cause):
    """Label each line with its probable execution phase."""
    rc_line = root_cause["line_no"] if root_cause else len(parsed) + 1
    _STARTUP_KW = re.compile(r"initializ|start(?:ing|ed|up)|bootstrap|loading|connecting|checking|validat", re.I)
    _CLEANUP_KW = re.compile(r"cleanup|clean up|shutdown|closing|finaliz|disconnect|teardown", re.I)

    for entry in parsed:
        ln = entry["line_no"]
        line = entry["line"]
        if _CLEANUP_KW.search(line):
            entry["phase"] = "Cleanup"
        elif ln < rc_line and _STARTUP_KW.search(line):
            entry["phase"] = "Startup"
        elif entry["is_root_cause"] or entry["is_symptom"]:
            entry["phase"] = "Failure"
        elif ln < rc_line:
            entry["phase"] = "Processing"
        else:
            entry["phase"] = "Post-failure"

# ═══════════════════════════════════════════════════════════════════════════════
#  REPORT BUILDERS
# ═══════════════════════════════════════════════════════════════════════════════

def compute_log_stats(parsed):
    """Compute comprehensive statistics from parsed log entries."""
    total = len(parsed)
    counts = Counter()
    timestamps = []
    phases = Counter()

    for entry in parsed:
        sev = entry.get("severity", "") or "OTHER"
        counts[sev] += 1
        if entry.get("timestamp"):
            timestamps.append(entry["timestamp"])
        if entry.get("phase"):
            phases[entry["phase"]] += 1

    duration = ""
    time_span = ""
    if timestamps:
        first, last = timestamps[0], timestamps[-1]
        delta = last - first
        total_secs = max(int(delta.total_seconds()), 0)
        if total_secs >= 3600:
            duration = f"{total_secs // 3600}h {(total_secs % 3600) // 60}m {total_secs % 60}s"
        elif total_secs >= 60:
            duration = f"{total_secs // 60}m {total_secs % 60}s"
        else:
            duration = f"{total_secs}s"
        time_span = f"{first:%Y-%m-%d %H:%M:%S}  →  {last:%Y-%m-%d %H:%M:%S}"

    return {
        "total_lines": total,
        "counts": dict(counts),
        "time_span": time_span,
        "duration": duration,
        "phases": dict(phases),
    }


def build_event_chain(result):
    """Generate a causal-chain narrative."""
    root = result.get("root_cause")
    symptoms = result.get("symptoms", [])
    unique = result.get("unique_errors", [])

    if not root:
        return "No specific error pattern was matched in the log. Manual review is required."

    rule = root["rule"]
    parts = [f"**Root Cause (Line {root['line_no']}):** `{root['line'].strip()}`"]
    parts.append(f"**Category:** {rule['category']}  ·  **Suggested owner:** {rule['owner']}  ·  **Priority:** {rule['priority']}")
    parts.append(f"**Assessment:** {rule['cause']}")

    if symptoms:
        parts.append("")
        parts.append(f"**Downstream effects ({len(symptoms)} signal{'s' if len(symptoms)!=1 else ''}):**")
        # Group symptoms by category for cleaner display
        sym_by_cat = defaultdict(list)
        for s in symptoms:
            sym_by_cat[s["rule"]["category"]].append(s)
        for cat, syms in sym_by_cat.items():
            if len(syms) <= 3:
                for s in syms:
                    parts.append(f"- Line {s['line_no']}: `{s['line'].strip()}` — _{cat}_")
            else:
                parts.append(f"- **{cat}** — {len(syms)} occurrences (lines {', '.join(str(s['line_no']) for s in syms[:5])}{'…' if len(syms) > 5 else ''})")

    # Dedup info
    repeated = [u for u in unique if u.get("occurrences", 1) > 1]
    if repeated:
        parts.append("")
        parts.append("**Repeated errors:**")
        for r in repeated:
            parts.append(f"- _{r['rule']['category']}_ — repeated {r['occurrences']}× (lines {', '.join(str(ln) for ln in r['all_line_nos'][:8])}{'…' if len(r['all_line_nos']) > 8 else ''})")

    parts.append("")
    sym_cats = list({s["rule"]["category"] for s in symptoms})
    if sym_cats:
        parts.append(
            f"**Conclusion:** The root failure is **{rule['category']}** at line {root['line_no']}.  "
            f"All {len(symptoms)} subsequent error signal(s) ({', '.join(sym_cats)}) are downstream consequences.  "
            f"Fix the root cause first; the symptoms should resolve."
        )
    else:
        parts.append(
            f"**Conclusion:** The log contains a single error signal — **{rule['category']}** at line {root['line_no']}.  "
            f"Investigate using the recommended checks."
        )

    # ── Timeline summary ──────────────────────────────────────────────────
    all_sym_ts = [s.get("timestamp") for s in symptoms if s.get("timestamp")]
    rc_ts = root.get("timestamp") if root else None
    if rc_ts or all_sym_ts:
        parts.append("")
        parts.append("**Timeline summary:**")
        if rc_ts:
            parts.append(f"- First error: `{rc_ts:%Y-%m-%d %H:%M:%S}` (root cause, line {root['line_no']})")
        if all_sym_ts:
            last_sym_ts = max(all_sym_ts)
            parts.append(f"- Last error:  `{last_sym_ts:%Y-%m-%d %H:%M:%S}` (symptom)")

    return "\n".join(parts)


def build_timeline_rows(parsed):
    """Build a flat list of dicts for the timeline dataframe."""
    rows = []
    for entry in parsed:
        role = ""
        if entry.get("is_root_cause"):
            role = "🔴 ROOT CAUSE"
        elif entry.get("is_symptom"):
            role = "🟡 SYMPTOM"
        elif entry.get("is_stack_continuation") and entry.get("stack_group"):
            role = "📎 Stack trace"

        ts_str = ""
        if entry.get("timestamp"):
            ts_str = entry["timestamp"].strftime("%H:%M:%S") if entry["timestamp"] else ""

        rows.append({
            "Line": entry["line_no"],
            "Time": ts_str,
            "Sev": entry.get("severity", ""),
            "Phase": entry.get("phase", ""),
            "Role": role,
            "Message": entry["line"],
        })
    return rows

# ── Full log HTML builder ────────────────────────────────────────────────────

def build_full_log_html(parsed, root_cause, symptoms):
    """Render the full log as color-coded HTML, one row per parsed entry."""
    rc_line_no = root_cause["line_no"] if root_cause else -1
    sym_line_nos = {s["line_no"] for s in symptoms}

    _SEV_BG = {
        "FATAL":     "#fff5f5",
        "CRITICAL":  "#fff5f5",
        "EMERGENCY": "#fff5f5",
        "SEVERE":    "#fff5f5",
        "ERROR":     "#fff5f5",
        "WARN":      "#fffde7",
        "WARNING":   "#fffde7",
    }
    _SEV_COLOR = {
        "FATAL":     "#c0392b",
        "CRITICAL":  "#c0392b",
        "EMERGENCY": "#c0392b",
        "SEVERE":    "#c0392b",
        "ERROR":     "#e74c3c",
        "WARN":      "#d68910",
        "WARNING":   "#d68910",
        "INFO":      "#2e86c1",
        "DEBUG":     "#7f8c8d",
        "TRACE":     "#aab7b8",
    }

    rows_html = []
    for entry in parsed:
        ln   = entry["line_no"]
        sev  = entry.get("severity", "")
        line = entry["line"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        # Choose background
        if ln == rc_line_no:
            bg = "#fde8e8"
        elif ln in sym_line_nos:
            bg = "#fef9e7"
        else:
            bg = _SEV_BG.get(sev, "transparent")

        # Severity badge
        badge_color = _SEV_COLOR.get(sev, "#95a5a6")
        if sev:
            badge = (
                f'<span style="display:inline-block;min-width:56px;text-align:center;'
                f'background:{badge_color};color:white;border-radius:4px;padding:0 5px;'
                f'font-size:.72rem;font-weight:600;margin-right:6px;">{sev}</span>'
            )
        else:
            badge = '<span style="display:inline-block;min-width:56px;margin-right:6px;"></span>'

        # Role marker
        role_marker = ""
        if ln == rc_line_no:
            role_marker = ' <span style="color:#c0392b;font-weight:700;">&#9668;&#9668;&#9668; ROOT CAUSE</span>'
        elif ln in sym_line_nos:
            role_marker = ' <span style="color:#d68910;">&#9668; symptom</span>'

        rows_html.append(
            f'<div style="background:{bg};padding:2px 6px;border-bottom:1px solid rgba(0,0,0,.04);">'
            f'<span style="color:#aaa;font-size:.75rem;min-width:38px;display:inline-block;'
            f'text-align:right;margin-right:8px;">{ln}</span>'
            f'{badge}'
            f'<span style="font-family:monospace;font-size:.82rem;">{line}</span>'
            f'{role_marker}'
            f'</div>'
        )

    return (
        '<div style="max-height:520px;overflow-y:auto;border:1px solid #ddd;border-radius:8px;'
        'background:#fafafa;padding:4px 0;">'
        + "".join(rows_html)
        + "</div>"
    )


# ── Notification parser ──────────────────────────────────────────────────────

def extract(pattern, text):
    m = re.search(pattern, text, re.I | re.M)
    return m.group(1).strip() if m else ""

def parse_notification(text):
    subject = extract(r"^\s*Subject\s*:\s*(.+)$", text)
    job = extract(r"^\s*(?:Job Name|Job|Task)\s*:\s*(.+)$", text)
    if not job and subject:
        job = re.sub(r"(?i)^.*?(?:job failure|job failed|failure)\s*[-:]\s*", "", subject).strip()
    return {
      "subject": subject, "job": job,
      "schedule": extract(r"^\s*(?:Schedule|Workflow)\s*:\s*(.+)$", text),
      "status": extract(r"^\s*Status\s*:\s*(.+)$", text),
      "time": extract(r"^\s*(?:Failure Time|Failed At|Timestamp)\s*:\s*(.+)$", text),
      "incident": extract(r"\b(INC\d{5,})\b", text),
      "environment": extract(r"^\s*Environment\s*:\s*(.+)$", text),
    }

def infer_job_details(log_text, meta):
    """Fill gaps in notification metadata using log content."""
    if not meta.get("job"):
        for pattern in [r"Job name\s*:\s*(.+)$", r"Initializing job\s+([A-Za-z0-9_.-]+)",
                        r"Starting\s+job\s+([A-Za-z0-9_.-]+)", r"job[=: ]+([A-Za-z0-9_.-]+)"]:
            found = extract(pattern, log_text)
            if found:
                meta["job"] = found
                break
    if not meta.get("schedule"):
        meta["schedule"] = extract(r"schedule\s+([A-Za-z0-9_.-]+)", log_text)
    if not meta.get("environment"):
        meta["environment"] = (extract(r"Environment\s*:\s*(.+)$", log_text) or
                               extract(r"Runtime environment\s*:\s*(.+)$", log_text) or
                               extract(r"env[=: ]+(\w+)", log_text))
    if not meta.get("time"):
        for line in log_text.splitlines():
            if re.search(r"error|failed|stuck|timeout|timed out|not found|no progress|fatal|critical", line, re.I):
                stamp = re.search(r"(\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2})", line)
                if stamp:
                    meta["time"] = stamp.group(1)
                    break
    if not meta.get("status"):
        if re.search(r"\b(stuck|no progress detected|maximum wait threshold reached|hung|stall|freeze)\b", log_text, re.I):
            meta["status"] = "Stuck / no progress detected"
        elif re.search(r"\b(failed|job failed|status FAILED|abend|terminated|crash)\b", log_text, re.I):
            meta["status"] = "Failed"
        else:
            meta["status"] = "Requires review"
    return meta

# ── Operator email builder ───────────────────────────────────────────────────

def build_operator_email(meta, result, log_filename, report_filename):
    root = result.get("root_cause") or result.get("selected")
    category = root["rule"]["category"] if root else "No configured pattern matched"

    # ALL matched lines — no truncation
    matched_lines = [f"- Line {m['line_no']}: [{m['rule']['category']}] {m['line']}" for m in result.get("matches", [])]
    evidence = "\n".join(matched_lines) if matched_lines else "- No configured error signature matched; please review the attached log."

    root_summary = ""
    if root:
        root_summary = (
            f"\nRoot Cause (Line {root['line_no']}): {root['line'].strip()}\n"
            f"Category: {root['rule']['category']}\n"
            f"Assessment: {root['rule']['cause']}\n"
        )
        symptoms = result.get("symptoms", [])
        if symptoms:
            root_summary += f"Downstream symptoms: {len(symptoms)} additional error signal(s) detected.\n"
        dedup = result.get("unique_errors", [])
        repeated = [u for u in dedup if u.get("occurrences", 1) > 1]
        if repeated:
            root_summary += f"Repeated errors: {sum(u['occurrences'] for u in repeated)} total from {len(repeated)} unique pattern(s).\n"

    return (
        "Hi Operator Team,\n\n"
        f"The OpCon job below has reported a failure or appears to be stuck. Please review the attached log ({log_filename}) and analysis report ({report_filename}).\n\n"
        f"Job Name: {meta.get('job') or 'Not detected'}\n"
        f"Schedule: {meta.get('schedule') or 'Not detected'}\n"
        f"Status: {meta.get('status') or 'Failed / stuck'}\n"
        f"Failure Time: {meta.get('time') or 'Not detected'}\n"
        f"Incident Number: {meta.get('incident') or 'Not provided'}\n"
        f"Environment: {meta.get('environment') or 'Not detected'}\n"
        f"Likely Error Category: {category}\n"
        f"{root_summary}\n"
        f"Full log evidence ({len(matched_lines)} matched line(s)):\n{evidence}\n\n"
        "Could you please review the logs and confirm whether we should kill the job and restart it, or whether another action is required? "
        "We will wait for your explicit green flag before taking any kill/restart action.\n\n"
        "Thanks & Regards,\nOperations Team"
    )

# ── Comprehensive report builder ─────────────────────────────────────────────

def make_report(meta, result):
    root = result.get("root_cause") or result.get("selected")
    rule = root["rule"] if root else None
    parsed = result.get("parsed", result.get("full_context", []))
    stats = compute_log_stats(parsed)
    symptoms = result.get("symptoms", [])
    unique = result.get("unique_errors", [])

    out = ["=" * 72]
    out.append("  OPS PILOT — COMPREHENSIVE JOB FAILURE ANALYSIS REPORT")
    out.append("=" * 72)
    out.append(f"Generated: {datetime.now():%Y-%m-%d %H:%M:%S}")
    out.append("")

    # Section 1: Job details
    out.append("─" * 44)
    out.append("  1. JOB & INCIDENT DETAILS")
    out.append("─" * 44)
    for key, label in [("job","Job"),("schedule","Schedule"),("incident","ServiceNow incident"),
                       ("time","Failure time"),("status","Reported status"),("environment","Environment")]:
        out.append(f"  {label}: {meta.get(key) or 'Not detected'}")

    # Section 2: Log statistics
    out.append("")
    out.append("─" * 44)
    out.append("  2. LOG STATISTICS")
    out.append("─" * 44)
    out.append(f"  Total lines scanned: {stats['total_lines']}")
    out.append(f"  Total error signals: {len(result.get('matches', []))}")
    out.append(f"  Unique error patterns: {len(unique)}")
    out.append(f"  Time span: {stats.get('time_span') or 'N/A'}")
    out.append(f"  Duration: {stats.get('duration') or 'N/A'}")
    for sev in ["ERROR", "FATAL", "CRITICAL", "WARN", "INFO", "DEBUG"]:
        cnt = stats["counts"].get(sev, 0)
        if cnt:
            out.append(f"  {sev} lines: {cnt}")
    if stats.get("phases"):
        out.append("  Execution phases:")
        for phase, cnt in sorted(stats["phases"].items()):
            out.append(f"    {phase}: {cnt} lines")

    # Section 3: Root cause
    out.append("")
    out.append("─" * 44)
    out.append("  3. ROOT CAUSE IDENTIFICATION")
    out.append("─" * 44)
    if root:
        out.append(f"  ▶ Line {root['line_no']}: {root['line']}")
        out.append(f"  Category: {rule['category']}")
        out.append(f"  Suggested owner: {rule['owner']}")
        out.append(f"  Priority: {rule['priority']}")
        out.append(f"  Assessment: {rule['cause']}")
    else:
        out.append("  No configured pattern matched. Manual review required.")

    # Section 4: Symptoms
    out.append("")
    out.append("─" * 44)
    out.append(f"  4. DOWNSTREAM SYMPTOMS ({len(symptoms)} detected)")
    out.append("─" * 44)
    if symptoms:
        for s in symptoms:
            out.append(f"  Line {s['line_no']}: [{s['rule']['category']}] {s['line']}")
    else:
        out.append("  No additional error signals beyond the root cause.")

    # Section 5: Deduplicated errors
    repeated = [u for u in unique if u.get("occurrences", 1) > 1]
    if repeated:
        out.append("")
        out.append("─" * 44)
        out.append(f"  5. REPEATED ERRORS ({len(repeated)} patterns)")
        out.append("─" * 44)
        for r in repeated:
            out.append(f"  [{r['rule']['category']}] × {r['occurrences']}")
            out.append(f"    First: Line {r['line_no']}: {r['line']}")
            out.append(f"    All lines: {', '.join(str(ln) for ln in r['all_line_nos'])}")

    # Section 6: Event chain
    out.append("")
    out.append("─" * 44)
    out.append("  6. EVENT CHAIN (causal narrative)")
    out.append("─" * 44)
    chain = build_event_chain(result)
    for cl in chain.splitlines():
        clean = cl.replace("**", "").replace("`", "").replace("_", "")
        out.append(f"  {clean}")

    # Section 7: Recommended checks
    out.append("")
    out.append("─" * 44)
    out.append("  7. RECOMMENDED CHECKS")
    out.append("─" * 44)
    if rule:
        for check in rule["checks"]:
            out.append(f"  • {check}")
        out.append(f"  ⚠ Guardrail: {rule['guardrail']}")
    else:
        out.append("  Review the full log manually and compare with approved runbooks.")

    # Section 8: All matched lines
    out.append("")
    out.append("─" * 44)
    out.append(f"  8. ALL MATCHED LOG LINES ({len(result.get('matches', []))} total)")
    out.append("─" * 44)
    for m in result.get("matches", []):
        marker = " ◄ ROOT CAUSE" if (root and m["line_no"] == root["line_no"]) else ""
        out.append(f"  Line {m['line_no']}: [{m['rule']['category']}] {m['line']}{marker}")
    if not result.get("matches"):
        out.append("  No configured patterns matched.")

    # Section 9: Full annotated log
    out.append("")
    out.append("─" * 44)
    out.append("  9. FULL LOG (annotated)")
    out.append("─" * 44)
    matched_set = {m["line_no"] for m in result.get("matches", [])}
    for entry in parsed:
        ln = entry["line_no"] if isinstance(entry, dict) else 0
        line_text = entry["line"] if isinstance(entry, dict) else str(entry)
        marker = ""
        if root and ln == root["line_no"]:
            marker = "  ◄◄◄ ROOT CAUSE"
        elif ln in matched_set:
            marker = "  ◄ SYMPTOM"
        phase_tag = f" [{entry.get('phase','')}]" if isinstance(entry, dict) and entry.get("phase") else ""
        out.append(f"  {ln:>5} |{phase_tag} {line_text}{marker}")

    out.append("")
    out.append("=" * 72)
    out.append("  Rule-based suggestion only. Validate against the approved runbook.")
    out.append("  No live system actions were performed.")
    out.append("=" * 72)
    return "\n".join(out)

# ═══════════════════════════════════════════════════════════════════════════════
#  STREAMLIT UI
# ═══════════════════════════════════════════════════════════════════════════════

# ── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🔎 OpsPilot")
    st.caption("Production Log Intelligence")
    st.markdown("### Quick demo")
    if st.button("Load sample email + log", use_container_width=True):
        st.session_state["notification"] = SAMPLE_EMAIL
        st.session_state["log_editor"] = SAMPLE_LOG
        st.session_state.pop("analysis", None)
    if st.button("Load sample 2 — DB timeout", use_container_width=True):
        st.session_state["notification"] = ""
        st.session_state["log_editor"] = SAMPLE_LOG_2
        st.session_state.pop("analysis", None)
    st.markdown("### Test log files")
    st.download_button("Sample 1 — Missing file", SAMPLE_LOG, file_name="sample_missing_input_file.log", mime="text/plain", use_container_width=True)
    st.download_button("Sample 2 — DB timeout / stuck", SAMPLE_LOG_2, file_name="sample_database_timeout_stuck.log", mime="text/plain", use_container_width=True)
    st.markdown("---")
    st.markdown("### Supported log formats")
    st.caption("✔ Any plain-text log  \n✔ Syslog  \n✔ Apache / Nginx  \n✔ Java stack traces  \n✔ Python tracebacks  \n✔ JSON logs (line-per-entry)  \n✔ Docker / K8s logs  \n✔ Windows Event logs  \n✔ Oracle / SQL Server / MySQL / PostgreSQL  \n✔ Custom timestamp formats")
    st.markdown("---")
    st.markdown("### Analysis depth")
    st.caption("OpsPilot reads 100% of your log. No line is skipped. Root cause = earliest specific error. Symptoms = all subsequent errors.")
    st.markdown("---")
    st.caption("Offline prototype · No live system connections")

# ── Hero ─────────────────────────────────────────────────────────────────────

st.markdown("""<div class="hero"><div class="eyebrow">Production-grade · Any log format · Full-depth analysis</div><h1>Job Failure Analysis Assistant</h1><p>Reads every line of your log. Identifies root cause vs symptoms. Groups stack traces. Deduplicates repeated errors. Builds a complete failure timeline.</p></div>""", unsafe_allow_html=True)
st.warning("Use fictional or client-approved sanitized data only. Rule-based analysis — not a confirmed root cause. Does not connect to live systems.")

tab1, tab2, tab3, tab4 = st.tabs(["🔍 Analyze log", "🟡 Operator approval", "✉️ Draft operator email", "📘 How it works"])

# ═══════════════════════════════════════════════════════════════════════════════
#  TAB 1 — Full-depth analysis
# ═══════════════════════════════════════════════════════════════════════════════

with tab1:
    col1, col2 = st.columns([1, 1.5], gap="large")

    with col1:
        st.subheader("1 · Failure notification")
        notification = st.text_area("Paste the failure email (optional)", value=st.session_state.get("notification",""), height=170, placeholder="Subject, job name, schedule, incident ID…", key="notification_editor")
        st.subheader("2 · Provide log")
        upload = st.file_uploader("Upload a .log or .txt file", type=["log","txt"])
        pasted_log = st.text_area("Or paste log text", value=st.session_state.get("log_editor",""), height=240, placeholder="Paste the FULL log — every line is analyzed…", key="pasted_log")
        if upload is not None:
            try:
                uploaded_text = upload.getvalue().decode("utf-8", errors="replace")
                st.caption(f"📄 Loaded: {upload.name} · {len(uploaded_text.splitlines())} lines · {len(uploaded_text):,} bytes")
                log_text = uploaded_text
            except Exception:
                log_text = pasted_log
        else:
            log_text = pasted_log
        st.caption("💡 Paste the **full log**. OpsPilot reads every line to find the true root cause — not just the first error.")
        if st.button("🔍 Analyze failure", type="primary", use_container_width=True):
            if not log_text.strip():
                st.error("Upload a log or paste log text first.")
            else:
                with st.spinner("Analyzing full log — scanning every line…"):
                    parsed_meta = infer_job_details(log_text, parse_notification(notification))
                    analysis_result = analyze(log_text)
                    st.session_state["analysis"] = {
                        "meta": parsed_meta,
                        "result": analysis_result,
                        "raw_log": log_text,
                        "log_filename": upload.name if upload is not None else "pasted_log.txt",
                        "notification": notification,
                        "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }

    with col2:
        st.subheader("3 · Analysis results")
        if "analysis" not in st.session_state:
            st.markdown(
                '<div class="panel"><div class="eyebrow">Ready for analysis</div>'
                '<h3>Waiting for a log</h3>'
                '<p>Provide a <b>full</b> log file or paste log content, then click <b>Analyze failure</b>.</p>'
                '<p>OpsPilot reads <b>every line</b>, detects <b>any log format</b>, groups stack traces, '
                'deduplicates repeated errors, and identifies the true root cause.</p></div>',
                unsafe_allow_html=True,
            )
        else:
            a = st.session_state["analysis"]
            meta, res = a["meta"], a["result"]
            root = res.get("root_cause")
            rule = root["rule"] if root else None
            symptoms = res.get("symptoms", [])
            unique = res.get("unique_errors", [])
            parsed_entries = res.get("parsed", res.get("full_context", []))
            stats = compute_log_stats(parsed_entries)

            # ── KPI row ──────────────────────────────────────────────────
            k1, k2, k3, k4, k5, k6 = st.columns(6)
            k1.metric("Lines scanned", stats["total_lines"])
            k2.metric("Error signals", len(res["matches"]))
            k3.metric("Unique errors", len(unique))
            k4.metric("Root cause", "✅ Found" if root else "❓ Review")
            k5.metric("Duration", stats.get("duration") or "N/A")
            k6.metric("RC Category", rule["category"].split("/")[0].strip() if rule else "N/A")

            # ── Job / incident details ───────────────────────────────────
            st.markdown("#### Job / incident details")
            d1, d2, d3 = st.columns(3)
            d1.write(f"**Job:** {meta.get('job') or 'Not detected'}")
            d1.write(f"**Schedule:** {meta.get('schedule') or 'Not detected'}")
            d2.write(f"**Incident:** {meta.get('incident') or 'Not detected'}")
            d2.write(f"**Failure time:** {meta.get('time') or 'Not detected'}")
            d3.write(f"**Environment:** {meta.get('environment') or 'Not detected'}")
            d3.write(f"**Status:** {meta.get('status') or 'Not detected'}")

            # ── ROOT CAUSE ───────────────────────────────────────────────
            st.markdown("#### 🔴 Root cause identification")
            if root:
                st.markdown(
                    f'<div class="rc-box">'
                    f'<strong>Line {root["line_no"]}:</strong> <code>{root["line"].strip()}</code><br>'
                    f'<strong>Category:</strong> {rule["category"]} · '
                    f'<strong>Owner:</strong> {rule["owner"]} · '
                    f'<strong>Priority:</strong> {rule["priority"]}'
                    f'<br><strong>Assessment:</strong> {rule["cause"]}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                st.markdown("**Recommended checks:**")
                for check in rule["checks"]:
                    st.markdown(f"- ✅ {check}")
                st.warning("⚠️ Recovery guardrail: " + rule["guardrail"])
            else:
                st.info("No configured pattern matched any line. Review the full log manually and consider adding new rule patterns.")

            # ── SYMPTOMS ─────────────────────────────────────────────────
            if symptoms:
                with st.expander(f"🟡 Downstream symptoms — {len(symptoms)} error signal(s)", expanded=True):
                    st.caption("These errors are consequences of the root cause. Fix the root cause first.")
                    # Group by category
                    sym_by_cat = defaultdict(list)
                    for s in symptoms:
                        sym_by_cat[s["rule"]["category"]].append(s)
                    for cat, syms in sym_by_cat.items():
                        st.markdown(f"**{cat}** — {len(syms)} signal(s)")
                        for s in syms[:10]:
                            st.markdown(
                                f'<div class="sym-box">Line {s["line_no"]}: <code>{s["line"].strip()}</code></div>',
                                unsafe_allow_html=True,
                            )
                        if len(syms) > 10:
                            st.caption(f"… and {len(syms) - 10} more")

            # ── DEDUPLICATED ERRORS ──────────────────────────────────────
            repeated = [u for u in unique if u.get("occurrences", 1) > 1]
            if repeated:
                with st.expander(f"🔁 Repeated errors — {len(repeated)} pattern(s)", expanded=False):
                    st.caption("These error messages appear multiple times. High counts may indicate a loop or cascade.")
                    for r in repeated:
                        st.markdown(
                            f'**{r["rule"]["category"]}** '
                            f'<span class="dup-badge">×{r["occurrences"]}</span>',
                            unsafe_allow_html=True,
                        )
                        st.code(r["line"], language=None)
                        st.caption(f"Lines: {', '.join(str(ln) for ln in r['all_line_nos'])}")

            # ── EVENT CHAIN ──────────────────────────────────────────────
            with st.expander("🔗 Event chain — causal narrative", expanded=True):
                st.markdown(build_event_chain(res))

            # ── PHASE ANALYSIS ───────────────────────────────────────────
            if stats.get("phases"):
                with st.expander("📐 Execution phase analysis", expanded=False):
                    st.caption("Detected phases of the job's execution.")
                    phase_data = []
                    for phase in ["Startup", "Processing", "Failure", "Post-failure", "Cleanup"]:
                        cnt = stats["phases"].get(phase, 0)
                        if cnt:
                            phase_data.append({"Phase": phase, "Lines": cnt})
                    if phase_data:
                        st.dataframe(phase_data, use_container_width=True, hide_index=True)

            # ── LOG STATISTICS ───────────────────────────────────────────
            with st.expander("📊 Log statistics", expanded=False):
                sc1, sc2, sc3, sc4, sc5, sc6 = st.columns(6)
                sc1.metric("Total", stats["total_lines"])
                sc2.metric("INFO", stats["counts"].get("INFO", 0))
                sc3.metric("WARN", stats["counts"].get("WARN", 0))
                sc4.metric("ERROR", stats["counts"].get("ERROR", 0))
                sc5.metric("FATAL", stats["counts"].get("FATAL", 0) + stats["counts"].get("CRITICAL", 0))
                sc6.metric("Other", stats["counts"].get("OTHER", 0) + stats["counts"].get("DEBUG", 0))
                if stats.get("time_span"):
                    st.write(f"**Time span:** {stats['time_span']}")
                    st.write(f"**Duration:** {stats['duration']}")
                if res.get("category_counts"):
                    st.markdown("**Error categories found:**")
                    for cat, cnt in sorted(res["category_counts"].items(), key=lambda x: -x[1]):
                        st.write(f"- {cat}: **{cnt}** line(s)")

            # ── ALL MATCHED EVIDENCE ─────────────────────────────────────
            with st.expander(f"📋 All matched log evidence — {len(res['matches'])} lines", expanded=False):
                if res["matches"]:
                    rows = []
                    for m in res["matches"]:
                        role = "🔴 ROOT CAUSE" if (root and m["line_no"] == root["line_no"]) else "🟡 Symptom"
                        rows.append({"Line": m["line_no"], "Role": role, "Category": m["rule"]["category"], "Log line": m["line"]})
                    st.dataframe(rows, use_container_width=True, hide_index=True)
                else:
                    st.caption("No configured error signature was found.")

            # ── FULL LOG TIMELINE ────────────────────────────────────────
            with st.expander("📜 Full log timeline — every line annotated", expanded=False):
                st.caption("Complete log with timestamps, severity, phases, root cause and symptoms marked. Nothing is truncated.")
                tl_rows = build_timeline_rows(parsed_entries)
                if tl_rows:
                    st.dataframe(tl_rows, use_container_width=True, hide_index=True, height=500)

            # ── FOCUSED CONTEXT ──────────────────────────────────────────
            with st.expander("🔍 Root cause context (±10 lines)", expanded=True):
                focused = res.get("focused_context", [])
                if focused:
                    code_lines = []
                    for x in focused:
                        marker = ""
                        if x.get("is_root_cause"):
                            marker = " ◄◄◄ ROOT CAUSE"
                        elif x.get("is_symptom"):
                            marker = " ◄ symptom"
                        elif x.get("is_stack_continuation") and x.get("stack_group"):
                            marker = " ◄ stack trace"
                        code_lines.append(f"{x['line_no']:>5} | {x['line']}{marker}")
                    st.code("\n".join(code_lines))
                else:
                    st.caption("No context available.")

            with st.expander("📄 Full log viewer — color-coded by severity", expanded=False):
                st.caption("Every log line, color-coded: 🔴 root cause · 🟡 symptoms · red = ERROR/FATAL · yellow = WARN")
                st.markdown(
                    build_full_log_html(parsed_entries, root, res.get("symptoms", [])),
                    unsafe_allow_html=True,
                )

            # ── DOWNLOAD ─────────────────────────────────────────────────
            st.download_button("📥 Download comprehensive analysis report", make_report(meta, res),
                             file_name="opspilot_analysis_report.txt", mime="text/plain", use_container_width=True)

# ═══════════════════════════════════════════════════════════════════════════════
#  TAB 2 — Operator approval
# ═══════════════════════════════════════════════════════════════════════════════

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
            "Operator team's instruction / notes (optional)", key="operator_notes",
            placeholder="Record the operator team's decision or reference. Do not include passwords or secrets.", height=100,
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
        st.download_button("Download operator workflow record (.txt)", report_text,
                         file_name="opspilot_operator_workflow.txt", mime="text/plain", use_container_width=True)
        st.caption("This tracker does not send messages, kill/restart jobs, or update ServiceNow automatically.")

# ═══════════════════════════════════════════════════════════════════════════════
#  TAB 3 — Draft operator email
# ═══════════════════════════════════════════════════════════════════════════════

with tab3:
    st.subheader("Draft email to operator team")
    st.caption("Creates a copyable email draft only. Does not send email.")
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
            email_status = st.selectbox("Job status", ["Failed", "Stuck / no progress detected", "Failed / stuck — needs review"],
                                       index=1 if "stuck" in (meta.get("status", "").lower()) else 0, key="email_status")
        with e2:
            email_incident = st.text_input("ServiceNow incident number", value=meta.get("incident", ""), key="email_incident")
            email_time = st.text_input("Failure time", value=meta.get("time", ""), key="email_time")
            email_environment = st.text_input("Environment", value=meta.get("environment", ""), key="email_environment")

        email_meta = {**meta, "job": email_job.strip(), "schedule": email_schedule.strip(),
                     "status": email_status, "incident": email_incident.strip(),
                     "time": email_time.strip(), "environment": email_environment.strip()}
        report_filename = "opspilot_analysis_report.txt"
        email_text = build_operator_email(email_meta, res, a.get("log_filename", "uploaded_log.log"), report_filename)
        st.text_input("Subject", value=f"Operator Guidance Required — {email_job or 'Job'} — {email_status}", key="email_subject")
        st.text_area("Email draft", value=email_text, height=400, key="email_body")
        c1, c2 = st.columns(2)
        with c1:
            st.download_button("Download email draft (.txt)", st.session_state.get("email_body", email_text),
                             file_name="operator_guidance_email.txt", mime="text/plain", use_container_width=True)
        with c2:
            st.download_button("Download original log for attachment", a["raw_log"],
                             file_name=a.get("log_filename", "uploaded_log.log"), mime="text/plain", use_container_width=True)
        st.download_button("Download analysis report to attach", make_report(email_meta, res),
                         file_name=report_filename, mime="text/plain", use_container_width=True)
        st.warning("Before sending, attach the downloaded log and analysis report to your email manually. Wait for the operator team's explicit green flag before any kill/restart action.")

# ═══════════════════════════════════════════════════════════════════════════════
#  TAB 4 — How it works
# ═══════════════════════════════════════════════════════════════════════════════

with tab4:
    st.subheader("How it works — production-grade analysis")
    st.markdown("""
**1. Universal log format support — any log, no predefined format needed:**  
OpsPilot automatically recognizes timestamps in ISO 8601, syslog, Apache CLF, Oracle, epoch-seconds/millis and many other formats.  
Severity levels are detected regardless of convention (ERROR, ERR, SEVERE, FATAL, CRITICAL, EMERGENCY, etc.).  
When no explicit severity token is present, context-based inference detects errors from keywords.

**2. Full-depth analysis — entire log scanned, not just the first error:**  
Every single line of the log is parsed and checked. OpsPilot **never stops at the first match**.  
Multi-line stack traces (Java, Python) are grouped with their parent error.  
The coverage percentage shows what fraction of lines matched a known error pattern.

**3. Root cause vs symptom distinction:**  
The **earliest specific, high-severity error** becomes the root cause.  
All subsequent matched errors are labelled as **downstream symptoms** — consequences, not causes.  
This prevents the common misdiagnosis where a cascade of later errors hides the original trigger.

**4. Timeline and event chain:**  
Every matched line is timestamped. A causal narrative (event chain) is auto-generated showing the  
flow from root cause through downstream symptoms, including first-error and last-error timestamps.

**5. Comprehensive reporting:**  
The downloadable report includes: job details, log statistics, root cause, symptoms, repeated errors,  
event chain, recommended checks, all matched lines (no truncation), and the full annotated log.

**6. No pattern truncation in emails or reports:**  
Every matched log line is included in the operator email evidence list and in the analysis report.

---

#### Supported error categories (13 rule categories, 150+ patterns)

| # | Category | Priority | Owner |
|---|----------|----------|-------|
| 1 | Missing input file / path error | High | Upstream / File Transfer Team |
| 2 | Database / connection error | High | Database / DBA Team |
| 3 | Network / connectivity error | High | Network / Infrastructure Team |
| 4 | Authentication / authorization error | High | Security / Access Management Team |
| 5 | Timeout / hung process | Medium | Application / Batch Support |
| 6 | Disk / storage capacity | High | Infrastructure / Storage Team |
| 7 | Memory / resource exhaustion | High | Application / Infrastructure Team |
| 8 | Data / format / parsing error | Medium | Application / Data Team |
| 9 | Configuration / environment error | Medium | DevOps / Configuration Team |
| 10 | Upstream service / API error | High | Service / Integration Team |
| 11 | Container / orchestration error | High | Platform / DevOps Team |
| 12 | Scheduler / batch control error | Medium | Operations / Batch Support |
| 13 | Application exception / crash | Medium | L2 / Application Development Team |

> **Generic error signal** (catch-all) is used when no specific category matches.

---

**Current limitations:**  Deterministic rule-based analysis. Pattern matches can be wrong or incomplete.  
Validate every suggestion against client-approved runbooks.

**Future scaling:**  After security approval, add read-only log retrieval through an approved API.  
Any integration must preserve operator approval and require client sign-off.
""")

st.divider()
st.caption("OpsPilot · Production-grade analysis engine · No live system connections or production actions")
