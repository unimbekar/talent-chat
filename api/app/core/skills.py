"""Skill synonym table. One alias may map to several canonical names."""

import re

# (alias, canonical). Matching is case-insensitive on word boundaries.
SEED_SYNONYMS: list[tuple[str, str]] = [
    ("Java", "Java"),
    ("J2EE", "Java"),
    ("Spring", "Java"),
    ("Spring Boot", "Java"),
    ("Python", "Python"),
    ("PySpark", "Python"),
    ("PySpark", "Spark"),
    ("JavaScript", "JavaScript"),
    ("TypeScript", "JavaScript"),
    ("Node.js", "JavaScript"),
    ("Node", "JavaScript"),
    ("React", "JavaScript"),
    ("AWS", "AWS"),
    ("Amazon Web Services", "AWS"),
    ("EC2", "AWS"),
    ("S3", "AWS"),
    ("Lambda", "AWS"),
    ("Palantir", "Palantir"),
    ("Foundry", "Palantir"),
    ("Gotham", "Palantir"),
    ("Salesforce", "Salesforce"),
    ("Apex", "Salesforce"),
    ("ServiceNow", "ServiceNow"),
    ("Service Now", "ServiceNow"),
    ("Oracle", "Oracle"),
    ("Oracle DB", "Oracle"),
    ("Spark", "Spark"),
    ("Apache Spark", "Spark"),
    ("DevOps", "DevOps"),
    ("CI/CD", "DevOps"),
    ("Kubernetes", "Kubernetes"),
    ("Docker", "Docker"),
    ("Cyber", "Cybersecurity"),
    ("Cybersecurity", "Cybersecurity"),
    ("Information Security", "Cybersecurity"),
]


# Résumé skills are the tool or language itself, not a sentence around it.
# (alias, display name). Longer aliases are tried first.
TOOL_CATALOG: list[tuple[str, str]] = [
    ("Amazon Web Services", "AWS"),
    ("Spring Boot", "Spring Boot"),
    ("Node.js", "Node.js"),
    ("Apache Spark", "Spark"),
    ("LangChain", "LangChain"),
    ("LangGraph", "LangGraph"),
    ("LangSmith", "LangSmith"),
    ("TypeScript", "TypeScript"),
    ("JavaScript", "JavaScript"),
    ("PostgreSQL", "PostgreSQL"),
    ("Terraform", "Terraform"),
    ("Terragrunt", "Terragrunt"),
    ("Kubernetes", "Kubernetes"),
    ("CloudFormation", "CloudFormation"),
    ("CloudWatch", "CloudWatch"),
    ("ElastiCache", "ElastiCache"),
    ("DynamoDB", "DynamoDB"),
    ("Elasticsearch", "Elasticsearch"),
    ("Elastic Search", "Elasticsearch"),
    ("OpenSearch", "OpenSearch"),
    ("Elasticsearch", "Elasticsearch"),
    ("ServiceNow", "ServiceNow"),
    ("Salesforce", "Salesforce"),
    ("Palantir", "Palantir"),
    ("Foundry", "Foundry"),
    ("Hugging Face", "Hugging Face"),
    ("TensorFlow", "TensorFlow"),
    ("PyTorch", "PyTorch"),
    ("PySpark", "PySpark"),
    ("MapReduce", "MapReduce"),
    ("PowerShell", "PowerShell"),
    ("PL/SQL", "PL/SQL"),
    ("GitHub", "GitHub"),
    ("GitLab", "GitLab"),
    ("Jenkins", "Jenkins"),
    ("Docker", "Docker"),
    ("Ansible", "Ansible"),
    ("Prometheus", "Prometheus"),
    ("Grafana", "Grafana"),
    ("Databricks", "Databricks"),
    ("Snowflake", "Snowflake"),
    ("Solr", "Solr"),
    ("Lucene", "Lucene"),
    ("Airflow", "Airflow"),
    ("Kafka", "Kafka"),
    ("Splunk", "Splunk"),
    ("Kibana", "Kibana"),
    ("Linux", "Linux"),
    ("Python", "Python"),
    ("Java", "Java"),
    ("Scala", "Scala"),
    ("Kotlin", "Kotlin"),
    ("Spring", "Spring"),
    ("React", "React"),
    ("Angular", "Angular"),
    ("SpringBoot", "Spring Boot"),
    ("Selenium", "Selenium"),
    ("Cypress", "Cypress"),
    ("Katalon", "Katalon"),
    ("Postman", "Postman"),
    ("JMeter", "JMeter"),
    ("JIRA", "Jira"),
    ("Jira", "Jira"),
    ("Oracle Certified Professional", "OCP"),
    ("Oracle Exadata", "Exadata"),
    ("Oracle Linux", "Oracle Linux"),
    ("Oracle SQL", "Oracle SQL"),
    ("Exadata", "Exadata"),
    ("OCP", "OCP"),
    ("Oracle", "Oracle"),
    ("Spark", "Spark"),
    ("Hadoop", "Hadoop"),
    ("HBase", "HBase"),
    ("Ambari", "Ambari"),
    ("Helm", "Helm"),
    ("KEDA", "KEDA"),
    ("Nginx", "Nginx"),
    ("Redis", "Redis"),
    ("MongoDB", "MongoDB"),
    ("Cassandra", "Cassandra"),
    ("MySQL", "MySQL"),
    ("Azure", "Azure"),
    ("GCP", "GCP"),
    ("OpenAI", "OpenAI"),
    ("Claude", "Claude"),
    ("vLLM", "vLLM"),
    ("Nemotron", "Nemotron"),
    ("Bash", "Bash"),
    ("SQL", "SQL"),
    ("HTML", "HTML"),
    ("CSS", "CSS"),
    ("AWS", "AWS"),
    ("EKS", "EKS"),
    ("VPC", "VPC"),
    ("IAM", "IAM"),
    ("IRSA", "IRSA"),
    ("KMS", "KMS"),
    ("RDS", "RDS"),
    ("SQS", "SQS"),
    ("SNS", "SNS"),
    ("S3", "S3"),
    ("EC2", "EC2"),
    ("Lambda", "Lambda"),
    ("Kinesis", "Kinesis"),
    ("Git", "Git"),
    ("C++", "C++"),
    ("C#", "C#"),
    ("Go", "Go"),
    ("R", "R"),
]

