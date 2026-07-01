"""
Skill normalization — alias map → canonical names. Stdlib only.

Why an alias map, not a library:
  The PRD prohibits ML, network calls, and any libs beyond phonenumbers / pdfplumber /
  python-docx / reportlab / pytest. No compliant skill-taxonomy library exists within
  those constraints. Unknown skills pass through (never dropped) at lower confidence,
  per PRD §5.3 and §4. This limitation is documented in README.
"""

from __future__ import annotations

# Maps lowercase aliases → canonical skill name.
# Lookup is always case-insensitive (caller lowercases before lookup).
SKILL_ALIASES: dict[str, str] = {
    # JavaScript / Web
    "js": "JavaScript",
    "javascript": "JavaScript",
    "ts": "TypeScript",
    "typescript": "TypeScript",
    "reactjs": "React",
    "react.js": "React",
    "react": "React",
    "nodejs": "Node.js",
    "node.js": "Node.js",
    "node": "Node.js",
    "html": "HTML",
    "html5": "HTML",
    "css": "CSS",
    "css3": "CSS",
    "vuejs": "Vue.js",
    "vue.js": "Vue.js",
    "vue": "Vue.js",
    "angular": "Angular",
    "angularjs": "Angular",
    "next.js": "Next.js",
    "nextjs": "Next.js",
    "nuxt": "Nuxt.js",
    "nuxtjs": "Nuxt.js",
    "svelte": "Svelte",
    # Python
    "py": "Python",
    "python": "Python",
    "python3": "Python",
    "python2": "Python",
    "flask": "Flask",
    "django": "Django",
    "fastapi": "FastAPI",
    # DevOps / Infra
    "k8s": "Kubernetes",
    "kubernetes": "Kubernetes",
    "docker": "Docker",
    "aws": "AWS",
    "amazon web services": "AWS",
    "gcp": "GCP",
    "google cloud": "GCP",
    "google cloud platform": "GCP",
    "azure": "Azure",
    "microsoft azure": "Azure",
    "terraform": "Terraform",
    "ansible": "Ansible",
    "jenkins": "Jenkins",
    "ci/cd": "CI/CD",
    "cicd": "CI/CD",
    "github actions": "GitHub Actions",
    "linux": "Linux",
    "unix": "Linux",
    "bash": "Bash",
    "shell": "Bash",
    "nginx": "Nginx",
    # ML / Data
    "ml": "Machine Learning",
    "machine learning": "Machine Learning",
    "dl": "Deep Learning",
    "deep learning": "Deep Learning",
    "nlp": "NLP",
    "natural language processing": "NLP",
    "cv": "Computer Vision",
    "computer vision": "Computer Vision",
    "tensorflow": "TensorFlow",
    "tf": "TensorFlow",
    "pytorch": "PyTorch",
    "torch": "PyTorch",
    "pandas": "Pandas",
    "numpy": "NumPy",
    "np": "NumPy",
    "sklearn": "Scikit-learn",
    "scikit-learn": "Scikit-learn",
    "scikit learn": "Scikit-learn",
    "scipy": "SciPy",
    "matplotlib": "Matplotlib",
    "seaborn": "Seaborn",
    "xgboost": "XGBoost",
    "lightgbm": "LightGBM",
    "huggingface": "Hugging Face",
    "hugging face": "Hugging Face",
    # Databases
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "mysql": "MySQL",
    "mongo": "MongoDB",
    "mongodb": "MongoDB",
    "redis": "Redis",
    "elasticsearch": "Elasticsearch",
    "elastic search": "Elasticsearch",
    "cassandra": "Cassandra",
    "dynamodb": "DynamoDB",
    "bigquery": "BigQuery",
    "snowflake": "Snowflake",
    "sqlite": "SQLite",
    "oracle": "Oracle DB",
    # Languages
    "java": "Java",
    "golang": "Go",
    "go": "Go",
    "rust": "Rust",
    "cpp": "C++",
    "c++": "C++",
    "c/c++": "C++",
    "cs": "C#",
    "c#": "C#",
    "dotnet": ".NET",
    ".net": ".NET",
    "ruby": "Ruby",
    "rails": "Ruby on Rails",
    "ruby on rails": "Ruby on Rails",
    "php": "PHP",
    "scala": "Scala",
    "kotlin": "Kotlin",
    "swift": "Swift",
    "dart": "Dart",
    "flutter": "Flutter",
    "r": "R",
    "matlab": "MATLAB",
    "perl": "Perl",
    "elixir": "Elixir",
    "erlang": "Erlang",
    "haskell": "Haskell",
    "clojure": "Clojure",
    "lua": "Lua",
    # Mobile
    "android": "Android",
    "ios": "iOS",
    "react native": "React Native",
    "react-native": "React Native",
    "xamarin": "Xamarin",
    # APIs / Architecture
    "rest": "REST",
    "rest api": "REST API",
    "restful": "REST",
    "graphql": "GraphQL",
    "grpc": "gRPC",
    "microservices": "Microservices",
    "kafka": "Kafka",
    "rabbitmq": "RabbitMQ",
    "celery": "Celery",
    # Tools
    "git": "Git",
    "github": "GitHub",
    "gitlab": "GitLab",
    "bitbucket": "Bitbucket",
    "jira": "Jira",
    "confluence": "Confluence",
    "figma": "Figma",
    "postman": "Postman",
    "spring": "Spring",
    "spring boot": "Spring Boot",
    "springboot": "Spring Boot",
    "sql": "SQL",
    "nosql": "NoSQL",
    "hadoop": "Hadoop",
    "spark": "Apache Spark",
    "apache spark": "Apache Spark",
    "airflow": "Apache Airflow",
    "apache airflow": "Apache Airflow",
    "dbt": "dbt",
    "tableau": "Tableau",
    "power bi": "Power BI",
    "powerbi": "Power BI",
    "excel": "Microsoft Excel",
    "microsoft excel": "Microsoft Excel",
}


def normalize_skill(raw: str) -> tuple[str | None, str, bool]:
    """
    Normalize a skill name via the alias map.

    Returns (canonical_name, method, ok).
    - Known alias (case-insensitive) → canonical name, method="alias_mapped".
    - Unknown → pass through (strip + title-case), method="passthrough", ok=True.
      Unknown skills are NOT dropped — kept at lower confidence per PRD §5.3.
    - Empty input → (None, "skill_empty", False).
    """
    if not raw or not raw.strip():
        return None, "skill_empty", False

    stripped = raw.strip()
    key = stripped.lower()

    canonical = SKILL_ALIASES.get(key)
    if canonical:
        return canonical, "alias_mapped", True

    # Pass through: unknown skills are kept, not dropped
    passed = stripped.title()
    return passed, "passthrough", True
