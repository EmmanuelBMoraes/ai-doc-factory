project_id = "PREENCHER"
region     = "us-central1"
zone       = "us-central1-a"
name       = "ai-doc-factory"

machine_type = "e2-standard-16"
disk_size_gb = 50

repo_url          = "https://github.com/EmmanuelBMoraes/ai-doc-factory.git"
github_repository = "EmmanuelBMoraes/ai-doc-factory"
deploy_branch     = "chore/infra-gcp"

domain     = ""
acme_email = ""

ssh_source_ranges = ["35.235.240.0/20"]
enable_snapshots  = true

billing_account_id = ""
budget_amount      = 300
budget_currency    = "BRL"
