resource "google_billing_budget" "this" {
  billing_account = var.billing_account_id
  display_name    = var.name

  budget_filter {
    projects = ["projects/${var.project_number}"]
    # Gasto bruto: com créditos do trial descontados o alerta nunca dispara.
    credit_types_treatment = "EXCLUDE_ALL_CREDITS"
  }

  amount {
    specified_amount {
      currency_code = var.currency
      units         = tostring(var.amount)
    }
  }

  dynamic "threshold_rules" {
    for_each = var.thresholds
    content {
      threshold_percent = threshold_rules.value
    }
  }
}
