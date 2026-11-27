"""Read-only validation of existing AI reservations, budgets and provider holds."""
import sqlite3
from pathlib import Path
from runtime_state import require_existing_database

class AdvisorLedgerError(ValueError):
    pass

TABLES={'advisor_requests','advisor_budget','advisor_provider_cooldown'}


def validate_budget_history(db):
    """Never repair missing counters from surviving rows: history can be partial."""
    try:
        db.execute('SELECT scope,request_hash,started,expires,day,state,result FROM advisor_requests LIMIT 0')
        db.execute('SELECT provider,observed,blocked_until,source,diagnostic FROM advisor_provider_cooldown LIMIT 0')
        if db.execute("SELECT 1 FROM advisor_budget WHERE typeof(day)!='integer' OR day<0 OR typeof(calls)!='integer' OR calls<0 LIMIT 1").fetchone():
            raise AdvisorLedgerError('AI budget history invalid; operator reconciliation required')
        if db.execute("SELECT 1 FROM advisor_requests WHERE typeof(day)!='integer' OR day<0 LIMIT 1").fetchone():
            raise AdvisorLedgerError('AI reservation history invalid; operator reconciliation required')
        if db.execute('''SELECT 1 FROM (SELECT day,count(*) AS reserved FROM advisor_requests GROUP BY day) r
            LEFT JOIN advisor_budget b ON b.day=r.day WHERE b.day IS NULL OR b.calls<r.reserved LIMIT 1''').fetchone():
            raise AdvisorLedgerError('AI reservations lack retained budget; operator reconciliation required')
        # A malformed cooldown must never be treated as an expired provider hold.
        if db.execute("""SELECT 1 FROM advisor_provider_cooldown WHERE
            typeof(observed) NOT IN ('integer','real') OR typeof(blocked_until) NOT IN ('integer','real')
            OR observed<0 OR blocked_until<observed OR blocked_until>1e100
            OR typeof(provider)!='text' OR length(provider)=0 LIMIT 1""").fetchone():
            raise AdvisorLedgerError('AI provider hold invalid; operator reconciliation required')
    except sqlite3.Error:
        raise AdvisorLedgerError('AI usage ledger incomplete; restore/reconcile history before inference') from None


def require_existing_advisor_ledger(path):
    try:
        require_existing_database(path,TABLES)
        db=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,timeout=5)
        try:validate_budget_history(db)
        finally:db.close()
    except (sqlite3.Error,ValueError,OSError):
        raise AdvisorLedgerError('AI usage ledger unavailable; restore before inference') from None
    return str(path)
