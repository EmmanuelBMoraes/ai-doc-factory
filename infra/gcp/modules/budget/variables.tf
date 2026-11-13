variable "name" {
  type = string
}

variable "billing_account_id" {
  type = string
}

variable "project_number" {
  type = string
}

variable "amount" {
  type = number
}

# Igual à moeda da conta de faturamento.
variable "currency" {
  type = string
}

variable "thresholds" {
  type    = list(number)
  default = [0.5, 0.9, 1.0]
}
