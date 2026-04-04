# Security Remediation Tasks

**Total Issues**: 3  
**Auto-fixable**: 1  
**Manual Review**: 2  

---

## High Priority (Auto-Fixable)

- [ ] Fix python.lang.security.insecure-hash-algorithms-md5.insecure-hash-algorithm-md5 in /tmp/test_vuln.py:14
  - **Issue**: Detected MD5 hash algorithm which is considered insecure. MD5 is not collision resistant and is therefore not suitable as a cryptographic signature. Use SHA256 or SHA3 instead.
  - **Severity**: WARNING
  - **Fix**: Automated fix available
  - **Sanity**: Re-run `hack audit /tmp/test_vuln.py`

## Medium Priority (Manual Review)

- [ ] Review python.lang.security.audit.formatted-sql-query.formatted-sql-query in /tmp/test_vuln.py:8
  - **Issue**: Detected possible formatted SQL query. Use parameterized queries instead.
  - **Severity**: WARNING
  - **Details**: Detected possible formatted SQL query. Use parameterized queries instead.
  - **Sanity**: Manual code review required

- [ ] Review python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query in /tmp/test_vuln.py:8
  - **Issue**: Avoiding SQL string concatenation: untrusted input concatenated with raw SQL query can result in SQL Injection. In order to execute raw query safely, prepared statement should be used. SQLAlchemy provides TextualSQL to easily used prepared statement with named parameters. For complex SQL composition, use SQL Expression Language or Schema Definition Language. In most cases, SQLAlchemy ORM will be a better option.
  - **Severity**: ERROR
  - **Details**: Avoiding SQL string concatenation: untrusted input concatenated with raw SQL query can result in SQL Injection. In order to execute raw query safely, prepared statement should be used. SQLAlchemy provides TextualSQL to easily used prepared statement with named parameters. For complex SQL composition, use SQL Expression Language or Schema Definition Language. In most cases, SQLAlchemy ORM will be a better option.
  - **Sanity**: Manual code review required

## Definition of Done

- [ ] All HIGH severity issues resolved
- [ ] Security scan shows 0 critical findings
- [ ] Existing tests still pass
- [ ] Manual security review completed