_TOOL_STOP = {
    "experience",
    "professional",
    "present",
    "earlier",
    "career",
    "projects",
    "security",
    "observability",
    "automation",
    "recovery",
    "routing",
    "fallback",
    "agents",
    "secrets",
    "namespaces",
    "deployments",
    "services",
    "including",
    "used",
    "built",
    "supported",
    "authentication",
    "management",
    "capabilities",
    "delivery",
    "enforcement",
    "isolation",
    "notification",
    "infrastructure",
    "and",
    "or",
    "with",
    "for",
    "the",
    "of",
}


def _pattern(alias: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w){re.escape(alias)}(?!\w)", re.I)


def find_canonicals(text: str, rows: list[tuple[str, str]] | None = None) -> list[str]:
    rows = rows if rows is not None else SEED_SYNONYMS
    found: list[str] = []
    seen: set[str] = set()
    for alias, canonical in sorted(rows, key=lambda row: len(row[0]), reverse=True):
        if _pattern(alias).search(text or ""):
            if canonical not in seen:
                seen.add(canonical)
                found.append(canonical)
    return found


def aliases_for(canonical: str, rows: list[tuple[str, str]] | None = None) -> list[str]:
    rows = rows if rows is not None else SEED_SYNONYMS
    names = [alias for alias, can in rows if can.lower() == canonical.lower()]
    if canonical not in names and canonical.lower() not in {n.lower() for n in names}:
        names.append(canonical)
    return names


def normalize_skill_list(skills: list[str], rows: list[tuple[str, str]] | None = None) -> list[str]:
    """Map model or parser skill strings onto canonical names. Drop clearance phrases."""
    from app.core.clearance import is_clearance_only

    out: list[str] = []
    seen: set[str] = set()
    for raw in skills:
        text = (raw or "").strip()
        if not text or is_clearance_only(text):
            continue
        canonicals = find_canonicals(text, rows)
        if canonicals:
            for name in canonicals:
                key = name.lower()
                if key not in seen:
                    seen.add(key)
                    out.append(name)
            continue
        tag = re.sub(r"\s+", " ", text).strip().lower()
        if not tag or is_clearance_only(tag):
            continue
        if tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out


def tools_and_languages(text: str, allow_unknown: bool = False) -> list[str]:
    """Keep tools and languages named in text. Drop dates, duties, and other prose."""
    if not text or not text.strip():
        return []
    found: list[str] = []
    seen: set[str] = set()
    catalog = sorted(TOOL_CATALOG, key=lambda row: len(row[0]), reverse=True)
    for piece in re.split(r"[\n,;|•·]+", text):
        token = piece.strip(" .")
        if not token:
            continue
        occupied = [False] * len(token)
        matched = False
        for alias, display in catalog:
            if len(alias) < 3 and token.lower() != alias.lower():
                continue
            for match in _pattern(alias).finditer(token):
                start, end = match.span()
                if any(occupied[start:end]):
                    continue
                occupied[start:end] = [True] * (end - start)
                matched = True
                key = display.lower()
                if key not in seen:
                    seen.add(key)
                    found.append(display)
        if matched or not allow_unknown:
            continue
        words = token.split()
        if not 1 <= len(words) <= 3 or any(word.lower() in _TOOL_STOP for word in words):
            continue
        if re.search(r"\d{4}|—|–|github\.com", token, re.I):
            continue
        if any(not re.fullmatch(r"[A-Za-z][A-Za-z0-9.+#-]{0,24}", word) for word in words):
            continue
        key = token.lower()
        if key not in seen:
            seen.add(key)
            found.append(token)
    return found


def skills_from_quotes(quotes: list[str], rows: list[tuple[str, str]] | None = None) -> list[str]:
    from app.core.clearance import is_clearance_only

    kept = [q for q in quotes if q and not is_clearance_only(q)]
    return normalize_skill_list(kept, rows)
